# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Dashboard rendering + counts (Phase 3 enrichments)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.main import app
from app.models.audit_log import AuditLog


def test_dashboard_renders_counts_section(admin_client):
    r = admin_client.get("/admin/")
    assert r.status_code == 200
    # The four count tiles.
    for label in ("Datasets", "Nodes", "Users", "Audit rows"):
        assert label in r.text


def test_dashboard_shows_activity_window(admin_client):
    """The 7-day activity section is always rendered (even if empty)."""
    r = admin_client.get("/admin/")
    assert r.status_code == 200
    assert "Activity (last 7 days)" in r.text


def test_dashboard_top_actors_lists_recent_actors(admin_client):
    """Insert audit rows within the window and confirm the actor name surfaces."""
    sess_factory = app.state.testing_session_local
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    with sess_factory() as db:
        for action in ("dataset.create", "dataset.update", "node.create"):
            db.add(AuditLog(
                occurred_at=recent,
                actor_label="alice-active",
                action=action,
            ))
        db.commit()
    r = admin_client.get("/admin/")
    assert r.status_code == 200
    assert "alice-active" in r.text


def test_dashboard_per_node_listing(admin_client):
    """The seeded fixtures include nodes; the per-node section should render them."""
    r = admin_client.get("/admin/")
    assert r.status_code == 200
    assert "Datasets per node" in r.text or "per node" in r.text.lower()
