# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
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


def test_discovery_lists_replicas_in_ranking_order(client):
    # dataset-3 is stored on A first, but B ranks better: the list must follow
    # the ranking, with the best node first, as DataLink's does.
    data = client.get("/discovery/dataset/dataset-3").json()
    assert [r["code"] for r in data["replicas"]] == ["B", "A"]
    datalink = client.get("/datalink/dataset-3").json()
    assert [r["code"] for r in datalink["routing"]["replicas"]] == ["B", "A"]


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


def test_cone_search_scales_ra_by_cos_dec(client):
    # At Dec 60 a 1.5 deg RA offset is 0.75 deg on the sky: inside a 1 deg
    # circle. The flat-sky distance used to put it at 1.5 deg and miss it.
    from app.main import app
    from app.ingestion.services.ingest_service import IngestService
    with app.state.testing_session_local() as db:
        IngestService(db, source_type="manual").ingest_records([{
            "obs_id": "high-dec", "dataproduct_type": "image", "node_id": "A",
            "access_url": "https://node-a.example.org/high-dec.fits",
            "s_ra": 101.5, "s_dec": 60.0,
        }])
    found = client.get("/discovery/search", params={"POS": "CIRCLE 100 60 1"}).json()["results"]
    assert [r["metadata"]["obs_id"] for r in found] == ["high-dec"]
    # And it is not inside a circle that is too small for 0.75 deg.
    assert client.get("/discovery/search", params={"POS": "CIRCLE 100 60 0.5"}).json()["results"] == []


def test_cone_search_around_the_pole_ignores_ra(client):
    from app.main import app
    from app.ingestion.services.ingest_service import IngestService
    with app.state.testing_session_local() as db:
        IngestService(db, source_type="manual").ingest_records([{
            "obs_id": "near-pole", "dataproduct_type": "image", "node_id": "A",
            "access_url": "https://node-a.example.org/near-pole.fits",
            "s_ra": 280.0, "s_dec": 89.5,
        }])
    found = client.get("/discovery/search", params={"POS": "CIRCLE 10 89.6 1"}).json()["results"]
    assert "near-pole" in [r["metadata"]["obs_id"] for r in found]



def _ingest(**fields):
    from app.main import app
    from app.ingestion.services.ingest_service import IngestService
    record = {"dataproduct_type": "image", "node_id": "A",
              "access_url": f"https://node-a.example.org/{fields['obs_id']}.fits", **fields}
    with app.state.testing_session_local() as db:
        IngestService(db, source_type="manual").ingest_records([record])


def _found(client, circle):
    return [r["metadata"]["obs_id"] for r in
            client.get("/discovery/search", params={"POS": f"CIRCLE {circle}"}).json()["results"]]


def test_cone_search_is_spherical_near_the_pole(client):
    # 0.866 deg from the centre: the small-angle distance said 1.16 deg.
    _ingest(obs_id="pole-a", s_ra=60.0, s_dec=89.5)
    assert "pole-a" in _found(client, "0 89 0.9")
    assert "pole-a" not in _found(client, "0 89 0.8")


def test_cone_search_counts_the_dataset_footprint_at_both_poles(client):
    # Centres 0.7 deg apart, radii 0.1 + 1.0: they overlap.
    _ingest(obs_id="north-wide", s_ra=180.0, s_dec=89.8, s_fov=2.0)
    _ingest(obs_id="south-wide", s_ra=180.0, s_dec=-89.8, s_fov=2.0)
    assert "north-wide" in _found(client, "0 89.5 0.1")
    assert "south-wide" in _found(client, "0 -89.5 0.1")


def test_cone_search_across_ra_zero(client):
    _ingest(obs_id="wrap", s_ra=359.8, s_dec=10.0)
    assert "wrap" in _found(client, "0.1 10 0.4")



def test_a_tiny_cone_finds_the_dataset_at_its_centre(client):
    _ingest(obs_id="centre", s_ra=0.0, s_dec=10.0)
    assert "centre" in _found(client, "0 10 0.00000001")


def test_sqlite_math_functions_keep_null_semantics():
    from app.db import engine
    from sqlalchemy import text
    with engine.connect() as conn:
        assert conn.execute(text("SELECT sin(NULL), cos(NULL), radians(NULL)")).fetchone() == (None, None, None)


def test_rest_pos_overlaps_the_footprint_and_tap_contains_tests_the_centre(client):
    # A dataset 2 deg across, its centre 0.7 deg from a 0.2 deg cone: the
    # cone intersects its footprint (0.7 < 0.2 + 1.0) but holds no centre.
    _ingest(obs_id="extended", s_ra=10.0, s_dec=0.0, s_fov=2.0)
    assert "extended" in _found(client, "10.7 0 0.2")
    query = ("SELECT * FROM ivoa.obscore WHERE "
             "1 = CONTAINS(POINT('ICRS', s_ra, s_dec), CIRCLE('ICRS', 10.7, 0, 0.2))")
    rows = client.get("/tap/sync", params={"QUERY": query, "FORMAT": "json"}).json()["results"]
    assert "extended" not in [r["metadata"]["obs_id"] for r in rows]
    # Centre inside: both find it.
    query_centre = query.replace("10.7, 0, 0.2", "10.1, 0, 0.2")
    rows = client.get("/tap/sync", params={"QUERY": query_centre, "FORMAT": "json"}).json()["results"]
    assert "extended" in [r["metadata"]["obs_id"] for r in rows]
