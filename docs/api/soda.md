# SODA API

`POST /soda/sync` and (planned) `POST /soda/async` — IVOA
SODA-compatible endpoints for server-side operations on data access.

```{note}
The sync endpoint currently **validates the request and routes**
through the federation logic but does not yet execute the cutout
itself. Result is a response indicating "would have routed to node
X" without the materialised file. Full execution is on the roadmap.
```

## Endpoints

```{list-table}
:header-rows: 1
:widths: 25 18 57

* - Endpoint
  - Status
  - Notes
* - ``POST /soda/sync``
  - validating only
  - JSON body. Returns parameter-validation result + the routing
    decision that would be applied if execution were enabled.
* - ``POST /soda/async``
  - placeholder (501)
  - Reserved for the future async job interface. Reachable only
    when ``capabilities.supports_soda_async`` is true.
```

## Sync request

```bash
curl -s -X POST "https://skava.inaf.it/soda/sync" \
    -H "Content-Type: application/json" \
    -d '{
          "ID": "power9-3a7f1b2c0e5d4986",
          "POS": "CIRCLE 83.6 22.0 0.1",
          "BAND": "1.4e-3 2.1e-3",
          "TIME": "59010.0 59010.5",
          "RESPONSEFORMAT": "application/fits"
        }' | jq
```

### Parameters

```{list-table}
:header-rows: 1
:widths: 20 14 12 54

* - Name
  - Type
  - Required?
  - Meaning
* - ``ID``
  - str
  - **yes**
  - obs_id of the dataset to operate on.
* - ``POS``
  - str
  - no
  - SODA-standard geometry: ``CIRCLE ra dec radius`` \| ``RANGE …`` \|
    ``POLYGON …``. Decimal degrees.
* - ``BAND``
  - str ``"min max"``
  - no
  - Wavelength range in metres.
* - ``TIME``
  - str ``"min max"``
  - no
  - Time range in MJD.
* - ``RESPONSEFORMAT``
  - str
  - no
  - ``application/fits`` (default) or ``image/png``.
```

### Response

```json
{
    "valid":  true,
    "error":  "",
    "obs_id": "power9-3a7f1b2c0e5d4986",
    "routing": {
        "best_node": "POWER9",
        "access_endpoint": "http://pleiadi-gpu.oact.inaf.it:8001/data/crab.fits",
        "would_execute_at": "POWER9"
    },
    "operations_planned": [
        {"type": "POS", "value": "CIRCLE 83.6 22.0 0.1"},
        {"type": "BAND", "value": "1.4e-3 2.1e-3"}
    ],
    "execution_status": "not-implemented"
}
```

When `valid=false`, `error` holds the human message and
`details[]` carries the structured per-parameter errors.

## What execution will look like (roadmap)

Phase 2 of the SODA work plan:

1. Sync endpoint stays the same on the wire.
2. SKAVA dispatches the request to the VisIVO backend at the
   chosen node (using its existing cube cutout API).
3. Backend returns the cutout bytes; SKAVA streams them with the
   `RESPONSEFORMAT` Content-Type.
4. `execution_status` becomes one of `success`, `partial`, `failed`.

For async:

1. Submit returns a 303 with `Location: /soda/async/jobs/{id}`.
2. Job lifecycle endpoints: GET `/jobs/{id}` (status), GET
   `/jobs/{id}/results` (bytes when done), DELETE `/jobs/{id}`
   (abort).
3. Worker pool processes jobs out of the request thread.

The HTTP surface is stable today; only the implementation backing it
will change.

## Use from VO tools

Aladin and TOPCAT understand the SODA descriptors emitted by the
DataLink endpoint. Once execution lands, the existing client UI for
"apply cutout" will work transparently against SKAVA's `/soda/sync`.

## Errors

```{list-table}
:header-rows: 1
:widths: 18 82

* - Status
  - When
* - 200
  - Request parsed and (would-be) routed. ``valid`` field tells
    you whether parameters passed schema checks.
* - 400
  - Body not JSON, missing ``ID``, unrecognised parameter.
* - 404
  - obs_id unknown.
* - 501
  - Async endpoint reached (capabilities advertise it as disabled
    today).
```

## See also

* [DataLink API](datalink) where the SODA service descriptor lives.
* [Architecture / overview](../architecture/overview) for why
  routing is decoupled from execution.
