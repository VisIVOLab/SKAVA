# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""E4: bytes moved, measured on the node's link.

For each dataset, what crosses the data node's network interface (the
kernel's own counters, read inside the container) when a client:

* opens it in place and takes the first look (open, a downsampled preview,
  one channel slice);
* cuts a region out as a SODA job and opens the product in place;
* computes a moment-0 map as a SODA job and opens the product in place;
* runs the source finder through the Computing Broker, reads the catalogue
  it produced and opens the mask in place;
* downloads the file (a plain HTTP server inside the node, a client
  container on the testbed network pulling it; measured last, so the pull
  does not warm the node's cache for the operations above).

The counters include everything on the link, SKAVA's probe among it: an
idle interval is measured first and reported as the baseline rate. A row
whose product could not be opened in place (a node whose backend refuses
its own workspace) is kept, marked ``complete = False``.

Usage: ``python -m experiments.e4_bytes [--datasets tb-cube-s ...]``
"""
from __future__ import annotations

import argparse
import time
from urllib.parse import quote

from . import common as c

BIG = c.NODES["BIG"]


def counted(container: str, fn):
    """Run ``fn`` and return (seconds, rx bytes, tx bytes, result) on the
    container's link; the bytes are None when the two readings do not
    belong to one container lifetime."""
    before = c.net_snapshot(container)
    t0 = time.perf_counter()
    result = fn()
    seconds = time.perf_counter() - t0
    delta = c.net_delta(before, c.net_snapshot(container))
    rx, tx = delta if delta else (None, None)
    return seconds, rx, tx, result


def open_and_look(backend: str, path: str, errors: list[str]) -> bool:
    """Open a product where it was made and look at it; False (recorded) when
    the backend refuses the path."""
    try:
        c.look_at(backend, c.open_path_on_node(backend, path))
        return True
    except c.HttpFailure as exc:
        errors.append(f"{backend} {path}: {exc}")
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datasets", nargs="+", default=c.DATASETS)
    ap.add_argument("--baseline-seconds", type=float, default=20.0)
    args = ap.parse_args()

    rows: list[dict] = []
    open_errors: list[str] = []
    # The link's idle traffic (SKAVA's probe, the broker's status reads).
    seconds, rx, tx, _ = counted(BIG["container"], lambda: time.sleep(args.baseline_seconds))
    if rx is None:            # the node restarted meanwhile: once more, then it is unknown
        seconds, rx, tx, _ = counted(BIG["container"], lambda: time.sleep(args.baseline_seconds))
    if rx is None:
        baseline = {"rx_per_s": None, "tx_per_s": None}
        c.say("baseline: unknown (the node's counters did not hold still)")
    else:
        baseline = {"rx_per_s": rx / seconds, "tx_per_s": tx / seconds}
        c.say(f"baseline: {baseline['rx_per_s']:.0f} B/s in, {baseline['tx_per_s']:.0f} B/s out")

    try:
        for obs_id in args.datasets:
            file_bytes = c.dataset_bytes(obs_id)
            datalink = c.skava_datalink(obs_id)
            replica = next((r for r in datalink["routing"]["replicas"] if r["code"] == "BIG"), None)
            if replica is None:
                c.say(f"{obs_id}: no replica on BIG, skipped")
                continue
            access_url = replica["access_endpoint"]
            ra, dec = 150.0, -30.0           # the synthetic field's centre (make_data.py)
            width = {"px": 0}                # the cube's width, read when it is opened

            def add(operation: str, seconds: float, rx: int | None, tx: int | None, node: str = "BIG",
                    product: str = "", complete: bool = True, extra: dict | None = None):
                size = c.file_size_in(c.NODES[node]["container"], product) if product and node in c.NODES else 0
                rows.append({"dataset": obs_id, "file_bytes": file_bytes, "operation": operation, "node": node,
                             "seconds": round(seconds, 3), "bytes_rx": rx, "bytes_tx": tx,
                             "product_bytes": size, "complete": complete, **(extra or {})})
                shown = f"{tx:,} B out, {rx:,} B in" if tx is not None and rx is not None else "bytes unknown"
                c.say(f"  {obs_id} {operation} on {node}: {seconds:.2f} s, {shown}"
                      + ("" if complete else " (incomplete)"))

            # Open in place and look: open, a downsampled preview, one channel.
            def open_and_look_cube():
                opened = c.open_on_node(BIG["url"], obs_id, access_url)
                width["px"] = int(opened.shape[0] or 0)
                c.cube_preview(opened, downsample=4)
                c.first_slice(opened)
                return opened
            seconds, rx, tx, _ = counted(BIG["container"], open_and_look_cube)
            add("open+preview", seconds, rx, tx, complete=rx is not None)

            # A cutout as a SODA job, opened where it was made: a circle of an
            # eighth of the field (4 arcsec pixels, make_data.py), so the
            # region is the same fraction of every cube.
            if not width["px"]:
                raise RuntimeError(f"{obs_id}: the open did not say how wide the cube is")
            radius = 4.0 / 3600 * width["px"] / 8
            def cutout():
                job = c.soda_job(BIG["url"], {"ID": access_url, "POS": f"CIRCLE {ra} {dec} {radius:.6f}"})
                return job, open_and_look(BIG["url"], job["output_path"], open_errors)
            seconds, rx, tx, (job, opened) = counted(BIG["container"], cutout)
            add("cutout+open", seconds, rx, tx, product=job["output_path"], complete=opened and rx is not None)

            # A moment-0 map as a SODA job, opened where it was made.
            def moment():
                job = c.soda_job(BIG["url"], {"ID": access_url, "OPERATION": "MOMENT", "MOMENT": "0"})
                return job, open_and_look(BIG["url"], job["output_path"], open_errors)
            seconds, rx, tx, (job, opened) = counted(BIG["container"], moment)
            add("moment0+open", seconds, rx, tx, product=job["output_path"], complete=opened and rx is not None)

            # The source finder through the broker: one submission, the
            # counters of every node read before and after, and the bytes
            # attributed to the node the broker placed the job on, where the
            # catalogue is then read and the mask opened.
            before = {code: c.net_snapshot(n["container"]) for code, n in c.NODES.items()
                      if c.container_running(n["container"])}
            t0 = time.perf_counter()
            job = c.broker_job(obs_id, "sofia2", {"scfind.threshold": 5.0})
            placement = job.get("placement") or {}
            result = job.get("result") or {}
            node = placement.get("node") or result.get("node") or ""
            complete = job["status"] == "COMPLETE" and node in c.NODES and bool(result.get("catalog_path"))
            if complete:
                try:
                    c.catalogue_rows(c.NODES[node]["url"], result["catalog_path"])
                except c.HttpFailure as exc:
                    open_errors.append(f"{node} {result['catalog_path']}: {exc}")
                    complete = False
                complete = open_and_look(c.NODES[node]["url"], result["mask_path"], open_errors) and complete
            seconds = time.perf_counter() - t0
            after = {code: c.net_snapshot(n["container"]) for code, n in c.NODES.items()
                     if c.container_running(n["container"])}
            delta = c.net_delta(before.get(node), after.get(node))
            if delta:
                rx, tx = delta
            else:
                # No counter on both sides of one container lifetime (the node
                # was not running, restarted, or is not one of ours): the
                # bytes are unknown, not zero.
                rx = tx = None
                complete = False
            if job["status"] != "COMPLETE":
                c.say(f"  {obs_id} finder: broker job {job['status']} on {node or '?'}: {job.get('error')}")
            add("finder+catalogue", seconds, rx, tx, node=node if node in c.NODES else "BIG",
                product=result.get("catalog_path", ""), complete=complete,
                extra={"n_sources": result.get("n_sources"), "placed_on": node,
                       "rank_reason": placement.get("rank_reason", ""),
                       "error": "" if job["status"] == "COMPLETE" else str(job.get("error"))[:200]})

            # Download: the file itself, pulled by a client on the network, last.
            def download():
                # The URL goes in as a positional parameter, not into the script's text.
                url = f"http://{BIG['host']}:{c.FILE_SERVER_PORT}/cubes/{quote(obs_id)}.fits"
                proc = c.run_client(f"testbed-e4-client-{obs_id}", [
                    "sh", "-c", "curl -sS --fail -o /dev/null -w '%{time_total} %{size_download}' \"$1\"", "sh", url])
                if proc.returncode != 0:
                    raise RuntimeError(f"download failed: {proc.stderr.strip()[:200]}")
                t_curl, size = proc.stdout.split()
                if int(size) != file_bytes:
                    raise RuntimeError(f"download size {size} differs from the file's {file_bytes}")
                return float(t_curl), int(size)
            token = c.start_file_server(BIG["container"])
            try:
                seconds, rx, tx, (t_curl, size) = counted(BIG["container"], download)
            finally:
                c.stop_file_server(BIG["container"], token)
            add("download", seconds, rx, tx, complete=rx is not None,
                extra={"curl_seconds": round(t_curl, 3), "curl_bytes": size})
    finally:
        out = c.write_results("e4_bytes", rows, {"baseline": baseline, "baseline_seconds": args.baseline_seconds,
                                                  "product_open_errors": open_errors})
        if open_errors:
            c.say(f"{len(open_errors)} product(s) could not be opened in place; see the results' metadata")
        c.say("written", out)


if __name__ == "__main__":
    main()
