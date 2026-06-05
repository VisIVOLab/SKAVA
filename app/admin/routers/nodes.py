"""CRUD for ``nodes`` — the federation of SKAVA-known data nodes.

Permissions: viewing requires any authenticated user; mutating
requires the ``ingester`` role (admin implicitly satisfies that).

Delete safety: ``Node.replicas`` has cascade=all, delete-orphan, so
removing a node would silently drop every dataset replica that
referenced it. To make that intent explicit, the delete endpoint
refuses if any replicas point at the node; the operator must remove
those datasets first (or change the cascade in a future migration).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.audit.service import log_action
from app.admin.auth.rbac import require_role
from app.admin.auth.session import current_user_required
from app.admin.csrf import CSRFDep
from app.admin.templating import flash, render
from app.db import get_db
from app.models.node import Node
from app.models.replica import DatasetReplica
from app.models.user import User, UserRole

router = APIRouter(prefix="/nodes")


# Reusable RBAC dep — exposed as a callable so every mutating route
# uses the same set of roles without per-route duplication. Kept as a
# bare callable (NOT pre-wrapped with ``Depends(...)``) so each route
# can do ``Depends(_can_edit)`` — wrapping it here would result in
# ``Depends(Depends(...))`` which FastAPI rejects with ``not a
# callable object``.
_can_edit = require_role(UserRole.ingester)


# ─── Field-extraction helper ────────────────────────────────────────────────
#
# Pulled out so create + update share one validation path. Returns the
# parsed dict ready to feed into ``Node(**)`` or to ``setattr`` on an
# existing instance. Raises HTTPException(400) with an inline message
# on the first invalid field.


def _parse_node_form(form: dict[str, str]) -> dict:
    code = (form.get("code") or "").strip().upper()
    name = (form.get("name") or "").strip()
    base_url = (form.get("base_url") or "").strip()
    if not code:
        raise HTTPException(400, "Code is required.")
    if " " in code:
        raise HTTPException(400, "Code cannot contain spaces.")
    if not name:
        raise HTTPException(400, "Name is required.")
    if not base_url or not (
        base_url.startswith("http://") or base_url.startswith("https://")
    ):
        raise HTTPException(400, "Base URL must start with http:// or https://")

    def _opt_float(key: str) -> float | None:
        raw = (form.get(key) or "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError as exc:
            raise HTTPException(400, f"{key} must be numeric.") from exc

    visivo_url = (form.get("visivo_backend_url") or "").strip() or None
    if visivo_url and not (
        visivo_url.startswith("http://") or visivo_url.startswith("https://")
    ):
        raise HTTPException(
            400, "VisIVO backend URL must start with http:// or https://"
        )

    return {
        "code": code,
        "name": name,
        "base_url": base_url,
        "is_enabled": form.get("is_enabled") == "on",
        "is_available": form.get("is_available") == "on",
        "latency_score": _opt_float("latency_score"),
        "load_score": _opt_float("load_score"),
        "capability_score": _opt_float("capability_score"),
        "visivo_backend_url": visivo_url,
        "visivo_backend_requires_auth":
            form.get("visivo_backend_requires_auth") == "on",
    }


# ─── List ────────────────────────────────────────────────────────────────────


@router.get("/")
def list_nodes(
    request: Request,
    user: Annotated[User, Depends(current_user_required)],
    db: Annotated[Session, Depends(get_db)],
):
    nodes = list(db.scalars(select(Node).order_by(Node.code)))
    # Show replica counts so operators know which nodes are in active
    # use before they go editing/deleting.
    replica_counts: dict[int, int] = dict(
        db.execute(
            select(DatasetReplica.node_id, func.count(DatasetReplica.id))
            .group_by(DatasetReplica.node_id)
        ).all()
    )
    return render(
        request,
        "nodes/list.html",
        {
            "current_user": user,
            "nodes": nodes,
            "replica_counts": replica_counts,
            "can_edit": user.has_role(UserRole.ingester, UserRole.admin),
        },
    )


# ─── New ─────────────────────────────────────────────────────────────────────


@router.get("/new")
def new_form(
    request: Request,
    user: Annotated[User, Depends(_can_edit)],
):
    return render(
        request,
        "nodes/edit.html",
        {
            "current_user": user,
            "node": None,
            "form": {},
            "is_new": True,
            "error": None,
        },
    )


@router.post("/new")
async def create_node(
    request: Request,
    _: CSRFDep,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_can_edit)],
):
    form = dict(await request.form())
    try:
        fields = _parse_node_form(form)
    except HTTPException as exc:
        return render(
            request, "nodes/edit.html",
            {"current_user": user, "node": None, "form": form,
             "is_new": True, "error": exc.detail},
            status_code=400,
        )

    if db.scalar(select(Node).where(Node.code == fields["code"])) is not None:
        return render(
            request, "nodes/edit.html",
            {"current_user": user, "node": None, "form": form,
             "is_new": True,
             "error": f"A node with code {fields['code']!r} already exists."},
            status_code=400,
        )

    node = Node(**fields)
    db.add(node)
    db.flush()
    log_action(
        db, request, actor=user, action="node.create",
        target_type="node", target_id=node.id,
        changes={"after": fields},
    )
    db.commit()
    flash(request, "success", f"Created node {node.code}.")
    return RedirectResponse(
        f"/admin/nodes/{node.id}/edit",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ─── Edit ────────────────────────────────────────────────────────────────────


def _load_node_or_404(db: Session, node_id: int) -> Node:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(404, "Node not found.")
    return node


@router.get("/{node_id}/edit")
def edit_form(
    node_id: int,
    request: Request,
    user: Annotated[User, Depends(_can_edit)],
    db: Annotated[Session, Depends(get_db)],
):
    node = _load_node_or_404(db, node_id)
    return render(
        request,
        "nodes/edit.html",
        {
            "current_user": user,
            "node": node,
            "form": {},
            "is_new": False,
            "error": None,
        },
    )


@router.post("/{node_id}/edit")
async def update_node(
    node_id: int,
    request: Request,
    _: CSRFDep,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_can_edit)],
):
    node = _load_node_or_404(db, node_id)
    form = dict(await request.form())
    try:
        fields = _parse_node_form(form)
    except HTTPException as exc:
        return render(
            request, "nodes/edit.html",
            {"current_user": user, "node": node, "form": form,
             "is_new": False, "error": exc.detail},
            status_code=400,
        )

    # If the code changed, ensure the new code is still unique.
    if fields["code"] != node.code:
        clash = db.scalar(select(Node).where(Node.code == fields["code"]))
        if clash is not None:
            return render(
                request, "nodes/edit.html",
                {"current_user": user, "node": node, "form": form,
                 "is_new": False,
                 "error": f"A node with code {fields['code']!r} already exists."},
                status_code=400,
            )

    # Capture before/after for the audit row.
    before = {k: getattr(node, k) for k in fields.keys()}
    for key, value in fields.items():
        setattr(node, key, value)
    db.flush()
    log_action(
        db, request, actor=user, action="node.update",
        target_type="node", target_id=node.id,
        changes={"before": before, "after": fields},
    )
    db.commit()
    flash(request, "success", f"Updated node {node.code}.")
    return RedirectResponse(
        f"/admin/nodes/{node.id}/edit",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ─── Delete ─────────────────────────────────────────────────────────────────


@router.post("/{node_id}/delete")
async def delete_node(
    node_id: int,
    request: Request,
    _: CSRFDep,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_can_edit)],
):
    node = _load_node_or_404(db, node_id)

    # Refuse deletes that would silently orphan replicas — the model's
    # cascade=delete-orphan would otherwise wipe them with no warning.
    n_replicas = db.scalar(
        select(func.count(DatasetReplica.id))
        .where(DatasetReplica.node_id == node.id)
    ) or 0
    if n_replicas > 0:
        flash(
            request, "error",
            f"Cannot delete {node.code}: {n_replicas} dataset replica(s) "
            f"reference it. Remove those datasets first.",
        )
        return RedirectResponse(
            "/admin/nodes/", status_code=status.HTTP_303_SEE_OTHER,
        )

    snapshot = {
        "code": node.code, "name": node.name, "base_url": node.base_url,
    }
    target_id = node.id
    db.delete(node)
    db.flush()
    log_action(
        db, request, actor=user, action="node.delete",
        target_type="node", target_id=target_id,
        changes={"before": snapshot},
    )
    db.commit()
    flash(request, "success", f"Deleted node {snapshot['code']}.")
    return RedirectResponse("/admin/nodes/", status_code=status.HTTP_303_SEE_OTHER)
