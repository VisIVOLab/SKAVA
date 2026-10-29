"""E6, federation: two catalogues, one search.

The testbed's second site (``skava-2``) catalogues the far and busy nodes and
requires the IAM's tokens; the first (``skava``) is open and lists the second
as a federated source, and the second lists the first. This script measures
what a federated search does and costs:

  merge      signed in, one search on the first site lists every cube once,
             the second site under ``also_at`` for the cubes it has too;
  auth       anonymous, the second site refuses the forwarded (missing) token
             and the search still answers from the first; asked directly, the
             second site challenges with ``ivoa_bearer`` naming the IAM;
  latency    the local search, the federated search and the second site asked
             directly with a token it validates, p50 and p95;
  degraded   the second site stopped: the federated search answers from the
             first within the federation timeout; the site back: listed again.

Usage: ``python -m experiments.e6_federation [--requests 200] [--trials 5]``
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time

from . import common as c
from .e1_prober import percentile

CHALLENGE = 'ivoa_bearer standard_id="ivo://ivoa.net/sso#BearerToken"'


def timed_ms(fn, n: int, warmup: int, good) -> dict:
    """``fn`` timed ``n`` times after ``warmup`` calls; a sample whose answer
    ``good`` rejects (a sibling in error, a result list that is not the
    expected one) is counted as failed and left out of the statistics."""
    for _ in range(warmup):
        fn()
    times, failed = [], 0
    for _ in range(n):
        t, answer = c.timed(fn)
        if good(answer):
            times.append(t * 1000)
        else:
            failed += 1
    stats = {"n": n, "failed": failed, "ok": failed == 0 and bool(times)}
    if times:
        stats.update(p50_ms=round(percentile(times, 50), 2), p95_ms=round(percentile(times, 95), 2),
                     mean_ms=round(statistics.mean(times), 2))
    return stats


def status_of(answer: dict, base: str) -> dict | None:
    return next((s for s in answer["sources"] if s["base_url"] == base), None)


def ids_of(answer: dict) -> list[str]:
    return [r["metadata"]["obs_id"] for r in answer["results"]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--requests", type=int, default=200)
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--trials", type=int, default=5, help="federated searches with the second site down")
    args = ap.parse_args()
    rows: list[dict] = []
    meta = {"requests": args.requests, "trials": args.trials, "second_site": c.SKAVA2_INTERNAL_URL,
            "iam": c.iam_wellknown()}
    try:
        run(args, rows)
    except Exception as exc:  # noqa: BLE001 — recorded with what was measured before it
        rows.append({"what": "error", "case": exc.__class__.__name__, "detail": str(exc)[:300], "ok": False})
        c.say("FAILED:", exc)
    finally:
        out = c.write_results("e6_federation", rows, meta)
    failed = [r for r in rows if not r.get("ok", True)]
    c.say("wrote", out, "all ok" if not failed else f"{len(failed)} CHECK(S) FAILED")
    return 1 if failed else 0


def run(args, rows: list[dict]) -> None:
    remote = c.SKAVA2_INTERNAL_URL

    c.wait_skava(base=c.SKAVA_URL)
    c.wait_skava(base=c.SKAVA2_URL)
    token = c.iam_token()
    c.say("signed in at the IAM")

    # ── merge ──────────────────────────────────────────────────────────────
    local = c.skava_search(limit=100)["results"]
    local_ids = [r["metadata"]["obs_id"] for r in local]
    second = c.http("GET", f"{c.SKAVA2_URL}/discovery/search?limit=100", headers=c.bearer(token))["results"]
    second_by_id = {r["metadata"]["obs_id"]: r for r in second}
    # The checks below are about what the two catalogues share: they mean
    # nothing on empty or disjoint catalogues (an unseeded testbed).
    missing = [d for d in c.DATASETS if d not in local_ids]
    if missing or not set(local_ids) & set(second_by_id):
        raise RuntimeError(f"the testbed is not seeded as expected: first site lacks {missing}, "
                           f"shared with the second site: {sorted(set(local_ids) & set(second_by_id))}")
    merged = c.federated_search(token, limit=100)
    ids = [r["metadata"]["obs_id"] for r in merged["results"]]
    by_id = {r["metadata"]["obs_id"]: r for r in merged["results"]}
    also_ok = True
    for obs_id, entry in by_id.items():
        here = [a for a in entry["also_at"] if a["source"] == remote]
        if obs_id in second_by_id:
            also_ok &= len(here) == 1 and here[0]["best_node"] == second_by_id[obs_id]["best_node"]
        else:
            also_ok &= here == []
    remote_status = status_of(merged, remote) or {}
    row = {"what": "merge", "case": "signed-in", "returned": merged["returned"],
           "unique": len(ids) == len(set(ids)), "local_first": ids[:len(local_ids)] == local_ids,
           "local_returned": len(local), "second_returned": len(second),
           "duplicates_merged": merged["duplicates_merged"],
           "expected_duplicates": len(set(local_ids) & set(second_by_id)),
           "second_status": remote_status.get("status"), "second_elapsed_ms": remote_status.get("elapsed_ms"),
           "also_at_ok": also_ok}
    row["ok"] = bool(row["unique"] and row["local_first"] and row["also_at_ok"]
                     and row["duplicates_merged"] == row["expected_duplicates"] and row["second_status"] == "ok"
                     and set(ids) == set(local_ids) | set(second_by_id))
    rows.append(row)
    c.say(f"merge: {merged['returned']} datasets, {merged['duplicates_merged']} merged, second site "
          f"{row['second_status']} in {row['second_elapsed_ms']} ms, ok={row['ok']}")

    # ── auth ───────────────────────────────────────────────────────────────
    anon = c.federated_search(None, limit=100)
    anon_status = status_of(anon, remote) or {}
    rows.append({"what": "auth", "case": "anonymous-federated", "returned": anon["returned"],
                 "second_status": anon_status.get("status"), "second_error": anon_status.get("error"),
                 "ok": anon_status.get("status") == "unauthorized" and anon["returned"] == len(local)})
    code, headers, _body, _url = c.http("GET", f"{c.SKAVA2_URL}/discovery/search?limit=1", raw=True)
    challenge = {k.lower(): v for k, v in headers.items()}.get("www-authenticate", "")
    rows.append({"what": "auth", "case": "anonymous-direct", "status": code,
                 "challenge_ivoa_bearer": CHALLENGE in challenge,
                 "challenge_names_the_iam": c.iam_wellknown() in challenge,
                 "ok": code == 401 and CHALLENGE in challenge and c.iam_wellknown() in challenge})
    code, _h, _b, _u = c.http("GET", f"{c.SKAVA2_URL}/discovery/search?limit=1", raw=True,
                              headers=c.bearer("not.a.token"))
    rows.append({"what": "auth", "case": "garbage-token-direct", "status": code, "ok": code == 401})
    code, _h, body, _u = c.http("GET", f"{c.SKAVA2_URL}/discovery/search?limit=100", raw=True,
                                headers=c.bearer(token))
    rows.append({"what": "auth", "case": "signed-in-direct", "status": code, "returned": len(second),
                 "ok": code == 200})
    c.say("auth:", ", ".join(f"{r['case']} ok={r['ok']}" for r in rows if r["what"] == "auth"))

    # ── latency ────────────────────────────────────────────────────────────
    expected_ids = ids  # the merged answer measured above
    cases = {
        "local": (lambda: c.skava_search(limit=100),
                  lambda a: ids_of(a) == local_ids),
        "federated": (lambda: c.federated_search(token, limit=100),
                      lambda a: ids_of(a) == expected_ids and (status_of(a, remote) or {}).get("status") == "ok"),
        "second-site-direct": (lambda: c.http("GET", f"{c.SKAVA2_URL}/discovery/search?limit=100",
                                              headers=c.bearer(token)),
                               lambda a: sorted(ids_of(a)) == sorted(second_by_id)),
    }
    for case, (fn, good) in cases.items():
        stats = timed_ms(fn, args.requests, args.warmup, good)
        rows.append({"what": "latency", "case": case, **stats})
        c.say(f"latency {case}: p50 {stats.get('p50_ms')} ms, p95 {stats.get('p95_ms')} ms, "
              f"{stats['failed']} failed")

    # ── degraded ───────────────────────────────────────────────────────────
    try:
        c.compose("stop", "skava-2")
        c.say("second site stopped")
        trials = []
        for _ in range(args.trials):
            t, answer = c.timed(lambda: c.federated_search(token, limit=100))
            trials.append((t * 1000, answer))
        statuses = [status_of(a, remote) or {} for _t, a in trials]
        rows.append({"what": "degraded", "case": "site-down", "trials": args.trials,
                     "second_status": ",".join(sorted({s.get("status") or "?" for s in statuses})),
                     "second_error": statuses[0].get("error"),
                     "request_ms_p50": round(percentile([t for t, _a in trials], 50), 2),
                     "request_ms_max": round(max(t for t, _a in trials), 2),
                     "returned": trials[0][1]["returned"],
                     "ok": all(a["returned"] == len(local) for _t, a in trials)
                           and all(s.get("status") in ("error", "timeout") for s in statuses)})
        c.say(f"site down: federated search answers {trials[0][1]['returned']} datasets in "
              f"{rows[-1]['request_ms_p50']} ms (second site {rows[-1]['second_status']})")
    finally:
        t0 = time.monotonic()
        c.compose("start", "skava-2")
        c.wait_skava(base=c.SKAVA2_URL)
        recovery = round(time.monotonic() - t0, 1)
    back = c.federated_search(token, limit=100)
    back_status = status_of(back, remote) or {}
    rows.append({"what": "degraded", "case": "site-back", "recovery_s": recovery,
                 "second_status": back_status.get("status"), "duplicates_merged": back["duplicates_merged"],
                 "ok": back_status.get("status") == "ok" and back["duplicates_merged"] == merged["duplicates_merged"]})
    c.say(f"site back after {recovery} s: second site {back_status.get('status')}")



if __name__ == "__main__":
    sys.exit(main())
