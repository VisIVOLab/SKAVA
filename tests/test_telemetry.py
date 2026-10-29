# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
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


def test_resource_aware_is_the_default_and_falls_back_to_declared_scores(client):
    # The default policy, with no telemetry yet, keeps the declared order and
    # says why; the defaults themselves are resource_aware and a 10 s probe.
    from app.config import Settings
    defaults = Settings.model_fields
    assert defaults["ranking_policy"].default == "resource_aware"
    assert defaults["telemetry_interval_seconds"].default == 10.0
    routing = client.get("/datalink/dataset-3").json()["routing"]
    assert routing["policy"] == "resource_aware"
    assert routing["best_node"] == "B"
    assert routing["replicas"][0]["rank_reason"].startswith("no co-located backend to measure")
    assert routing["excluded"] == []


def test_static_policy_is_unchanged(client, monkeypatch):
    monkeypatch.setattr(settings, "ranking_policy", "static")
    routing = client.get("/datalink/dataset-3").json()["routing"]
    assert routing["policy"] == "static" and routing["best_node"] == "B"
    assert routing["replicas"][0]["rank_reason"].startswith("declared latency")


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



def _report(client, code, status, rtt_ms=None, token=None):
    from app.security.node_token import node_token
    body = {"node_code": code, "status": status}
    if rtt_ms is not None:
        body["rtt_ms"] = rtt_ms
    return client.post("/internal/telemetry/report", json=body,
                       headers={"X-Skava-Node-Token": token if token is not None else node_token(code)})


def test_a_node_can_push_its_state_and_is_ranked_on_it(client, mocked_nodes, monkeypatch):
    # A node behind a firewall: the probe cannot reach it, it reports itself.
    statuses, down = mocked_nodes
    monkeypatch.setattr(settings, "ranking_policy", "resource_aware")
    with app.state.testing_session_local() as db:
        _give_backends(db, statuses)
    down.update({"A", "B", "C"})
    assert _report(client, "A", _status(pressure=5.0), rtt_ms=12.5).json() == {"node": "A", "accepted": True}
    assert _report(client, "B", _status(pressure=95.0), rtt_ms=3.0).json()["accepted"]
    with app.state.testing_session_local() as db:
        a = db.query(Node).filter_by(code="A").one()
        assert a.probe_ok and a.probe_rtt_ms == 12.5 and a.telemetry_json["source"] == "push"
        # The prober leaves reporting nodes alone: the failing ping does not
        # mark them unreachable while their report is fresh.
        results = asyncio.run(telemetry_service.probe_all(db))
        assert {r.code for r in results} == {"C"}
        assert db.query(Node).filter_by(code="A").one().probe_ok
    routing = client.get("/datalink/dataset-3").json()["routing"]
    assert routing["best_node"] == "A"                       # B reports 95% CPU pressure
    assert "cpu pressure 5%" in routing["replicas"][0]["rank_reason"]


def test_push_needs_the_key_and_a_known_node(client):
    from app.security.node_token import node_token
    assert _report(client, "A", _status(), token="wrong").status_code == 401
    # Node B's token does not let it speak for A, nor does the internal key.
    assert _report(client, "A", _status(), token=node_token("B")).status_code == 401
    assert _report(client, "A", _status(), token="test-internal-key").status_code == 401
    assert _report(client, "A", _status(), token="é".encode("latin-1") * 64).status_code == 401
    assert _report(client, "NOPE", _status()).status_code == 400
    assert _report(client, "A", ["not", "a", "document"]).status_code in (400, 422)
    assert _report(client, "A", {**_status(), "node_code": "B"}).status_code == 400


def test_a_stale_report_is_probed_again(client, mocked_nodes):
    from datetime import timedelta
    statuses, down = mocked_nodes
    with app.state.testing_session_local() as db:
        _give_backends(db, statuses)
    _report(client, "A", _status())
    with app.state.testing_session_local() as db:
        a = db.query(Node).filter_by(code="A").one()
        a.telemetry_at = a.telemetry_at - timedelta(seconds=settings.telemetry_ttl_seconds + 1)
        db.commit()
        results = asyncio.run(telemetry_service.probe_all(db))
        assert "A" in {r.code for r in results}
        assert db.query(Node).filter_by(code="A").one().telemetry_json["source"] == "probe"


def test_a_report_landing_during_a_probe_is_not_overwritten(client, mocked_nodes, monkeypatch):
    # The probe began before the node reported; its (failed) result is older.
    statuses, down = mocked_nodes
    with app.state.testing_session_local() as db:
        _give_backends(db, statuses)
    original = telemetry_service.probe_node

    async def probe_while_a_report_lands(http, node):
        if node.code == "A":
            assert _report(client, "A", _status(pressure=4.0)).json()["accepted"]
            down.add("A")
        return await original(http, node)

    monkeypatch.setattr(telemetry_service, "probe_node", probe_while_a_report_lands)
    with app.state.testing_session_local() as db:
        asyncio.run(telemetry_service.probe_all(db))
        a = db.query(Node).filter_by(code="A").one()
        assert a.probe_ok and a.telemetry_json["source"] == "push"


def test_the_node_token_command_prints_the_token(capsys):
    from app.security.node_token import main, node_token
    assert main(["A"]) == 0
    assert capsys.readouterr().out.strip() == node_token("A") != node_token("B")


def test_a_report_landing_before_the_probe_starts_is_kept(client, mocked_nodes, monkeypatch):
    # Reported between the prober's eligibility read and its probe.
    statuses, down = mocked_nodes
    with app.state.testing_session_local() as db:
        _give_backends(db, statuses)
    checked = telemetry_service._pushed_recently

    def report_after_the_check(node, now=None):
        skip = checked(node, now)
        if node.code == "A":
            _report(client, "A", _status())
            down.add("A")
        return skip

    monkeypatch.setattr(telemetry_service, "_pushed_recently", report_after_the_check)
    with app.state.testing_session_local() as db:
        asyncio.run(telemetry_service.probe_all(db))
        assert db.query(Node).filter_by(code="A").one().probe_ok
