# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
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


def test_replica_merge_behavior(client, monkeypatch):
    # A curated catalogue that trusts its obs_id convention: no checksum needed.
    from app.config import settings
    monkeypatch.setattr(settings, "replica_identity", "metadata")
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


def _record(obs_id, node, **extra):
    return {"obs_id": obs_id, "dataproduct_type": "cube", "node_id": node,
            "access_url": f"https://node-{node.lower()}.example.org/{obs_id}.fits", **extra}


def test_same_obs_id_different_product_is_not_a_replica(client):
    # A Stokes I cube on A and a Stokes Q cube on B, both under the
    # observation's obs_id: different checksums, so B's is refused.
    first = _run_ingestion(client, [_record("obs-123", "A", checksum="aaa", access_estsize=20000)],
                           source_type="manual")
    assert first.skipped_records == 0
    second = _run_ingestion(client, [_record("obs-123", "B", checksum="bbb", access_estsize=20000)],
                            source_type="manual")
    assert second.skipped_records == 1
    assert second.validation_errors[0].code == "replica_conflict"
    assert "checksum bbb here, aaa in the catalogue" in second.validation_errors[0].message
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "obs-123").one()
        assert dataset.checksum == "aaa"                  # not overwritten by the refused record
        assert db.query(DatasetReplica).filter(DatasetReplica.dataset_id == dataset.id).count() == 1


def test_a_true_copy_joins_and_a_size_mismatch_does_not(client):
    _run_ingestion(client, [_record("obs-200", "A", checksum="ccc", access_estsize=500)], source_type="manual")
    copy = _run_ingestion(client, [_record("obs-200", "B", checksum="ccc", access_estsize=500)],
                          source_type="manual")
    assert copy.skipped_records == 0 and copy.inserted_replicas == 1
    # No checksum on the third (a file too large to hash): the size still tells.
    other = _run_ingestion(client, [_record("obs-200", "C", access_estsize=900)], source_type="manual")
    assert other.validation_errors[0].code == "replica_conflict"
    assert "access_estsize" in other.validation_errors[0].message


def test_the_only_holder_may_update_its_file(client):
    _run_ingestion(client, [_record("obs-300", "A", checksum="old", access_estsize=10)], source_type="manual")
    update = _run_ingestion(client, [_record("obs-300", "A", checksum="new", access_estsize=11)],
                            source_type="manual")
    assert update.skipped_records == 0
    with app.state.testing_session_local() as db:
        assert db.query(Dataset).filter(Dataset.obs_id == "obs-300").one().checksum == "new"


def test_a_holder_whose_file_changed_is_refused_and_withdrawn(client):
    # A and B hold the same file; A's file changes. A's new record is refused
    # (B still holds the catalogued product) and A's replica leaves routing,
    # so two different files are never served as one dataset.
    _run_ingestion(client, [_record("obs-350", "A", checksum="xxx", access_estsize=10),
                            _record("obs-350", "B", checksum="xxx", access_estsize=10)],
                   source_type="manual")
    changed = _run_ingestion(client, [_record("obs-350", "A", checksum="yyy", access_estsize=10)],
                             source_type="manual")
    assert changed.skipped_records == 1
    assert changed.validation_errors[0].code == "replica_conflict"
    assert "quarantined" in changed.validation_errors[0].message
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "obs-350").one()
        assert dataset.checksum == "xxx"
        status = {r.node.code: r.status for r in
                  db.query(DatasetReplica).filter(DatasetReplica.dataset_id == dataset.id)}
        assert status == {"A": "quarantined", "B": "available"}
    routing = client.get("/datalink/obs-350").json()["routing"]
    assert [r["code"] for r in routing["replicas"]] == ["B"]
    assert routing["excluded"][0]["code"] == "A"
    # A's file is put back: its record agrees again and the replica returns.
    back = _run_ingestion(client, [_record("obs-350", "A", checksum="xxx", access_estsize=10)],
                          source_type="manual")
    assert back.skipped_records == 0
    with app.state.testing_session_local() as db:
        replicas = db.query(DatasetReplica).join(Dataset).filter(Dataset.obs_id == "obs-350")
        assert {r.status for r in replicas} == {"available"}


def test_a_quarantined_replica_returns_only_with_proof(client):
    # Omitting the checksum that disagreed proves nothing: the replica stays out.
    _run_ingestion(client, [_record("obs-370", "A", checksum="xxx"), _record("obs-370", "B", checksum="xxx")],
                   source_type="manual")
    _run_ingestion(client, [_record("obs-370", "A", checksum="yyy")], source_type="manual")
    silent = [_record("obs-370", "A")]
    assert _run_ingestion(client, silent, source_type="manual", dry_run=True) \
        .validation_errors[0].code == "replica_unverified"
    assert _run_ingestion(client, silent, source_type="manual").validation_errors[0].code == "replica_unverified"
    with app.state.testing_session_local() as db:
        replica = db.query(DatasetReplica).join(Dataset).filter(
            Dataset.obs_id == "obs-370", DatasetReplica.node.has(code="A")).one()
        assert replica.status == "quarantined"
    # The same within one batch, in a dry run and for real.
    batch = [_record("obs-380", "A", checksum="xxx"), _record("obs-380", "B", checksum="xxx"),
             _record("obs-380", "A", checksum="yyy"), _record("obs-380", "A")]
    codes = [e.code for e in _run_ingestion(client, batch, source_type="manual", dry_run=True).validation_errors]
    assert codes == ["replica_conflict", "replica_unverified"]
    codes = [e.code for e in _run_ingestion(client, batch, source_type="manual").validation_errors]
    assert codes == ["replica_conflict", "replica_unverified"]


