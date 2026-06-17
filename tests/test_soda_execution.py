"""Tests for SODA execution delegated to a node's co-located VisIVO backend.

These cover the compute-next-to-data path of /soda/execute:
* delegation to the backend when the best node has visivo_backend_url and a
  file:// replica → FITS streamed back;
* graceful fallback to the staging handoff when there is no backend;
* the DataLink capability flags flipping to reflect execution availability.
"""
import httpx

from app.main import app
from app.models.dataset import Dataset
from app.models.replica import DatasetReplica


def _enable_backend_on_best_node(file_url: str = "file:///data/dataset-3.fits") -> None:
    """Point dataset-3's replicas at a file:// URL and give their nodes a backend."""
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "dataset-3").one()
        replicas = db.query(DatasetReplica).filter(DatasetReplica.dataset_id == dataset.id).all()
        for replica in replicas:
            replica.access_endpoint = file_url
            replica.status = "available"
            replica.is_public = True
            replica.node.visivo_backend_url = "http://node-backend:8000"
            replica.node.visivo_backend_requires_auth = False
        db.commit()


def test_soda_execute_delegates_to_backend(client, monkeypatch):
    _enable_backend_on_best_node()

    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200,
            content=b"SIMPLE  =                    T / FITS cutout",
            headers={
                "content-type": "application/fits",
                "content-disposition": 'attachment; filename="dataset-3_cutout.fits"',
                "X-Soda-Applied": "pos",
            },
        )

    monkeypatch.setattr("app.services.soda_execution_service.httpx.post", fake_post)

    resp = client.post("/soda/execute", params={"ID": "dataset-3", "POS": "CIRCLE 103 -23 0.05"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/fits")
    assert resp.headers["X-Soda-Applied"] == "pos"
    assert resp.content.startswith(b"SIMPLE")
    # SKAVA delegated to the node backend's cutout endpoint with the file URL.
    assert captured["url"] == "http://node-backend:8000/v1/datasets/cutout"
    assert captured["json"]["access_url"] == "file:///data/dataset-3.fits"
    assert captured["json"]["pos"] == "CIRCLE 103.0 -23.0 0.05"


def test_soda_execute_backend_error_surfaces_502(client, monkeypatch):
    _enable_backend_on_best_node()

    def fake_post(url, json=None, headers=None, timeout=None):
        return httpx.Response(400, json={"detail": "POS does not overlap"})

    monkeypatch.setattr("app.services.soda_execution_service.httpx.post", fake_post)

    resp = client.post("/soda/execute", params={"ID": "dataset-3", "POS": "CIRCLE 10 80 0.01"})
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "backend_execution_failed"


def test_soda_execute_falls_back_to_staging_without_backend(client):
    # No backend configured on the seed nodes → metadata-cache handoff JSON.
    resp = client.post("/soda/execute", params={"ID": "dataset-3", "POS": "CIRCLE 103 -23 0.05"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["operation"]["type"] == "subset"


def test_datalink_capabilities_flip_when_backend_present(client):
    _enable_backend_on_best_node()
    caps = client.get("/datalink/dataset-3").json()["capabilities"]
    assert caps["supports_soda_sync_execution"] is True
    assert caps["supports_soda_sync"] is True
    assert caps["supports_cutout"] is True


def test_datalink_cutout_descriptor_enabled_with_backend(client):
    _enable_backend_on_best_node()
    descriptors = client.get("/datalink/dataset-3").json()["service_descriptors"]
    cutout = next(d for d in descriptors if d["service_type"] == "cutout")
    assert cutout["enabled"] is True
    assert cutout["access_url"].endswith("/soda/execute")
