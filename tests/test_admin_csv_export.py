# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""CSV export helper + datasets export route (Phase 3)."""
from __future__ import annotations

from app.admin.csv_export import _format_value, stream_csv
from datetime import datetime, timezone


def _drain_streaming_body(resp) -> str:
    """Drain a StreamingResponse body across Starlette versions.

    Newer Starlette wraps even a *sync* content generator so ``body_iterator``
    becomes an async generator; older versions expose the sync generator
    directly. Handle both so the test is version-robust.
    """
    it = resp.body_iterator
    if hasattr(it, "__aiter__"):
        import anyio

        async def _collect():
            return [chunk async for chunk in it]

        parts = anyio.run(_collect)
    else:
        parts = list(it)
    return "".join(p if isinstance(p, str) else p.decode() for p in parts)


def test_format_value_handles_none_and_primitives():
    assert _format_value(None) == ""
    assert _format_value(42) == "42"
    assert _format_value(3.14) == "3.14"
    assert _format_value("hi") == "hi"


def test_format_value_datetime_is_iso():
    dt = datetime(2026, 6, 6, 12, 30, tzinfo=timezone.utc)
    assert _format_value(dt) == "2026-06-06T12:30:00+00:00"


def test_format_value_naive_datetime_assumed_utc():
    dt = datetime(2026, 6, 6, 12, 30)   # no tz
    assert _format_value(dt).endswith("+00:00")


def test_format_value_json_compact():
    assert _format_value({"a": 1, "b": "two"}) == '{"a":1,"b":"two"}'
    assert _format_value([1, 2, 3]) == "[1,2,3]"


def test_stream_csv_emits_header_and_rows():
    resp = stream_csv(
        header=["col1", "col2"],
        rows=[(1, "one"), (2, "two")],
        filename="test.csv",
    )
    body = _drain_streaming_body(resp)
    assert body.startswith("col1,col2")
    assert "1,one" in body
    assert "2,two" in body
    assert resp.media_type.startswith("text/csv")


def test_datasets_csv_export_route(admin_client):
    r = admin_client.get("/admin/datasets/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    # Header row is canonical ObsCore-ish.
    first_line = r.text.splitlines()[0]
    assert "obs_id" in first_line
    assert "obs_collection" in first_line
    assert "replica_count" in first_line


def test_datasets_csv_export_respects_filter(admin_client):
    """Filter query params propagate into the export query."""
    r = admin_client.get("/admin/datasets/export.csv?collection=does-not-exist")
    assert r.status_code == 200
    # Only header line present (no matching rows).
    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    assert len(lines) == 1
