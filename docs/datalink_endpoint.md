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
  content_length, link_auth, link_authorized`) and their spec UCDs, plus the SKAVA
  extensions `node_id`, `rank_reason` and `score` (the routing decision, on the `#this`
  rows);
- semantics expressed with the IVOA vocabulary terms (`#this`, `#preview`, `#auxiliary`,
  `#cutout`, `#proc`);
- a service-descriptor `RESOURCE` (`utype="adhoc:service"`) for each service of the node
  that holds the selected replica (its SODA cutout, synchronous and as a UWS job; the
  moment-map and PV operations for a cube), with an `inputParams` `GROUP` of typed
  parameters and `ID` fixed to the replica's identifier on that node.

The JSON descriptor remains the default response; the VisIVO desktop reads either form
(`service_descriptors` in the JSON, the rows and `RESOURCE`s in the VOTable) and VO
tools (pyvo/TOPCAT) the VOTable. See [api/datalink](api/datalink.md) for the details.

## SODA

- `/soda/sync` validates a SODA request (`ID`, `POS` or `CIRCLE`/`POLYGON`, `BAND`,
  `TIME`) and, when the node holding the selected replica advertises a SODA service,
  answers `303 See Other` to that node's `/soda/sync` with the request's parameters
  and `ID` replaced by the replica's identifier there; a standard client follows it
  and gets the cutout from the node. Without such a node service it answers the
  routing descriptor as JSON (the stub behaviour) — see [SODA sync](soda_sync.md).
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
