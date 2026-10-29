"""Federated discovery: the local catalogue and the siblings, merged on the
logical dataset identity, asked with the caller's token, degraded sibling by
sibling."""
from __future__ import annotations

import json

import httpx
import pytest

from app.config import settings
from app.services import federation_service

SIBLING = "https://skava.sibling.example"
OTHER = "https://skava.other.example"


def _local_rows(client, limit=5):
    return client.get("/discovery/search", params={"limit": limit}).json()["results"]


def _entry(obs_id, best_node="ZA-1", access_url="file:///za/x.fits", replicas=2):
    return {
        "metadata": {"obs_id": obs_id, "obs_collection": "sibling", "dataproduct_type": "cube"},
        "replicas": [{"code": f"{best_node}-{i}", "name": "n", "is_enabled": True, "is_available": True,
                      "access_endpoint": access_url} for i in range(replicas)],
        "best_node": best_node,
        "access_url": access_url,
    }


def _answer(entries):
    return {"results": entries, "total": len(entries), "limit": 100, "offset": 0, "returned": len(entries)}


@pytest.fixture()
def siblings(monkeypatch):
    """Fake sibling instances behind httpx; ``world[url]`` is a handler
    (request → response) or an exception to raise."""
    world: dict[str, object] = {}
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        base = f"{request.url.scheme}://{request.url.host}"
        target = world.get(base)
        if isinstance(target, Exception):
            raise target
        if target is None:
            return httpx.Response(404)
        return target(request)

    monkeypatch.setattr(settings, "federation_timeout_seconds", 1.0)
    monkeypatch.setattr(federation_service, "_client",
                        lambda: httpx.Client(transport=httpx.MockTransport(handler),
                                             timeout=settings.federation_timeout_seconds))
    monkeypatch.setattr(settings, "federated_src_urls", f"{SIBLING},{OTHER}")
    world["seen"] = seen
    return world


