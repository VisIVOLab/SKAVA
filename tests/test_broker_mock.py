"""The Computing Broker stand-in: placement through SKAVA, execution on the node, the job API."""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "testbed"))
from broker_mock.app import JobRequest, Settings, create_app  # noqa: E402

SKAVA = "http://skava.test"
BIG, SMALL = "http://big.test:8000", "http://small.test:8000"


def _datalink(did: str) -> dict:
    """SKAVA's answer: SMALL ranks first but lacks SoFiA-2; BIG has it."""
    return {
        "dataset": {"obs_id": did, "dataproduct_type": "cube"},
        "primary_access": {"access_url": f"file:///data/{did}.fits", "access_format": "image/fits",
                           "access_estsize": 1048576},        # kB: a 1 GB cube
        "routing": {
            "best_node": "SMALL",
            "policy": "resource_aware",
            "replicas": [
                {"code": "SMALL", "access_endpoint": f"file:///data/{did}.fits", "rank_reason": "rtt 1 ms", "score": 2.1},
                {"code": "BIG", "access_endpoint": f"file:///data/{did}.fits", "rank_reason": "rtt 2 ms", "score": 2.4},
                {"code": "FAR", "access_endpoint": f"http://far.test/{did}.fits", "rank_reason": "rtt 80 ms", "score": 82.0},
            ],
            "excluded": [{"code": "BUSY", "reason": "backend unreachable at the last probe"}],
        },
        "service_descriptors": [
            {"service_type": "visivo-backend", "node_code": "SMALL", "endpoint": SMALL, "enabled": True, "requires_auth": True},
            {"service_type": "visivo-backend", "node_code": "BIG", "endpoint": BIG, "enabled": True, "requires_auth": True},
            {"service_type": "visivo-backend", "node_code": "FAR", "endpoint": "http://far.test:8000", "enabled": True},
        ],
    }


