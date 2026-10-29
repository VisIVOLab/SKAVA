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


def test_title_facility_and_instrument_are_stored(client):
    # The publisher's extractors send them; ingestion used to drop all three.
    record = {
        "obs_id": "titled-1", "dataproduct_type": "cube", "node_id": "A",
        "access_url": "https://node-a.example.org/titled-1.fits",
        "obs_title": "HI survey of field 1", "facility_name": "MeerKAT",
        "instrument_name": "L-band",
    }
    summary = _run_ingestion(client, [record], source_type="manual")
    assert summary.skipped_records == 0
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "titled-1").one()
        assert (dataset.obs_title, dataset.facility_name, dataset.instrument_name) == (
            "HI survey of field 1", "MeerKAT", "L-band")

    # A later record without them keeps what is stored (an operator's edit too).
    _run_ingestion(client, [{k: v for k, v in record.items()
                             if k not in ("obs_title", "facility_name", "instrument_name")}],
                   source_type="manual")
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "titled-1").one()
        assert dataset.facility_name == "MeerKAT"


def test_overlong_values_skip_the_record_not_the_batch(client):
    # PostgreSQL enforces column widths (SQLite does not): one long value
    # used to fail the whole run; now only its record is refused.
    good = {"obs_id": "fits-ok", "dataproduct_type": "cube", "node_id": "A",
            "access_url": "https://node-a.example.org/ok.fits"}
    long_target = dict(good, obs_id="too-long-target", target_name="x" * 129)
    long_url = dict(good, obs_id="too-long-url",
                    access_url="https://node-a.example.org/" + "x" * 600)
    summary = _run_ingestion(client, [good, long_target, long_url], source_type="manual")
    assert summary.skipped_records == 2
    reasons = {e.index: e.message for e in summary.validation_errors}
    assert "target_name is longer than 128 characters" in reasons[1]
    assert "access_url is longer than 512 characters" in reasons[2]
    with app.state.testing_session_local() as db:
        assert db.query(Dataset).filter(Dataset.obs_id == "fits-ok").one()
