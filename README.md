# SKAVA Data Discovery and Access Service

Production-ready backend service for distributed data discovery and access routing in a SRC-like environment.

## Architecture Summary

- FastAPI application with modular service layers (`routers`, `services`, `ranking`, `vo`).
- PostgreSQL metadata catalog with ObsCore-inspired `datasets` and distributed placement via `dataset_replicas`.
- Ranking policy filters disabled/unavailable nodes and supports fallback to next candidate.
- Access endpoint returns routing metadata (DataLink/SODA precursor), not raw file payloads.
- Structured JSON logging, request tracing, Prometheus metrics, and health endpoints.

## Funding
Funded by INAF under the Astrophysics Fundamental Research Grant (Techno Grant).

## Features

- Discovery: `/discovery/search`, `/discovery/dataset/{obs_id}`
- Canonical DataLink descriptor: `/datalink/{obs_id}`
- SODA sync stub endpoint: `/soda/sync`
- Access routing: `/access/{obs_id}`
- Operational endpoints: `/availability`, `/health/db`, `/metrics`, `/capabilities`
- VO-aligned metadata and capability model (without claiming full TAP/DataLink/SODA server compliance)

## Guides

- Internal ingestion API guide: `docs/internal_ingestion.md`
- Ingestion guide: `docs/ingestion.md`
- Discovery query guide: `docs/discovery_queries.md`
- Access DataLink-like guide: `docs/access_datalink.md`
- Canonical DataLink endpoint guide: `docs/datalink_endpoint.md`
- SODA sync guide: `docs/soda_sync.md`
- Install guide: `docs/install.md`
- Runbook: `docs/runbook.md`
- VO alignment notes: `docs/vo_alignment.md`
- Architecture notes: `docs/architecture.md`

## Configuration

All runtime configuration is environment-driven.

Required in `staging` and `production`:
- `SKAVA_DATABASE_URL`
- `SKAVA_PUBLIC_BASE_URL`

Core variables:
- `INTERNAL_API_KEY` (required for internal ingestion control API)
- `SKAVA_ENV=dev|staging|production`
- `SKAVA_LOG_LEVEL=DEBUG|INFO|WARNING|ERROR`
- `SKAVA_DB_POOL_SIZE`
- `SKAVA_DB_MAX_OVERFLOW`
- `SKAVA_DB_POOL_TIMEOUT`
- `SKAVA_DB_POOL_RECYCLE`
- `SKAVA_DB_CONNECT_RETRIES`
- `SKAVA_DB_CONNECT_RETRY_DELAY`

See `.env.example` for defaults.

## Local Run (dev)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

# PostgreSQL must be available at SKAVA_DATABASE_URL
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

## Docker Run (dev)

```bash
docker compose up --build
```

Service URL: `http://localhost:8000`

## Docker Run (staging stack)

Includes:
- `skava-discovery`
- `postgres`
- `reverse-proxy` (nginx)

```bash
docker compose -f docker-compose.staging.yml up --build
```

Staging ingress URL: `http://localhost:8080`

## API Examples

```bash
curl 'http://localhost:8000/availability?include_nodes=true'
curl 'http://localhost:8000/health/db'
curl 'http://localhost:8000/metrics'
curl 'http://localhost:8000/discovery/search?COLLECTION=skava-demo&DPTYPE=image'
curl 'http://localhost:8000/discovery/search?POS=CIRCLE%20180%20-30%200.2&BAND=1.3e-6%201.4e-6&TIME=59003.1%2059003.4'
curl 'http://localhost:8000/discovery/dataset/dataset-3'
curl 'http://localhost:8000/datalink/dataset-3'
curl 'http://localhost:8000/soda/sync?ID=dataset-3&POS=CIRCLE%20103%20-23%200.05&BAND=1.3e-6%201.4e-6&TIME=59003.1%2059003.3'
curl 'http://localhost:8000/access/dataset-3'
```

Discovery semantics (production-oriented):
- `POS` supports `CIRCLE ra dec radius` with center-based overlap approximation using `s_ra/s_dec` and optional `s_fov`.
- `BAND` requires `min max` and overlaps against `em_min/em_max`.
- `TIME` requires `min max` and overlaps against `t_min/t_max`.

Access semantics (DataLink-like JSON):
- `/datalink/{obs_id}` is the canonical DataLink-like JSON descriptor endpoint.
- `/access/{obs_id}` is a compatibility facade that delegates to `/datalink/{obs_id}` and preserves legacy fields.
- current response is JSON-only and production-ready, designed as a precursor to full VO DataLink serialization.

SODA sync semantics:
- `/soda/sync` validates `ID`, `POS`, `BAND`, `TIME`, `RESPONSEFORMAT` and resolves routing.
- endpoint is operational as a validation/orchestration stub.
- real server-side subsetting execution is not implemented yet.

Example discovery response (abridged):
```json
{
  "metadata": {"obs_id": "dataset-3", "obs_collection": "skava-demo"},
  "replicas": [{"code": "A"}, {"code": "B"}],
  "best_node": "B",
  "access_url": "http://localhost:8000/access/dataset-3"
}
```

Example error response:
```json
{
  "error": {
    "code": "invalid_query",
    "message": "BAND contains non-numeric values"
  },
  "request_id": "..."
}
```

## Testing

```bash
pytest
```

## Standards Position

This service is VO-aligned in production use.
It intentionally does not implement full TAP/ObsTAP, full DataLink, or full SODA processing yet.
