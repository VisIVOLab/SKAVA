# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import pytest

from app.main import app
from app.models.dataset import Dataset
from app.models.ingestion_job import IngestionJob
from app.services import ingestion_job_service


DATA_DIR = Path(__file__).parent / "data"
API_KEY_HEADER = {"X-Internal-Api-Key": "test-internal-key"}


def _file_payload(path: Path, content_type: str):
    return {"file": (path.name, path.read_bytes(), content_type)}


def test_unauthorized_request(client):
    files = _file_payload(DATA_DIR / "ingest_valid.csv", "text/csv")
    resp = client.post("/internal/ingestion/dry-run", files=files)
    assert resp.status_code == 401


def test_dry_run_upload_success(client):
    files = _file_payload(DATA_DIR / "ingest_valid.csv", "text/csv")
    resp = client.post(
        "/internal/ingestion/dry-run",
        files=files,
        data={"format": "csv", "source_type": "csv", "source_ref": "test-dry"},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["job"]["status"] == "dry_run"
    assert data["summary"]["processed"] == 3


def test_real_ingestion_upload_success(client):
    files = _file_payload(DATA_DIR / "ingest_valid.json", "application/json")
    resp = client.post(
        "/internal/ingestion/run",
        files=files,
        data={"format": "json", "source_type": "json", "source_ref": "test-run"},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["job"]["status"] == "succeeded"
    assert data["summary"]["processed"] == 2

    with app.state.testing_session_local() as db:
        assert db.query(Dataset).filter(Dataset.obs_id == "dataset-10").first() is not None


def test_invalid_file_format(client):
    files = {"file": ("invalid.txt", b"hello", "text/plain")}
    resp = client.post("/internal/ingestion/run", files=files, headers=API_KEY_HEADER)
    assert resp.status_code == 400


def test_concurrent_job_blocked(client):
    with app.state.testing_session_local() as db:
        db.add(
            IngestionJob(
                started_at=ingestion_job_service._utcnow(),
                completed_at=None,
                status="running",
                source_type="csv",
                source_ref="manual",
                filename="manual.csv",
                dry_run=False,
                record_count=0,
                summary_json=None,
                error_message=None,
                triggered_by="test",
            )
        )
        db.commit()

    files = _file_payload(DATA_DIR / "ingest_valid.csv", "text/csv")
    resp = client.post(
        "/internal/ingestion/run",
        files=files,
        data={"format": "csv"},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 409


def test_ingestion_history_listing(client):
    files = _file_payload(DATA_DIR / "ingest_valid.csv", "text/csv")
    run = client.post(
        "/internal/ingestion/dry-run",
        files=files,
        data={"format": "csv", "source_ref": "hist-list"},
        headers=API_KEY_HEADER,
    )
    assert run.status_code == 200

    resp = client.get("/internal/ingestion/history", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert "job_id" in data[0]


def test_ingestion_history_detail(client):
    files = _file_payload(DATA_DIR / "ingest_valid.csv", "text/csv")
    run = client.post(
        "/internal/ingestion/dry-run",
        files=files,
        data={"format": "csv", "source_ref": "hist-detail"},
        headers=API_KEY_HEADER,
    )
    assert run.status_code == 200
    job_id = run.json()["job"]["job_id"]

    resp = client.get(f"/internal/ingestion/history/{job_id}", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    assert resp.json()["job_id"] == job_id


def test_failure_path_persists_failed_job_record(client, monkeypatch):
    original = ingestion_job_service.IngestService.ingest_records

    def _boom(self, raw_records):  # noqa: ANN001
        raise RuntimeError("forced-failure")

    monkeypatch.setattr(ingestion_job_service.IngestService, "ingest_records", _boom)

    files = _file_payload(DATA_DIR / "ingest_valid.csv", "text/csv")
    resp = client.post(
        "/internal/ingestion/run",
        files=files,
        data={"format": "csv", "source_ref": "forced-failure"},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 500

    with app.state.testing_session_local() as db:
        failed = db.query(IngestionJob).filter(IngestionJob.source_ref == "forced-failure").order_by(IngestionJob.id.desc()).first()
        assert failed is not None
        assert failed.status == "failed"
        assert failed.error_message is not None

    monkeypatch.setattr(ingestion_job_service.IngestService, "ingest_records", original)
