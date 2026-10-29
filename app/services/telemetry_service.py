# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Probe the nodes' co-located backends and record what they report.

For every enabled node with a ``visivo_backend_url`` the prober measures the
round trip of ``/v1/ping`` (median of a few samples) and reads
``/v1/node/status`` (CPU and memory under the node's own limits, tasks, render
slots, finders). The result is stored on the node and read by the
resource-aware ranking policy. A node whose backend does not answer is
recorded as such, which the policy treats as "do not route here".

The probe runs from SKAVA, so the round trip it measures is SKAVA's, not the
client's; on a federation where SKAVA sits next to its nodes that is the
node's own network distance, which is the quantity the policy needs.
"""
from __future__ import annotations

import asyncio
import logging
import math
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.metrics import record_probe
from app.models.node import Node

logger = logging.getLogger("skava.telemetry")


@dataclass
class ProbeResult:
    code: str
    ok: bool
    rtt_ms: float | None = None
    status: dict[str, Any] | None = None
    error: str | None = None
    # When the measurement completed (UTC, naive): a result is stored only if it
    # is newer than what the node already has, so a slow probe never overwrites
    # a later one.
    observed_at: datetime | None = None


def _number(value: Any) -> float | None:
    """A finite, non-negative number, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except OverflowError:            # a JSON integer beyond float range
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _section(status: dict, key: str) -> dict:
    value = status.get(key)
    return value if isinstance(value, dict) else {}


def clean_status(status: Any) -> dict[str, Any]:
    """Keep only the fields the policy reads, with the types it expects.

    A node reports what it reports; a malformed or partial document must not
    break routing for everyone, so anything unusable becomes None (unknown).
    """
    if not isinstance(status, dict):
        raise ValueError("node status is not a JSON object")
    cpu, mem = _section(status, "cpu"), _section(status, "memory")
    tasks, workers = _section(status, "tasks"), _section(status, "workers")
    caps = _section(status, "capabilities")

    def strings(values: Any) -> list[str]:
        return [v for v in values if isinstance(v, str)][:32] if isinstance(values, list) else []

    def text(value: Any) -> str | None:
        return value[:64] if isinstance(value, str) else None

    return {
        "node_code": text(status.get("node_code")),
        "version": text(status.get("version")),
        "cpu": {"cpus": _number(cpu.get("cpus")), "pressure_pct": _number(cpu.get("pressure_pct")),
                "utilisation_pct": _number(cpu.get("utilisation_pct"))},
        "memory": {"total_bytes": _number(mem.get("total_bytes")),
                   "available_bytes": _number(mem.get("available_bytes")),
                   "pressure_pct": _number(mem.get("pressure_pct"))},
        "disk": {"workspace_free_bytes": _number(_section(status, "disk").get("workspace_free_bytes"))},
        "workers": {"total": _number(workers.get("total"))},
        "tasks": {"running": _number(tasks.get("running")), "queued": _number(tasks.get("queued"))},
        "render": {"active": _number(_section(status, "render").get("active")),
                   "capacity": _number(_section(status, "render").get("capacity"))},
        "gpu": status.get("gpu") if isinstance(status.get("gpu"), bool) else None,
        "capabilities": {"kinds": strings(caps.get("kinds")), "finders": strings(caps.get("finders"))},
    }


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _headers(node: Node) -> dict[str, str]:
    if node.visivo_backend_requires_auth and settings.visivo_backend_token:
        return {"X-Visivo-Token": settings.visivo_backend_token}
    return {}


async def probe_node(client: httpx.AsyncClient, node: Node) -> ProbeResult:
    base = node.visivo_backend_url.rstrip("/")
    try:
        samples = []
        for _ in range(settings.telemetry_ping_samples):
            t0 = time.perf_counter()
            resp = await client.get(f"{base}/v1/ping")
            resp.raise_for_status()
            samples.append((time.perf_counter() - t0) * 1000.0)
        resp = await client.get(f"{base}/v1/node/status", headers=_headers(node))
        resp.raise_for_status()
        status = clean_status(resp.json())
    except (httpx.HTTPError, ValueError) as exc:
        message = f"{type(exc).__name__}: {exc}"[:250]
        return ProbeResult(code=node.code, ok=False, error=message, observed_at=_now())
    return ProbeResult(code=node.code, ok=True, rtt_ms=round(statistics.median(samples), 3),
                       status=status, observed_at=_now())


