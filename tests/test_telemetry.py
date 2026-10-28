"""The prober, and DataLink answers under the resource-aware policy."""
import asyncio

import httpx
import pytest

from app.config import settings
from app.main import app
from app.models.node import Node
from app.services import telemetry_service


def _status(pressure=0.0, free=8 << 30):
    return {"cpu": {"pressure_pct": pressure}, "memory": {"available_bytes": free},
            "tasks": {"running": 0, "queued": 0}, "workers": {"total": 2}}


def _give_backends(db, statuses):
    for node in db.query(Node).all():
        node.visivo_backend_url = f"http://{node.code.lower()}.test:8000"
        node.visivo_backend_requires_auth = False
    db.commit()


def _transport(statuses, down=()):
    def handler(request: httpx.Request) -> httpx.Response:
        code = request.url.host.split(".")[0].upper()
        if code in down:
            raise httpx.ConnectError("refused", request=request)
        if request.url.path == "/v1/ping":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json=statuses[code])
    return httpx.MockTransport(handler)


@pytest.fixture()
def mocked_nodes(monkeypatch):
    statuses = {"A": _status(), "B": _status(pressure=90.0), "C": _status()}
    down = set()
    real = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = _transport(statuses, down)
        return real(*args, **kwargs)

    monkeypatch.setattr(telemetry_service.httpx, "AsyncClient", client_factory)
    return statuses, down


def test_probe_records_status_and_failures(client, mocked_nodes):
    statuses, down = mocked_nodes
    down.add("C")
    with app.state.testing_session_local() as db:
        _give_backends(db, statuses)
        results = asyncio.run(telemetry_service.probe_all(db))
        assert {r.code: r.ok for r in results} == {"A": True, "B": True, "C": False}
        a = db.query(Node).filter_by(code="A").one()
        assert a.probe_ok and a.probe_rtt_ms is not None and a.telemetry_json["workers"]["total"] == 2
        c = db.query(Node).filter_by(code="C").one()
        assert c.probe_ok is False and "refused" in c.probe_error


def test_datalink_routes_by_measured_state_and_explains(client, mocked_nodes, monkeypatch):
    statuses, _ = mocked_nodes
    monkeypatch.setattr(settings, "ranking_policy", "resource_aware")
    with app.state.testing_session_local() as db:
        _give_backends(db, statuses)
        asyncio.run(telemetry_service.probe_all(db))
    # dataset-3 is on A and B. Declared scores prefer B; B reports 90 % CPU pressure.
    body = client.get("/datalink/dataset-3").json()
    routing = body["routing"]
    assert routing["policy"] == "resource_aware"
    assert routing["best_node"] == "A"
    assert [r["code"] for r in routing["replicas"]] == ["A", "B"]
    assert "cpu pressure 90%" in routing["replicas"][1]["rank_reason"]
    assert routing["replicas"][0]["score"] < routing["replicas"][1]["score"]
    assert routing["replicas"][0]["telemetry_age_s"] is not None


def test_static_policy_is_the_default_and_unchanged(client):
    routing = client.get("/datalink/dataset-3").json()["routing"]
    assert routing["policy"] == "static"
    assert routing["best_node"] == "B"
    assert routing["replicas"][0]["rank_reason"].startswith("declared latency")
    assert routing["excluded"] == []


def test_probe_route_needs_the_internal_key(client, mocked_nodes):
    assert client.post("/internal/telemetry/probe").status_code in (401, 403)


def test_clean_status_keeps_types_and_drops_garbage():
    cleaned = telemetry_service.clean_status(
        {"cpu": {"pressure_pct": "high", "cpus": 2}, "memory": {"available_bytes": float("nan")},
         "tasks": "none", "capabilities": {"finders": ["sofia2", 3]}, "secret": "x"})
    assert cleaned["cpu"] == {"cpus": 2.0, "pressure_pct": None, "utilisation_pct": None}
    assert cleaned["memory"]["available_bytes"] is None
    assert cleaned["tasks"] == {"running": None, "queued": None}
    assert cleaned["capabilities"]["finders"] == ["sofia2"]
    assert "secret" not in cleaned
    with pytest.raises(ValueError):
        telemetry_service.clean_status(["not", "a", "dict"])
    # A valid JSON integer too large for a float is unknown, not a crash.
    assert telemetry_service.clean_status({"memory": {"available_bytes": 10 ** 400}})["memory"][
        "available_bytes"] is None


def test_an_older_probe_never_overwrites_a_newer_one(client, monkeypatch):
    from datetime import datetime

    with app.state.testing_session_local() as db:
        _give_backends(db, {})
        newer = datetime(2026, 10, 27, 12, 0, 10)
        older = datetime(2026, 10, 27, 12, 0, 0)

        async def fake_probe(_client, node):
            return telemetry_service.ProbeResult(code=node.code, ok=True, rtt_ms=1.0,
                                                 status={"marker": "new"}, observed_at=newer)

        monkeypatch.setattr(telemetry_service, "probe_node", fake_probe)
        asyncio.run(telemetry_service.probe_all(db))

        async def slow_failure(_client, node):
            return telemetry_service.ProbeResult(code=node.code, ok=False, error="old timeout",
                                                 observed_at=older)

        monkeypatch.setattr(telemetry_service, "probe_node", slow_failure)
        asyncio.run(telemetry_service.probe_all(db))
        a = db.query(Node).filter_by(code="A").one()
        assert a.probe_ok is True and a.telemetry_at == newer
