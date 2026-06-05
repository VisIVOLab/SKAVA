"""Bulk CSV / JSON manifest upload via the admin UI.

This is the session-authenticated front-end for the same ingestion
pipeline that the publisher CLI hits over HTTP. Operators who don't
want to deal with the ``X-Internal-Api-Key`` shared secret (or who
want to spot-check a small manifest from their browser) can drag a
file onto ``/admin/upload``, choose dry-run vs run, and see the per-
record summary rendered inline.

The route does NOT call ``/internal/ingestion/run`` over HTTP — it
reuses ``IngestionJobService`` directly in-process. That avoids the
need to put the internal API key in the admin UI's own environment
and keeps everything within the admin session's audit trail.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.admin.audit.service import log_action
from app.admin.auth.rbac import require_role
from app.admin.auth.session import current_user_required
from app.admin.csrf import CSRFDep
from app.admin.templating import flash, render
from app.db import get_db
from app.errors import InvalidQueryError, SKAVAError
from app.ingestion.parsers.csv_parser import parse_csv_bytes
from app.ingestion.parsers.json_parser import parse_json_bytes
from app.models.user import User, UserRole
from app.services.ingestion_job_service import (
    IngestionJobService,
    detect_manifest_format,
)

router = APIRouter(prefix="/upload")

_can_ingest = require_role(UserRole.ingester)


# ── GET /admin/upload — form ─────────────────────────────────────────────────


@router.get("/")
def upload_form(
    request: Request,
    user: Annotated[User, Depends(current_user_required)],
):
    """Render the drag-drop upload form."""
    return render(
        request,
        "upload/index.html",
        {
            "current_user": user,
            "can_ingest": user.has_role(UserRole.ingester, UserRole.admin),
            "result": None,
        },
    )


# ── POST /admin/upload — submit ─────────────────────────────────────────────


# Cap on a single uploaded manifest. Larger imports should go via the
# publisher CLI, which streams records server-side without buffering
# the whole file in memory.
_MAX_MANIFEST_BYTES = 32 * 1024 * 1024  # 32 MB


def _parse_manifest(payload: bytes, fmt: str) -> list[dict]:
    """Reuse the same CSV / JSON parsers the /internal API uses."""
    try:
        if fmt == "csv":
            return parse_csv_bytes(payload)
        if fmt == "json":
            return parse_json_bytes(payload)
    except ValueError as exc:
        raise InvalidQueryError(str(exc)) from exc
    raise InvalidQueryError("Unsupported format. Use csv or json")


@router.post("/")
async def upload_submit(
    request: Request,
    _: CSRFDep,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_can_ingest)],
    file: Annotated[UploadFile, File(...)],
    dry_run: Annotated[str, Form()] = "false",
    format: Annotated[str, Form()] = "",
    source_ref: Annotated[str, Form()] = "",
):
    """Validate the form, run the ingestion, render the summary inline."""
    is_dry_run = dry_run in ("true", "on", "1", "yes")

    # ── Read with a hard upper bound ─────────────────────────────────────
    buf = bytearray()
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > _MAX_MANIFEST_BYTES:
            return render(
                request, "upload/index.html",
                {
                    "current_user": user, "can_ingest": True, "result": None,
                    "error": (
                        f"File exceeds {_MAX_MANIFEST_BYTES // (1024 * 1024)} MB. "
                        f"Use the publisher CLI for larger manifests."
                    ),
                },
                status_code=413,
            )
    if not buf:
        return render(
            request, "upload/index.html",
            {"current_user": user, "can_ingest": True, "result": None,
             "error": "Uploaded file is empty."},
            status_code=400,
        )

    fmt_hint = format.strip().lower() or None
    try:
        fmt = detect_manifest_format(file.filename, fmt_hint)
        records = _parse_manifest(bytes(buf), fmt)
    except SKAVAError as exc:
        return render(
            request, "upload/index.html",
            {"current_user": user, "can_ingest": True, "result": None,
             "error": f"Parse error: {exc.message}"},
            status_code=400,
        )

    # ── Drive the same service the /internal endpoint uses ──────────────
    svc = IngestionJobService(db)
    try:
        job, summary = svc.run_job(
            records,
            dry_run=is_dry_run,
            source_type=fmt,
            source_ref=source_ref.strip() or f"admin-ui:{user.username}",
            filename=file.filename,
            triggered_by=f"admin-ui:{user.username}",
        )
    except SKAVAError as exc:
        return render(
            request, "upload/index.html",
            {"current_user": user, "can_ingest": True, "result": None,
             "error": f"Ingestion refused: {exc.message}"},
            status_code=exc.status_code,
        )

    # Audit row — the IngestionJobService already records its own audit
    # via the IngestionJob table; we add a complementary admin-audit row
    # so the cross-cutting audit page surfaces UI-triggered ingestions.
    log_action(
        db, request, actor=user,
        action="ingestion.upload" + (".dry_run" if is_dry_run else ""),
        target_type="ingestion_job", target_id=job.job_id,
        changes={
            "filename": file.filename,
            "format": fmt,
            "record_count": len(records),
            "summary": {
                "inserted_datasets": summary.inserted_datasets,
                "updated_datasets": summary.updated_datasets,
                "skipped": summary.skipped,
                "validation_errors_count": len(summary.validation_errors),
            },
        },
    )
    db.commit()

    if is_dry_run:
        flash(request, "info",
              f"Dry-run completed: {len(records)} record(s) validated.")
    else:
        flash(
            request, "success",
            f"Published {summary.inserted_datasets + summary.updated_datasets} "
            f"dataset(s); {summary.skipped} skipped.",
        )

    # Render the same page with the result block visible. Keeping a
    # single template avoids a redirect-and-lose-the-summary pattern.
    return render(
        request,
        "upload/index.html",
        {
            "current_user": user,
            "can_ingest": True,
            "result": {
                "job": job,
                "summary": summary,
                "dry_run": is_dry_run,
                "filename": file.filename,
                "format": fmt,
            },
            "error": None,
        },
    )
