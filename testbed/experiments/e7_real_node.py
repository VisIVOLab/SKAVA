# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""E7: the full chain on a real node, recorded.

What the desktop does, step by step, against a SKAVA catalogue and one node
running the VisIVO backend next to its data, each step timed and its answer
kept: the ADQL query that finds the dataset, the DataLink resolution (the
node chosen, the policy and its reason, the node's measured state), the open
in place on that node, the first channel slice, a moment-0 map as a SODA job
on the node, and the product opened where it was made. The node's own status
document is recorded before and after. Nothing is downloaded.

    TESTBED_SKAVA_URL=http://localhost:8000 TESTBED_BACKEND_TOKEN=<node token> \\
        python -m experiments.e7_real_node --node PLEIADI-GPU --backend http://localhost:18900 \\
            --collection inaf-pleiadi --name e7_pleiadi

``--backend`` is the node's backend as this client reaches it (a tunnel is
fine); the catalogue may know it by another address. Writes
``results/<name>.json`` (and ``.csv``) with the run's metadata.
"""
from __future__ import annotations

import argparse
import sys
from urllib.parse import quote

from . import common as c


def adql(query: str) -> dict:
    return c.http("GET", f"{c.SKAVA_URL}/tap/sync?LANG=ADQL&REQUEST=doQuery&RESPONSEFORMAT=json"
                         f"&QUERY={quote(query)}")


def node_status(backend: str) -> dict:
    status = c.http("GET", f"{backend}/v1/node/status", headers=c.backend_headers())
    keep = ("node_code", "version", "cpu", "memory", "gpu", "workers", "tasks", "capabilities")
    return {k: status.get(k) for k in keep if k in status}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--node", required=True, help="the node's code in the catalogue")
    ap.add_argument("--backend", required=True, help="the node's backend as this client reaches it")
    ap.add_argument("--collection", help="ObsCore obs_collection to search")
    ap.add_argument("--obs-id", help="the dataset, instead of the first one the query finds")
    ap.add_argument("--name", default="e7_real_node", help="result file name")
    ap.add_argument("--moment-timeout", type=float, default=1800.0)
    args = ap.parse_args()
    backend = args.backend.rstrip("/")

    rows: list[dict] = []

    def step(name: str, fn, **extra):
        try:
            seconds, out = c.timed(fn)
        except Exception as exc:  # noqa: BLE001 - every step is recorded, ok or not
            rows.append({"step": name, "ok": False, "seconds": None, "error": str(exc)[:500], **extra})
            c.say(f"FAIL {name}: {exc}")
            return None
        rows.append({"step": name, "ok": True, "seconds": round(seconds, 3), **extra})
        c.say(f"ok   {name} ({seconds:.3f} s)")
        return out

    meta: dict = {"node": args.node, "backend": backend, "skava": c.SKAVA_URL}
    meta["node_status_before"] = step("node status (before)", lambda: node_status(backend))

    def literal(value: str) -> str:
        # An ADQL string literal: an embedded apostrophe is doubled.
        return "'" + value.replace("'", "''") + "'"

    where = []
    if args.obs_id:
        where.append(f"obs_id = {literal(args.obs_id)}")
    if args.collection:
        where.append(f"obs_collection = {literal(args.collection)}")
    query = "SELECT TOP 10 obs_id, access_url, dataproduct_type, s_ra, s_dec FROM ivoa.obscore"
    if where:
        query += " WHERE " + " AND ".join(where)
    found = step("ADQL query on the catalogue", lambda: adql(query), query=query)
    if not found or not found.get("results"):
        rows.append({"step": "dataset found", "ok": False, "error": "the query found no dataset"})
        c.write_results(args.name, rows, meta)
        return 1
    obs_id = args.obs_id or found["results"][0]["metadata"]["obs_id"]
    meta["obs_id"] = obs_id
    meta["query_rows"] = len(found["results"])

    datalink = step("DataLink resolution", lambda: c.skava_datalink(obs_id))
    if not datalink:
        c.write_results(args.name, rows, meta)
        return 1
    routing = datalink["routing"]
    meta["routing"] = {
        "policy": routing.get("policy"),
        "best_node": routing.get("best_node"),
        "replicas": [{k: r.get(k) for k in ("code", "rank_reason", "score", "telemetry_age_s")}
                     for r in routing.get("replicas", [])],
        "excluded": routing.get("excluded"),
        "content_length": (datalink.get("primary_access") or {}).get("content_length"),
    }
    cands = c.candidates(datalink, {args.node: {"url": backend}})
    if not cands:
        rows.append({"step": "routed to the node", "ok": False,
                     "error": f"the DataLink names no visivo-backend for {args.node}"})
        c.write_results(args.name, rows, meta)
        return 1
    cand = cands[0]
    rows.append({"step": "routed to the node", "ok": routing.get("best_node") == args.node,
                 "node": cand.node, "reason": cand.rank_reason})

    opened = step("open in place on the node", lambda: c.open_on_node(backend, obs_id, cand.access_url),
                  access_url=cand.access_url)
    if opened:
        meta["opened"] = {"dataset_id": opened.dataset_id, "kind": opened.kind, "shape": list(opened.shape)}
        if opened.kind == "cube":
            step("first channel slice", lambda: c.first_slice(opened))
            job = step("moment-0 map as a SODA job on the node",
                       lambda: c.soda_job(backend, {"ID": cand.access_url, "OPERATION": "MOMENT", "MOMENT": "0"},
                                          timeout=args.moment_timeout))
            if job:
                rows[-1]["job_seconds"] = c.job_duration(job)
                rows[-1]["product"] = job.get("output_path")
                product = job.get("output_path")
                if product:
                    step("product opened where it was made",
                         lambda: c.look_at(backend, c.open_path_on_node(backend, product)))
        else:
            step("image preview", lambda: c.look_at(backend, {"dataset_id": opened.dataset_id,
                                                              "session_id": opened.session_id,
                                                              "kind": opened.kind}))
    meta["node_status_after"] = step("node status (after)", lambda: node_status(backend))

    path = c.write_results(args.name, rows, meta)
    failed = [r["step"] for r in rows if not r.get("ok")]
    c.say(f"wrote {path}; " + ("all steps ok" if not failed else f"failed: {failed}"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
