# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""What the experiments share: the testbed's addresses, a scripted client
that speaks the same APIs as the VisIVO desktop (SKAVA discovery and
DataLink, the node backends' open / slice / SODA job routes, the Computing
Broker's job API), the routing rule the desktop applies to a DataLink answer,
the containers' network counters, and the result files.

Standard library only, so any Python runs it: ``make experiments`` uses the
repository's virtualenv.
"""
from __future__ import annotations

import csv
import json
import os
import platform
import shlex
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
TESTBED = HERE.parent
RESULTS = TESTBED / "results"
COMPOSE = ["docker", "compose", "-f", str(TESTBED / "docker-compose.yml")]

SKAVA_URL = os.environ.get("TESTBED_SKAVA_URL", "http://localhost:18000")
# The second site (far and busy nodes, the IAM's tokens required) and the IAM.
SKAVA2_URL = os.environ.get("TESTBED_SKAVA2_URL", "http://localhost:18001")
SKAVA2_INTERNAL_URL = os.environ.get("TESTBED_SKAVA2_INTERNAL_URL", "http://skava-2:8000")
KEYCLOAK_URL = os.environ.get("TESTBED_KEYCLOAK_URL", "http://localhost:18300")
IAM_REALM = os.environ.get("TESTBED_IAM_REALM", "srcnet")
IAM_CLIENT = os.environ.get("TESTBED_IAM_CLIENT", "visivo")
IAM_USER = os.environ.get("TESTBED_IAM_USER", "astronomer")
IAM_PASSWORD = os.environ.get("TESTBED_IAM_PASSWORD", "testbed")
BROKER_URL = os.environ.get("TESTBED_BROKER_URL", "http://localhost:18200")
BACKEND_TOKEN = os.environ.get("TESTBED_BACKEND_TOKEN", "testbed-backend-token")
INTERNAL_API_KEY = os.environ.get("TESTBED_INTERNAL_API_KEY", "testbed-internal-api-key")
NETWORK = os.environ.get("TESTBED_NETWORK", "testbed_default")
CLIENT_IMAGE = os.environ.get("TESTBED_CLIENT_IMAGE", "skava-testbed-node")

# The nodes as the desktop would register them: SKAVA's code, the backend
# reachable from this host, the container, and the address SKAVA names.
NODES = {
    "BIG": {"url": "http://localhost:18101", "container": "testbed-node-big-1", "host": "node-big"},
    "SMALL": {"url": "http://localhost:18102", "container": "testbed-node-small-1", "host": "node-small"},
    "FAR": {"url": "http://localhost:18103", "container": "testbed-node-far-1", "host": "node-far"},
    "BUSY": {"url": "http://localhost:18104", "container": "testbed-node-busy-1", "host": "node-busy"},
}
DATASETS = ["tb-cube-s", "tb-cube-m", "tb-cube-l"]

# How often a job or task is asked where it is. The wall times of the
# experiments include this granularity; a job's own clock (job_duration) does not.
POLL_S = 0.1

# The host's wall clock against its monotonic clock since the start: a host
# that slept during a run (a laptop) stops the latter but not the former,
# nor the nodes' own job clocks, and a measurement that spans the sleep is
# wrong. The skew is written with every result file, and said out loud.
_T0_WALL, _T0_MONO = time.time(), time.monotonic()


def host_clock_skew_s() -> float:
    return round((time.time() - _T0_WALL) - (time.monotonic() - _T0_MONO), 1)


class HttpFailure(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status, self.body = status, body


def http(method: str, url: str, *, json_body: Any = None, form: dict | None = None,
         headers: dict | None = None, timeout: float = 120.0, raw: bool = False) -> Any:
    """One request; JSON in, JSON out (or ``(status, headers, body, final_url)`` with ``raw``)."""
    data = None
    hdrs = {"Accept": "application/json", **(headers or {})}
    if json_body is not None:
        data = json.dumps(json_body).encode()
        hdrs["Content-Type"] = "application/json"
    elif form is not None:
        data = urlencode(form).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    req = Request(url, data=data, method=method, headers=hdrs)
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            if raw:
                # urllib follows redirects: resp.url is where it ended up.
                return resp.status, dict(resp.headers), body, resp.url
            return json.loads(body) if body else {}
    except HTTPError as exc:
        body = exc.read().decode(errors="replace")
        if raw:
            return exc.code, dict(exc.headers), body.encode(), exc.url
        raise HttpFailure(exc.code, body) from exc
    except URLError as exc:
        raise HttpFailure(0, str(exc.reason)) from exc


# ── SKAVA ──────────────────────────────────────────────────────────────────

def skava_search(**params: Any) -> dict:
    query = urlencode({k: v for k, v in params.items() if v is not None})
    return http("GET", f"{SKAVA_URL}/discovery/search?{query}")


def skava_datalink(obs_id: str, timeout: float = 120.0) -> dict:
    return http("GET", f"{SKAVA_URL}/datalink/{obs_id}", timeout=timeout)


def iam_wellknown() -> str:
    return f"{KEYCLOAK_URL}/realms/{IAM_REALM}/.well-known/openid-configuration"


def iam_token() -> str:
    """An access token of the testbed's user, from the IAM's token endpoint
    (the public client's password grant: what a script does where the
    desktop opens the IAM's sign-in page)."""
    answer = http("POST", f"{KEYCLOAK_URL}/realms/{IAM_REALM}/protocol/openid-connect/token",
                  form={"grant_type": "password", "client_id": IAM_CLIENT, "username": IAM_USER,
                        "password": IAM_PASSWORD, "scope": "openid"}, timeout=30)
    return answer["access_token"]


def bearer(token: str | None) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


def federated_search(token: str | None = None, base: str = SKAVA_URL, **params: Any) -> dict:
    query = urlencode({k: v for k, v in params.items() if v is not None})
    return http("GET", f"{base}/federation/search?{query}", headers=bearer(token))


def skava_telemetry() -> dict:
    return http("GET", f"{SKAVA_URL}/internal/telemetry", headers={"X-Internal-API-Key": INTERNAL_API_KEY})


def skava_metrics() -> str:
    _, _, body, _ = http("GET", f"{SKAVA_URL}/metrics", raw=True)
    return body.decode(errors="replace")


# ── The desktop's routing rule ──────────────────────────────────────────────

@dataclass
class Candidate:
    node: str
    backend: str          # the backend as THIS client reaches it
    access_url: str
    rank_reason: str
    score: float | None


def candidates(datalink: dict, registry: dict[str, dict] = NODES) -> list[Candidate]:
    """The nodes a client can open the dataset on, in SKAVA's order: the
    visivo-backend descriptors matched against the registered backends by
    node code, each with the replica's own URL there (BackendRouting in the
    desktop)."""
    replicas = {r["code"]: r for r in datalink["routing"]["replicas"]}
    out: list[Candidate] = []
    for desc in datalink["service_descriptors"]:
        if desc["service_type"] != "visivo-backend" or not desc["enabled"]:
            continue
        code = desc["node_code"]
        if code not in registry or code not in replicas:
            continue
        rep = replicas[code]
        out.append(Candidate(code, registry[code]["url"], rep["access_endpoint"],
                             rep.get("rank_reason") or "", rep.get("score")))
    return out


# ── A node's VisIVO backend ────────────────────────────────────────────────

@dataclass
class Opened:
    backend: str
    dataset_id: str
    session_id: str
    kind: str
    shape: tuple[int, int, int]


def backend_headers(session_id: str | None = None) -> dict:
    h = {"X-Visivo-Token": BACKEND_TOKEN}
    if session_id:
        h["X-Visivo-Session"] = session_id
    return h


def open_on_node(backend: str, obs_id: str, access_url: str) -> Opened:
    r = http("POST", f"{backend}/v1/datasets/open_skava", json_body={"obs_id": obs_id, "access_url": access_url},
             headers=backend_headers())
    if not r.get("valid"):
        raise HttpFailure(200, r.get("error") or "open refused")
    return Opened(backend, r["dataset_id"], r.get("session_id", ""), r.get("kind", ""),
                  (r.get("width", 0), r.get("height", 0), r.get("depth", 0)))


def open_path_on_node(backend: str, path: str) -> dict:
    """The desktop opens a product where it was made: by path, on that backend."""
    r = http("POST", f"{backend}/v1/datasets/open", json_body={"path": path}, headers=backend_headers())
    if not r.get("valid"):
        raise HttpFailure(200, r.get("error") or "open refused")
    return r


def first_slice(opened: Opened, index: int | None = None) -> dict:
    """The desktop's first picture of a cube: one channel through /v1/cube/slice."""
    z = opened.shape[2] // 2 if index is None else index
    r = http("POST", f"{opened.backend}/v1/cube/slice", json_body={"dataset_id": opened.dataset_id, "axis": "z", "index": z},
             headers=backend_headers(opened.session_id))
    if not r.get("valid"):
        raise HttpFailure(200, r.get("error") or "slice refused")
    return r


def cube_preview(opened: Opened, downsample: int = 4) -> dict:
    r = http("POST", f"{opened.backend}/v1/cube/preview", json_body={"dataset_id": opened.dataset_id, "downsample": downsample},
             headers=backend_headers(opened.session_id))
    if not r.get("valid"):
        raise HttpFailure(200, r.get("error") or "preview refused")
    return r


def look_at(backend: str, opened: dict) -> None:
    """The first picture of an opened product: a slice of a cube, the image itself for a 2-D one."""
    session = opened.get("session_id")
    if opened.get("kind") == "cube" and opened.get("depth", 0) > 1:
        r = http("POST", f"{backend}/v1/cube/slice",
                 json_body={"dataset_id": opened["dataset_id"], "axis": "z", "index": opened["depth"] // 2},
                 headers=backend_headers(session))
    else:
        r = http("POST", f"{backend}/v1/image/preview", json_body={"dataset_id": opened["dataset_id"]},
                 headers=backend_headers(session))
    # The routes answer 200 with valid=False for a failure of their own.
    if not r.get("valid", True):
        raise HttpFailure(200, r.get("error") or "the picture was refused")


def catalogue_rows(backend: str, path: str, fmt: str = "votable", limit: int = 1000) -> dict:
    """The desktop's catalogue window: open the table on the node, then read
    its rows (the open answers with metadata only)."""
    opened = http("POST", f"{backend}/v1/catalogue/open", json_body={"path": path, "format": fmt},
                  headers=backend_headers())
    if not opened.get("valid") or not opened.get("dataset_id"):
        raise HttpFailure(200, opened.get("error") or "catalogue open refused")
    rows = http("POST", f"{backend}/v1/catalogue/query",
                json_body={"dataset_id": opened["dataset_id"], "limit": limit},
                headers=backend_headers(opened.get("session_id")))
    if not rows.get("valid", True):
        raise HttpFailure(200, rows.get("error") or "catalogue query refused")
    return rows


def job_duration(view: dict) -> float | None:
    """A UWS job's own duration, from the node's start and end times."""
    try:
        start = datetime.fromisoformat(view["start_time"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(view["end_time"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return (end - start).total_seconds()


def soda_job(backend: str, params: dict[str, str], poll_s: float = POLL_S, timeout: float = 3600.0) -> dict:
    """A SODA (UWS) job on the node, run to its end; the JSON view of the job
    (``output_path`` is the product on the node). A job that does not end in
    time is aborted on the node before the error is raised."""
    # The creation answers 303 to the job; urllib follows it, so what comes
    # back is the job's JSON view and the URL it lives at.
    status, headers, body, final_url = http("POST", f"{backend}/soda/async", form={**params, "PHASE": "RUN"},
                                            headers=backend_headers(), raw=True)
    if status == 303:
        job_url = headers.get("Location") or headers.get("location")
        if job_url.startswith("/"):
            job_url = backend + job_url
    elif status == 200 and b"job_id" in body:
        job_url = final_url
    else:
        raise HttpFailure(status, body.decode(errors="replace"))
    deadline = time.monotonic() + timeout
    ended = False
    try:
        while time.monotonic() < deadline:
            view = http("GET", job_url, headers=backend_headers())
            if view["phase"] in ("COMPLETED", "ERROR", "ABORTED"):
                ended = True
                if view["phase"] != "COMPLETED":
                    raise HttpFailure(200, f"job {view['phase']}: {view.get('error')}")
                return view
            time.sleep(poll_s)
        raise TimeoutError(f"job {job_url} did not end")
    finally:
        # Whatever cut the wait short (the deadline, a failed poll, an
        # interruption), a job still running is not left to load the node.
        if not ended:
            try:
                http("POST", job_url + "/phase", form={"PHASE": "ABORT"}, headers=backend_headers(), timeout=30)
            except Exception as exc:  # noqa: BLE001 — the original error is the one to report
                say(f"job {job_url} could not be aborted: {exc}")


def backend_task(backend: str, route: str, body: dict, session_id: str, poll_s: float = POLL_S,
                 timeout: float = 3600.0) -> dict:
    """A task of the node's backend (moment, source finder) run to its end;
    cancelled on the node if it does not end in time."""
    created = http("POST", f"{backend}{route}", json_body=body, headers=backend_headers(session_id))
    if not created.get("valid"):
        raise HttpFailure(200, created.get("error") or "task refused")
    task_id = created["task_id"]
    deadline = time.monotonic() + timeout
    ended = False
    try:
        while time.monotonic() < deadline:
            status = http("GET", f"{backend}/v1/tasks/{task_id}", headers=backend_headers(session_id))
            if status.get("status") in ("completed", "failed", "cancelled"):
                ended = True
                if status["status"] != "completed":
                    raise HttpFailure(200, f"task {status['status']}: {status.get('error')}")
                return status
            time.sleep(poll_s)
        raise TimeoutError(f"task {task_id} did not end")
    finally:
        if not ended:
            try:
                http("DELETE", f"{backend}/v1/tasks/{task_id}", headers=backend_headers(session_id), timeout=30)
            except Exception as exc:  # noqa: BLE001
                say(f"task {task_id} could not be cancelled: {exc}")


# ── The Computing Broker ───────────────────────────────────────────────────

def broker_job(did: str, finder: str, params: dict, poll_s: float = 0.2, timeout: float = 7200.0) -> dict:
    """A finder job through the broker, run to its end; cancelled on the
    broker if it does not end in time."""
    job = http("POST", f"{BROKER_URL}/v1/jobs", json_body={
        "image": "inaf:visivo-finders:1.0", "cmd": ["sourcefind"], "rucio_did": did,
        "requires_capability": [f"finder:{finder}"], "cpu": 2,
        # No memory figure: the broker sizes it from what the node states
        # for the finder and the dataset's size, as the desktop lets it.
        "parameters": {"finder": finder, "params": params}})
    deadline = time.monotonic() + timeout
    ended = False
    try:
        while time.monotonic() < deadline:
            view = http("GET", f"{BROKER_URL}/v1/jobs/{job['id']}")
            if view["status"] in ("COMPLETE", "FAILED", "CANCELLED"):
                ended = True
                return view
            time.sleep(poll_s)
        raise TimeoutError(f"broker job {job['id']} did not end")
    finally:
        if not ended:
            try:
                http("POST", f"{BROKER_URL}/v1/jobs/{job['id']}/cancel", json_body={}, timeout=30)
            except Exception as exc:  # noqa: BLE001
                say(f"broker job {job['id']} could not be cancelled: {exc}")


def broker_job_duration(job: dict) -> float | None:
    """The job's own duration on the broker's clock: from its start to its end."""
    try:
        start = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(job["ended_at"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return (end - start).total_seconds()


# ── Containers ─────────────────────────────────────────────────────────────

def compose(*args: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run([*COMPOSE, *args], check=check, capture_output=capture, text=True)


def docker(*args: str, check: bool = True) -> str:
    return subprocess.run(["docker", *args], check=check, capture_output=True, text=True).stdout


def net_bytes(container: str, iface: str = "eth0") -> tuple[int, int]:
    """(received, transmitted) bytes of the container's interface, from the
    kernel's own counters: what actually crossed the link."""
    text = docker("exec", container, "cat", "/proc/net/dev")
    for line in text.splitlines():
        if line.strip().startswith(iface + ":"):
            fields = line.split(":", 1)[1].split()
            return int(fields[0]), int(fields[8])
    raise RuntimeError(f"{container}: no interface {iface}")


def net_snapshot(container: str) -> dict:
    """The link's counters together with the container's start time: a
    delta between two snapshots is only a measurement when both come from
    the same container lifetime (the counters start again with it)."""
    def started_at() -> str:
        return docker("inspect", "-f", "{{.State.StartedAt}}", container).strip()

    # The lifetime is read on both sides of the counters: a restart in
    # between would label old counters with the new lifetime.
    for _ in range(3):
        before = started_at()
        rx, tx = net_bytes(container)
        if started_at() == before:
            return {"rx": rx, "tx": tx, "started": before}
    raise RuntimeError(f"{container}: restarting while its counters were read")


def net_delta(before: dict | None, after: dict | None) -> tuple[int, int] | None:
    """(received, transmitted) bytes between two snapshots, or None when
    they do not measure the same thing: one is missing, the container was
    restarted in between, or a counter went backwards."""
    if not before or not after or before["started"] != after["started"]:
        return None
    rx, tx = after["rx"] - before["rx"], after["tx"] - before["tx"]
    return (rx, tx) if rx >= 0 and tx >= 0 else None


def container_running(container: str) -> bool:
    return docker("inspect", "-f", "{{.State.Running}}", container, check=False).strip() == "true"


def file_size_in(container: str, path: str) -> int:
    out = docker("exec", container, "stat", "-c", "%s", path, check=False)
    return int(out) if out.strip().isdigit() else -1


FILE_SERVER_PORT = 8080
_PID_FILE = "/tmp/testbed-fileserver.pid"


def _file_server_answers(container: str) -> bool:
    code = docker("exec", container, "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                  f"http://127.0.0.1:{FILE_SERVER_PORT}/", check=False).strip()
    return code == "200"


def _port_taken(container: str) -> bool:
    """Whether anything listens on the file server's port, whatever it answers."""
    probe = (f"import socket, sys; s = socket.socket(); s.settimeout(2); "
             f"sys.exit(0 if s.connect_ex(('127.0.0.1', {FILE_SERVER_PORT})) == 0 else 1)")
    return subprocess.run(["docker", "exec", container, "python", "-c", probe],
                          capture_output=True, text=True).returncode == 0


def start_file_server(container: str, directory: str = "/data") -> str:
    """A plain HTTP server inside the node, serving its data directory, for
    the download case. The port must be free first (a listener already there
    is not ours to use or to stop); the process is started under a token of
    this invocation, which :func:`stop_file_server` needs to stop it, and
    it is checked to be alive and answering. The experiments run one at a
    time: two invocations racing for the port are not supported, and the
    second fails here."""
    import uuid  # noqa: PLC0415

    if _port_taken(container):
        raise RuntimeError(f"{container}: something already listens on {FILE_SERVER_PORT}")
    token = uuid.uuid4().hex
    docker("exec", "-d", container, "sh", "-c",
           f"python -m http.server {FILE_SERVER_PORT} --directory {shlex.quote(directory)} >/dev/null 2>&1 & "
           f"echo $! {token} > {_PID_FILE}")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = docker("exec", container, "sh", "-c",
                       f"read pid tok < {_PID_FILE} 2>/dev/null && [ \"$tok\" = {token} ] && "
                       f"kill -0 $pid 2>/dev/null && echo alive", check=False).strip()
        if state == "alive" and _file_server_answers(container):
            return token
        if state != "alive" and time.monotonic() > deadline - 13:
            break                        # the process died (or is not ours): no point waiting
        time.sleep(0.5)
    stop_file_server(container, token)
    raise RuntimeError(f"{container}: the file server did not come up")


def stop_file_server(container: str, token: str | None = None) -> None:
    """Stop the server started here: the PID in the file is killed only when
    the file carries this invocation's token (or any token, when none is
    given, for a cleanup that did not get to keep one) and the PID is still
    a python http.server (PIDs get reused)."""
    want = f'[ "$tok" = {token} ]' if token else "true"
    docker("exec", container, "sh", "-c",
           f"if read pid tok < {_PID_FILE} 2>/dev/null; then "
           f"if {want}; then grep -q http.server /proc/$pid/cmdline 2>/dev/null && kill $pid; rm -f {_PID_FILE}; fi; fi",
           check=False)


def run_client(name: str, command: list[str], *, cpus: str | None = None, memory: str | None = None,
               timeout: float = 7200.0) -> subprocess.CompletedProcess:
    """A throw-away client container on the testbed network, under a name of
    its own (a random suffix) so that only it is removed whatever happens;
    with a memory limit, no swap beyond it (the nodes have none either)."""
    import re  # noqa: PLC0415
    import uuid  # noqa: PLC0415

    # Docker takes [a-zA-Z0-9][a-zA-Z0-9_.-]*: a dataset id can hold anything.
    stem = re.sub(r"[^A-Za-z0-9_.-]", "-", name).lstrip("_.-") or "client"
    name = f"{stem}-{uuid.uuid4().hex[:8]}"
    args = ["docker", "run", "--rm", "--name", name, "--network", NETWORK]
    if cpus:
        args += ["--cpus", cpus]
    if memory:
        args += ["--memory", memory, "--memory-swap", memory]
    try:
        return subprocess.run([*args, CLIENT_IMAGE, *command], capture_output=True, text=True, timeout=timeout)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def wait_backend(url: str, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            http("GET", f"{url}/v1/ping", timeout=3)
            return
        except Exception:  # noqa: BLE001
            time.sleep(1)
    raise TimeoutError(f"{url} did not come up")


def wait_skava(timeout: float = 120.0, base: str = SKAVA_URL) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            http("GET", f"{base}/availability", timeout=3)
            return
        except Exception:  # noqa: BLE001
            time.sleep(1)
    raise TimeoutError(f"{base} did not come up")


def restart_skava_with_policy(policy: str) -> None:
    """Recreate the SKAVA container with the given ranking policy (static /
    resource_aware); the catalogue and the nodes stay."""
    env = {**os.environ, "TESTBED_POLICY": policy}
    subprocess.run([*COMPOSE, "up", "-d", "--no-deps", "--force-recreate", "skava"], check=True, env=env,
                   capture_output=True, text=True)
    wait_skava()


def current_policy() -> str:
    return skava_datalink(DATASETS[0])["routing"].get("policy") or "unknown"


# ── Timing and results ─────────────────────────────────────────────────────

def timed(fn: Callable[[], Any]) -> tuple[float, Any]:
    t0 = time.perf_counter()
    out = fn()
    return time.perf_counter() - t0, out


def run_metadata(extra: dict | None = None) -> dict:
    def sha(repo: Path) -> str:
        try:
            return subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True,
                                  text=True, check=True).stdout.strip()
        except Exception:  # noqa: BLE001
            return "?"
    visivo = Path(os.environ.get("VISIVO_REPO", TESTBED.parent.parent / "VisIVO-next"))
    return {
        "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": platform.node(),
        "platform": platform.platform(),
        "skava_commit": sha(TESTBED.parent),
        "visivo_commit": sha(visivo),
        "profile": data_profile(),
        "poll_s": POLL_S,
        **(extra or {}),
    }


def data_profile() -> str:
    """Which data profile the testbed holds, from the large cube's size."""
    try:
        size = (TESTBED / "data" / "_store" / "tb-cube-l.fits").stat().st_size
    except OSError:
        return "unknown"
    return "paper" if size > 1 << 30 else "ci"


def dataset_bytes(obs_id: str) -> int:
    return (TESTBED / "data" / "_store" / f"{obs_id}.fits").stat().st_size


def write_results(name: str, rows: list[dict], meta: dict | None = None) -> Path:
    skew = host_clock_skew_s()
    if abs(skew) > 5:
        say(f"WARNING: the host's clocks disagree by {skew} s since the start (it slept, or its clock was "
            "adjusted): job clocks that spanned that time are wrong")
    meta = {**(meta or {}), "host_clock_skew_s": skew}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{name}.json").write_text(json.dumps({"meta": run_metadata(meta), "rows": rows}, indent=2))
    if rows:
        keys = list(dict.fromkeys(k for row in rows for k in row))
        with (RESULTS / f"{name}.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    return RESULTS / f"{name}.json"


def say(*parts: Any) -> None:
    print(time.strftime("%H:%M:%S"), *parts, flush=True)
