# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""A stand-in for the SRCNet Computing Broker: batch jobs placed next to the data.

The SRCNet architecture runs batch work through a Computing Broker: a client
submits a job (``POST /v1/jobs``: a software image, a command, the Rucio DID of
the input, where the output goes, the capabilities the site must have, the
resources), the broker chooses a site that passes its filters and runs the job
there, and the client follows it (``GET /v1/jobs/{id}``, a stream of events,
the logs, ``cancel``). This service has the same interface, so the client of
this testbed is written against it and not against something invented here,
and does the work in the only way the testbed can: it asks SKAVA where the
dataset is, picks the first ranked node whose backend has the requested
finder, and runs the finder as a task on that backend, next to the data.

What it is not: a scheduler. One job is one task on one node, now; there is
no queue, no container image is pulled, and the "image" and "cmd" fields are
recorded, not executed. It exists so the end-to-end chain (discover, place,
run next to the data, collect) can be exercised and measured.

Configuration (environment): ``BROKER_SKAVA_URL`` (the catalogue),
``BROKER_SKAVA_TOKEN`` (its bearer token, if it needs one),
``BROKER_BACKEND_TOKEN`` (the nodes' VisIVO token), ``BROKER_POLL_SECONDS``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("broker-mock")

VERSION = "0.1"
# The job's life, as the broker reports it.
PENDING, RUNNING, COMPLETE, FAILED, CANCELLED = "PENDING", "RUNNING", "COMPLETE", "FAILED", "CANCELLED"
TERMINAL = {COMPLETE, FAILED, CANCELLED}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


_MEMORY_UNITS = {"": 1, "k": 1 << 10, "m": 1 << 20, "g": 1 << 30, "t": 1 << 40}
_MEMORY_RE = re.compile(r"^(\d{1,15})(?:\.(\d{1,6}))?\s*([kmgt]?)$")
_MEMORY_MAX = 1 << 50         # a petabyte: beyond any node, so a typo rather than a need


def parse_memory(text: str) -> int:
    """A memory figure as batch systems write it ("4G", "512M", "8Gi",
    "1.5G", "1073741824") in whole bytes, more than zero; ValueError for
    anything else. Parsed exactly: no float on the way."""
    s = text.strip().lower()
    for suffix in ("b", "i"):      # "GB", "GiB", "Gi" all mean the binary unit here
        s = s.removesuffix(suffix)
    m = _MEMORY_RE.match(s)
    if not m:
        raise ValueError(f"memory {text!r} is not a figure like 4G, 512M or a number of bytes")
    whole, fraction, unit = m.group(1), m.group(2) or "", m.group(3)
    scale = 10 ** len(fraction)
    # A need is rounded up to the byte, never down.
    value = -(-int(whole + fraction) * _MEMORY_UNITS[unit] // scale)
    if value <= 0:
        raise ValueError(f"memory {text!r} is not more than zero bytes")
    if value > _MEMORY_MAX:
        raise ValueError(f"memory {text!r} is beyond any node")
    return value


def _figure(value: Any) -> float | None:
    """A finite, non-negative number from JSON, no larger than any memory
    figure could be, or None (booleans are not figures)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except OverflowError:
        return None
    return value if math.isfinite(value) and 0 <= value <= _MEMORY_MAX else None


def _gb(n: float) -> str:
    return f"{n / (1 << 30):.1f} GB" if n >= (1 << 30) else f"{n / (1 << 20):.0f} MB"


class JobRequest(BaseModel):
    """What a client submits; the field names are the broker's."""

    image: str = Field(description="software image, e.g. inaf:visivo-finders:1.0")
    cmd: list[str] = Field(default_factory=list)
    rucio_did: str = Field(description="the input dataset's identifier (its obs_id in SKAVA)")
    output: str | None = Field(default=None, description="where results go, e.g. dav://...")
    requires_capability: list[str] = Field(default_factory=list, description="e.g. finder:sofia2")
    cpu: int = 1
    # Memory the job needs ("4G", "512M"); left out, the broker sizes it from
    # what the node states for the finder and the dataset's size.
    memory: str | None = None
    gpu: int = 0
    # Job-specific inputs; for a finder job: finder (name) and params (its parameters).
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("memory")
    @classmethod
    def _memory_is_a_figure(cls, value: str | None) -> str | None:
        if value is not None:
            parse_memory(value)
        return value

    def memory_bytes(self) -> int | None:
        return parse_memory(self.memory) if self.memory else None

    def finder(self) -> str:
        if self.parameters.get("finder"):
            return str(self.parameters["finder"])
        for cap in self.requires_capability:
            if cap.startswith("finder:"):
                return cap.split(":", 1)[1]
        return "sofia2"


@dataclass
class Job:
    id: str
    request: JobRequest
    status: str = PENDING
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    ended_at: str | None = None
    placement: dict[str, Any] = field(default_factory=dict)
    backend: str | None = None
    session_id: str | None = None
    dataset_id: str | None = None
    task_id: str | None = None
    # The task-creation request in flight, kept so that a cancellation that
    # interrupts it can still learn the task's id and stop it on the node.
    submission: asyncio.Future | None = None
    # Whether the node's task has ended (then there is nothing to stop).
    task_ended: bool = False
    # The one cleanup a cancellation runs; later cancellations wait for it.
    cancellation: asyncio.Task | None = None
    # Set once the runner is stopping the task on the node, on any path: a
    # cancellation that arrives then waits for that instead of interrupting it.
    cleaning: bool = False
    result: dict[str, Any] | None = None
    error: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)
    runner: asyncio.Task | None = None

    def view(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "request": self.request.model_dump(),
            "placement": self.placement,
            "backend": self.backend,
            "task_id": self.task_id,
            "result": self.result,
            "error": self.error,
        }


class Settings:
    def __init__(self) -> None:
        self.skava_url = os.environ.get("BROKER_SKAVA_URL", "http://skava:8000").rstrip("/")
        self.skava_token = os.environ.get("BROKER_SKAVA_TOKEN") or None
        self.backend_token = os.environ.get("BROKER_BACKEND_TOKEN") or None
        self.poll_seconds = float(os.environ.get("BROKER_POLL_SECONDS", "1.0"))
        self.http_timeout = float(os.environ.get("BROKER_HTTP_TIMEOUT", "30"))
        self.timeout = httpx.Timeout(self.http_timeout)
        # Consecutive polling failures tolerated before the job is given up.
        self.poll_retries = int(os.environ.get("BROKER_POLL_RETRIES", "5"))


class Broker:
    """The jobs and the work behind them."""

    def __init__(self, settings: Settings, client_factory: Callable[[], httpx.AsyncClient] | None = None):
        self.settings = settings
        self.jobs: dict[str, Job] = {}
        self._client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=settings.timeout))

    # ── events and logs ─────────────────────────────────────────────────────
    async def _emit(self, job: Job, kind: str, **data: Any) -> None:
        async with job.changed:
            job.events.append({"seq": len(job.events) + 1, "time": _now(), "type": kind, **data})
            job.changed.notify_all()

    async def _set_status(self, job: Job, status: str, **extra: Any) -> None:
        job.status = status
        if status == RUNNING and job.started_at is None:
            job.started_at = _now()
        if status in TERMINAL:
            job.ended_at = _now()
        await self._emit(job, "status", status=status, **extra)

    async def _log(self, job: Job, line: str) -> None:
        job.logs.append(f"{_now()} {line}")
        await self._emit(job, "log", message=line)

    # ── placement ────────────────────────────────────────────────────────────
    @staticmethod
    def memory_need(job: Job, finder: str, status: dict[str, Any],
                    datalink: dict[str, Any]) -> tuple[int | None, str]:
        """The job's memory need in bytes and where the figure comes from:
        the request's own, or the node's statement for the finder (factor ×
        dataset bytes + floor) applied to the dataset's size in the
        catalogue. Without the size, the floor alone is the need (a lower
        bound); None with the reason when nothing is known. A statement
        that is not made of figures counts as no statement."""
        requested = job.request.memory_bytes()
        if requested is not None:
            return requested, "as requested"
        stated = ((status.get("capabilities") or {}).get("finder_memory") or {}).get(finder)
        if not isinstance(stated, dict):
            return None, f"the node does not state what {finder} needs"
        factor = _figure(stated.get("factor", 1.0))
        floor = _figure(stated.get("floor_bytes", 0))
        if factor is None or floor is None:
            return None, f"the node's statement for {finder} is not made of figures"
        size_kb = _figure((datalink.get("primary_access") or {}).get("access_estsize"))
        if not size_kb:
            return int(floor), f"{finder} needs at least {_gb(floor)}; the dataset's size is not in the catalogue"
        need = factor * size_kb * 1024 + floor      # each bounded: no overflow here
        if need > _MEMORY_MAX:
            return None, f"the node's statement for {finder} puts the need beyond any node"
        return int(need), f"{finder} needs {factor:g}x the {_gb(size_kb * 1024)} dataset"

    async def place(self, client: httpx.AsyncClient, job: Job) -> dict[str, Any]:
        """The node that runs the job: the first ranked replica whose backend
        has the finder and the memory the job needs.

        SKAVA's ranking orders the candidates (with its reasons); the broker
        applies the hard filters a batch system applies, a node that can run
        this software with the memory it needs (as requested, or as the node
        states for the finder and the dataset's size), and takes the first
        that passes. A node that reports no memory figure is not held back
        by one. Every candidate is reported with why it was taken or left.
        """
        headers = {"Authorization": f"Bearer {self.settings.skava_token}"} if self.settings.skava_token else {}
        resp = await client.get(f"{self.settings.skava_url}/datalink/{job.request.rucio_did}", headers=headers)
        if resp.status_code == 404:
            raise RuntimeError(f"dataset {job.request.rucio_did!r} is not in the catalogue")
        resp.raise_for_status()
        datalink = resp.json()
        backends = {d["node_code"]: d for d in datalink.get("service_descriptors", [])
                    if d.get("service_type") == "visivo-backend" and d.get("enabled") and d.get("endpoint")}
        finder = job.request.finder()
        candidates: list[dict[str, Any]] = []
        chosen = None
        for replica in datalink["routing"]["replicas"]:
            code = replica["code"]
            entry = {"node": code, "rank_reason": replica.get("rank_reason"), "score": replica.get("score")}
            backend = backends.get(code)
            if backend is None:
                entry["skipped"] = "no co-located backend"
            elif not str(replica.get("access_endpoint", "")).startswith("file://"):
                entry["skipped"] = "replica is not a local file on that node"
            else:
                try:
                    probe = await client.get(f"{backend['endpoint'].rstrip('/')}/v1/node/status",
                                             headers=self._token_header())
                    if probe.status_code in (401, 403):
                        raise PermissionError("the backend's status requires a token the broker does not hold")
                    probe.raise_for_status()
                    status = probe.json()
                    if not isinstance(status, dict):
                        raise ValueError("status is not a JSON object")
                    finders = (status.get("capabilities") or {}).get("finders") or []
                except PermissionError as exc:
                    entry["skipped"] = str(exc)
                except (httpx.HTTPError, ValueError) as exc:
                    entry["skipped"] = f"backend unreachable: {type(exc).__name__}"
                else:
                    if finder not in finders:
                        entry["skipped"] = f"finder {finder!r} not available (has: {', '.join(finders) or 'none'})"
                        candidates.append(entry)
                        continue
                    need, basis = self.memory_need(job, finder, status, datalink)
                    free = _figure((status.get("memory") or {}).get("available_bytes"))
                    free = int(free) if free is not None else None
                    entry["memory"] = {"need_bytes": need, "free_bytes": free, "basis": basis}
                    if need is not None and free is not None and need > free:
                        entry["skipped"] = f"not enough memory: needs {_gb(need)} ({basis}), {_gb(free)} free"
                    elif chosen is None:
                        chosen = {"node": code, "backend": backend["endpoint"].rstrip("/"),
                                  "access_url": replica["access_endpoint"],
                                  "requires_auth": bool(backend.get("requires_auth")),
                                  "rank_reason": replica.get("rank_reason"),
                                  "memory_need_bytes": need, "memory_basis": basis}
                        entry["chosen"] = True
                    else:
                        entry["skipped"] = "a better-ranked node can run it"
            candidates.append(entry)
        for excluded in datalink["routing"].get("excluded", []):
            candidates.append({"node": excluded["code"], "skipped": f"excluded by SKAVA: {excluded['reason']}"})
        placement = {"policy": datalink["routing"].get("policy"), "finder": finder, "candidates": candidates}
        if chosen is None:
            # The report of every candidate is the job's placement even when
            # it placed nothing: the verdicts stay readable, not only the error.
            job.placement = placement
            raise RuntimeError(f"no node can run {finder} on {job.request.rucio_did}: "
                               + "; ".join(f"{c['node']}: {c.get('skipped')}" for c in candidates))
        placement.update(chosen)
        return placement

    # ── execution ────────────────────────────────────────────────────────────
    def _token_header(self) -> dict[str, str]:
        return {"X-Visivo-Token": self.settings.backend_token} if self.settings.backend_token else {}

    def _backend_headers(self, job: Job) -> dict[str, str]:
        headers = self._token_header()
        if job.session_id:
            headers["X-Visivo-Session"] = job.session_id
        return headers

    async def run(self, job: Job) -> None:
        async with self._client_factory() as client:
            try:
                await self._log(job, f"placing {job.request.rucio_did} for finder {job.request.finder()}")
                job.placement = await self.place(client, job)
                job.backend = job.placement["backend"]
                await self._log(job, f"placed on {job.placement['node']} ({job.backend}): "
                                     f"{job.placement.get('rank_reason') or 'first eligible'}")
                await self._set_status(job, RUNNING, node=job.placement["node"])

                opened = await client.post(f"{job.backend}/v1/datasets/open_skava",
                                           json={"obs_id": job.request.rucio_did,
                                                 "access_url": job.placement["access_url"]},
                                           headers=self._backend_headers(job))
                opened.raise_for_status()
                body = opened.json()
                if not body.get("valid"):
                    raise RuntimeError(f"the node could not open the dataset: {body.get('error')}")
                job.session_id, job.dataset_id = body["session_id"], body["dataset_id"]
                await self._log(job, f"opened as {job.dataset_id} ({body.get('kind')}, "
                                     f"{body.get('width')}x{body.get('height')}x{body.get('depth')})")

                params = dict(job.request.parameters.get("params") or {})
                # Shielded: if the job is cancelled while the node is accepting
                # the task, the answer still arrives and names the task to stop.
                job.submission = asyncio.ensure_future(client.post(
                    f"{job.backend}/v1/tasks/sourcefind",
                    json={"dataset_id": job.dataset_id, "finder": job.request.finder(), "params": params},
                    headers=self._backend_headers(job)))
                created = await asyncio.shield(job.submission)
                job.task_id = self._task_id_of(created)
                await self._log(job, f"task {job.task_id} started on the node")

                last_progress = -1.0
                failures = 0
                while True:
                    await asyncio.sleep(self.settings.poll_seconds)
                    try:
                        polled = await client.get(f"{job.backend}/v1/tasks/{job.task_id}",
                                                  headers=self._backend_headers(job))
                        if polled.status_code == 404:
                            job.task_ended = True
                            raise RuntimeError(f"the node no longer knows task {job.task_id}")
                        polled.raise_for_status()
                        task = polled.json()
                        if not isinstance(task, dict) or "status" not in task:
                            raise ValueError("no status in the answer")
                    except (httpx.HTTPError, ValueError) as exc:
                        # A transient failure to ask is not a failure of the task.
                        failures += 1
                        await self._log(job, f"could not poll task {job.task_id} ({type(exc).__name__}), "
                                             f"attempt {failures} of {self.settings.poll_retries}")
                        if failures > self.settings.poll_retries:
                            raise RuntimeError(f"the node stopped answering about task {job.task_id}") from exc
                        continue
                    failures = 0
                    if task["status"] in ("completed", "failed", "cancelled"):
                        job.task_ended = True
                    progress = float(task.get("progress") or 0.0)
                    if progress != last_progress:
                        await self._emit(job, "progress", progress=progress)
                        last_progress = progress
                    status = task.get("status")
                    if status == "completed":
                        result = task.get("result") or {}
                        job.result = {"node": job.placement["node"], "backend": job.backend,
                                      "task_id": job.task_id, "finder": result.get("finder"),
                                      "n_sources": result.get("n_sources"),
                                      "mask_path": result.get("mask_path"),
                                      "catalog_path": result.get("catalog_path"),
                                      "output": job.request.output}
                        await self._log(job, f"finished: {result.get('n_sources')} sources")
                        await self._set_status(job, COMPLETE)
                        return
                    if status == "failed":
                        raise RuntimeError(task.get("error") or "the task failed")
                    if status == "cancelled":
                        await self._set_status(job, CANCELLED)
                        return
            except asyncio.CancelledError:
                job.cleaning = True
                await self._stop_task(client, job)
                await self._set_status(job, CANCELLED)
                raise
            except Exception as exc:  # noqa: BLE001 — the job's failure, reported as such
                job.cleaning = True
                job.error = str(exc)
                await self._log(job, f"failed: {exc}")
                # A task the node is still running is not left behind.
                await self._stop_task(client, job)
                await self._set_status(job, FAILED, error=job.error)

    @staticmethod
    def _task_id_of(created: httpx.Response) -> str:
        if created.status_code != 200:
            raise RuntimeError(f"the node refused the task: HTTP {created.status_code} {created.text[:300]}")
        try:
            return str(created.json()["task_id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("the node's answer names no task") from exc

    async def _stop_task(self, client: httpx.AsyncClient, job: Job) -> None:
        """Stop the job's task on the node, if there is or is about to be one."""
        if job.task_ended:
            return
        if job.task_id is None and job.submission is not None:
            # The node may have accepted the task after the cancellation hit:
            # wait for its answer as long as the request itself may take.
            try:
                job.task_id = self._task_id_of(
                    await asyncio.wait_for(asyncio.shield(job.submission), self.settings.http_timeout + 1.0))
            except (RuntimeError, httpx.HTTPError) as exc:
                await self._log(job, f"no task to stop on the node ({type(exc).__name__}: {exc})")
            except asyncio.TimeoutError:
                job.error = "cancellation unresolved: the node did not say whether it accepted the task"
                await self._log(job, job.error)
                job.submission.cancel()
        if not (job.backend and job.task_id):
            return
        try:
            resp = await client.delete(f"{job.backend}/v1/tasks/{job.task_id}", headers=self._backend_headers(job))
        except httpx.HTTPError as exc:
            job.error = f"the node could not be asked to stop task {job.task_id}: {exc}"
            await self._log(job, job.error)
            return
        if resp.status_code == 200:
            await self._log(job, f"task {job.task_id} cancelled on the node")
        elif resp.status_code in (404, 409):
            await self._log(job, f"task {job.task_id} had already ended on the node")
        else:
            job.error = f"the node did not confirm the cancellation of task {job.task_id}: HTTP {resp.status_code}"
            await self._log(job, job.error)

    # ── API operations ───────────────────────────────────────────────────────
    def submit(self, request: JobRequest) -> Job:
        job = Job(id=f"job-{uuid.uuid4().hex[:12]}", request=request)
        self.jobs[job.id] = job
        job.runner = asyncio.create_task(self.run(job))
        return job

    async def cancel(self, job: Job) -> None:
        """Cancel the job once; a second request waits for the same cleanup."""
        if job.status in TERMINAL:
            return
        if job.cancellation is None:
            job.cancellation = asyncio.create_task(self._cancel(job))
        try:
            await asyncio.shield(job.cancellation)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — the cleanup's own errors are in the job's log
            pass

    async def _cancel(self, job: Job) -> None:
        if job.runner is not None and not job.runner.done():
            if not job.cleaning:
                job.runner.cancel()      # already cleaning up: let it finish
            try:
                await job.runner
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if job.status not in TERMINAL:
            await self._set_status(job, CANCELLED)

    async def events(self, job: Job) -> AsyncIterator[str]:
        """Server-sent events: everything so far, then each new one, until the job ends."""
        sent = 0
        while True:
            async with job.changed:
                while sent >= len(job.events) and job.status not in TERMINAL:
                    await job.changed.wait()
                pending = job.events[sent:]
                sent = len(job.events)
            for event in pending:
                yield f"id: {event['seq']}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"
            if sent >= len(job.events) and job.status in TERMINAL:
                return


def create_app(settings: Settings | None = None,
               client_factory: Callable[[], httpx.AsyncClient] | None = None) -> FastAPI:
    settings = settings or Settings()
    broker = Broker(settings, client_factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        # Stop what is running and give each runner time to stop its task on
        # the node, so a broker going down does not leave work behind.
        runners = [j.runner for j in broker.jobs.values() if j.runner is not None and not j.runner.done()]
        for job in broker.jobs.values():
            if job.runner is not None and not job.runner.done() and not job.cleaning:
                job.runner.cancel()
        if runners:
            # Long enough for a submission in flight to answer and then for the
            # task to be stopped, two requests of up to http_timeout each (see
            # _stop_task); the container's stop grace period is set above this.
            await asyncio.wait(runners, timeout=2 * settings.http_timeout + 10.0)

    app = FastAPI(title="Computing Broker (testbed mock)", version=VERSION, lifespan=lifespan)
    app.state.broker = broker

    def _job(job_id: str) -> Job:
        job = broker.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, f"no such job: {job_id}")
        return job

    @app.get("/v1/info")
    async def info() -> dict:
        return {"service": "computing-broker-mock", "version": VERSION, "skava_url": settings.skava_url,
                "jobs": len(broker.jobs)}

    @app.post("/v1/jobs", status_code=201)
    async def submit(request: JobRequest) -> dict:
        job = broker.submit(request)
        return job.view()

    @app.get("/v1/jobs")
    async def list_jobs() -> dict:
        return {"jobs": [j.view() for j in broker.jobs.values()]}

    @app.get("/v1/jobs/{job_id}")
    async def get_job(job_id: str) -> dict:
        return _job(job_id).view()

    @app.post("/v1/jobs/{job_id}/cancel")
    async def cancel(job_id: str) -> dict:
        job = _job(job_id)
        await broker.cancel(job)
        return job.view()

    @app.get("/v1/jobs/{job_id}/logs", response_class=PlainTextResponse)
    async def logs(job_id: str) -> str:
        return "\n".join(_job(job_id).logs) + ("\n" if _job(job_id).logs else "")

    @app.get("/v1/jobs/{job_id}/events")
    async def events(job_id: str, request: Request) -> StreamingResponse:
        job = _job(job_id)
        return StreamingResponse(broker.events(job), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
