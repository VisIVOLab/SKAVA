# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from app.main import app
from app.models.dataset import Dataset
from app.models.replica import DatasetReplica


def test_soda_sync_valid_id_only(client):
    resp = client.get("/soda/sync", params={"ID": "dataset-3"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["mode"] == "soda-sync-stub"
    assert data["dataset"]["obs_id"] == "dataset-3"


def test_soda_sync_valid_id_pos(client):
    resp = client.get("/soda/sync", params={"ID": "dataset-3", "POS": "CIRCLE 103 -23 0.05"})
    assert resp.status_code == 200
    assert resp.json()["request"]["POS"] == "CIRCLE 103.0 -23.0 0.05"


def test_soda_sync_valid_id_band(client):
    resp = client.get("/soda/sync", params={"ID": "dataset-3", "BAND": "1.3e-6 1.4e-6"})
    assert resp.status_code == 200
    assert resp.json()["request"]["BAND"] == "1.3e-06 1.4e-06"


def test_soda_sync_valid_id_time(client):
    resp = client.get("/soda/sync", params={"ID": "dataset-3", "TIME": "59003.1 59003.3"})
    assert resp.status_code == 200
    assert resp.json()["request"]["TIME"] == "59003.1 59003.3"


def test_soda_sync_valid_all_subset_params(client):
    resp = client.get(
        "/soda/sync",
        params={
            "ID": "dataset-3",
            "POS": "CIRCLE 103 -23 0.05",
            "BAND": "1.3e-6 1.4e-6",
            "TIME": "59003.1 59003.3",
            "RESPONSEFORMAT": "image/fits",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["request"]["ID"] == "dataset-3"
    assert payload["request"]["RESPONSEFORMAT"] == "image/fits"


def test_soda_sync_missing_id(client):
    resp = client.get("/soda/sync")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_query"


def test_soda_sync_invalid_pos(client):
    resp = client.get("/soda/sync", params={"ID": "dataset-3", "POS": "BOX 103 -23 0.05"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_query"


def test_soda_sync_invalid_band(client):
    resp = client.get("/soda/sync", params={"ID": "dataset-3", "BAND": "1.3e-6"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_query"


def test_soda_sync_invalid_time(client):
    resp = client.get("/soda/sync", params={"ID": "dataset-3", "TIME": "59005 59001"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_query"


def test_soda_sync_dataset_not_found(client):
    resp = client.get("/soda/sync", params={"ID": "missing"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "dataset_not_found"


def test_soda_sync_no_available_replicas(client):
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "dataset-3").one()
        replicas = db.query(DatasetReplica).filter(DatasetReplica.dataset_id == dataset.id).all()
        for replica in replicas:
            replica.node.is_available = False
        db.commit()

    resp = client.get("/soda/sync", params={"ID": "dataset-3"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "no_available_nodes"

