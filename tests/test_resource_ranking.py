"""The resource-aware ranking policy: filters, cost, fallbacks and reasons."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.ranking.resource_aware import ResourceAwareRankingPolicy

NOW = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
GB = 1024 ** 3


def node(code, *, rtt=1.0, cpu=0.0, free=8 * GB, running=0, queued=0, workers=2,
         ok=True, age=5.0, backend=True, latency=10.0, enabled=True):
    return SimpleNamespace(
        code=code, is_enabled=enabled, is_available=True,
        latency_score=latency, load_score=0.1, capability_score=1.0,
        visivo_backend_url=f"http://{code.lower()}:8000" if backend else None,
        probe_ok=ok, probe_rtt_ms=rtt, probe_error=None if ok else "ConnectError: refused",
        telemetry_at=(NOW - timedelta(seconds=age)).replace(tzinfo=None) if age is not None else None,
        telemetry_json={
            "cpu": {"pressure_pct": cpu},
            "memory": {"available_bytes": free},
            "tasks": {"running": running, "queued": queued},
            "workers": {"total": workers},
        },
    )


def rep(n):
    return SimpleNamespace(node=n, status="available", is_public=True)


def explain(*nodes, estsize_kb=None):
    return ResourceAwareRankingPolicy(now=NOW).explain([rep(n) for n in nodes], estsize_kb=estsize_kb)


def codes(decisions, eligible=True):
    return [d.replica.node.code for d in decisions if d.eligible is eligible]


def test_measured_cost_orders_the_nodes():
    # 80 ms away, 41 % CPU pressure, and an idle nearby node.
    decisions = explain(node("FAR", rtt=80), node("BUSY", cpu=41), node("BIG"))
    assert codes(decisions) == ["BIG", "BUSY", "FAR"]
    assert decisions[0].score < decisions[1].score < decisions[2].score
    assert "rtt 1.0 ms" in decisions[0].reason


def test_queue_per_worker_counts():
    decisions = explain(node("A", running=2, queued=2, workers=2), node("B", rtt=10))
    # A: 2 tasks per worker × 20 = 40 > B: 10 ms
    assert codes(decisions) == ["B", "A"]


def test_too_little_memory_is_excluded_with_the_reason():
    decisions = explain(node("SMALL", free=1 * GB), node("BIG", rtt=5), estsize_kb=3 * 1024 * 1024)
    assert codes(decisions) == ["BIG"]
    small = next(d for d in decisions if d.replica.node.code == "SMALL")
    assert not small.eligible and small.reason.startswith("not enough memory")
    assert "3.0 GB of 1.0 GB free" in small.reason


def test_when_nobody_has_room_the_roomiest_serves_and_says_so():
    decisions = explain(node("A", free=1 * GB), node("B", free=2 * GB), estsize_kb=3 * 1024 * 1024)
    assert codes(decisions) == ["B"]
    assert decisions[0].reason.startswith("no node has enough free memory")
    assert codes(decisions, eligible=False) == ["A"]


def test_unreachable_backend_is_excluded():
    decisions = explain(node("DOWN", ok=False), node("UP", rtt=50))
    assert codes(decisions) == ["UP"]
    down = next(d for d in decisions if not d.eligible)
    assert "unreachable" in down.reason and "refused" in down.reason


def test_stale_or_missing_telemetry_follows_the_measured_by_declared_scores():
    decisions = explain(node("STALE", age=3600, latency=1), node("NEVER", age=None, latency=2),
                        node("NOBACKEND", backend=False, latency=0), node("MEASURED", rtt=200))
    assert codes(decisions) == ["MEASURED", "NOBACKEND", "STALE", "NEVER"]
    reasons = {d.replica.node.code: d.reason for d in decisions}
    assert reasons["STALE"].startswith("telemetry stale")
    assert reasons["NEVER"].startswith("no telemetry yet")
    assert reasons["NOBACKEND"].startswith("no co-located backend")


def test_operator_exclusions_still_apply():
    decisions = explain(node("OFF", enabled=False), node("ON"))
    assert codes(decisions) == ["ON"]
    assert "disabled" in next(d for d in decisions if not d.eligible).reason


def test_unknown_values_are_not_read_as_idle():
    unknown = node("UNKNOWN")
    unknown.telemetry_json = {"cpu": {"pressure_pct": None}, "memory": {"available_bytes": None},
                              "tasks": {}, "workers": {}}
    decisions = explain(unknown, node("KNOWN"), estsize_kb=1024 * 1024)
    assert codes(decisions) == ["KNOWN", "UNKNOWN"]
    reason = next(d for d in decisions if d.replica.node.code == "UNKNOWN").reason
    assert "cpu pressure unknown" in reason and "free memory unknown" in reason


def test_an_unmeasured_replica_serves_before_memory_is_relaxed():
    decisions = explain(node("SMALL", free=1 * GB), node("UNMEASURED", age=None),
                        estsize_kb=3 * 1024 * 1024)
    assert codes(decisions) == ["UNMEASURED"]
    assert next(d for d in decisions if not d.eligible).reason.startswith("not enough memory")


def test_malformed_stored_telemetry_does_not_break_routing():
    bad = node("BAD")
    bad.telemetry_json = {"cpu": "unknown", "tasks": [1], "memory": 5}
    decisions = explain(bad, node("GOOD"))
    assert codes(decisions) == ["GOOD", "BAD"]


def test_a_choose_only_policy_still_works():
    from app.ranking.base import RankingPolicy

    class Legacy(RankingPolicy):
        name = "legacy"

        def choose(self, replicas):
            return replicas[-1]

    reps = [rep(node("A")), rep(node("B")), rep(node("OFF", enabled=False))]
    decisions = Legacy().explain(reps)
    assert [d.replica.node.code for d in decisions if d.eligible] == ["B", "A"]
    assert Legacy().choose(reps[:2]).node.code == "B"
