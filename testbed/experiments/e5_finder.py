# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""E5: source finding through the broker versus download-and-run.

For each dataset, the same SoFiA-2 run (the same parameters) is made two
ways: as a job of the Computing Broker, which asks SKAVA for the node and
runs the finder on that node's VisIVO backend, next to the data; and the
classical way, a client that pulls the file over the network and runs
SoFiA-2 itself, in a container with the big node's CPU and memory limits
(and, like the nodes, no swap). Two times are recorded for each: the whole
of it as the user waits for the catalogue (``t_total``, which for the broker
includes placement, the open, the submission and the polling), and the
finder's own run (``t_worker``: the broker's job clock, or SoFiA's run in the
client); plus the bytes that crossed the data node's link.

Usage: ``python -m experiments.e5_finder [--datasets ...] [--threshold 5.0]``
"""
from __future__ import annotations

import argparse
import time
from urllib.parse import quote

from . import common as c

BIG = c.NODES["BIG"]

# Run as: bash -c "$LOCAL_SCRIPT" bash <url> <expected bytes> <threshold>.
# The inputs come in as positional parameters, never spliced into the text.
LOCAL_SCRIPT = r"""
set -e
url=$1; expected=$2; threshold=$3
t0=$(date +%s.%N)
curl -sS --fail -o /tmp/cube.fits "$url"
t1=$(date +%s.%N)
size=$(stat -c %s /tmp/cube.fits)
[ "$size" = "$expected" ] || { echo "SIZE MISMATCH $size" >&2; exit 2; }
mkdir -p /tmp/out
cat > /tmp/sofia.par <<EOF
input.data = /tmp/cube.fits
output.directory = /tmp/out
output.filename = sofia_out
output.writeCatXML = true
output.writeMask = true
output.overwrite = true
scfind.threshold = $threshold
EOF
sofia2 /tmp/sofia.par > /tmp/sofia.log 2>&1 || { code=$?; echo "sofia2 exit $code" >&2; tail -n 20 /tmp/sofia.log >&2; exit $code; }
t2=$(date +%s.%N)
n=$(grep -c "<TR>" /tmp/out/sofia_out_cat.xml || true)
echo "RESULT $t0 $t1 $t2 $n"
"""


def all_counters() -> dict[str, dict]:
    return {code: c.net_snapshot(node["container"]) for code, node in c.NODES.items()
            if c.container_running(node["container"])}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datasets", nargs="+", default=c.DATASETS)
    ap.add_argument("--threshold", type=float, default=5.0)
    ap.add_argument("--cpus", default="4", help="the client container's CPUs (the big node's)")
    ap.add_argument("--memory", default="8g", help="the client container's memory (the big node's)")
    args = ap.parse_args()

    rows: list[dict] = []
    token = c.start_file_server(BIG["container"])
    try:
        for obs_id in args.datasets:
            file_bytes = c.dataset_bytes(obs_id)

            # Through the broker: placed by SKAVA, run on the node.
            before = all_counters()
            t0 = time.perf_counter()
            job = c.broker_job(obs_id, "sofia2", {"scfind.threshold": args.threshold})
            t_total = time.perf_counter() - t0
            after = all_counters()
            placement = job.get("placement") or {}
            result = job.get("result") or {}
            node = placement.get("node") or result.get("node") or ""
            delta = c.net_delta(before.get(node), after.get(node))
            rx, tx = delta if delta else (None, None)
            ok = job["status"] == "COMPLETE"
            rows.append({"dataset": obs_id, "file_bytes": file_bytes, "mode": "broker", "node": node,
                         "rank_reason": placement.get("rank_reason", ""),
                         "t_total": round(t_total, 3), "t_transfer": 0.0,
                         "t_worker": round(c.broker_job_duration(job) or 0.0, 3) if ok else None,
                         "bytes_rx": rx, "bytes_tx": tx,
                         "n_sources": result.get("n_sources") if ok else None,
                         "error": "" if ok else str(job.get("error"))[:200]})
            c.say(f"{obs_id} broker on {node}: {t_total:.1f} s (job {rows[-1]['t_worker']}), {tx} B out, "
                  f"{rows[-1]['n_sources']} sources")

            # Download and run locally: a client with the big node's limits.
            before_big = c.net_snapshot(BIG["container"])
            t0 = time.perf_counter()
            url = f"http://{BIG['host']}:{c.FILE_SERVER_PORT}/cubes/{quote(obs_id)}.fits"
            proc = c.run_client(f"testbed-e5-client-{obs_id}",
                                ["bash", "-c", LOCAL_SCRIPT, "bash", url, str(file_bytes), str(args.threshold)],
                                cpus=args.cpus, memory=args.memory)
            t_total = time.perf_counter() - t0
            delta = c.net_delta(before_big, c.net_snapshot(BIG["container"]))
            line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT")), "")
            row = {"dataset": obs_id, "file_bytes": file_bytes, "mode": "download+local", "node": "client",
                   "rank_reason": "", "t_total": round(t_total, 3), "t_transfer": None, "t_worker": None,
                   "bytes_rx": delta[0] if delta else None, "bytes_tx": delta[1] if delta else None,
                   "n_sources": None, "error": ""}
            if proc.returncode == 0 and line:
                _, a, b, d, n = line.split()
                row["t_transfer"] = round(float(b) - float(a), 3)
                row["t_worker"] = round(float(d) - float(b), 3)
                row["n_sources"] = int(n)
            else:
                # Never an empty error: a run that printed nothing before it
                # died (its output went to the log) is still a failed run.
                said = (proc.stderr or proc.stdout).strip()[-300:]
                row["error"] = f"exit {proc.returncode}" + (": " + said if said else "") \
                    + ("" if line or proc.returncode else "; no RESULT line")
            rows.append(row)
            c.say(f"{obs_id} download+local: {t_total:.1f} s (transfer {row['t_transfer']}, run {row['t_worker']}), "
                  f"{row['bytes_tx']} B out, {row['n_sources']} sources{' ERROR ' + row['error'] if row['error'] else ''}")
    finally:
        c.stop_file_server(BIG["container"], token)
        out = c.write_results("e5_finder", rows, {"threshold": args.threshold, "client_cpus": args.cpus,
                                                   "client_memory": args.memory, "client_memory_swap": args.memory})
        c.say("written", out)


if __name__ == "__main__":
    main()
