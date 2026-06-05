# TAP Sync and Async ObsCore Compatibility Profile

## Overview

`/tap/sync` provides a minimal production-safe TAP sync compatibility profile for `ivoa.ObsCore`.

It is intentionally constrained:
- synchronous requests only
- `ADQL` only
- `SELECT` from `ivoa.ObsCore`
- equality predicates for `obs_id`, `obs_collection`, and `dataproduct_type`
- `MAXREC` capped at `1000`
- output as VOTable by default or JSON with `FORMAT=json`

This is not a full TAP/ADQL server. It gives VO clients a stable standards-oriented entrypoint while broader TAP/ObsTAP support evolves.

## Endpoints

- `GET /tap/capabilities`
- `GET /tap/sync`
- `POST /tap/sync`
- `POST /tap/async`
- `GET /tap/async/{job_id}`

## Examples

```bash
curl 'http://localhost:8000/tap/capabilities'

curl 'http://localhost:8000/tap/sync?REQUEST=doQuery&LANG=ADQL&QUERY=SELECT%20TOP%201%20*%20FROM%20ivoa.ObsCore%20WHERE%20obs_id%20%3D%20%27dataset-3%27'

curl 'http://localhost:8000/tap/sync?QUERY=SELECT%20*%20FROM%20ivoa.ObsCore%20WHERE%20dataproduct_type%20%3D%20%27image%27&MAXREC=100&FORMAT=json'

curl -X POST 'http://localhost:8000/tap/async' \
  -F 'REQUEST=doQuery' \
  -F 'LANG=ADQL' \
  -F 'QUERY=SELECT TOP 1 * FROM ivoa.ObsCore WHERE obs_id = '\''dataset-3'\''' \
  -F 'FORMAT=json'
```

## Production Safety

- unsupported predicates are rejected with structured `400` errors
- result size is bounded
- queries route through the same discovery service used by `/discovery/search`
- replica eligibility honors dataset replica status and public accessibility
- async jobs are persisted in `tap_jobs`; this implementation executes them immediately and can later be backed by a worker queue
