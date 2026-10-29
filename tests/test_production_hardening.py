# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from app.main import app
from app.models.dataset import Dataset
from app.models.replica import DatasetReplica


def test_discovery_search_is_paginated(client):
    resp = client.get("/discovery/search", params={"COLLECTION": "skava-demo", "DPTYPE": "image", "limit": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 7
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert data["returned"] == 2
    assert len(data["results"]) == 2


def test_discovery_search_rejects_excessive_limit(client):
    resp = client.get("/discovery/search", params={"limit": 1001})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_query"


def test_private_replica_is_not_selected_for_public_access(client):
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "dataset-3").one()
        replica_b = (
            db.query(DatasetReplica)
            .join(DatasetReplica.node)
            .filter(DatasetReplica.dataset_id == dataset.id, DatasetReplica.node.has(code="B"))
            .one()
        )
        replica_b.is_public = False
        db.commit()

    resp = client.get("/access/dataset-3")
    assert resp.status_code == 200
    assert resp.json()["best_node"] == "A"


def test_datalink_votable_response(client):
    resp = client.get("/datalink/dataset-3", params={"RESPONSEFORMAT": "application/x-votable+xml"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-votable+xml")
    assert "<VOTABLE" in resp.text
    # Conformant IVOA DataLink output: standard {links} columns, the
    # #this semantics term, and a SODA cutout service descriptor.
    assert 'name="access_url"' in resp.text
    assert 'name="semantics"' in resp.text
    assert "#this" in resp.text
    # dataset-3 has no node able to cut it: no cutout row, no SODA resource,
    # and no link to the not-yet-existing async endpoint.
    assert "#cutout" not in resp.text
    assert 'utype="adhoc:service"' not in resp.text
    assert "/soda/async" not in resp.text


def test_tap_sync_json_profile(client):
    resp = client.get(
        "/tap/sync",
        params={
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "QUERY": "SELECT TOP 1 * FROM ivoa.ObsCore WHERE obs_id = 'dataset-3'",
            "FORMAT": "json",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["returned"] == 1
    assert data["results"][0]["metadata"]["obs_id"] == "dataset-3"


def test_tap_sync_votable_default(client):
    resp = client.get(
        "/tap/sync",
        params={"QUERY": "SELECT TOP 1 * FROM ivoa.ObsCore WHERE dataproduct_type = 'image'"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-votable+xml")
    assert "<TABLE name=\"ivoa.ObsCore\">" in resp.text


def test_tap_rejects_unsupported_where_clause(client):
    # OR, unknown columns and unsupported geometry remain rejected even though
    # range/equality predicates on whitelisted ObsCore columns are now allowed.
    for query in (
        "SELECT * FROM ivoa.ObsCore WHERE obs_id = 'x' OR obs_id = 'y'",
        "SELECT * FROM ivoa.ObsCore WHERE bogus_column > 1",
        "SELECT * FROM ivoa.ObsCore WHERE 1 = INTERSECTS(POINT('ICRS', s_ra, s_dec), CIRCLE('ICRS', 1, 2, 3))",
    ):
        resp = client.get("/tap/sync", params={"QUERY": query})
        assert resp.status_code == 400, query
        assert resp.json()["error"]["code"] == "invalid_query"
