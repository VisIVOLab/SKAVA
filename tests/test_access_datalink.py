# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from app.main import app
from app.models.dataset import Dataset
from app.models.replica import DatasetReplica


def test_access_dataset_with_one_replica(client):
    resp = client.get("/access/dataset-4")
    assert resp.status_code == 200
    data = resp.json()
    assert data["routing"]["best_node"] == "B"
    assert len(data["routing"]["replicas"]) == 1


def test_access_dataset_with_multiple_replicas(client):
    resp = client.get("/access/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["routing"]["replicas"]) == 2


def test_access_best_node_selection_enriched_response(client):
    resp = client.get("/access/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["best_node"] == "B"
    assert data["routing"]["best_node"] == "B"


def test_access_primary_access_block_present(client):
    resp = client.get("/access/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    assert "primary_access" in data
    assert data["primary_access"]["access_url"].startswith("https://")
    assert data["primary_access"]["access_format"] == "image/fits"


def test_access_alternate_replica_links_present(client):
    resp = client.get("/access/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    alternates = [link for link in data["links"] if link["rel"] == "alternate-replica"]
    assert len(alternates) == 1
    assert alternates[0]["node_id"] == "A"


def test_access_service_descriptors_present(client):
    resp = client.get("/access/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    types = {item["service_type"] for item in data["service_descriptors"]}
    assert "access-resolution" in types
    assert "soda-sync" in types
    assert "soda-async" in types
    assert "cutout" in types


def test_access_dataset_not_found(client):
    resp = client.get("/access/missing-dataset")
    assert resp.status_code == 404
    payload = resp.json()
    assert payload["error"]["code"] == "dataset_not_found"


def test_access_no_available_replicas(client):
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "dataset-3").one()
        replicas = db.query(DatasetReplica).filter(DatasetReplica.dataset_id == dataset.id).all()
        for replica in replicas:
            replica.node.is_available = False
        db.commit()

    resp = client.get("/access/dataset-3")
    assert resp.status_code == 503
    payload = resp.json()
    assert payload["error"]["code"] == "no_available_nodes"


def test_access_backward_compatibility_fields_present(client):
    resp = client.get("/access/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["obs_id"] == "dataset-3"
    assert data["best_node"] == "B"
    assert data["access_url"].startswith("https://")
    assert data["access_mode"] == "remote-routing"
    assert isinstance(data["supported_operations"], list)
    # No node holding dataset-3 runs a VisIVO backend: download only, no SODA.
    assert data["supports_soda"] is False
    assert data["supports_datalink"] is True


def test_access_capability_flags_consistency(client):
    resp = client.get("/access/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    caps = data["capabilities"]
    assert caps["supports_datalink"] is True
    assert caps["supports_soda_sync"] is False
    assert caps["supports_soda_async"] is False
    assert caps["supports_cutout"] is False
    assert caps["supports_preview"] is False
    assert caps["supports_soda_sync_endpoint"] is True
    assert caps["supports_soda_sync_execution"] is False
    assert data["supports_datalink"] == caps["supports_datalink"]


def test_access_contains_embedded_datalink_object(client):
    resp = client.get("/access/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["datalink"]["dataset"]["obs_id"] == "dataset-3"
