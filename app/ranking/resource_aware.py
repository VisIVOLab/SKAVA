# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Rank replicas by what their nodes can take on now, as the nodes report it.

The static policy trusts scores an operator declared when the node was
registered. This one reads the telemetry SKAVA's prober collects from each
node's co-located backend (app/services/telemetry_service.py) and decides in
two steps, the way a scheduler does:

1. **Filter.** Besides the operator's own exclusions, a replica is set aside
   when its node's backend did not answer the last probe, or when the node
   reports less free memory than the dataset needs. If no other replica can
   serve (none measured with room, none unmeasured) the memory filter is
   relaxed: the node with the most room serves, and the reason says so. A
   catalogue that answers "nowhere" helps nobody.
2. **Rank.** The rest are ordered by a cost in millisecond-equivalents:

       cost = w_rtt · rtt_ms + w_cpu · cpu_pressure_% + w_queue · tasks_per_worker
              + w_mem · (needed / free memory)

   so the terms read alike: 80 ms of round trip weighs as much as 80 % CPU
   pressure (with the default unit weights).
   A quantity the node did not report is never read as "idle": it is costed
   as a poor value would be (UNKNOWN_* below) and the reason says "unknown".

Nodes without a backend, or without fresh telemetry, cannot be measured; they
follow the measured ones, in the static policy's order. Every replica carries
the reason for its place, which the DataLink response publishes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.config import settings
from app.models.replica import DatasetReplica
from app.ranking.base import RankedReplica, RankingPolicy, static_exclusion
from app.ranking.default import DefaultRankingPolicy


def _fmt_bytes(n: float | None) -> str:
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _age_seconds(node, now: datetime) -> float | None:
    taken = getattr(node, "telemetry_at", None)
    if taken is None:
        return None
    if taken.tzinfo is None:
        taken = taken.replace(tzinfo=timezone.utc)
    return max(0.0, (now - taken).total_seconds())


# Cost of a quantity the node did not report: as bad as a poor measurement.
UNKNOWN_RTT_MS = 100.0
UNKNOWN_CPU_PCT = 50.0
UNKNOWN_TASKS_PER_WORKER = 1.0


def _get(status: dict, section: str, key: str):
    part = status.get(section)
    return part.get(key) if isinstance(part, dict) else None


def _value(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value == value and value >= 0 else None


class ResourceAwareRankingPolicy(RankingPolicy):
    name = "resource_aware"

    def __init__(self, *, now: datetime | None = None):
        self._now = now  # fixed clock for tests

    def explain(self, replicas: list[DatasetReplica], *,
                estsize_kb: int | None = None) -> list[RankedReplica]:
        now = self._now or datetime.now(timezone.utc)
        need = (estsize_kb or 0) * 1024 * settings.ranking_memory_factor
        measured: list[RankedReplica] = []
        unmeasured: list[DatasetReplica] = []
        out_of_memory: list[RankedReplica] = []
        excluded: list[RankedReplica] = []

        for rep in replicas:
            reason = static_exclusion(rep)
            if reason is not None:
                excluded.append(RankedReplica(rep, False, reason))
                continue
            node = rep.node
            age = _age_seconds(node, now)
            fresh = age is not None and age <= settings.telemetry_ttl_seconds
            if not getattr(node, "visivo_backend_url", None) or not fresh:
                unmeasured.append(rep)
                continue
            if getattr(node, "probe_ok", None) is False:
                error = getattr(node, "probe_error", None) or "no answer"
                excluded.append(RankedReplica(rep, False, f"backend unreachable at the last probe ({error})",
                                              telemetry_age_s=age))
                continue

            status = getattr(node, "telemetry_json", None)
            status = status if isinstance(status, dict) else {}
            rtt = _value(getattr(node, "probe_rtt_ms", None))
            cpu = _value(_get(status, "cpu", "pressure_pct"))
            running = _value(_get(status, "tasks", "running"))
            queued = _value(_get(status, "tasks", "queued"))
            workers = max(1.0, _value(_get(status, "workers", "total")) or 1.0)
            free = _value(_get(status, "memory", "available_bytes"))

            # An unknown is never read as "idle": it costs as much as a bad
            # value would, and the reason says it is unknown.
            rtt_term = rtt if rtt is not None else UNKNOWN_RTT_MS
            cpu_term = cpu if cpu is not None else UNKNOWN_CPU_PCT
            tasks_term = ((running or 0.0) + (queued or 0.0)) / workers if None not in (running, queued) \
                else UNKNOWN_TASKS_PER_WORKER
            if not need:
                mem_term = 0.0
            elif free:
                mem_term = need / free
            else:
                mem_term = 1.0
            cost = (settings.ranking_weight_rtt * rtt_term
                    + settings.ranking_weight_cpu * cpu_term
                    + settings.ranking_weight_queue * tasks_term
                    + settings.ranking_weight_memory * mem_term)
            reason = ", ".join([
                f"rtt {rtt:.1f} ms" if rtt is not None else "rtt unknown",
                f"cpu pressure {cpu:.0f}%" if cpu is not None else "cpu pressure unknown",
                f"{tasks_term:.1f} tasks/worker" if None not in (running, queued) else "tasks unknown",
                (f"needs {_fmt_bytes(need)} of {_fmt_bytes(free)} free" if free is not None
                 else f"needs {_fmt_bytes(need)}, free memory unknown"),
            ])
            decision = RankedReplica(rep, True, reason, score=round(cost, 2), telemetry_age_s=age)
            if need and free is not None and free < need:
                decision.eligible = False
                decision.reason = f"not enough memory: {reason}"
                out_of_memory.append(decision)
            else:
                measured.append(decision)

        measured.sort(key=lambda d: (d.score, d.replica.node.code))
        fallback = DefaultRankingPolicy().explain(unmeasured)
        if not measured and not fallback and out_of_memory:
            # Nobody has room: serve from the node with the most, and say so.
            out_of_memory.sort(key=lambda d: -(((d.replica.node.telemetry_json or {})
                                                .get("memory") or {}).get("available_bytes") or 0))
            best = out_of_memory.pop(0)
            best.eligible = True
            best.reason = f"no node has enough free memory; most room here: {best.reason[len('not enough memory: '):]}"
            measured.append(best)

        for d in fallback:
            age = _age_seconds(d.replica.node, now)
            why = ("no co-located backend to measure" if not getattr(d.replica.node, "visivo_backend_url", None)
                   else "no telemetry yet" if age is None
                   else f"telemetry stale ({age:.0f} s old)")
            d.reason = f"{why}; {d.reason}"
            d.telemetry_age_s = age
        return measured + fallback + out_of_memory + excluded
