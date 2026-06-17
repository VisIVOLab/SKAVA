# SKAVA Metadata Ingestion

## Scope

The ingestion subsystem is metadata-only:
- extracts metadata from manifests
- normalizes and validates records
- upserts datasets and replica availability into catalog tables

Out of scope:
- data file copying/moving
- node-to-node transfer
- heavy FITS processing pipelines

## Package Layout

`app/ingestion/`
- `base.py`: core ingestion dataclasses and summary model
- `parsers/json_parser.py`: JSON manifest parser
- `parsers/csv_parser.py`: CSV manifest parser
- `normalizers/obscore_normalizer.py`: maps external fields to SKAVA ObsCore-oriented record
- `validators/metadata_validator.py`: required/type validations
- `services/ingest_service.py`: DB upsert orchestration + dry-run + summary
- `cli.py`: command-line interface

## Input Model (First Version)

Supported source formats:
- JSON
- CSV

Expected conceptual fields per record:
- `obs_id`, `obs_collection`, `dataproduct_type`, `calib_level`, `target_name`
- `s_ra`, `s_dec`, `t_min`, `t_max`, `em_min`, `em_max`
- `access_format`, `access_estsize`
- `node_id`, `access_url`, `is_public`
- optional bookkeeping: `source_type`, `source_ref`, `checksum`

One record can represent one replica. Multiple records with same `obs_id` merge into one dataset + many replicas.

## Validation Rules

Required fields:
- `obs_id`
- `dataproduct_type`
- `node_id`
- `access_url`

Additional checks:
- `access_url` must start with `http://` or `https://`
- coordinate/time/range sanity checks where provided

Invalid records are skipped and collected as structured ingestion errors.

## Upsert Behavior

Datasets:
- upsert by `obs_id`
- update mutable metadata fields
- update ingestion bookkeeping (`ingested_at`, `updated_at`, `source_type`, `source_ref`, `checksum`)

Replicas:
- upsert by `(dataset_id, node_id)`
- update `access_endpoint`, `status`, `is_public`
- insert missing replicas

## Dry Run

`--dry-run` parses and validates all records, computes insert/update outcomes, and rolls back DB writes.

## CLI Usage

```bash
python -m app.ingestion.cli --file ./tests/data/ingest_valid.csv --format csv
python -m app.ingestion.cli --file ./tests/data/ingest_valid.json --format json --dry-run
python -m app.ingestion.cli --file ./tests/data/ingest_valid.csv --format csv --source-type catalog --source-ref nightly-import
```

## Summary Output

CLI outputs ingestion summary JSON with:
- total records processed
- inserted/updated datasets
- inserted/updated replicas
- skipped records
- validation errors
