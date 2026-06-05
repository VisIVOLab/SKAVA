# SKAVA Installation Guide

## Prerequisites

- Docker + Docker Compose
- Python 3.11+ (only for local non-docker run)
- PostgreSQL (only for local non-docker run)

## Environment Variables

Use `.env.example` as baseline.

Required for `staging` and `production`:
- `SKAVA_DATABASE_URL`
- `SKAVA_PUBLIC_BASE_URL`

Useful runtime settings:
- `SKAVA_ENV=dev|staging|production`
- `SKAVA_LOG_LEVEL`
- `INTERNAL_API_KEY` (required for `/internal/ingestion/*` endpoints)
- `SKAVA_DB_POOL_SIZE`
- `SKAVA_DB_MAX_OVERFLOW`
- `SKAVA_DB_POOL_TIMEOUT`
- `SKAVA_DB_POOL_RECYCLE`
- `SKAVA_DB_CONNECT_RETRIES`
- `SKAVA_DB_CONNECT_RETRY_DELAY`

## Install and Run (Local Python)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

API URL: `http://localhost:8000`

## Install and Run (Docker Dev)

```bash
docker compose up --build
```

API URL: `http://localhost:8000`

## Install and Run (Staging Stack)

This stack includes:
- `skava-discovery`
- `postgres`
- `reverse-proxy` (nginx)

```bash
docker compose -f docker-compose.staging.yml up --build
```

Ingress URL: `http://localhost:8080`

## Post-Deploy Validation

```bash
curl -s http://localhost:8080/availability?include_nodes=true
curl -s http://localhost:8080/health/db
curl -s http://localhost:8080/metrics | head
curl -s http://localhost:8080/capabilities
```

## Smoke API Checks

```bash
curl 'http://localhost:8080/discovery/dataset/dataset-3'
curl 'http://localhost:8080/discovery/search?COLLECTION=skava-demo&DPTYPE=image'
curl 'http://localhost:8080/access/dataset-3'
```

## Internal Ingestion API Checks

```bash
export INTERNAL_API_KEY='change-me-internal'

curl -X POST 'http://localhost:8080/internal/ingestion/dry-run' \
  -H "X-Internal-Api-Key: ${INTERNAL_API_KEY}" \
  -F "format=csv" \
  -F "source_ref=install-check" \
  -F "file=@tests/data/ingest_valid.csv"

curl -H "X-Internal-Api-Key: ${INTERNAL_API_KEY}" \
  'http://localhost:8080/internal/ingestion/history?limit=10'
```

## Notes

- `/access/{obs_id}` returns routing metadata, not raw file content.
- Service is production-hardened and VO-aligned; it includes a minimal TAP sync profile and DataLink VOTable output, while full TAP/DataLink/SODA server compliance is not claimed yet.
