# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from app.spatial_index import compute_spatial_cell


def test_provenance_endpoint_returns_pid_doi_metadata(client):
    resp = client.get("/provenance/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["obs_id"] == "dataset-3"
    assert data["doi"] == "10.0000/skava.demo.3"
    assert data["pid"] == "skava:demo:dataset-3"
    assert data["license"] == "CC-BY-4.0"


def test_staging_metadata_cache_job(client):
    submit = client.post("/staging/jobs", params={"ID": "dataset-3"})
    assert submit.status_code == 200
    payload = submit.json()
    assert payload["status"] == "ready"
    assert payload["staged_url"].startswith("https://")

    detail = client.get(f"/staging/jobs/{payload['job_id']}")
    assert detail.status_code == 200
    assert detail.json()["obs_id"] == "dataset-3"


def test_soda_execute_creates_subset_handoff(client):
    resp = client.post("/soda/execute", params={"ID": "dataset-3", "POS": "CIRCLE 103 -23 0.05"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["operation"]["type"] == "subset"
    assert data["request"]["POS"] == "CIRCLE 103.0 -23.0 0.05"


def test_tap_async_job_completes(client):
    submit = client.post(
        "/tap/async",
        data={
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "QUERY": "SELECT TOP 1 * FROM ivoa.ObsCore WHERE obs_id = 'dataset-3'",
            "FORMAT": "json",
        },
    )
    assert submit.status_code == 200
    payload = submit.json()
    assert payload["status"] == "completed"
    assert payload["result"]["returned"] == 1

    detail = client.get(f"/tap/async/{payload['job_id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "completed"


def test_discovery_spatial_cell_filter(client):
    cell = compute_spatial_cell(103.0, -23.0)
    resp = client.get("/discovery/search", params={"SPATIAL_CELL": cell, "limit": 10})
    assert resp.status_code == 200
    assert any(item["metadata"]["obs_id"] == "dataset-3" for item in resp.json()["results"])


def test_federation_sources_empty_by_default(client):
    resp = client.get("/federation/sources")
    assert resp.status_code == 200
    assert resp.json()["sources"] == []