class FakeWorld:
    """SKAVA and two node backends, answered from memory."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.task_polls = 0
        self.task_status = "running"
        self.cancelled: list[str] = []
        self.task_error = ""
        self.status_needs_token = False
        self.poll_http = 200
        self.delete_http = 200
        self.hold_submission: "asyncio.Event | None" = None
        self.hold_delete: "asyncio.Event | None" = None
        # What each node's status says it has free, when it says anything.
        self.memory_free: dict[str, int] = {}
        self.small_has_sofia = False

    async def handler(self, request: httpx.Request) -> httpx.Response:
        url, method = str(request.url), request.method
        self.calls.append((method, url))
        if url.startswith(f"{SKAVA}/datalink/"):
            did = url.rsplit("/", 1)[1]
            return httpx.Response(404) if did == "missing" else httpx.Response(200, json=_datalink(did))
        if url.endswith("/v1/node/status"):
            if self.status_needs_token and request.headers.get("X-Visivo-Token") != "tok":
                return httpx.Response(401, json={"detail": "token"})
            finders = ["sofia2", "photutils"] if url.startswith(BIG) or self.small_has_sofia else ["photutils"]
            status = {"capabilities": {"finders": finders,
                                       "finder_memory": {"sofia2": {"factor": 2.5, "floor_bytes": 64 << 20}}}}
            base = BIG if url.startswith(BIG) else SMALL
            if base in self.memory_free:
                status["memory"] = {"available_bytes": self.memory_free[base]}
            return httpx.Response(200, json=status)
        if url.endswith("/v1/datasets/open_skava"):
            assert request.headers.get("X-Visivo-Token") == "tok"
            return httpx.Response(200, json={"valid": True, "dataset_id": "ds_1", "session_id": "sess_1",
                                             "kind": "cube", "width": 64, "height": 64, "depth": 32})
        if url.endswith("/v1/tasks/sourcefind"):
            assert request.headers.get("X-Visivo-Session") == "sess_1"
            body = json.loads(request.content)
            assert body == {"dataset_id": "ds_1", "finder": "sofia2", "params": {"scfind.threshold": 4.0}}
            if self.hold_submission is not None:
                await self.hold_submission.wait()
            return httpx.Response(200, json={"valid": True, "error": "", "task_id": "task_9", "status": "running"})
        if url.endswith("/v1/tasks/task_9") and method == "GET":
            self.task_polls += 1
            if self.poll_http != 200:
                return httpx.Response(self.poll_http, json={"detail": "gone"})
            status = self.task_status if self.task_polls >= 2 else "running"
            result = {"finder": "sofia2", "n_sources": 3, "mask_path": "/exports/sourcefind/task_9/sofia_out_mask.fits",
                      "catalog_path": "/exports/sourcefind/task_9/sofia_out_cat.xml"} if status == "completed" else None
            return httpx.Response(200, json={"valid": True, "task_id": "task_9", "status": status,
                                             "progress": 0.5 * self.task_polls, "result": result,
                                             "error": self.task_error})
        if url.endswith("/v1/tasks/task_9") and method == "DELETE":
            if self.hold_delete is not None:
                await self.hold_delete.wait()
            self.cancelled.append(url)
            return httpx.Response(self.delete_http, json={"cancelled": self.delete_http == 200})
        return httpx.Response(500, text=f"unexpected {method} {url}")


@pytest.fixture()
def world(monkeypatch):
    monkeypatch.setenv("BROKER_SKAVA_URL", SKAVA)
    monkeypatch.setenv("BROKER_BACKEND_TOKEN", "tok")
    monkeypatch.setenv("BROKER_POLL_SECONDS", "0.01")
    monkeypatch.setenv("BROKER_POLL_RETRIES", "3")
    fake = FakeWorld()
    transport = httpx.MockTransport(fake.handler)
    app = create_app(Settings(), lambda: httpx.AsyncClient(transport=transport))
    with TestClient(app) as client:
        yield client, fake


def _submit(client, did="tb-cube-l", **extra):
    return client.post("/v1/jobs", json={"image": "inaf:visivo-finders:1.0", "cmd": ["sourcefind"],
                                         "rucio_did": did, "output": "dav://out/", "requires_capability": ["finder:sofia2"],
                                         "cpu": 2, "memory": "8G",
                                         "parameters": {"params": {"scfind.threshold": 4.0}}, **extra})


def _wait(client, job_id, until=("COMPLETE", "FAILED", "CANCELLED")):
    import time

    for _ in range(300):
        job = client.get(f"/v1/jobs/{job_id}").json()
        if job["status"] in until:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job did not finish: {job}")


def test_job_runs_on_the_first_ranked_node_that_has_the_finder(world):
    client, fake = world
    fake.task_status = "completed"
    created = _submit(client)
    assert created.status_code == 201 and created.json()["status"] == "PENDING"
    job = _wait(client, created.json()["id"])
    assert job["status"] == "COMPLETE", job
    assert job["placement"]["node"] == "BIG"
    reasons = {c["node"]: c.get("skipped") for c in job["placement"]["candidates"]}
    assert "not available" in reasons["SMALL"] and reasons["BIG"] is None
    assert "not a local file" in reasons["FAR"] and "excluded by SKAVA" in reasons["BUSY"]
    assert job["result"]["n_sources"] == 3 and job["result"]["node"] == "BIG"
    assert job["result"]["mask_path"].endswith("sofia_out_mask.fits") and job["result"]["output"] == "dav://out/"
    assert job["started_at"] and job["ended_at"]
    # The node was asked in order: open, then the task, then polls.
    backend_calls = [u.split("8000", 1)[1] for m, u in fake.calls if u.startswith(BIG)]
    assert backend_calls[:3] == ["/v1/node/status", "/v1/datasets/open_skava", "/v1/tasks/sourcefind"]


def test_a_node_without_the_memory_is_skipped_for_the_next(world):
    client, fake = world
    fake.task_status = "completed"
    fake.small_has_sofia = True
    # SMALL ranks first but has 1 GB free; SoFiA-2 on the 1 GB cube needs 2.5 GB + 64 MB.
    fake.memory_free = {SMALL: 1 << 30, BIG: 16 << 30}
    created = _submit(client, memory=None)
    job = _wait(client, created.json()["id"])
    assert job["status"] == "COMPLETE", job
    assert job["placement"]["node"] == "BIG"
    assert job["placement"]["memory_need_bytes"] == int(2.5 * (1 << 30)) + (64 << 20)
    assert "2.5x the 1.0 GB dataset" in job["placement"]["memory_basis"]
    by_node = {c["node"]: c for c in job["placement"]["candidates"]}
    assert by_node["SMALL"]["skipped"].startswith("not enough memory: needs 2.6 GB")
    assert "1.0 GB free" in by_node["SMALL"]["skipped"]
    assert by_node["BIG"]["chosen"] is True and by_node["BIG"]["memory"]["free_bytes"] == 16 << 30


def test_the_request_memory_figure_is_the_need(world):
    client, fake = world
    fake.memory_free = {BIG: 4 << 30}
    job = _wait(client, _submit(client, memory="8G").json()["id"])
    assert job["status"] == "FAILED"
    assert "BIG: not enough memory: needs 8.0 GB (as requested), 4.0 GB free" in job["error"]
    # The verdicts are in the placement report even though nothing was placed.
    by_node = {c["node"]: c for c in job["placement"]["candidates"]}
    assert by_node["BIG"]["memory"] == {"need_bytes": 8 << 30, "free_bytes": 4 << 30, "basis": "as requested"}
    assert "not available" in by_node["SMALL"]["skipped"] and "memory" not in by_node["SMALL"]
    # A node that reports no memory figure is not held back by one.
    fake.memory_free = {}
    fake.task_status = "completed"
    job = _wait(client, _submit(client, memory="8G").json()["id"])
    assert job["status"] == "COMPLETE" and job["placement"]["memory_basis"] == "as requested"


def test_memory_figures_are_checked_at_submission(world):
    client, _ = world
    for bad in ("lots", "0", "0G", "0.0000001", "-1G", "9" * 400 + "G", "2P"):
        assert _submit(client, memory=bad).status_code == 422, bad
    assert JobRequest.model_validate({"image": "i", "rucio_did": "d", "memory": "1.5G"}).memory_bytes() == 3 << 29
    assert JobRequest.model_validate({"image": "i", "rucio_did": "d", "memory": "562949953421313"}).memory_bytes() \
        == 562949953421313
    assert JobRequest.model_validate({"image": "i", "rucio_did": "d", "memory": "512M"}).memory_bytes() == 512 << 20
    assert JobRequest.model_validate({"image": "i", "rucio_did": "d", "memory": "8GiB"}).memory_bytes() == 8 << 30
    assert JobRequest.model_validate({"image": "i", "rucio_did": "d", "memory": "1073741824"}).memory_bytes() == 1 << 30
    assert JobRequest.model_validate({"image": "i", "rucio_did": "d"}).memory_bytes() is None


def test_the_need_without_a_size_or_with_a_bad_statement():
    from broker_mock.app import Broker

    job = type("J", (), {"request": JobRequest.model_validate({"image": "i", "rucio_did": "d"})})()
    stated = {"capabilities": {"finder_memory": {"sofia2": {"factor": 2.5, "floor_bytes": 512 << 20}}}}
    # No size in the catalogue: the floor is still a lower bound.
    need, basis = Broker.memory_need(job, "sofia2", stated, {"primary_access": {}})
    assert need == 512 << 20 and basis.startswith("sofia2 needs at least 512 MB")
    need, _ = Broker.memory_need(job, "sofia2", stated, {"primary_access": {"access_estsize": 0}})
    assert need == 512 << 20
    # A statement that is not made of figures is no statement; a negative one neither.
    for odd in ({"factor": "NaN"}, {"factor": float("inf")}, {"factor": -2}, {"factor": True}, {"floor_bytes": "x"},
                {"factor": 10 ** 400}, {"floor_bytes": 1e308}):
        need, basis = Broker.memory_need(job, "sofia2", {"capabilities": {"finder_memory": {"sofia2": odd}}},
                                         {"primary_access": {"access_estsize": 1024}})
        assert need is None and "not made of figures" in basis, odd
    # Figures that are each in range but multiply out beyond any node.
    need, basis = Broker.memory_need(job, "sofia2", {"capabilities": {"finder_memory": {"sofia2": {"factor": 1e12}}}},
                                     {"primary_access": {"access_estsize": 1 << 40}})
    assert need is None and "beyond any node" in basis
    # A fractional figure is rounded up to the byte.
    assert JobRequest.model_validate({"image": "i", "rucio_did": "d", "memory": "0.000001M"}).memory_bytes() == 2


def test_events_and_logs_tell_the_story(world):
    client, fake = world
    fake.task_status = "completed"
    job_id = _submit(client).json()["id"]
    _wait(client, job_id)
    stream = client.get(f"/v1/jobs/{job_id}/events").text
    kinds = [line.split(": ", 1)[1] for line in stream.splitlines() if line.startswith("event: ")]
    assert kinds[0] == "log" and "status" in kinds and "progress" in kinds
    statuses = [json.loads(line[6:])["status"] for line in stream.splitlines()
                if line.startswith("data: ") and json.loads(line[6:])["type"] == "status"]
    assert statuses == ["RUNNING", "COMPLETE"]
    logs = client.get(f"/v1/jobs/{job_id}/logs").text
    assert "placed on BIG" in logs and "finished: 3 sources" in logs


def test_failure_on_the_node_fails_the_job(world):
    client, fake = world
    fake.task_status, fake.task_error = "failed", "SoFiA-2 failed (exit 1): bad kernel"
    job = _wait(client, _submit(client).json()["id"])
    assert job["status"] == "FAILED" and "bad kernel" in job["error"]


def test_unknown_dataset_and_no_capable_node(world):
    client, fake = world
    job = _wait(client, _submit(client, did="missing").json()["id"])
    assert job["status"] == "FAILED" and "not in the catalogue" in job["error"]
    job = _wait(client, _submit(client, requires_capability=["finder:aegean"],
                                parameters={"params": {"scfind.threshold": 4.0}}).json()["id"])
    assert job["status"] == "FAILED" and "no node can run aegean" in job["error"]


def test_cancel_stops_the_task_on_the_node(world):
    client, fake = world
    job_id = _submit(client).json()["id"]
    _wait(client, job_id, until=("RUNNING",))
    cancelled = client.post(f"/v1/jobs/{job_id}/cancel").json()
    assert cancelled["status"] == "CANCELLED"
    assert fake.cancelled and fake.cancelled[0].endswith("/v1/tasks/task_9")
    # Cancelling again, or a finished job, changes nothing.
    assert client.post(f"/v1/jobs/{job_id}/cancel").json()["status"] == "CANCELLED"
    assert client.get("/v1/jobs/nope").status_code == 404


def test_status_probe_carries_the_backend_token(world):
    client, fake = world
    fake.status_needs_token, fake.task_status = True, "completed"
    job = _wait(client, _submit(client).json()["id"])
    assert job["status"] == "COMPLETE" and job["placement"]["node"] == "BIG"


def test_a_lost_task_fails_the_job_instead_of_polling_forever(world):
    client, fake = world
    fake.poll_http = 404
    job = _wait(client, _submit(client).json()["id"])
    assert job["status"] == "FAILED" and "no longer knows" in job["error"]


def test_unconfirmed_cancellation_is_reported(world):
    client, fake = world
    fake.delete_http = 500
    job_id = _submit(client).json()["id"]
    _wait(client, job_id, until=("RUNNING",))
    job = client.post(f"/v1/jobs/{job_id}/cancel").json()
    assert job["status"] == "CANCELLED" and "did not confirm" in job["error"]
    assert "did not confirm" in client.get(f"/v1/jobs/{job_id}/logs").text


def test_cancel_during_submission_still_stops_the_task(world):
    client, fake = world
    fake.hold_submission = asyncio.Event()
    job_id = _submit(client).json()["id"]
    _wait(client, job_id, until=("RUNNING",))
    # The node is still deciding when the cancellation arrives: the broker
    # waits for its answer, learns the task's id and stops it.
    import threading

    def release_later():
        import time

        time.sleep(0.1)
        client.portal.call(fake.hold_submission.set)

    threading.Thread(target=release_later).start()
    job = client.post(f"/v1/jobs/{job_id}/cancel").json()
    assert job["status"] == "CANCELLED"
    assert fake.cancelled and fake.cancelled[0].endswith("/v1/tasks/task_9")


def test_a_node_that_stops_answering_has_its_task_stopped(world):
    client, fake = world
    fake.poll_http = 500
    job_id = _submit(client).json()["id"]
    job = _wait(client, job_id)
    assert job["status"] == "FAILED" and "stopped answering" in job["error"]
    assert fake.cancelled and fake.cancelled[0].endswith("/v1/tasks/task_9")
    assert "attempt 3 of 3" in client.get(f"/v1/jobs/{job_id}/logs").text


def test_concurrent_cancellations_share_one_cleanup(world):
    import threading

    client, fake = world
    fake.hold_submission = asyncio.Event()
    job_id = _submit(client).json()["id"]
    _wait(client, job_id, until=("RUNNING",))
    results = []

    def cancel():
        results.append(client.post(f"/v1/jobs/{job_id}/cancel").json()["status"])

    threads = [threading.Thread(target=cancel) for _ in range(2)]
    for thread in threads:
        thread.start()

    def release_later():
        import time

        time.sleep(0.2)
        client.portal.call(fake.hold_submission.set)

    threading.Thread(target=release_later).start()
    for thread in threads:
        thread.join(5)
    assert results == ["CANCELLED", "CANCELLED"]
    assert len(fake.cancelled) == 1 and fake.cancelled[0].endswith("/v1/tasks/task_9")


def test_a_failed_task_is_not_cancelled_again(world):
    client, fake = world
    fake.task_status, fake.task_error = "failed", "boom"
    job = _wait(client, _submit(client).json()["id"])
    assert job["status"] == "FAILED" and not fake.cancelled


def test_cancel_during_failure_cleanup_lets_the_delete_finish(world):
    import threading

    client, fake = world
    fake.poll_http = 500
    fake.hold_delete = asyncio.Event()
    job_id = _submit(client).json()["id"]
    # The job is failing and its DELETE on the node is in flight when the
    # cancellation arrives: the cleanup is left to finish.
    import time

    for _ in range(300):
        if "attempt 3 of 3" in client.get(f"/v1/jobs/{job_id}/logs").text:
            break
        time.sleep(0.02)
    time.sleep(0.05)

    def release_later():
        time.sleep(0.1)
        client.portal.call(fake.hold_delete.set)

    threading.Thread(target=release_later).start()
    job = client.post(f"/v1/jobs/{job_id}/cancel").json()
    assert job["status"] == "FAILED" and "stopped answering" in job["error"]
    assert len(fake.cancelled) == 1


def test_shutdown_waits_for_the_cleanup_of_running_jobs(monkeypatch):
    # The broker goes down while a job's submission and then its DELETE are
    # slow to answer: both complete before the application has shut down.
    monkeypatch.setenv("BROKER_SKAVA_URL", SKAVA)
    monkeypatch.setenv("BROKER_BACKEND_TOKEN", "tok")
    monkeypatch.setenv("BROKER_POLL_SECONDS", "0.01")

    async def scenario():
        fake = FakeWorld()
        fake.hold_submission, fake.hold_delete = asyncio.Event(), asyncio.Event()
        transport = httpx.MockTransport(fake.handler)
        app = create_app(Settings(), lambda: httpx.AsyncClient(transport=transport))
        broker = app.state.broker
        async with app.router.lifespan_context(app):
            job = broker.submit(JobRequest(image="x", rucio_did="tb-cube-l",
                                           parameters={"params": {"scfind.threshold": 4.0}}))
            while not any(u.endswith("/v1/tasks/sourcefind") for _, u in fake.calls):
                await asyncio.sleep(0.005)

            async def release():
                await asyncio.sleep(0.05)
                fake.hold_submission.set()
                await asyncio.sleep(0.05)
                fake.hold_delete.set()

            releaser = asyncio.create_task(release())
        await releaser
        assert job.status == "CANCELLED" and len(fake.cancelled) == 1
        assert job.runner.done()

    asyncio.run(scenario())