async def probe_all(db: Session) -> list[ProbeResult]:
    """Probe every enabled node that has a backend, concurrently, and store the results."""
    # Taken before the eligibility read: a report that lands after it is newer.
    started = _now()
    nodes = [node for node in db.scalars(
        select(Node).where(Node.is_enabled.is_(True), Node.visivo_backend_url.is_not(None))
    ).all() if not _pushed_recently(node)]
    if not nodes:
        return []
    timeout = httpx.Timeout(settings.telemetry_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        results = await asyncio.gather(*(probe_node(client, node) for node in nodes))
    for node, result in zip(nodes, results):
        values = {"probe_ok": result.ok, "probe_error": result.error, "telemetry_at": result.observed_at}
        if result.ok:
            values.update(probe_rtt_ms=result.rtt_ms, telemetry_json={**result.status, "source": "probe"})
        # Conditional in the database: anything stored while this probe was in
        # flight (a node's own report, another cycle, another SKAVA worker)
        # is newer than what the probe saw and wins.
        accepted = db.execute(
            update(Node)
            .where(Node.id == node.id,
                   or_(Node.telemetry_at.is_(None),
                       Node.telemetry_at < min(started, result.observed_at)))
            .values(**values)
            .execution_options(synchronize_session=False)
        ).rowcount > 0
        # Every attempt is counted; only an accepted (newest) observation sets the gauge.
        record_probe(node.code, result.ok, result.rtt_ms if accepted else None)
        if not result.ok:
            logger.warning("node_probe_failed", extra={"node": node.code, "error": result.error})
    db.commit()
    db.expire_all()
    return results


def _pushed_recently(node: Node, now: datetime | None = None) -> bool:
    """A node that reports its own state (it may sit behind a firewall the
    probe cannot cross) is not probed while that report is within the TTL:
    a failing ping must not mark a node unreachable that is reporting."""
    status = node.telemetry_json if isinstance(node.telemetry_json, dict) else {}
    if status.get("source") != "push" or node.telemetry_at is None:
        return False
    age = ((now or _now()) - node.telemetry_at).total_seconds()
    return age < settings.telemetry_ttl_seconds


def store_report(db: Session, node: Node, status: Any, rtt_ms: float | None) -> bool:
    """Store a state the node pushed itself; True when it was the newest.

    The same rule as the probe's: an older observation never replaces a newer
    one. The round trip, when the node gives one, is what it measured on its
    own exchange with the catalogue; without one the last known value stays.
    """
    observed_at = _now()
    values: dict[str, Any] = {"probe_ok": True, "probe_error": None, "telemetry_at": observed_at,
                              "telemetry_json": {**clean_status(status), "source": "push"}}
    rtt = _number(rtt_ms)
    if rtt is not None and 0.0 <= rtt < 60_000.0:
        values["probe_rtt_ms"] = round(rtt, 3)
    accepted = db.execute(
        update(Node)
        .where(Node.id == node.id,
               or_(Node.telemetry_at.is_(None), Node.telemetry_at < observed_at))
        .values(**values)
        .execution_options(synchronize_session=False)
    ).rowcount > 0
    db.commit()
    db.expire_all()
    record_probe(node.code, True, values.get("probe_rtt_ms") if accepted else None)
    return accepted


async def run_prober(session_factory, interval_seconds: float) -> None:
    """Probe forever, every ``interval_seconds``; one failed cycle never stops the loop."""
    while True:
        try:
            with session_factory() as db:
                await probe_all(db)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — keep probing whatever one cycle hit
            logger.exception("node_probe_cycle_failed")
        await asyncio.sleep(interval_seconds)
