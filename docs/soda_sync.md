# SODA Endpoints (sync validation + execute)

## Overview

SKAVA exposes two SODA-oriented endpoints:

- `GET /soda/sync` — an operational, production-safe SODA **validation/orchestration**
  endpoint. It validates SODA-like parameters, resolves dataset routing, and returns a
  structured JSON descriptor. It does **not** stream pixels itself.
- `POST /soda/execute` — performs a **real byte-level FITS cutout** when the dataset's
  best node runs a co-located VisIVO backend and serves a `file://` replica. The cutout
  is computed *on the node* (compute-next-to-data) and the resulting FITS is streamed
  back. When no such backend is available, it falls back to a metadata-cache staging
  handoff (the previous behaviour). See [SODA execution](soda_execution.md).

## Supported Parameters

Required:
- `ID`

Optional:
- `POS` (`CIRCLE ra dec radius`)
- `BAND` (`min max`)
- `TIME` (`min max`)
- `RESPONSEFORMAT`

`RESPONSEFORMAT` currently accepts placeholder values:
- `application/fits`
- `image/fits`
- `application/octet-stream`
- `application/json`

## Behavior

The endpoint:
1. validates query parameters
2. resolves dataset and best available node
3. returns a stable JSON stub response describing the planned subset operation

## Curl Examples

```bash
curl 'http://localhost:8000/soda/sync?ID=dataset-3'

curl 'http://localhost:8000/soda/sync?ID=dataset-3&POS=CIRCLE%20103%20-23%200.05&BAND=1.3e-6%201.4e-6&TIME=59003.1%2059003.3&RESPONSEFORMAT=image/fits'
```

## Example Success Response (abridged)

```json
{
  "status": "accepted",
  "mode": "soda-sync-stub",
  "dataset": {"obs_id": "dataset-3"},
  "routing": {"best_node": "B", "access_url": "https://node-b.example.org/datalink/dataset-3"},
  "request": {"ID": "dataset-3", "POS": "CIRCLE 103.0 -23.0 0.05"},
  "operation": {
    "type": "subset",
    "supports_execution": false,
    "message": "SODA sync endpoint is declared and validated, but server-side processing is not implemented yet."
  },
  "next_step": {
    "planned_backend": "future remote cutout/subset service",
    "datalink": "http://localhost:8000/datalink/dataset-3"
  }
}
```

## Error Semantics

- `400` invalid/malformed request parameters or missing `ID`
- `404` dataset not found
- `503` no available replicas

## `/soda/execute` — real cutout vs staging fallback

`POST /soda/execute` resolves the dataset, picks the best node, then:

1. **If** the node has `visivo_backend_url` **and** its replica is a `file://` URL,
   SKAVA POSTs the cutout request to the node's `/v1/datasets/cutout` and streams the
   resulting `application/fits` back to the caller. Response headers:
   - `X-Soda-Applied`: which subsets were applied (e.g. `pos,band`)
   - `X-Soda-Executed-On`: the node code that ran the cutout
2. **Else**, it falls back to a metadata-cache staging handoff and returns the legacy
   JSON job descriptor.

A node backend that is reachable but rejects/fails the request surfaces as
`502 backend_execution_failed`.

```bash
# Real cutout (node has a co-located VisIVO backend + file:// replica)
curl -X POST 'http://localhost:8000/soda/execute?ID=dataset-3&POS=CIRCLE%20103%20-23%200.05' -o cutout.fits
```

## DataLink Integration

`/datalink/{obs_id}` advertises `soda-sync` as enabled at endpoint level, and the
`cutout` service descriptor is enabled when execution is available for the dataset.

Capability distinction (per dataset):
- endpoint availability: `supports_soda_sync_endpoint = true` (always)
- execution capability: `supports_soda_sync_execution = true` **only when** at least one
  ranked node for the dataset exposes a co-located VisIVO backend; otherwise `false`.

