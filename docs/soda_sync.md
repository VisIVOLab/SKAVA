# SODA Sync Endpoint (Stub)

## Overview

`GET /soda/sync` is an operational, production-safe SODA sync stub endpoint.

It validates SODA-like parameters, resolves dataset routing, and returns a structured orchestration response.
It does **not** execute server-side data subsetting yet.

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

## DataLink Integration

`/datalink/{obs_id}` advertises `soda-sync` as enabled at endpoint level.

Capability distinction:
- endpoint availability: `supports_soda_sync_endpoint = true`
- execution capability: `supports_soda_sync_execution = false`

