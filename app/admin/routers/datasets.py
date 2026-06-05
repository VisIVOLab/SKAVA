"""CRUD for the ``datasets`` table (and inline replica management).

ObsCore-shaped fields with optional provenance and per-replica
location records. Permissions follow the same pattern as nodes:

* viewing requires any authenticated user
* mutating requires ``ingester`` (or ``admin``)

Delete cascades replicas (ondelete=CASCADE on the FK). The UI shows
the replica count before confirmation so the operator sees how much
will go.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import (
    APIRouter, Depends, File, HTTPException, Request, UploadFile, status,
)
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.admin.audit.service import log_action
from app.admin.auth.rbac import require_role
from app.admin.auth.session import current_user_required
from app.admin.csrf import CSRFDep
from app.admin.services.fits_extract import extract_obscore_from_fits
from app.admin.templating import flash, render
from app.db import get_db
from app.models.dataset import Dataset
from app.models.node import Node
from app.models.replica import DatasetReplica
from app.models.user import User, UserRole

router = APIRouter(prefix="/datasets")

_can_edit = require_role(UserRole.ingester)


# ─── ObsCore field set ──────────────────────────────────────────────────────
#
# Centralised so the form template, the parser and the audit "before"
# snapshot all reference the same list.

_TEXT_FIELDS = (
    "obs_id", "obs_collection", "obs_title", "dataproduct_type",
    "target_name", "facility_name", "instrument_name",
    "access_format", "source_type", "source_ref",
    "checksum", "doi", "pid", "citation", "license",
)
_INT_FIELDS = ("calib_level", "access_estsize", "spatial_index_order")
_FLOAT_FIELDS = (
    "s_ra", "s_dec", "s_fov",
    "t_min", "t_max", "em_min", "em_max",
)
_ALL_DATASET_FIELDS = (
    *_TEXT_FIELDS, *_INT_FIELDS, *_FLOAT_FIELDS, "spatial_index_cell",
)


def _opt_str(value: str) -> str | None:
    v = (value or "").strip()
    return v or None


def _opt_int(value: str, field: str) -> int | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise HTTPException(400, f"{field} must be an integer.") from exc


def _opt_float(value: str, field: str) -> float | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise HTTPException(400, f"{field} must be numeric.") from exc


def _parse_dataset_form(form: dict[str, str]) -> dict:
    obs_id = (form.get("obs_id") or "").strip()
    if not obs_id:
        raise HTTPException(400, "obs_id is required.")

    out: dict[str, Any] = {"obs_id": obs_id}
    for f in _TEXT_FIELDS:
        if f == "obs_id":
            continue
        out[f] = _opt_str(form.get(f, ""))
    for f in _INT_FIELDS:
        out[f] = _opt_int(form.get(f, ""), f)
    for f in _FLOAT_FIELDS:
        out[f] = _opt_float(form.get(f, ""), f)
    out["spatial_index_cell"] = _opt_str(form.get("spatial_index_cell", ""))

    # Range sanity — nice-to-have, not a hard failure if only one bound set.
    for lo, hi in (("t_min", "t_max"), ("em_min", "em_max")):
        if out[lo] is not None and out[hi] is not None and out[lo] > out[hi]:
            raise HTTPException(
                400, f"{lo} ({out[lo]}) must be ≤ {hi} ({out[hi]}).")

    return out


# ─── List ────────────────────────────────────────────────────────────────────

_PAGE_SIZE = 50


@router.get("/")
def list_datasets(
    request: Request,
    user: Annotated[User, Depends(current_user_required)],
    db: Annotated[Session, Depends(get_db)],
    q: str = "",
    collection: str = "",
    dptype: str = "",
    page: int = 1,
):
    page = max(1, page)
    stmt = select(Dataset).order_by(Dataset.obs_id)
    count_stmt = select(func.count(Dataset.id))

    if q:
        like = f"%{q.strip()}%"
        cond = or_(
            Dataset.obs_id.ilike(like),
            Dataset.obs_title.ilike(like),
            Dataset.target_name.ilike(like),
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if collection:
        stmt = stmt.where(Dataset.obs_collection == collection)
        count_stmt = count_stmt.where(Dataset.obs_collection == collection)
    if dptype:
        stmt = stmt.where(Dataset.dataproduct_type == dptype)
        count_stmt = count_stmt.where(Dataset.dataproduct_type == dptype)

    total = db.scalar(count_stmt) or 0
    n_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    rows = list(db.scalars(
        stmt.offset((page - 1) * _PAGE_SIZE).limit(_PAGE_SIZE)
    ))

    # Build replica counts so the table can show "3 replicas" without
    # firing per-row queries.
    rep_counts: dict[int, int] = dict(db.execute(
        select(DatasetReplica.dataset_id, func.count(DatasetReplica.id))
        .where(DatasetReplica.dataset_id.in_([r.id for r in rows]) if rows else False)
        .group_by(DatasetReplica.dataset_id)
    ).all())

    # Filter dropdown choices — DISTINCT scans on a small admin DB are
    # fine; for million-row catalogues replace with a cached materialised view.
    collections = [
        c for (c,) in db.execute(
            select(Dataset.obs_collection)
            .where(Dataset.obs_collection.is_not(None))
            .distinct().order_by(Dataset.obs_collection)
        ).all()
    ]
    dptypes = [
        d for (d,) in db.execute(
            select(Dataset.dataproduct_type)
            .where(Dataset.dataproduct_type.is_not(None))
            .distinct().order_by(Dataset.dataproduct_type)
        ).all()
    ]

    return render(
        request,
        "datasets/list.html",
        {
            "current_user": user,
            "rows": rows,
            "replica_counts": rep_counts,
            "total": total,
            "page": page,
            "n_pages": n_pages,
            "q": q,
            "collection": collection,
            "dptype": dptype,
            "collections": collections,
            "dptypes": dptypes,
            "can_edit": user.has_role(UserRole.ingester, UserRole.admin),
        },
    )


# ─── Detail ──────────────────────────────────────────────────────────────────


def _load_dataset_or_404(db: Session, dataset_id: int) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise HTTPException(404, "Dataset not found.")
    return ds


@router.get("/{dataset_id}")
def detail(
    dataset_id: int,
    request: Request,
    user: Annotated[User, Depends(current_user_required)],
    db: Annotated[Session, Depends(get_db)],
):
    ds = db.scalar(
        select(Dataset)
        .where(Dataset.id == dataset_id)
        .options(selectinload(Dataset.replicas).selectinload(DatasetReplica.node))
    )
    if ds is None:
        raise HTTPException(404, "Dataset not found.")
    nodes = list(db.scalars(
        select(Node).where(Node.is_enabled.is_(True)).order_by(Node.code)
    ))
    return render(
        request,
        "datasets/detail.html",
        {
            "current_user": user,
            "ds": ds,
            "nodes_for_replica": nodes,
            "can_edit": user.has_role(UserRole.ingester, UserRole.admin),
        },
    )


# ─── New / Edit ──────────────────────────────────────────────────────────────


@router.get("/new")
def new_form(
    request: Request,
    user: Annotated[User, Depends(_can_edit)],
):
    return render(
        request,
        "datasets/edit.html",
        {
            "current_user": user, "ds": None, "form": {},
            "is_new": True, "error": None,
        },
    )


@router.post("/new")
async def create_dataset(
    request: Request,
    _: CSRFDep,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_can_edit)],
):
    form = dict(await request.form())
    try:
        fields = _parse_dataset_form(form)
    except HTTPException as exc:
        return render(
            request, "datasets/edit.html",
            {"current_user": user, "ds": None, "form": form,
             "is_new": True, "error": exc.detail},
            status_code=400,
        )
    if db.scalar(select(Dataset).where(Dataset.obs_id == fields["obs_id"])) is not None:
        return render(
            request, "datasets/edit.html",
            {"current_user": user, "ds": None, "form": form,
             "is_new": True,
             "error": f"A dataset with obs_id {fields['obs_id']!r} already exists."},
            status_code=400,
        )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ds = Dataset(**fields, ingested_at=now, updated_at=now,
                 source_type=fields.get("source_type") or "admin-ui")
    db.add(ds)
    db.flush()
    log_action(
        db, request, actor=user, action="dataset.create",
        target_type="dataset", target_id=ds.id,
        changes={"after": fields},
    )
    db.commit()
    flash(request, "success", f"Created dataset {ds.obs_id}.")
    return RedirectResponse(
        f"/admin/datasets/{ds.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/{dataset_id}/edit")
def edit_form(
    dataset_id: int,
    request: Request,
    user: Annotated[User, Depends(_can_edit)],
    db: Annotated[Session, Depends(get_db)],
):
    ds = _load_dataset_or_404(db, dataset_id)
    return render(
        request,
        "datasets/edit.html",
        {"current_user": user, "ds": ds, "form": {},
         "is_new": False, "error": None},
    )


@router.post("/{dataset_id}/edit")
async def update_dataset(
    dataset_id: int,
    request: Request,
    _: CSRFDep,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_can_edit)],
):
    ds = _load_dataset_or_404(db, dataset_id)
    form = dict(await request.form())
    try:
        fields = _parse_dataset_form(form)
    except HTTPException as exc:
        return render(
            request, "datasets/edit.html",
            {"current_user": user, "ds": ds, "form": form,
             "is_new": False, "error": exc.detail},
            status_code=400,
        )
    if fields["obs_id"] != ds.obs_id:
        clash = db.scalar(select(Dataset).where(Dataset.obs_id == fields["obs_id"]))
        if clash is not None:
            return render(
                request, "datasets/edit.html",
                {"current_user": user, "ds": ds, "form": form,
                 "is_new": False,
                 "error": f"A dataset with obs_id {fields['obs_id']!r} already exists."},
                status_code=400,
            )
    before = {k: getattr(ds, k) for k in _ALL_DATASET_FIELDS}
    for k, v in fields.items():
        setattr(ds, k, v)
    ds.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.flush()
    log_action(
        db, request, actor=user, action="dataset.update",
        target_type="dataset", target_id=ds.id,
        changes={"before": before, "after": fields},
    )
    db.commit()
    flash(request, "success", f"Updated dataset {ds.obs_id}.")
    return RedirectResponse(
        f"/admin/datasets/{ds.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ─── Delete ─────────────────────────────────────────────────────────────────


@router.post("/{dataset_id}/delete")
async def delete_dataset(
    dataset_id: int,
    request: Request,
    _: CSRFDep,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_can_edit)],
):
    ds = _load_dataset_or_404(db, dataset_id)
    snapshot = {"obs_id": ds.obs_id, "obs_collection": ds.obs_collection,
                "dataproduct_type": ds.dataproduct_type}
    target_id = ds.id
    db.delete(ds)
    db.flush()
    log_action(
        db, request, actor=user, action="dataset.delete",
        target_type="dataset", target_id=target_id,
        changes={"before": snapshot},
    )
    db.commit()
    flash(request, "success", f"Deleted dataset {snapshot['obs_id']}.")
    return RedirectResponse(
        "/admin/datasets/", status_code=status.HTTP_303_SEE_OTHER)


# ─── Replicas (inline on the detail page) ───────────────────────────────────


@router.post("/{dataset_id}/replicas/new")
async def add_replica(
    dataset_id: int,
    request: Request,
    _: CSRFDep,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_can_edit)],
):
    ds = _load_dataset_or_404(db, dataset_id)
    form = dict(await request.form())
    node_id_raw = (form.get("node_id") or "").strip()
    remote_path = (form.get("remote_path") or "").strip()
    access_endpoint = (form.get("access_endpoint") or "").strip()
    is_public = form.get("is_public") == "on"

    if not node_id_raw or not remote_path or not access_endpoint:
        flash(request, "error", "Node, remote path and access endpoint are all required.")
        return RedirectResponse(
            f"/admin/datasets/{ds.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    try:
        node_id = int(node_id_raw)
    except ValueError:
        flash(request, "error", "Invalid node selection.")
        return RedirectResponse(
            f"/admin/datasets/{ds.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    node = db.get(Node, node_id)
    if node is None:
        flash(request, "error", "Selected node does not exist.")
        return RedirectResponse(
            f"/admin/datasets/{ds.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Uniqueness — DatasetReplica has UniqueConstraint(dataset_id, node_id).
    existing = db.scalar(
        select(DatasetReplica)
        .where(DatasetReplica.dataset_id == ds.id,
               DatasetReplica.node_id == node.id)
    )
    if existing is not None:
        flash(
            request, "error",
            f"A replica on node {node.code} already exists for this dataset. "
            f"Remove it first to recreate.",
        )
        return RedirectResponse(
            f"/admin/datasets/{ds.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    rep = DatasetReplica(
        dataset_id=ds.id, node_id=node.id,
        remote_path=remote_path, access_endpoint=access_endpoint,
        status="available", is_public=is_public,
    )
    db.add(rep)
    db.flush()
    log_action(
        db, request, actor=user, action="replica.create",
        target_type="replica", target_id=rep.id,
        changes={"dataset_id": ds.id, "node_id": node.id,
                 "remote_path": remote_path,
                 "access_endpoint": access_endpoint},
    )
    db.commit()
    flash(request, "success", f"Replica on {node.code} added.")
    return RedirectResponse(
        f"/admin/datasets/{ds.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ─── FITS pre-fill helper ───────────────────────────────────────────────────
#
# Used by the JS snippet at the top of edit.html: operator uploads a
# FITS file, we parse the primary HDU header (lazily importing astropy
# so the rest of SKAVA boots fast) and return a JSON dict keyed by the
# form input ``name=`` attributes. The client-side JS then fills only
# the EMPTY form fields, leaving anything the operator already typed
# untouched.

# Limit to ~5 MB of header bytes — FITS headers are 2880-byte blocks
# and rarely exceed 100 KB; a 5 MB cap is generous and stops a hostile
# upload from exhausting the worker memory.
_MAX_FITS_UPLOAD = 5 * 1024 * 1024


@router.post("/extract-from-fits")
async def extract_from_fits(
    request: Request,
    _: CSRFDep,
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_can_edit)],
):
    """Parse a FITS file's primary header and return ObsCore form values."""
    # Read in chunks so an oversized upload is rejected early.
    buf = bytearray()
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > _MAX_FITS_UPLOAD:
            raise HTTPException(
                413, f"FITS upload exceeds {_MAX_FITS_UPLOAD // (1024 * 1024)} MB.",
            )
    if not buf:
        raise HTTPException(400, "Empty file.")

    try:
        result = extract_obscore_from_fits(io.BytesIO(bytes(buf)))
    except Exception as exc:  # noqa: BLE001 — astropy raises many types
        raise HTTPException(
            400,
            f"Could not parse as FITS: {exc.__class__.__name__}: {exc}",
        ) from exc

    # Audit row so we can tell who asked for what. ``target_id`` is the
    # uploaded filename rather than a DB id because no dataset is
    # created here — the operator still has to confirm + submit the form.
    log_action(
        db, request, actor=user, action="dataset.extract_from_fits",
        target_type="fits-upload",
        target_id=file.filename or "<unnamed>",
        changes={"fields_extracted": sorted(result.keys()),
                 "file_size_bytes": len(buf)},
    )
    db.commit()

    return JSONResponse(result)


@router.post("/{dataset_id}/replicas/{replica_id}/delete")
async def delete_replica(
    dataset_id: int,
    replica_id: int,
    request: Request,
    _: CSRFDep,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_can_edit)],
):
    ds = _load_dataset_or_404(db, dataset_id)
    rep = db.get(DatasetReplica, replica_id)
    if rep is None or rep.dataset_id != ds.id:
        raise HTTPException(404, "Replica not found for this dataset.")
    node_code = rep.node.code if rep.node else f"node {rep.node_id}"
    snapshot = {"dataset_id": rep.dataset_id, "node_id": rep.node_id,
                "remote_path": rep.remote_path,
                "access_endpoint": rep.access_endpoint}
    target_id = rep.id
    db.delete(rep)
    db.flush()
    log_action(
        db, request, actor=user, action="replica.delete",
        target_type="replica", target_id=target_id,
        changes={"before": snapshot},
    )
    db.commit()
    flash(request, "success", f"Replica on {node_code} removed.")
    return RedirectResponse(
        f"/admin/datasets/{ds.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
