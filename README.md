# SKAVA Data Discovery and Access Service

Production-hardened backend service for distributed data discovery and access routing in a SRC-like environment.

## Architecture Summary

- FastAPI application with modular service layers (`routers`, `services`, `ranking`, `vo`).
- PostgreSQL metadata catalog with ObsCore-inspired `datasets` and distributed placement via `dataset_replicas`.
- Ranking policy filters disabled/unavailable nodes and supports fallback to next candidate.
- Access endpoint returns routing metadata; `/soda/execute` performs real node-local FITS cutouts (compute-next-to-data) without moving the dataset.
- Structured JSON logging, request tracing, Prometheus metrics, and health endpoints.

## Funding
Funded by INAF under the Astrophysics Fundamental Research Grant (Techno Grant).

## Features

- Discovery: `/discovery/search`, `/discovery/dataset/{obs_id}`
- Canonical DataLink descriptor: `/datalink/{obs_id}`
- TAP sync ObsCore compatibility profile: `/tap/sync`
- TAP async job profile: `/tap/async`
- SODA sync validation endpoint: `/soda/sync`
- SODA cutout execution (node-local, compute-next-to-data): `/soda/execute`
- Metadata-cache staging: `/staging/jobs`
- Provenance/PID/citation endpoint: `/provenance/{obs_id}`
- Federated discovery peer queries: `/federation/search`
- Access routing: `/access/{obs_id}`
- Operational endpoints: `/availability`, `/health/db`, `/metrics`, `/capabilities`
- VO-aligned metadata and capability model (without claiming full TAP/DataLink/SODA server compliance)

## Guides

- Internal ingestion API guide: `docs/internal_ingestion.md`
- Ingestion guide: `docs/ingestion.md`
- Discovery query guide: `docs/discovery_queries.md`
- Access DataLink-like guide: `docs/access_datalink.md`
- Canonical DataLink endpoint guide: `docs/datalink_endpoint.md`
- TAP sync guide: `docs/tap_sync.md`
- SODA sync guide: `docs/soda_sync.md`
- SODA execution (compute-next-to-data) guide: `docs/soda_execution.md`
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
- `SKAVA_ACCESS_TOKENS` (optional comma-separated bearer tokens for discovery/access endpoints)
- `SKAVA_FEDERATED_SRC_URLS` (optional comma-separated peer base URLs)
- `SKAVA_FEDERATION_TIMEOUT_SECONDS`
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
curl 'http://localhost:8000/datalink/dataset-3?RESPONSEFORMAT=application/x-votable+xml'
curl 'http://localhost:8000/tap/sync?QUERY=SELECT%20TOP%201%20*%20FROM%20ivoa.ObsCore%20WHERE%20obs_id%20%3D%20%27dataset-3%27'
curl -X POST 'http://localhost:8000/tap/async' -F 'QUERY=SELECT TOP 1 * FROM ivoa.ObsCore WHERE obs_id = '\''dataset-3'\'''
curl 'http://localhost:8000/soda/sync?ID=dataset-3&POS=CIRCLE%20103%20-23%200.05&BAND=1.3e-6%201.4e-6&TIME=59003.1%2059003.3'
curl -X POST 'http://localhost:8000/soda/execute?ID=dataset-3&POS=CIRCLE%20103%20-23%200.05' -o cutout.fits
curl -X POST 'http://localhost:8000/staging/jobs?ID=dataset-3'
curl 'http://localhost:8000/provenance/dataset-3'
curl 'http://localhost:8000/federation/sources'
curl 'http://localhost:8000/access/dataset-3'
```

Discovery semantics (production-oriented):
- `POS` supports `CIRCLE ra dec radius` with center-based overlap approximation using `s_ra/s_dec` and optional `s_fov`.
- `BAND` requires `min max` and overlaps against `em_min/em_max`.
- `TIME` requires `min max` and overlaps against `t_min/t_max`.
- `limit` and `offset` bound result sets for production-safe scans.
- `SPATIAL_CELL` can filter the lightweight HEALPix/MOC-ready spatial cell key exposed in metadata.

Access semantics (DataLink):
- `/datalink/{obs_id}` is the canonical access descriptor endpoint (JSON by default).
- `/datalink/{obs_id}?RESPONSEFORMAT=application/x-votable+xml` returns a **conformant IVOA
  DataLink VOTable**: standard `{links}` columns with spec UCDs, `#`-prefixed semantics
  terms, and a SODA cutout service descriptor (`utype="adhoc:service"`) — consumable by
  pyvo/TOPCAT.
- `/access/{obs_id}` is a compatibility facade that delegates to `/datalink/{obs_id}` and preserves legacy fields.

TAP sync semantics:
- `/tap/sync` provides a minimal ObsCore compatibility profile.
- Supported ADQL is intentionally constrained to `SELECT` from `ivoa.ObsCore` with equality predicates for `obs_id`, `obs_collection`, and `dataproduct_type`.
- Default output is VOTable; use `FORMAT=json` for JSON.
- `/tap/async` persists TAP jobs and returns job status/results. In the current profile jobs execute immediately; the storage model is ready for a future worker queue.

Staging semantics:
- `/staging/jobs` creates a metadata-cache staging handoff and returns the selected access URL.
- This does not yet perform byte-level data movement; it is the control-plane primitive for future prefetch/staging workers.

Federation semantics:
- `/federation/search` queries configured peer `/discovery/search` endpoints using `SKAVA_FEDERATED_SRC_URLS`.
- Failures are reported per source without failing the whole response.

SODA semantics:
- `/soda/sync` validates `ID`, `POS`, `BAND`, `TIME`, `RESPONSEFORMAT` and resolves routing (JSON descriptor).
- `/soda/execute` performs a **real byte-level FITS cutout** when the dataset's best node
  exposes a co-located VisIVO backend (`Node.visivo_backend_url`) serving a `file://`
  replica: SKAVA delegates to the node's `/v1/datasets/cutout`, the cutout is computed on
  the node, and `application/fits` is streamed back (compute-next-to-data).
- When no co-located backend is available, `/soda/execute` falls back to a metadata-cache
  staging handoff (legacy behaviour).
- A reachable backend that fails the cutout surfaces as `502 backend_execution_failed`.
- See `docs/soda_execution.md` for the delegation design and the backend endpoint.

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

This service is VO-aligned in production use:
- DataLink is served both as JSON and as a conformant IVOA DataLink VOTable descriptor;
- SODA cutout execution (`POS`/`BAND`) is implemented via compute-next-to-data delegation
  to a node's co-located VisIVO backend, with a staging-handoff fallback.

It intentionally does not yet implement full TAP async / full ADQL, asynchronous
DataLink/SODA job services, or full standard-server compliance across all operations.
