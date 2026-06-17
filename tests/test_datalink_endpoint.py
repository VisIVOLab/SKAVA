def test_datalink_valid_dataset(client):
    resp = client.get("/datalink/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dataset"]["obs_id"] == "dataset-3"


def test_datalink_multiple_replicas_and_best_node(client):
    resp = client.get("/datalink/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["routing"]["best_node"] == "B"
    assert len(data["routing"]["replicas"]) == 2


def test_datalink_links_present(client):
    resp = client.get("/datalink/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    rels = {item["rel"] for item in data["links"]}
    assert "self" in rels
    assert "direct-download" in rels


def test_datalink_service_descriptors_present(client):
    resp = client.get("/datalink/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    descriptor_types = {item["service_type"] for item in data["service_descriptors"]}
    assert "access-resolution" in descriptor_types
    assert "soda-sync" in descriptor_types


def test_datalink_soda_sync_descriptor_points_to_soda_sync(client):
    resp = client.get("/datalink/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    soda = next(item for item in data["service_descriptors"] if item["service_type"] == "soda-sync")
    assert soda["access_url"].endswith("/soda/sync")
    assert soda["enabled"] is True


def test_datalink_capability_flags_consistency(client):
    resp = client.get("/datalink/dataset-3")
    assert resp.status_code == 200
    caps = resp.json()["capabilities"]
    assert caps["supports_soda_sync"] is False
    assert caps["supports_soda_sync_endpoint"] is True
    assert caps["supports_soda_sync_execution"] is False


def test_datalink_not_found(client):
    resp = client.get("/datalink/missing")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "dataset_not_found"


def test_datalink_access_consistency_with_access_facade(client):
    datalink = client.get("/datalink/dataset-3")
    assert datalink.status_code == 200
    access = client.get("/access/dataset-3")
    assert access.status_code == 200

    datalink_payload = datalink.json()
    access_payload = access.json()
    assert datalink_payload["primary_access"]["access_url"] == access_payload["access_url"]