def test_a_dry_run_reports_the_quarantine_without_doing_it(client):
    _run_ingestion(client, [_record("obs-360", "A", checksum="xxx"), _record("obs-360", "B", checksum="xxx")],
                   source_type="manual")
    dry = _run_ingestion(client, [_record("obs-360", "A", checksum="yyy")], source_type="manual", dry_run=True)
    assert "quarantined" in dry.validation_errors[0].message
    with app.state.testing_session_local() as db:
        replicas = db.query(DatasetReplica).join(Dataset).filter(Dataset.obs_id == "obs-360")
        assert {r.status for r in replicas} == {"available"}


def test_conflicts_within_one_batch_are_caught(client):
    batch = [_record("obs-400", "A", checksum="aaa"), _record("obs-400", "B", checksum="bbb")]
    dry = _run_ingestion(client, batch, source_type="manual", dry_run=True)
    real = _run_ingestion(client, batch, source_type="manual")
    assert dry.skipped_records == real.skipped_records == 1
    assert real.validation_errors[0].code == "replica_conflict"


def test_dry_run_follows_an_update_then_its_copy(client):
    _run_ingestion(client, [_record("obs-500", "A", checksum="old")], source_type="manual")
    batch = [_record("obs-500", "A", checksum="new"), _record("obs-500", "B", checksum="new")]
    dry = _run_ingestion(client, batch, source_type="manual", dry_run=True)
    real = _run_ingestion(client, batch, source_type="manual")
    assert dry.skipped_records == real.skipped_records == 0


def test_a_replaced_file_forgets_what_its_record_does_not_restate(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "replica_identity", "metadata")
    # A replaces its file (new size, no checksum this time): the old checksum
    # must not later refuse B's true copy of the new file.
    _run_ingestion(client, [_record("obs-600", "A", checksum="old", access_estsize=100)], source_type="manual")
    _run_ingestion(client, [_record("obs-600", "A", access_estsize=200)], source_type="manual")
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "obs-600").one()
        assert dataset.checksum is None and dataset.access_estsize == 200
    copy = [_record("obs-600", "B", checksum="new", access_estsize=200)]
    assert _run_ingestion(client, copy, source_type="manual", dry_run=True).skipped_records == 0
    assert _run_ingestion(client, copy, source_type="manual").skipped_records == 0
    # The same within one batch, in a dry run.
    batch = [_record("obs-700", "A", checksum="old", access_estsize=100),
             _record("obs-700", "A", access_estsize=200),
             _record("obs-700", "B", checksum="new", access_estsize=200)]
    assert _run_ingestion(client, batch, source_type="manual", dry_run=True).skipped_records == 0
    real = _run_ingestion(client, batch, source_type="manual")
    assert real.skipped_records == 0 and real.inserted_replicas == 2 and real.updated_replicas == 1



def test_without_checksums_a_new_node_is_not_merged(client):
    # Fail-closed (the default): two products of one observation, equal size
    # and type, no checksum. The second node's record is refused, recorded
    # in the job with the reason, and the dataset keeps one replica.
    _run_ingestion(client, [_record("obs-800", "A", access_estsize=100_000_000)], source_type="manual")
    other = _run_ingestion(client, [_record("obs-800", "B", access_estsize=100_000_000)], source_type="manual")
    assert other.skipped_records == 1
    assert other.validation_errors[0].code == "replica_unverified"
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "obs-800").one()
        assert db.query(DatasetReplica).filter(DatasetReplica.dataset_id == dataset.id).count() == 1
    # The holder publishes its checksum (an update of its own replica): from
    # then on a node with the same checksum joins, one without does not.
    assert _run_ingestion(client, [_record("obs-800", "A", checksum="sha256:x", access_estsize=100_000_000)],
                          source_type="manual").skipped_records == 0
    assert _run_ingestion(client, [_record("obs-800", "B", checksum="sha256:x", access_estsize=100_000_000)],
                          source_type="manual").inserted_replicas == 1
    third = _run_ingestion(client, [_record("obs-800", "C", access_estsize=100_000_000)], source_type="manual")
    assert third.validation_errors[0].code == "replica_unverified"


def test_metadata_mode_accepts_what_does_not_contradict(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "replica_identity", "metadata")
    _run_ingestion(client, [_record("obs-900", "A", access_estsize=10)], source_type="manual")
    assert _run_ingestion(client, [_record("obs-900", "B", access_estsize=10)],
                          source_type="manual").inserted_replicas == 1
