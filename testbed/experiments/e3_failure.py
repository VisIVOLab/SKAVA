# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""E3: a node dies in the middle of a session.

The dataset is opened on the node SKAVA ranked first; that node's container
is then killed. Two clocks start at the kill, and run at the same time: the
client's, which (like the desktop) retries the open on the next node of
SKAVA's ranking as soon as the first refuses, and the catalogue's, which
notices the node through its probe and stops ranking it. Both are measured,
over several trials, together with how long SKAVA takes to rank the node
again once its backend is back.

Usage: ``python -m experiments.e3_failure [--trials 5] [--dataset tb-cube-l]``
"""
from __future__ import annotations

import argparse
import threading
import time

from . import common as c


def ranked(obs_id: str, timeout: float = 10.0) -> list[str]:
    return [r["code"] for r in c.skava_datalink(obs_id, timeout=timeout)["routing"]["replicas"]]


def watch_detection(obs_id: str, victim: str, t_kill: float, deadline: float, stop: threading.Event,
                    out: dict) -> None:
    """The catalogue's clock: when its ranking stops naming the dead node."""
    while not stop.is_set() and time.monotonic() < deadline:
        try:
            gone = victim not in ranked(obs_id, timeout=min(10.0, max(1.0, deadline - time.monotonic())))
        except Exception:  # noqa: BLE001 — the catalogue itself is not under test
            gone = False
        # An answer that arrived after the window closed (or after the node
        # was told to come back) is not a detection.
        if gone and not stop.is_set() and time.monotonic() < deadline:
            out["t_skava_detect"] = round(time.monotonic() - t_kill, 3)
            return
        stop.wait(0.5)


def end_watcher(watcher: threading.Thread | None, stop: threading.Event, grace: float,
                patience: float = 60.0) -> None:
    """Stop the watcher and wait for it to end, a bounded wait: a timed join
    proves nothing by itself, so the thread is checked, but a socket
    timeout bounds a request's silence, not its length, and an answer that
    trickles could hold the thread longer. After ``patience`` the trial goes
    on without it: an answer that arrives after ``stop`` is set is not taken
    for a detection (the watcher checks before it records), so the node may
    come back."""
    if watcher is None:
        return
    watcher.join(timeout=grace)
    stop.set()
    watcher.join(timeout=patience)
    if watcher.is_alive():
        c.say("  the detection watcher is still waiting for an answer; going on without it")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--dataset", default="tb-cube-l")
    ap.add_argument("--detect-timeout", type=float, default=120.0)
    args = ap.parse_args()

    if c.current_policy() != "resource_aware":
        c.restart_skava_with_policy("resource_aware")
        time.sleep(15)
    rows: list[dict] = []
    victim = ""
    watcher: threading.Thread | None = None
    stop = threading.Event()
    try:
        for trial in range(1, args.trials + 1):
            # Everything up and ranked before the trial starts.
            for code, node in c.NODES.items():
                if not c.container_running(node["container"]):
                    c.docker("start", node["container"])
                    c.wait_backend(node["url"])
            deadline = time.monotonic() + args.detect_timeout
            cands = c.candidates(c.skava_datalink(args.dataset))
            while len(cands) < 2 and time.monotonic() < deadline:
                time.sleep(1)
                cands = c.candidates(c.skava_datalink(args.dataset))
            if len(cands) < 2:
                raise RuntimeError(f"{args.dataset}: fewer than two candidates ({[x.node for x in cands]}); "
                                   "nothing to fall back on")
            first = cands[0]
            victim = first.node
            opened = c.open_on_node(first.backend, args.dataset, first.access_url)
            c.first_slice(opened)
            c.say(f"trial {trial}: session on {first.node}; killing it")
            row = {"trial": trial, "victim": first.node, "fallback_node": "", "t_client_fallback": None,
                   "t_skava_detect": None, "t_skava_recover": None, "attempts": 0, "success": False, "error": ""}

            c.docker("kill", c.NODES[first.node]["container"])
            t_kill = time.monotonic()
            stop = threading.Event()
            watcher = threading.Thread(target=watch_detection, daemon=True,
                                       args=(args.dataset, first.node, t_kill, t_kill + args.detect_timeout, stop, row))
            watcher.start()
            # The client's clock: the next operation fails, the desktop moves on
            # to the next candidate of the ranking it already holds (no new
            # DataLink needed), and the session resumes there.
            for attempt, cand in enumerate(cands, start=1):
                row["attempts"] = attempt
                try:
                    reopened = c.open_on_node(cand.backend, args.dataset, cand.access_url)
                    c.first_slice(reopened)
                    row["fallback_node"] = cand.node
                    row["t_client_fallback"] = round(time.monotonic() - t_kill, 3)
                    row["success"] = True
                    break
                except Exception as exc:  # noqa: BLE001
                    row["error"] = f"{cand.node}: {str(exc)[:120]}"
                    continue
            end_watcher(watcher, stop, grace=args.detect_timeout + 15)
            watcher = None
            c.say(f"  fallback {row['fallback_node']} after {row['t_client_fallback']} s "
                  f"(attempts {row['attempts']}); SKAVA noticed after {row['t_skava_detect']} s")
            # Back up, and ranked again: the clock starts when the backend answers.
            c.docker("start", c.NODES[first.node]["container"])
            c.wait_backend(c.NODES[first.node]["url"])
            t_back = time.monotonic()
            deadline = time.monotonic() + args.detect_timeout
            while time.monotonic() < deadline:
                if first.node in ranked(args.dataset):
                    row["t_skava_recover"] = round(time.monotonic() - t_back, 3)
                    break
                time.sleep(0.5)
            victim = ""
            c.say(f"  ranked again after {row['t_skava_recover']} s")
            rows.append(row)
    finally:
        # The watcher is ended before the victim is brought back, so it
        # cannot take the recovered node for a detection.
        end_watcher(watcher, stop, grace=0.0)
        if victim and not c.container_running(c.NODES[victim]["container"]):
            c.docker("start", c.NODES[victim]["container"], check=False)
        out = c.write_results("e3_failure", rows, {"trials": args.trials, "dataset": args.dataset})
        c.say("written", out)


if __name__ == "__main__":
    main()
