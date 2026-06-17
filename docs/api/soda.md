# SODA API

`GET /soda/sync`, `POST /soda/execute`, and (planned) `POST /soda/async`
— IVOA SODA-oriented endpoints for server-side operations on data access.

```{note}
`/soda/sync` **validates and routes** a SODA request and returns a JSON
descriptor. `/soda/execute` **performs a real byte-level FITS cutout**:
when the dataset's best node runs a co-located VisIVO backend serving a
`file://` replica, SKAVA delegates the cutout to that backend
(`/v1/datasets/cutout`), which computes it in place (compute-next-to-data)
and streams the FITS back. Otherwise `/soda/execute` falls back to a
metadata-cache staging handoff.
```

## Endpoints

```{list-table}
:header-rows: 1
:widths: 25 18 57

* - Endpoint
  - Status
  - Notes
* - ``GET /soda/sync``
  - validation + routing
  - Returns a JSON descriptor (parameter validation + routing decision).
    Does not stream pixels.
* - ``POST /soda/execute``
  - real cutout / fallback
  - Streams ``application/fits`` when the best node has a co-located
    VisIVO backend + ``file://`` replica; otherwise returns a staging
    handoff JSON job.
* - ``POST /soda/async``
  - placeholder (disabled)
  - Reserved for the future async job interface. Advertised via
    ``capabilities.supports_soda_async`` (false today).
```

## Execute request (real cutout)

```bash
curl -s -X POST \
    "https://skava.inaf.it/soda/execute?ID=power9-3a7f1b2c0e5d4986&POS=CIRCLE%2083.6%2022.0%200.1&BAND=1.4e-3%202.1e-3" \
    -o crab_cutout.fits
# Response headers on success:
#   Content-Type: application/fits
#   X-Soda-Applied: pos,band
#   X-Soda-Executed-On: POWER9
```

Delegation requires the best node to have ``visivo_backend_url`` set and
the replica to be a ``file://`` URL. A reachable backend that fails the
cutout returns ``502 backend_execution_failed``. See
[SODA execution](../soda_execution) for the design.

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

### `/soda/sync` response (validation descriptor)

```json
{
    "status": "accepted",
    "mode": "soda-sync-stub",
    "dataset": {"obs_id": "power9-3a7f1b2c0e5d4986"},
    "routing": {"best_node": "POWER9", "access_url": "file:///data/crab.fits"},
    "request": {"ID": "power9-3a7f1b2c0e5d4986", "POS": "CIRCLE 83.6 22.0 0.1"},
    "operation": {"type": "subset", "supports_execution": false},
    "next_step": {"datalink": "https://skava.inaf.it/datalink/power9-3a7f1b2c0e5d4986"}
}
```

`/soda/sync` validates and routes only; use `/soda/execute` to get pixels.

### `/soda/execute` execution flow

1. SKAVA resolves the dataset and its best node.
2. If the node has a co-located VisIVO backend **and** a `file://` replica,
   SKAVA POSTs the cutout request to the node's `/v1/datasets/cutout`.
3. The backend opens the FITS locally, applies `POS`/`BAND` with astropy,
   and returns the subset; SKAVA streams it back as `application/fits`
   with `X-Soda-Applied` / `X-Soda-Executed-On` headers.
4. If no co-located backend is available, SKAVA returns a metadata-cache
   staging handoff JSON instead.

Async SODA (`/soda/async`) with a job queue and lifecycle endpoints
remains future work; the HTTP surface above is stable.

## Use from VO tools

Aladin and TOPCAT understand the SODA descriptors emitted by the DataLink
endpoint (`utype="adhoc:service"`, `standardID = SODA#sync-1.0`, pointing
at `/soda/execute`). Their "apply cutout" UI works against SKAVA's
`/soda/execute` for datasets whose node runs a co-located VisIVO backend.

## Errors

```{list-table}
:header-rows: 1
:widths: 18 82

* - Status
  - When
* - 200
  - `/soda/sync`: validated + routed. `/soda/execute`: streamed cutout,
    or staging-handoff JSON when no co-located backend.
* - 400
  - Missing ``ID``, malformed/unsupported ``POS``/``BAND``/``TIME``, or a
    region that does not overlap the dataset.
* - 404
  - obs_id unknown.
* - 502
  - ``backend_execution_failed`` — node backend reachable but the cutout
    failed or timed out.
* - 503
  - No available replicas for the dataset.
```

## See also

* [DataLink API](datalink) where the SODA service descriptor lives.
* [Architecture / overview](../architecture/overview) for why
  routing is decoupled from execution.
