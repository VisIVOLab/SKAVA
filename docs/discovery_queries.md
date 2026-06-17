# Discovery Query Guide

## Supported Scientific Parameters

`GET /discovery/search` supports VO-style parameters:
- `POS`
- `BAND`
- `TIME`
- plus existing filters: `COLLECTION`, `DPTYPE`, `obs_id`
- `SPATIAL_CELL`
- production safety controls: `limit`, `offset`

All filters are combined with AND semantics.

Results are paginated. Defaults:
- `limit=100`
- `offset=0`

Limits:
- `limit` must be between `1` and `1000`
- `offset` must be non-negative and no larger than `1000000`

## Syntax

### POS

Currently supported shape:
- `POS=CIRCLE <ra> <dec> <radius>`

Example:
- `POS=CIRCLE 103 -23 0.05`

Validation:
- only `CIRCLE` is supported
- numeric values required
- `ra` in `[0, 360]`
- `dec` in `[-90, 90]`
- `radius > 0`

Current overlap behavior:
- practical approximation using `s_ra`, `s_dec`, and optional `s_fov`
- dataset center distance is compared to `radius + (s_fov / 2)`
- this is a production-safe approximation, not full region geometry intersection

### BAND

Syntax:
- `BAND=<min> <max>`

Example:
- `BAND=1.3e-6 1.4e-6`

Semantics:
- overlap against dataset `em_min/em_max`

Validation:
- exactly two numeric values
- `min <= max`

### TIME

Syntax:
- `TIME=<min> <max>`

Example:
- `TIME=59003.1 59003.4`

Semantics:
- overlap against dataset `t_min/t_max`

Validation:
- exactly two numeric values
- `min <= max`

## Curl Examples

```bash
curl 'http://localhost:8000/discovery/search?POS=CIRCLE%20103%20-23%200.05'

curl 'http://localhost:8000/discovery/search?BAND=1.3e-6%201.4e-6&TIME=59003.1%2059003.4'

curl 'http://localhost:8000/discovery/search?POS=CIRCLE%20103%20-23%200.05&BAND=1.3e-6%201.4e-6&TIME=59003.1%2059003.4'

curl 'http://localhost:8000/discovery/search?COLLECTION=skava-demo&DPTYPE=image'

curl 'http://localhost:8000/discovery/search?COLLECTION=skava-demo&DPTYPE=image&limit=50&offset=0'

curl 'http://localhost:8000/discovery/search?SPATIAL_CELL=order8:ra146:dec95'
```

## Error Model

Malformed scientific parameters return structured `400` responses:

```json
{
  "error": {
    "code": "invalid_query",
    "message": "BAND must contain exactly two numeric values"
  },
  "request_id": "..."
}
```

## Future Evolution

Planned incremental improvements:
- richer sky region support beyond `CIRCLE`
- more complete VO region semantics
- replacement/backfill of the current dependency-free spatial cell with true HEALPix/MOC identifiers
- broader TAP/ObsTAP query coverage beyond the current minimal sync profile
