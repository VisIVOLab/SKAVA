# DataLink Endpoint

## Overview

`GET /datalink/{obs_id}` is the canonical DataLink-like JSON descriptor endpoint.

`GET /access/{obs_id}` remains available as a compatibility facade and delegates to the same internal resolution logic.

## Endpoint Roles

- `/datalink/{obs_id}`:
  - canonical access descriptor endpoint
  - returns only DataLink-like envelope fields
- `/access/{obs_id}`:
  - legacy-compatible endpoint
  - keeps historical fields (`obs_id`, `best_node`, `access_url`, ...)
  - reuses the same datalink resolution output internally

## /datalink Response Shape

```json
{
  "dataset": {},
  "routing": {},
  "primary_access": {},
  "links": [],
  "service_descriptors": [],
  "capabilities": {}
}
```

## Relationship with Future VO Compliance

Current implementation is JSON-only and production-ready.
It is designed so it can evolve toward full IVOA DataLink serialization (for example VOTable links output) without changing core service logic.

`/soda/sync` is now exposed as an operational stub endpoint for SODA request validation and routing orchestration.
Actual SODA subset execution is not implemented yet.

## Curl Examples

```bash
curl 'http://localhost:8000/datalink/dataset-3'
curl 'http://localhost:8000/soda/sync?ID=dataset-3'
curl 'http://localhost:8000/access/dataset-3'
```
