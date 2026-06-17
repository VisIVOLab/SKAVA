# DataLink Endpoint

## Overview

`GET /datalink/{obs_id}` is the canonical DataLink descriptor endpoint.
It returns JSON by default and a conformant IVOA DataLink VOTable when requested with:

- `RESPONSEFORMAT=application/x-votable+xml`
- `FORMAT=votable`

`GET /access/{obs_id}` remains available as a compatibility facade and delegates to the same internal resolution logic.

## Endpoint Roles

- `/datalink/{obs_id}`:
  - canonical access descriptor endpoint
  - returns DataLink-like JSON by default
  - returns VOTable link rows for VO-oriented clients
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

## VOTable serialisation (IVOA DataLink)

With `RESPONSEFORMAT=application/x-votable+xml` (or `FORMAT=votable`), the endpoint
returns a **conformant IVOA DataLink VOTable**:

- a `{links}` results table with the standard columns
  (`ID, access_url, service_def, error_message, semantics, description, content_type,
  content_length`, plus the SKAVA `node_id` extension) and their spec UCDs;
- semantics expressed with the IVOA vocabulary terms (`#this`, `#preview`, `#cutout`, …);
- a service-descriptor `RESOURCE` (`utype="adhoc:service"`) for the SODA cutout, with an
  `inputParams` `GROUP` (`ID` ref + `POS`/`BAND`/`TIME`) pointing at `/soda/execute`.

The JSON descriptor remains the default response and is what the VisIVO desktop consumes
(via `service_descriptors`); the VOTable targets VO tools (pyvo/TOPCAT).

## SODA

- `/soda/sync` validates SODA requests and returns a routing descriptor.
- `/soda/execute` performs a real cutout (node-local delegation) with staging fallback —
  see [SODA execution](soda_execution.md).

## Curl Examples

```bash
curl 'http://localhost:8000/datalink/dataset-3'
curl 'http://localhost:8000/datalink/dataset-3?RESPONSEFORMAT=application/x-votable+xml'
curl 'http://localhost:8000/soda/sync?ID=dataset-3'
curl -X POST 'http://localhost:8000/soda/execute?ID=dataset-3&POS=CIRCLE%20103%20-23%200.05' -o cutout.fits
curl 'http://localhost:8000/access/dataset-3'
```
