from pathlib import Path

from app.ingestion.parsers.csv_parser import parse_csv_file
from app.ingestion.parsers.json_parser import parse_json_file
from app.ingestion.services.ingest_service import IngestService
from app.main import app
from app.models.dataset import Dataset
from app.models.replica import DatasetReplica


DATA_DIR = Path(__file__).parent / "data"


def _run_ingestion(client, records, **kwargs):
    with app.state.testing_session_local() as db:
        service = IngestService(db, **kwargs)
        summary = service.ingest_records(records)
    return summary


def test_valid_csv_ingestion(client):
    records = parse_csv_file(DATA_DIR / "ingest_valid.csv")
    summary = _run_ingestion(client, records, source_type="csv", source_ref="tests/data/ingest_valid.csv")

    assert summary.total_records == 3
    assert summary.inserted_datasets == 2
    assert summary.updated_datasets == 1
    assert summary.inserted_replicas == 3
    assert summary.skipped_records == 0

    with app.state.testing_session_local() as db:
        dataset_8 = db.query(Dataset).filter(Dataset.obs_id == "dataset-8").one()
        replicas = db.query(DatasetReplica).filter(DatasetReplica.dataset_id == dataset_8.id).all()
        assert len(replicas) == 2


def test_valid_json_ingestion(client):
    records = parse_json_file(DATA_DIR / "ingest_valid.json")
    summary = _run_ingestion(client, records, source_type="json", source_ref="tests/data/ingest_valid.json")

    assert summary.total_records == 2
    assert summary.inserted_datasets == 2
    assert summary.inserted_replicas == 2
    assert summary.skipped_records == 0


def test_dry_run_mode(client):
    records = parse_csv_file(DATA_DIR / "ingest_valid.csv")
    summary = _run_ingestion(client, records, dry_run=True, source_type="csv")

    assert summary.total_records == 3
    with app.state.testing_session_local() as db:
        assert db.query(Dataset).filter(Dataset.obs_id == "dataset-8").first() is None


def test_invalid_record_rejection(client):
    records = parse_csv_file(DATA_DIR / "ingest_invalid.csv")
    summary = _run_ingestion(client, records, source_type="csv")

    assert summary.total_records == 3
    assert summary.skipped_records == 3
    assert len(summary.validation_errors) == 3


def test_upsert_behavior(client):
    records = [
        {
            "obs_id": "dataset-3",
            "obs_collection": "skava-demo",
            "dataproduct_type": "image",
            "target_name": "updated-target-3",
            "node_id": "A",
            "access_url": "https://node-a.example.org/datalink/dataset-3-v2",
        }
    ]
    summary = _run_ingestion(client, records, source_type="manual")

    assert summary.updated_datasets == 1
    assert summary.updated_replicas == 1

    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "dataset-3").one()
        assert dataset.target_name == "updated-target-3"


def test_replica_merge_behavior(client):
    records = [
        {
            "obs_id": "dataset-3",
            "obs_collection": "skava-demo",
            "dataproduct_type": "image",
            "node_id": "C",
            "access_url": "https://node-c.example.org/datalink/dataset-3",
            "is_public": True,
        }
    ]
    summary = _run_ingestion(client, records, source_type="manual")

    assert summary.updated_datasets == 1
    assert summary.inserted_replicas == 1

    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "dataset-3").one()
        replicas = db.query(DatasetReplica).filter(DatasetReplica.dataset_id == dataset.id).all()
        assert len(replicas) == 3


def test_ingestion_summary_correctness(client):
    records = [
        {
            "obs_id": "dataset-12",
            "obs_collection": "skava-mix",
            "dataproduct_type": "image",
            "node_id": "A",
            "access_url": "https://node-a.example.org/datalink/dataset-12",
        },
        {
            "obs_id": "",
            "obs_collection": "skava-mix",
            "dataproduct_type": "image",
            "node_id": "A",
            "access_url": "https://node-a.example.org/datalink/bad",
        },
    ]
    summary = _run_ingestion(client, records, source_type="mixed")

    assert summary.total_records == 2
    assert summary.inserted_datasets == 1
    assert summary.inserted_replicas == 1
    assert summary.skipped_records == 1
    assert len(summary.validation_errors) == 1
