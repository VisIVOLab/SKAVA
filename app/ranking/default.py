# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from app.models.replica import DatasetReplica
from app.ranking.base import RankedReplica, RankingPolicy, static_exclusion


def _score(value: float | None, default: float) -> float:
    return value if value is not None else default


class DefaultRankingPolicy(RankingPolicy):
    """Rank by the scores declared on each node: latency, then load, then capability."""

    name = "static"

    def explain(self, replicas: list[DatasetReplica], *,
                estsize_kb: int | None = None) -> list[RankedReplica]:
        eligible = [rep for rep in replicas if static_exclusion(rep) is None]
        eligible.sort(
            key=lambda r: (
                _score(getattr(r.node, "latency_score", None), float("inf")),
                _score(getattr(r.node, "load_score", None), float("inf")),
                -_score(getattr(r.node, "capability_score", None), float("-inf")),
            ),
        )
        out = [
            RankedReplica(
                replica=rep,
                eligible=True,
                reason=(f"declared latency {getattr(rep.node, 'latency_score', None)}, "
                        f"load {getattr(rep.node, 'load_score', None)}, "
                        f"capability {getattr(rep.node, 'capability_score', None)}"),
            )
            for rep in eligible
        ]
        out += [
            RankedReplica(replica=rep, eligible=False, reason=static_exclusion(rep))
            for rep in replicas if static_exclusion(rep) is not None
        ]
        return out
