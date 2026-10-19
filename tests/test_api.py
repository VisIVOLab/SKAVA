from app.main import app
from app.models.dataset import Dataset
from app.models.node import Node
from app.models.replica import DatasetReplica


def test_availability(client):
    resp = client.get("/availability")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["database"]["status"] == "ok"


def test_db_health(client):
    resp = client.get("/health/db")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["database"] == "reachable"


def test_metrics_endpoint(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "skava_http_requests_total" in resp.text


def test_capabilities_vosi_inspired_shape(client):
    resp = client.get("/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["profile"] == "VO-aligned Production Service"
    assert "vosi" in data
    assert any(std["name"] == "ObsCore" for std in data["standards"])


def test_discovery_dataset_4_best_node_b(client):
    resp = client.get("/discovery/dataset/dataset-4")
    assert resp.status_code == 200
    data = resp.json()
    assert data["best_node"] == "B"
    assert len(data["replicas"]) == 1


def test_discovery_dataset_3_best_node_by_policy(client):
    resp = client.get("/discovery/dataset/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    nodes = sorted([r["code"] for r in data["replicas"]])
    assert nodes == ["A", "B"]
    assert data["best_node"] == "B"


def test_discovery_search_collection_and_dptype(client):
    resp = client.get("/discovery/search", params={"COLLECTION": "skava-demo", "DPTYPE": "image"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 7


def test_discovery_search_band_and_time(client):
    resp = client.get("/discovery/search", params={"BAND": "1.3e-6 1.4e-6", "TIME": "59003.1 59003.4"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["metadata"]["obs_id"] == "dataset-3"


def test_discovery_search_valid_pos_query(client):
    resp = client.get("/discovery/search", params={"POS": "CIRCLE 103 -23 0.05"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["metadata"]["obs_id"] == "dataset-3"


def test_discovery_search_invalid_pos_query(client):
    resp = client.get("/discovery/search", params={"POS": "BOX 103 -23 0.1"})
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "invalid_query"


def test_discovery_search_valid_band_query(client):
    resp = client.get("/discovery/search", params={"BAND": "1.1e-6 1.25e-6"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 7


def test_discovery_search_invalid_band_query(client):
    resp = client.get("/discovery/search", params={"BAND": "1.3e-6"})
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "invalid_query"


def test_discovery_search_valid_time_query(client):
    resp = client.get("/discovery/search", params={"TIME": "59004.1 59004.2"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["metadata"]["obs_id"] == "dataset-4"


def test_discovery_search_invalid_time_query(client):
    resp = client.get("/discovery/search", params={"TIME": "59005 59001"})
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "invalid_query"


def test_discovery_search_combined_pos_band(client):
    resp = client.get("/discovery/search", params={"POS": "CIRCLE 103 -23 0.05", "BAND": "1.3e-6 1.4e-6"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["metadata"]["obs_id"] == "dataset-3"


def test_discovery_search_combined_pos_time(client):
    resp = client.get("/discovery/search", params={"POS": "CIRCLE 103 -23 0.05", "TIME": "59003.1 59003.2"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["metadata"]["obs_id"] == "dataset-3"


def test_discovery_search_combined_pos_band_time(client):
    resp = client.get(
        "/discovery/search",
        params={"POS": "CIRCLE 103 -23 0.05", "BAND": "1.3e-6 1.4e-6", "TIME": "59003.1 59003.2"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["metadata"]["obs_id"] == "dataset-3"


def test_discovery_search_no_matches(client):
    resp = client.get("/discovery/search", params={"BAND": "3.0e-6 4.0e-6"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"] == []


def test_discovery_search_backward_compatible_existing_params(client):
    resp = client.get("/discovery/search", params={"obs_id": "dataset-3", "COLLECTION": "skava-demo", "DPTYPE": "image"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["metadata"]["obs_id"] == "dataset-3"


def test_access_returns_precursor_contract(client):
    resp = client.get("/access/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["best_node"] == "B"
    assert data["supports_datalink"] is True
    # Operations are what this deployment can do, never placeholders.
    assert data["supported_operations"] == ["download"]
    assert data["supports_soda"] is False
    assert not any(op.endswith(":TBD") for op in data["supported_operations"])


def test_access_fallback_to_next_candidate(client):
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "dataset-3").one()
        node_b = db.query(Node).filter(Node.code == "B").one()
        replica_b = (
            db.query(DatasetReplica)
            .filter(DatasetReplica.dataset_id == dataset.id, DatasetReplica.node_id == node_b.id)
            .one()
        )
        replica_b.access_endpoint = ""
        db.commit()

    resp = client.get("/access/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["best_node"] == "A"


def test_invalid_query_returns_structured_400(client):
    resp = client.get("/discovery/search", params={"BAND": "abc"})
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "invalid_query"


def test_dataset_not_found_returns_structured_404(client):
    resp = client.get("/discovery/dataset/missing")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "dataset_not_found"


def test_no_available_nodes_returns_503(client):
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "dataset-3").one()
        replicas = db.query(DatasetReplica).filter(DatasetReplica.dataset_id == dataset.id).all()
        for replica in replicas:
            replica.node.is_available = False
        db.commit()

    resp = client.get("/access/dataset-3")
    assert resp.status_code == 503
    data = resp.json()
    assert data["error"]["code"] == "no_available_nodes"
