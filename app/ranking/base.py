# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from abc import ABC
from dataclasses import dataclass

from app.models.replica import DatasetReplica


@dataclass
class RankedReplica:
    """One replica's place in a routing decision, with the reason for it.

    ``eligible`` replicas come first, best first; the others are listed with
    the reason they were set aside. ``score`` is the policy's cost (lower is
    better) where the policy has one.
    """

    replica: DatasetReplica
    eligible: bool
    reason: str
    score: float | None = None
    telemetry_age_s: float | None = None


class RankingPolicy(ABC):
    """A routing policy. Implement ``explain``; policies written before it
    existed, which implement only ``choose(replicas)``, keep working: their
    choice goes first and the other eligible replicas follow."""

    name = "custom"

    def explain(self, replicas: list[DatasetReplica], *,
                estsize_kb: int | None = None) -> list[RankedReplica]:
        """Every replica, eligible ones first in ranking order, each with its reason."""
        if type(self).choose is RankingPolicy.choose:
            raise NotImplementedError("a RankingPolicy implements explain() (or, historically, choose())")
        eligible = [rep for rep in replicas if static_exclusion(rep) is None]
        if not eligible:
            return [RankedReplica(rep, False, static_exclusion(rep)) for rep in replicas]
        chosen = self.choose(eligible)
        ordered = [chosen] + [rep for rep in eligible if rep is not chosen]
        out = [RankedReplica(rep, True, f"chosen by the {self.name} policy" if rep is chosen
                             else f"fallback under the {self.name} policy") for rep in ordered]
        out += [RankedReplica(rep, False, static_exclusion(rep))
                for rep in replicas if static_exclusion(rep) is not None]
        return out

    def rank(self, replicas: list[DatasetReplica], *,
             estsize_kb: int | None = None) -> list[DatasetReplica]:
        return [d.replica for d in self.explain(replicas, estsize_kb=estsize_kb) if d.eligible]

    def eligible(self, replicas: list[DatasetReplica]) -> list[DatasetReplica]:
        """The replicas the catalogue may hand out at all, in input order."""
        return [rep for rep in replicas if static_exclusion(rep) is None]

    def choose(self, replicas: list[DatasetReplica], *,
               estsize_kb: int | None = None) -> DatasetReplica:
        ranked = self.rank(replicas, estsize_kb=estsize_kb)
        if not ranked:
            raise ValueError("No eligible replicas available")
        return ranked[0]


def static_exclusion(rep: DatasetReplica) -> str | None:
    """Why the catalogue itself sets a replica aside (operator state), or None."""
    if getattr(rep, "status", "available") != "available":
        return f"replica {getattr(rep, 'status', '')}"
    if not getattr(rep, "is_public", True):
        return "replica not public"
    if not rep.node.is_enabled:
        return "node disabled by the operator"
    if not rep.node.is_available:
        return "node marked unavailable by the operator"
    return None
