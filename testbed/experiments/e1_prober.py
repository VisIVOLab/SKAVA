# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""E1, the running service: the decision through the real container, and
what the probe costs.

``benchmark_routing.py`` measures the decision in process against a large
synthetic catalogue. This script measures the same resolution through the
SKAVA container of the testbed (its network, its PostgreSQL, the
resource-aware policy on live telemetry), and reads from SKAVA's metrics
what the probe of the four nodes costs it: probes made, their round trips,
and the time the telemetry endpoint takes.

Usage: ``python -m experiments.e1_prober [--requests 200]``
"""
from __future__ import annotations

import argparse
import re
import statistics
import time

from . import common as c


def percentile(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def metric_samples(text: str, name: str) -> list[tuple[dict, float]]:
    out = []
    for line in text.splitlines():
        if not line.startswith(name):
            continue
        m = re.match(rf"{name}(\{{(.*)\}})?\s+([0-9.eE+-]+)", line)
        if not m:
            continue
        labels = dict(re.findall(r'(\w+)="([^"]*)"', m.group(2) or ""))
        out.append((labels, float(m.group(3))))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--requests", type=int, default=200)
    ap.add_argument("--warmup", type=int, default=10)
    args = ap.parse_args()

    rows: list[dict] = []
    policy = c.current_policy()
    for obs_id in c.DATASETS:
        for _ in range(args.warmup):
            c.skava_datalink(obs_id)
        times = []
        for _ in range(args.requests):
            t, _ = c.timed(lambda: c.skava_datalink(obs_id))
            times.append(t * 1000)
        rows.append({"what": "datalink", "dataset": obs_id, "policy": policy, "requests": args.requests,
                     "p50_ms": round(percentile(times, 50), 2), "p95_ms": round(percentile(times, 95), 2),
                     "mean_ms": round(statistics.mean(times), 2)})
        c.say(f"datalink {obs_id} ({policy}): p50 {rows[-1]['p50_ms']} ms, p95 {rows[-1]['p95_ms']} ms")
    times = []
    for _ in range(args.requests):
        t, _ = c.timed(lambda: c.skava_search(COLLECTION="skava-testbed", limit=100))
        times.append(t * 1000)
    rows.append({"what": "search", "dataset": "", "policy": policy, "requests": args.requests,
                 "p50_ms": round(percentile(times, 50), 2), "p95_ms": round(percentile(times, 95), 2),
                 "mean_ms": round(statistics.mean(times), 2)})

    # The probe, from SKAVA's own counters over an interval.
    m0 = c.skava_metrics()
    t0 = time.monotonic()
    time.sleep(60)
    m1 = c.skava_metrics()
    elapsed = time.monotonic() - t0
    probes0 = {tuple(sorted(l.items())): v for l, v in metric_samples(m0, "skava_node_probes_total")}
    probes1 = {tuple(sorted(l.items())): v for l, v in metric_samples(m1, "skava_node_probes_total")}
    made = sum(probes1.get(k, 0) - probes0.get(k, 0) for k in probes1)
    rtts = {l.get("node", "?"): v for l, v in metric_samples(m1, "skava_node_rtt_ms")}
    t, telemetry = c.timed(c.skava_telemetry)
    rows.append({"what": "probe", "dataset": "", "policy": policy, "requests": int(made),
                 "p50_ms": None, "p95_ms": None, "mean_ms": None,
                 "probes_per_s": round(made / elapsed, 3), "rtt_ms": rtts,
                 "telemetry_read_ms": round(t * 1000, 2), "nodes": len(telemetry.get("nodes", telemetry) or [])})
    c.say(f"probe: {made:.0f} probes in {elapsed:.0f} s, rtt {rtts}")
    out = c.write_results("e1_prober", rows, {"requests": args.requests})
    c.say("written", out)


if __name__ == "__main__":
    main()