def test_without_siblings_the_answer_is_the_local_catalogue(client):
    local = _local_rows(client)
    r = client.get("/federation/search", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert [x["metadata"]["obs_id"] for x in body["results"]] == [x["metadata"]["obs_id"] for x in local]
    assert all(x["source"] == "local" and x["also_at"] == [] for x in body["results"])
    assert body["sources"] == [{"base_url": "http://testserver", "status": "local", "returned": len(local),
                                "total": body["sources"][0]["total"], "elapsed_ms": body["sources"][0]["elapsed_ms"],
                                "error": None}]
    assert body["duplicates_merged"] == 0 and body["returned"] == len(local)


def test_siblings_are_merged_on_obs_id_local_first(client, siblings):
    local = _local_rows(client, limit=10)
    shared = local[1]["metadata"]["obs_id"]
    siblings[SIBLING] = lambda req: httpx.Response(200, json=_answer([_entry(shared), _entry("za-only")]))
    siblings[OTHER] = lambda req: httpx.Response(200, json=_answer([_entry("za-only", "AU-1", "file:///au/x.fits", 1),
                                                                    _entry("au-only")]))
    body = client.get("/federation/search", params={"limit": 10}).json()
    ids = [x["metadata"]["obs_id"] for x in body["results"]]
    assert ids[:len(local)] == [x["metadata"]["obs_id"] for x in local], "the local catalogue first, in its order"
    assert ids[len(local):] == ["za-only", "au-only"]
    merged = {x["metadata"]["obs_id"]: x for x in body["results"]}
    # The local decision for the shared dataset stands; the sibling is another place it is at.
    assert merged[shared]["source"] == "local" and merged[shared]["best_node"] == local[1]["best_node"]
    assert merged[shared]["also_at"] == [{"source": SIBLING, "best_node": "ZA-1", "access_url": "file:///za/x.fits",
                                          "replicas": 2}]
    assert merged["za-only"]["source"] == SIBLING
    assert merged["za-only"]["also_at"] == [{"source": OTHER, "best_node": "AU-1", "access_url": "file:///au/x.fits",
                                             "replicas": 1}]
    assert merged["au-only"]["source"] == OTHER and merged["au-only"]["also_at"] == []
    assert body["duplicates_merged"] == 2
    statuses = {s["base_url"]: s for s in body["sources"]}
    assert statuses[SIBLING]["status"] == "ok" and statuses[SIBLING]["returned"] == 2
    assert statuses[OTHER]["status"] == "ok" and statuses[OTHER]["elapsed_ms"] is not None


def test_siblings_get_the_callers_query_and_token_at_their_own_catalogue(client, siblings, monkeypatch):
    siblings[SIBLING] = lambda req: httpx.Response(200, json=_answer([]))
    siblings[OTHER] = lambda req: httpx.Response(200, json=_answer([]))
    monkeypatch.setattr(settings, "access_tokens", "shared-token")
    r = client.get("/federation/search", params={"COLLECTION": "demo", "BAND": "0.2 0.3", "limit": 7},
                   headers={"Authorization": "Bearer shared-token"})
    assert r.status_code == 200
    asked = [req for req in siblings["seen"]]
    assert sorted(f"{q.url.scheme}://{q.url.host}" for q in asked) == sorted([SIBLING, OTHER])
    for req in asked:
        assert req.url.path == "/discovery/search", "a sibling's own catalogue, never its fan-out"
        assert dict(req.url.params) == {"COLLECTION": "demo", "BAND": "0.2 0.3", "limit": "7"}
        assert req.headers["Authorization"] == "Bearer shared-token"
        assert req.headers["Accept"] == "application/json"


def test_an_anonymous_caller_forwards_no_token(client, siblings):
    siblings[SIBLING] = lambda req: httpx.Response(200, json=_answer([]))
    siblings[OTHER] = lambda req: httpx.Response(200, json=_answer([]))
    assert client.get("/federation/search").status_code == 200
    assert all("Authorization" not in req.headers for req in siblings["seen"])


def test_a_failing_sibling_is_reported_and_the_rest_answers(client, siblings):
    local = _local_rows(client)
    siblings[SIBLING] = lambda req: httpx.Response(401, json={"error": {"code": "unauthorized"}})
    siblings[OTHER] = httpx.ConnectTimeout("connect timed out")
    body = client.get("/federation/search", params={"limit": 5}).json()
    assert len(body["results"]) == len(local)
    statuses = {s["base_url"]: s for s in body["sources"]}
    assert statuses[SIBLING]["status"] == "unauthorized" and statuses[SIBLING]["error"] == "HTTP 401"
    assert statuses[OTHER]["status"] == "timeout" and statuses[OTHER]["error"] == "no answer within 1 s"

    siblings[SIBLING] = lambda req: httpx.Response(200, content=b"<html>not json</html>")
    siblings[OTHER] = lambda req: httpx.Response(200, json={"results": [{"bad": True}]})
    body = client.get("/federation/search", params={"limit": 5}).json()
    statuses = {s["base_url"]: s for s in body["sources"]}
    assert statuses[SIBLING]["status"] == "error" and statuses[SIBLING]["error"].startswith("malformed answer")
    assert statuses[OTHER]["status"] == "error" and statuses[OTHER]["error"].startswith("malformed answer")
    assert statuses[SIBLING]["returned"] == 0

    siblings[SIBLING] = httpx.ConnectError("refused")
    siblings[OTHER] = lambda req: httpx.Response(503)
    body = client.get("/federation/search", params={"limit": 5}).json()
    statuses = {s["base_url"]: s for s in body["sources"]}
    assert statuses[SIBLING] == {"base_url": SIBLING, "status": "error", "returned": 0, "total": None,
                                 "elapsed_ms": statuses[SIBLING]["elapsed_ms"], "error": "refused"}
    assert statuses[OTHER]["status"] == "error" and statuses[OTHER]["error"] == "HTTP 503"


def test_a_misconfigured_sibling_url_does_not_fail_the_search(client, siblings, monkeypatch):
    monkeypatch.setattr(settings, "federated_src_urls", f"{SIBLING},https://site.example:bad")
    siblings[SIBLING] = lambda req: httpx.Response(200, json=_answer([_entry("za-only")]))
    body = client.get("/federation/search", params={"limit": 50}).json()
    assert "za-only" in [x["metadata"]["obs_id"] for x in body["results"]]
    statuses = {s["base_url"]: s for s in body["sources"]}
    assert statuses[SIBLING]["status"] == "ok"
    assert statuses["https://site.example:bad"]["status"] == "error"
    assert statuses["https://site.example:bad"]["error"]


def test_the_merged_list_is_cut_at_the_limit(client, siblings):
    siblings[SIBLING] = lambda req: httpx.Response(200, json=_answer([_entry(f"za-{i}") for i in range(5)]))
    siblings[OTHER] = lambda req: httpx.Response(200, json=_answer([]))
    body = client.get("/federation/search", params={"limit": 2}).json()
    assert body["returned"] == 2 and body["limit"] == 2 and len(body["results"]) == 2
    assert all(x["source"] == "local" for x in body["results"])
    assert dict(siblings["seen"][0].url.params)["limit"] == "2"


def test_federation_needs_the_token_when_the_catalogue_does(client, siblings, monkeypatch):
    monkeypatch.setattr(settings, "access_tokens", "shared-token")
    r = client.get("/federation/search")
    assert r.status_code == 401 and r.headers["WWW-Authenticate"].startswith('Bearer realm="SKAVA"')
    assert siblings["seen"] == [], "nothing is asked on behalf of a caller who was refused"


def test_sources_lists_the_configured_siblings(client, siblings):
    assert client.get("/federation/sources").json()["sources"] == [
        {"base_url": SIBLING, "status": "configured"}, {"base_url": OTHER, "status": "configured"}]


def test_service_merges_without_a_local_catalogue(siblings):
    siblings[SIBLING] = lambda req: httpx.Response(200, json=_answer([_entry("x")]))
    siblings[OTHER] = lambda req: httpx.Response(200, json=_answer([_entry("x", "AU-1")]))
    answer = federation_service.FederationService(token="t").search({"obs_id": "x", "POS": None}, 10)
    assert [r.metadata.obs_id for r in answer.results] == ["x"]
    assert answer.results[0].source == SIBLING and answer.results[0].also_at[0].source == OTHER
    assert [s.status for s in answer.sources] == ["ok", "ok"]
    assert json.loads(answer.model_dump_json())["duplicates_merged"] == 1
