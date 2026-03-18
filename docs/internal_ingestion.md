# Internal Ingestion Control API

## Purpose

Operational/internal API for controlled triggering of metadata ingestion jobs.

Scope:
- metadata-only ingestion
- dry-run and real execution
- job history and auditing

Out of scope:
- scientific data transfer
- public data-management API
- scheduler/queue/OIDC

## Protection

All endpoints under `/internal/ingestion/*` require:
- header: `X-Internal-Api-Key`
- value from env: `INTERNAL_API_KEY` (or `SKAVA_INTERNAL_API_KEY`)

Invalid/missing key returns `401`.

## Endpoints

- `POST /internal/ingestion/dry-run`
- `POST /internal/ingestion/run`
- `GET /internal/ingestion/history`
- `GET /internal/ingestion/history/{job_id}`

## Upload Handling

- Accepts `UploadFile` multipart
- Formats supported: `csv`, `json`
- Format from explicit `format` field or filename extension
- Unsupported format -> `400`

## Concurrency Control

Only one `running` ingestion job at a time, enforced DB-side via unique partial index on `ingestion_jobs(status)` where status is `running`.

Concurrent run request returns `409`.

## Curl Examples

```bash
export INTERNAL_API_KEY='your-key'

curl -X POST 'http://localhost:8000/internal/ingestion/dry-run' \
  -H "X-Internal-Api-Key: ${INTERNAL_API_KEY}" \
  -F "format=csv" \
  -F "source_ref=nightly-check" \
  -F "file=@tests/data/ingest_valid.csv"

curl -X POST 'http://localhost:8000/internal/ingestion/run' \
  -H "X-Internal-Api-Key: ${INTERNAL_API_KEY}" \
  -F "format=json" \
  -F "source_ref=nightly-run" \
  -F "file=@tests/data/ingest_valid.json"

curl -H "X-Internal-Api-Key: ${INTERNAL_API_KEY}" \
  'http://localhost:8000/internal/ingestion/history?limit=20'
```
