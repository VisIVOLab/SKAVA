# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""E2: placement quality, static policy versus resource-aware.

For each ranking policy the catalogue is asked where each dataset should be
opened, and the operations a session begins with are timed on the node it
chose AND on every other node holding a replica, the ones the policy set
aside included: opening the dataset in place, the first channel slice, a
moment-0 map as a SODA job (the job's own duration on the node). The quality
of a placement is how its times compare with the best any replica would have
given. The testbed's conditions (a loaded node, a far node, a node too small
for the large cube) are what the two policies see differently: the static
one only knows the scores declared at registration.

Every cell is measured after one discarded warm-up run, so the file caches
are warm for every node alike: the comparison is between nodes under the
same conditions, not between cold and warm.

Usage: ``python -m experiments.e2_placement [--repeats 3] [--policies static resource_aware]``
"""
from __future__ import annotations

import argparse
import statistics
import time

from . import common as c


def measure(cand: c.Candidate, obs_id: str, timeout: float) -> dict:
    row = {"node": cand.node, "t_open": None, "t_slice": None, "t_m0": None, "t_m0_wall": None, "error": ""}
    try:
        t_open, opened = c.timed(lambda: c.open_on_node(cand.backend, obs_id, cand.access_url))
        row["t_open"] = round(t_open, 3)
        t_slice, _ = c.timed(lambda: c.first_slice(opened))
        row["t_slice"] = round(t_slice, 3)
        t_m0, job = c.timed(lambda: c.soda_job(cand.backend, {"ID": cand.access_url, "OPERATION": "MOMENT", "MOMENT": "0"},
                                               timeout=timeout))
        # The wall time includes the polling; the job's own clock is the node's.
        row["t_m0"] = round(c.job_duration(job) or t_m0, 3)
        row["t_m0_wall"] = round(t_m0, 3)
    except Exception as exc:  # noqa: BLE001 — the failure IS the measurement
        row["error"] = str(exc)[:200]
    return row


def inventory(datasets: list[str]) -> dict[str, dict[str, str]]:
    """The statically eligible replicas of every dataset (node code → the
    replica's URL there), read under the static policy: it sets no replica
    aside for the node's state, only for the operator's switches, so it
    lists what the resource-aware policy may then exclude."""
    c.restart_skava_with_policy("static")
    out: dict[str, dict[str, str]] = {}
    for obs_id in datasets:
        dl = c.skava_datalink(obs_id)
        out[obs_id] = {r["code"]: r["access_endpoint"] for r in dl["routing"]["replicas"] if r["code"] in c.NODES}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--policies", nargs="+", default=["static", "resource_aware"])
    ap.add_argument("--datasets", nargs="+", default=c.DATASETS)
    ap.add_argument("--timeout", type=float, default=900.0, help="per operation, seconds")
    args = ap.parse_args()

    rows: list[dict] = []
    try:
        replicas = inventory(args.datasets)
        for policy in args.policies:
            c.say(f"policy {policy}: restarting SKAVA")
            c.restart_skava_with_policy(policy)
            if policy == "resource_aware":
                # One probe round, so the decision rests on measurements.
                time.sleep(15)
            for obs_id in args.datasets:
                datalink = c.skava_datalink(obs_id)
                cands = c.candidates(datalink)
                excluded = {e["code"]: e["reason"] for e in datalink["routing"].get("excluded", [])}
                c.say(f"  {obs_id}: order {[x.node for x in cands]}, excluded {excluded}")
                # The replicas the policy set aside are measured too: what it avoided.
                for code, reason in excluded.items():
                    if code in c.NODES and code not in {x.node for x in cands} and code in replicas[obs_id]:
                        cands.append(c.Candidate(code, c.NODES[code]["url"], replicas[obs_id][code],
                                                 f"excluded: {reason}", None))
                for rank, cand in enumerate(cands):
                    # One warm-up run, kept apart: its times are not reported,
                    # its failure is (and ends the cell).
                    samples: list[dict] = []
                    failed: list[dict] = []
                    cell_t0 = time.monotonic()
                    warmup = measure(cand, obs_id, args.timeout)
                    error = warmup["error"]
                    if error:
                        c.say(f"    {cand.node}: {error}")
                    else:
                        for _ in range(args.repeats):
                            t_run = time.monotonic()
                            sample = measure(cand, obs_id, args.timeout)
                            if sample["error"]:
                                # Kept, apart from the samples the medians come from.
                                error = sample["error"]
                                failed.append({**sample, "elapsed": round(time.monotonic() - t_run, 3)})
                                c.say(f"    {cand.node}: {error}")
                                break
                            samples.append(sample)

                    def med(key: str):
                        vals = [s[key] for s in samples if s[key] is not None]
                        return round(statistics.median(vals), 3) if vals else None

                    def worst(key: str):
                        vals = [s[key] for s in samples if s[key] is not None]
                        return round(max(vals), 3) if vals else None

                    # The medians are the figures; every run is kept too, with
                    # the warm-up and the whole cell's wall time, because a
                    # node short of memory is erratic rather than slow, and a
                    # median alone would hide it.
                    rows.append({
                        "policy": policy, "dataset": obs_id, "dataset_bytes": c.dataset_bytes(obs_id),
                        "node": cand.node, "rank": rank,
                        "chosen": rank == 0 and not cand.rank_reason.startswith("excluded"),
                        "rank_reason": cand.rank_reason, "score": cand.score,
                        "t_open": med("t_open"), "t_slice": med("t_slice"), "t_m0": med("t_m0"),
                        "t_m0_wall": med("t_m0_wall"), "t_m0_max": worst("t_m0_wall"),
                        "cell_seconds": round(time.monotonic() - cell_t0, 1),
                        "warmup": {k: warmup[k] for k in ("t_open", "t_slice", "t_m0", "t_m0_wall", "error")},
                        "samples": [{k: s[k] for k in ("t_open", "t_slice", "t_m0", "t_m0_wall")} for s in samples],
                        "failed": failed,
                        "error": error, "repeats": len(samples),
                    })
                    c.say(f"    {cand.node}: open {rows[-1]['t_open']} slice {rows[-1]['t_slice']} "
                          f"m0 {rows[-1]['t_m0']} (worst {rows[-1]['t_m0_max']}, warm-up {warmup['t_m0_wall']}, "
                          f"cell {rows[-1]['cell_seconds']} s)")
    finally:
        # Whatever happened, what was measured is kept, and the testbed is
        # left on its default policy even if the writing failed.
        try:
            out = c.write_results("e2_placement", rows, {"repeats": args.repeats, "policies": args.policies,
                                                          "warmup_runs": 1})
            c.say("written", out)
        finally:
            c.restart_skava_with_policy("resource_aware")


if __name__ == "__main__":
    main()
