# Production Readiness Phase 2

This note documents the second hardening tranche for T3.2.

## Implemented Capabilities

### TAP Async

- `POST /tap/async`
- `GET /tap/async/{job_id}`
- persisted job metadata in `tap_jobs`
- immediate execution in the current service profile
- ready to evolve toward a separate async worker queue

### Staging and Prefetch Control Plane

- `POST /staging/jobs?ID=<obs_id>`
- `GET /staging/jobs/{job_id}`
- `POST /soda/execute?ID=<obs_id>` for SODA subset handoff
- persisted job metadata in `staging_jobs`
- current mode: `metadata-cache`
- returns the selected access URL from DataLink routing

This does not yet transfer bytes. It is the control-plane primitive for future data staging, SODA cutout, and prefetch workers.

### Provenance and FAIR Metadata

- `GET /provenance/{obs_id}`
- dataset fields for:
  - `provenance_json`
  - `doi`
  - `pid`
  - `citation`
  - `license`
  - `checksum`
  - source metadata

### Spatial Index Baseline

- `spatial_index_order`
- `spatial_index_cell`
- discovery filter `SPATIAL_CELL`

The current cell implementation is a dependency-free equal-angle key. It is intended as a HEALPix/MOC-ready contract and can be replaced or backfilled with true HEALPix/MOC identifiers.

### SRC-Ready Optional Access Tokens

If `SKAVA_ACCESS_TOKENS` is configured, discovery/access/TAP/SODA/staging/provenance/federation endpoints require:

- `Authorization: Bearer <token>`
- or `X-SKAVA-Access-Token: <token>`

If no tokens are configured, public development behavior is preserved.

### Federated Discovery

- `GET /federation/sources`
- `GET /federation/search`
- peer list configured through `SKAVA_FEDERATED_SRC_URLS`
- best-effort remote querying of peer `/discovery/search` endpoints
- per-source error reporting

### Benchmark Tool

`scripts/benchmark_discovery.py` generates synthetic metadata in SQLite and measures repeated discovery query latency.

Example:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python scripts/benchmark_discovery.py --records 10000 --queries 20
```

## Remaining Gaps

- full TAP async worker execution is not yet separated from API workers
- full ADQL support is not implemented
- SODA validates and persists subset handoff jobs, but does not yet perform byte-level FITS cutout/subsetting execution
- spatial indexing is not true HEALPix/MOC yet
- staging is metadata/control-plane only
- federation is best-effort HTTP querying, not a full SRC broker
- authz is token-based, not full group/project/embargo policy enforcement
