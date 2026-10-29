# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace

from app.ranking.default import DefaultRankingPolicy


def make_replica(
    code: str,
    latency: float | None,
    capability: float | None,
    is_enabled: bool = True,
    is_available: bool = True,
):
    node = SimpleNamespace(
        code=code,
        latency_score=latency,
        capability_score=capability,
        is_enabled=is_enabled,
        is_available=is_available,
    )
    return SimpleNamespace(node=node)


def test_ranking_single_replica_returns_only_replica():
    policy = DefaultRankingPolicy()
    rep = make_replica("A", 10.0, 0.7)
    assert policy.choose([rep]).node.code == "A"


def test_ranking_prefers_lowest_latency_then_capability():
    policy = DefaultRankingPolicy()
    rep_a = make_replica("A", 15.0, 0.99)
    rep_b = make_replica("B", 10.0, 0.50)
    rep_c = make_replica("C", 10.0, 0.90)

    chosen = policy.choose([rep_a, rep_b, rep_c])
    assert chosen.node.code == "C"


def test_ranking_ignores_disabled_and_unavailable_nodes():
    policy = DefaultRankingPolicy()
    rep_a = make_replica("A", 1.0, 1.0, is_enabled=False)
    rep_b = make_replica("B", 1.0, 1.0, is_available=False)
    rep_c = make_replica("C", 5.0, 0.8, is_enabled=True, is_available=True)

    chosen = policy.choose([rep_a, rep_b, rep_c])
    assert chosen.node.code == "C"
