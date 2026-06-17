# SKAVA VO-aligned Architecture

## Summary

Independent FastAPI + PostgreSQL service for distributed metadata discovery and access routing.
The service is production-hardened and aligned with IVOA concepts.

## Data model

- `nodes`: node identity, endpoint, availability (`is_enabled`, `is_available`), ranking signals.
- `datasets`: ObsCore-practical fields (`obs_id`, `obs_collection`, `dataproduct_type`, `calib_level`, `s_ra`, `s_dec`, `t_min`, `t_max`, `em_min`, `em_max`, etc.).
- `dataset_replicas`: distributed placement and per-node access endpoints.

## API mapping

- `/discovery/search`: ObsCore-style discovery precursor; supports `POS`, `BAND`, `TIME`, `COLLECTION`, `DPTYPE`.
- `/discovery/dataset/{obs_id}`: dataset metadata + available replicas + ranked best node.
- `/access/{obs_id}`: access facade returning routing contract (`best_node`, `access_url`, supported operations).
- `/datalink/{obs_id}`: canonical DataLink descriptor — JSON, or conformant IVOA DataLink VOTable with `RESPONSEFORMAT=application/x-votable+xml`.
- `/soda/sync`: SODA request validation + routing descriptor.
- `/soda/execute`: real node-local FITS cutout via delegation to a node's co-located VisIVO backend (compute-next-to-data), with staging-handoff fallback.
- `/tap/sync`: minimal TAP sync ObsCore compatibility profile for bounded ADQL access.
- `/capabilities`: VOSI-inspired capability declaration.

## Production hardening

- Environment-driven config validation (`dev|staging|production`).
- DB pooling and startup retry logic.
- Structured JSON logs with request IDs.
- Prometheus metrics (`/metrics`).
- Error model standardization (`400`, `404`, `503` with structured payloads).
- Docker multi-stage non-root image and staging reverse-proxy stack.

## Standards status

- ObsCore metadata naming and discovery behavior: aligned.
- DataLink: JSON descriptor + conformant IVOA DataLink VOTable serialisation.
- SODA: `/soda/sync` validation; `/soda/execute` real cutout via node-local delegation
  (compute-next-to-data). Async SODA and full POLYGON geometry are planned.
- TAP/ObsTAP endpoint: minimal sync profile implemented; full TAP async and broad ADQL coverage planned.

## Compute-next-to-data

`/soda/execute` does not move data: when a dataset's best node exposes a co-located
VisIVO backend serving a `file://` replica, SKAVA delegates the byte-level cutout to that
backend (`/v1/datasets/cutout`), which opens the FITS in place and returns only the
subset. See `soda_execution.md`.
