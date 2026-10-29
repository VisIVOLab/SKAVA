# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Conformance of the testbed's VO surfaces, read with pyvo.

What a generic VO client does, against the running testbed: the catalogue's
TAP (ObsCore query, VOSI tables and capabilities), its DataLink document for
a dataset (the ``#this`` rows, each followed from outside the node and
compared byte for byte with the catalogued file, and the node's SODA
services advertised as adhoc service descriptors), the node's SODA sync service (a cutout through the
descriptor pyvo found, and through ``SodaQuery`` directly), the node's UWS
job list (a moment-map job, its document parsed by pyvo's UWS reader), and
the node's VOSI documents. Runs inside the testbed network (``make
conformance``), where the nodes' names resolve; the node's own token goes in
the session, as the DataLink's ``link_auth`` column says it must.

The checks build on each other (the TAP query names the dataset, the
DataLink document names the node's services): a check whose prerequisite
failed is reported as skipped, not as failed. Every request is bounded by a
timeout. Exit status 1 when a check fails.
"""
from __future__ import annotations

import io
import os
import sys
import time
import traceback

import pyvo
import requests
from pyvo.dal.adhoc import DatalinkResults, SodaQuery
from pyvo.io import uws
from pyvo.io.vosi import parse_availability, parse_capabilities

SKAVA = os.environ.get("TESTBED_SKAVA_URL", "http://skava:8000").rstrip("/")
TOKEN = os.environ.get("TESTBED_BACKEND_TOKEN", "testbed-backend-token")
PREFERRED = os.environ.get("TESTBED_CONFORMANCE_DATASET", "tb-cube-s")

TIMEOUT = float(os.environ.get("TESTBED_CONFORMANCE_TIMEOUT", "60"))


class BoundedSession(requests.Session):
    """A session whose every request has a timeout, also those pyvo makes."""

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", TIMEOUT)
        return super().request(method, url, **kwargs)


session = BoundedSession()
session.headers["X-Visivo-Token"] = TOKEN   # the nodes' own token (link_auth); SKAVA ignores it

results: list[tuple[str, str, str]] = []    # name, "ok" | "FAIL" | "skip", detail
state: dict = {}


class Skipped(Exception):
    pass


def needs(*keys: str) -> None:
    missing = [k for k in keys if k not in state]
    if missing:
        raise Skipped(f"needs {', '.join(missing)} from an earlier check that failed")


def check(name: str):
    def run(fn):
        try:
            detail = fn() or ""
            results.append((name, "ok", str(detail)))
            print(f"  ok   {name}: {detail}")
        except Skipped as exc:
            results.append((name, "skip", str(exc)))
            print(f"  skip {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 — every check reports, none stops the rest
            results.append((name, "FAIL", f"{exc.__class__.__name__}: {exc}"))
            print(f"  FAIL {name}: {exc.__class__.__name__}: {exc}")
            traceback.print_exc(limit=3)
        return fn
    return run


def adhoc_services(dl: DatalinkResults) -> list[dict]:
    """The adhoc:service resources of the DataLink document: standardID,
    accessURL, the input parameters with their values, the resource ID."""
    out = []
    for resource in dl.votable.resources:
        if (resource.utype or "").lower() != "adhoc:service":
            continue
        params = {p.name: p.value for p in resource.params}
        inputs = {}
        for group in resource.groups:
            if (group.name or "") == "inputParams":
                inputs = {p.name: p.value for p in group.entries if hasattr(p, "name")}
        out.append({"id": resource.ID, "standardID": str(params.get("standardID", "")),
                    "accessURL": str(params.get("accessURL", "")), "inputs": inputs})
    return out


@check("TAP: ObsCore query")
def _tap_query():
    tap = pyvo.dal.TAPService(f"{SKAVA}/tap", session=session)
    rows = tap.search("SELECT TOP 20 obs_id, access_url, access_format, s_ra, s_dec, s_fov FROM ivoa.obscore")
    assert len(rows) >= 1, "no rows"
    table = rows.to_table()
    chosen = next((r for r in table if str(r["obs_id"]) == PREFERRED), table[0])
    state.update(obs_id=str(chosen["obs_id"]), ra=float(chosen["s_ra"]), dec=float(chosen["s_dec"]),
                 fov=float(chosen["s_fov"]), access_url=str(chosen["access_url"]))
    assert "datalink" in str(chosen["access_format"]), f"access_format {chosen['access_format']!r}"
    return f"{len(rows)} rows; {state['obs_id']} → {state['access_url']}"


@check("TAP: VOSI tables and capabilities")
def _tap_vosi():
    tap = pyvo.dal.TAPService(f"{SKAVA}/tap", session=session)
    names = [t.name for t in tap.tables]
    assert any(n.lower().endswith("obscore") for n in names), names
    caps = tap.capabilities
    assert any("TAP" in str(c.standardid) for c in caps), [str(c.standardid) for c in caps]
    return f"tables {names}; {len(caps)} capabilities"


@check("DataLink: document, #this row and the node's service descriptors")
def _datalink():
    needs("obs_id")
    obs_id = state["obs_id"]
    url = f"{SKAVA}/datalink/{obs_id}?RESPONSEFORMAT=votable"
    dl = DatalinkResults.from_result_url(url, session=session)
    this = [r for r in dl.bysemantics("#this")]
    assert this, "no #this row"
    assert this[0].access_url, "the #this row has no access URL"
    services = adhoc_services(dl)
    kinds = {s["standardID"] for s in services}
    sync = next((s for s in services if "SODA#sync" in s["standardID"]), None)
    asyn = next((s for s in services if "SODA#async" in s["standardID"]), None)
    assert sync is not None, f"no SODA sync descriptor among {sorted(kinds)}"
    assert asyn is not None, f"no SODA async descriptor among {sorted(kinds)}"
    assert sync["inputs"].get("ID"), f"the sync descriptor carries no ID: {sync['inputs']}"
    state.update(dl=dl, sync=sync, asyn=asyn)
    return f"{len(list(dl))} rows, services {sorted(kinds)}, node {sync['accessURL']}"


@check("DataLink #this: every copy retrieved from outside the node is the catalogued file")
def _this_rows():
    # What the {links} rows promise a generic client: following a "#this"
    # access_url gives the dataset itself. A file on a node's storage is
    # linked through the node's SODA with no constraint; this check follows
    # every such link from this container (not a node), as an HTTP client,
    # and compares status, type, size and SHA-256 with what the catalogue
    # declares (content_length, content_type, the record's checksum).
    needs("dl", "obs_id")
    import hashlib

    obs_id = state["obs_id"]
    catalogued = session.get(f"{SKAVA}/discovery/dataset/{obs_id}").json()
    checksum = ((catalogued.get("metadata") or {}).get("checksum") or "").removeprefix("sha256:")
    assert checksum, f"the catalogue states no checksum for {obs_id}"
    rows = [r for r in state["dl"].bysemantics("#this")]
    assert rows, "no #this row"
    # The node token goes only to the nodes' own backends (the #auxiliary rows
    # name them), never to a direct copy elsewhere, and no request follows a
    # redirect with it.
    from urllib.parse import urlsplit

    def origin(url: str) -> tuple[str, str]:
        parts = urlsplit(url)
        return parts.scheme, parts.netloc

    nodes = {origin(str(r.access_url)) for r in state["dl"].bysemantics("#auxiliary")}
    anonymous = BoundedSession()
    deadline = float(os.environ.get("TESTBED_CONFORMANCE_DOWNLOAD_S", "600"))
    seen = []
    for row in rows:
        url = str(row.access_url)
        assert not url.startswith("file:"), f"a #this access_url a client cannot follow: {url}"
        declared = int(row.content_length)
        client = session if origin(url) in nodes else anonymous
        digest, got = hashlib.sha256(), {"size": 0, "status": None, "media": "", "error": None}

        def fetch() -> None:
            # The whole exchange (connection, headers, body) in a daemon
            # thread, so the deadline holds at every step: a fetch past it is
            # abandoned (it ends with the script) and the check fails.
            try:
                with client.get(url, stream=True, allow_redirects=False) as resp:
                    got["status"] = resp.status_code
                    got["media"] = resp.headers.get("content-type", "").split(";")[0]
                    if resp.status_code != 200:
                        return
                    for chunk in resp.iter_content(1 << 20):
                        digest.update(chunk)
                        got["size"] += len(chunk)
                        if got["size"] > declared:
                            raise AssertionError(f"{url}: more than the {declared} bytes declared")
            except Exception as exc:  # noqa: BLE001 - reported below
                got["error"] = exc

        import threading

        fetcher = threading.Thread(target=fetch, daemon=True)
        fetcher.start()
        fetcher.join(deadline)
        assert not fetcher.is_alive(), f"{url}: not done in {deadline:g} s"
        if got["error"] is not None:
            raise got["error"]
        assert got["status"] == 200, f"{url}: HTTP {got['status']}"
        media, size = got["media"], got["size"]
        node = row["node_id"]
        assert media == str(row.content_type), f"{node}: served {media}, row says {row.content_type}"
        assert size == declared, f"{node}: {size} bytes, row says {declared}"
        assert digest.hexdigest() == checksum, f"{node}: SHA-256 differs from the catalogue's"
        seen.append(f"{node} {size} B")
    return f"{len(rows)} copies, each the catalogued file ({', '.join(seen)})"


@check("SODA sync: a cutout through the descriptor pyvo found (SodaQuery.from_resource)")
def _soda_descriptor():
    # The #cutout row names its service descriptor (service_def); pyvo builds
    # the SODA query from that descriptor's inputParams (the replica's ID) and
    # the row. The session carries the node's token: DatalinkRecord.processed()
    # would build the same query but without the session (pyvo 1.9), and the
    # node, which requires its token, answers 401 to it.
    needs("dl", "sync")
    dl = state["dl"]
    radius = max(state["fov"] / 8, 1e-3)
    rec = next(r for r in dl if "cutout" in str(r.semantics) or "proc" in str(r.semantics))
    assert rec.service_def, "the row names no service descriptor"
    resource = dl.get_adhocservice_by_id(rec.service_def)
    query = SodaQuery.from_resource([rec], resource, session=session)
    query.circle = (state["ra"], state["dec"], radius)
    assert query["ID"] == state["sync"]["inputs"]["ID"], f"ID {query.get('ID')!r} from the descriptor"
    head = query.execute_stream().read(2880)
    assert head.startswith(b"SIMPLE"), f"not a FITS: {head[:30]!r}"
    return f"FITS from {query.queryurl} via {rec.service_def} (CIRCLE r={radius:.4g} deg)"


@check("SODA sync: a cutout with SodaQuery on the node's service")
def _soda_direct():
    needs("sync")
    sync = state["sync"]
    radius = max(state["fov"] / 8, 1e-3)
    query = SodaQuery(sync["accessURL"], session=session)
    query["ID"] = sync["inputs"]["ID"]
    query.circle = (state["ra"], state["dec"], radius)
    head = query.execute_stream().read(2880)
    assert head.startswith(b"SIMPLE"), f"not a FITS: {head[:30]!r}"
    return f"FITS from {sync['accessURL']}"


@check("UWS: a moment-map job on the node, its documents read by pyvo")
def _uws():
    needs("asyn")
    asyn = state["asyn"]
    created = session.post(asyn["accessURL"], data={"ID": asyn["inputs"]["ID"], "OPERATION": "MOMENT",
                                                    "MOMENT": "0", "PHASE": "RUN"},
                           allow_redirects=False)
    assert created.status_code in (303, 200, 201), f"HTTP {created.status_code}: {created.text[:200]}"
    job_url = created.headers["Location"]
    try:
        job = uws.parse_job(io.BytesIO(session.get(job_url, headers={"Accept": "application/xml"}).content))
        assert job.phase in ("PENDING", "QUEUED", "EXECUTING", "COMPLETED"), job.phase
        deadline = time.monotonic() + 300
        phase = job.phase
        while time.monotonic() < deadline:
            phase = session.get(f"{job_url}/phase").text.strip()
            if phase in ("COMPLETED", "ERROR", "ABORTED"):
                break
            time.sleep(0.5)
        assert phase == "COMPLETED", f"job ended {phase}"
        job = uws.parse_job(io.BytesIO(session.get(job_url, headers={"Accept": "application/xml"}).content))
        assert job.phase == "COMPLETED" and len(job.results) >= 1, (job.phase, len(job.results))
        assert job.starttime is not None and job.endtime is not None, "no start/end time"
        product = session.get(job.results[0].href, stream=True)
        head = product.raw.read(2880)
        product.close()
        assert head.startswith(b"SIMPLE"), f"the result is not a FITS: {head[:30]!r}"
    finally:
        # Whatever happened, the job (and its product) is not left on the node.
        gone = session.delete(job_url, allow_redirects=False)
        assert gone.status_code in (303, 200, 204), f"DELETE {job_url}: HTTP {gone.status_code}"
    return f"{job_url} COMPLETED, {len(job.results)} result(s), {job.starttime} → {job.endtime}"


@check("VOSI on the node: SODA capabilities and availability")
def _node_vosi():
    needs("sync")
    base = state["sync"]["accessURL"].rsplit("/soda/", 1)[0]
    caps = parse_capabilities(io.BytesIO(session.get(f"{base}/soda/capabilities").content))
    ids = [str(c.standardid) for c in caps]
    assert any("SODA#sync" in i for i in ids) and any("SODA#async" in i for i in ids), ids
    avail = parse_availability(io.BytesIO(session.get(f"{base}/soda/availability").content))
    assert avail.available, "not available"
    return f"{len(ids)} capabilities, available"


def main() -> int:
    print(f"pyvo {pyvo.__version__} against {SKAVA}")
    failed = [name for name, outcome, _d in results if outcome == "FAIL"]
    skipped = [name for name, outcome, _d in results if outcome == "skip"]
    passed = len(results) - len(failed) - len(skipped)
    print(f"{passed}/{len(results)} checks passed" + (f"; failed: {failed}" if failed else "")
          + (f"; skipped: {skipped}" if skipped else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
