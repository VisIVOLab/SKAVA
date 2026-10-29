# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Audit-history viewer + CSV export (Phase 3)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.main import app
from app.models.audit_log import AuditLog


def _seed_audit(rows: list[dict]) -> None:
    """Insert raw audit rows into the test DB used by the client fixture."""
    sess_factory = app.state.testing_session_local
    with sess_factory() as db:
        for r in rows:
            db.add(AuditLog(**r))
        db.commit()


def test_history_list_empty(admin_client):
    r = admin_client.get("/admin/history/")
    assert r.status_code == 200
    assert "Audit history" in r.text


def test_history_list_shows_seeded_rows(admin_client):
    _seed_audit([
        {
            "occurred_at": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
            "actor_label": "operator-alice",
            "action": "node.create",
            "target_type": "node",
            "target_id": "POWER9",
            "ip_address": "127.0.0.1",
            "request_id": "req-001",
            "changes_json": {"after": {"code": "POWER9"}},
        },
        {
            "occurred_at": datetime(2026, 6, 2, 13, 0, tzinfo=timezone.utc),
            "actor_label": "operator-bob",
            "action": "dataset.update",
            "target_type": "dataset",
            "target_id": "ds_xxx",
            "ip_address": "10.0.0.1",
            "request_id": "req-002",
            "changes_json": {"before": {"x": 1}, "after": {"x": 2}},
        },
    ])
    r = admin_client.get("/admin/history/")
    assert r.status_code == 200
    assert "operator-alice" in r.text
    assert "operator-bob" in r.text
    assert "node.create" in r.text


def test_history_filter_by_action_prefix(admin_client):
    _seed_audit([
        {"occurred_at": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
         "actor_label": "x", "action": "node.create"},
        {"occurred_at": datetime(2026, 6, 1, 12, 1, tzinfo=timezone.utc),
         "actor_label": "y", "action": "dataset.update"},
    ])
    r = admin_client.get("/admin/history/?action_prefix=node")
    assert r.status_code == 200
    assert "node.create" in r.text
    assert "dataset.update" not in r.text


def test_history_filter_by_actor(admin_client):
    _seed_audit([
        {"occurred_at": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
         "actor_label": "alice", "action": "x.y"},
        {"occurred_at": datetime(2026, 6, 1, 12, 1, tzinfo=timezone.utc),
         "actor_label": "bob",   "action": "x.y"},
    ])
    r = admin_client.get("/admin/history/?actor=alice")
    assert r.status_code == 200
    # The actor filter <datalist> autocompletes from ALL known actors, so it
    # legitimately contains "bob". Strip it before asserting on the results so
    # the test checks the filtered rows, not the filter UI.
    import re
    body = re.sub(r"<datalist\b.*?</datalist>", "", r.text, flags=re.DOTALL | re.IGNORECASE)
    assert "alice" in body
    assert "bob" not in body


def test_history_detail_page(admin_client):
    _seed_audit([
        {"occurred_at": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
         "actor_label": "carol", "action": "node.delete",
         "target_type": "node", "target_id": "old",
         "changes_json": {"before": {"code": "old"}}}
    ])
    # Find the inserted row's id.
    sess_factory = app.state.testing_session_local
    with sess_factory() as db:
        row_id = db.query(AuditLog).filter(AuditLog.actor_label == "carol").one().id
    r = admin_client.get(f"/admin/history/{row_id}")
    assert r.status_code == 200
    assert "node.delete" in r.text
    # JSON payload pretty-printed in the page.
    assert '"code"' in r.text


def test_history_detail_404(admin_client):
    r = admin_client.get("/admin/history/9999999")
    assert r.status_code == 404


def test_history_csv_export(admin_client):
    _seed_audit([
        {"occurred_at": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
         "actor_label": "exporter", "action": "dataset.create",
         "target_type": "dataset", "target_id": "ds_export_test",
         "ip_address": "10.0.0.99"},
    ])
    r = admin_client.get("/admin/history/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers.get("content-disposition", "").lower()
    body = r.text
    assert "occurred_at,actor,action" in body.splitlines()[0]
    assert "exporter" in body
    assert "dataset.create" in body
    assert "ds_export_test" in body


def test_history_csv_filter_propagated_to_export(admin_client):
    _seed_audit([
        {"occurred_at": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
         "actor_label": "alice", "action": "x.y", "target_id": "should-appear"},
        {"occurred_at": datetime(2026, 6, 1, 12, 1, tzinfo=timezone.utc),
         "actor_label": "bob",   "action": "x.y", "target_id": "should-NOT-appear"},
    ])
    r = admin_client.get("/admin/history/export.csv?actor=alice")
    assert r.status_code == 200
    assert "should-appear" in r.text
    assert "should-NOT-appear" not in r.text
