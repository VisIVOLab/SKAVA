# SODA API

`GET /soda/sync` and `POST /soda/execute` on SKAVA; the SODA services
themselves run on the nodes.

```{note}
SODA is node-local. The VisIVO backend of a node is a SODA service:
`/soda/sync` (SODA 1.0: `CIRCLE`, `RANGE` and `POLYGON` positions, `BAND`,
`TIME`) and `/soda/async`, a UWS 1.1 job list that also runs two operations
beyond the cutout, selected by `OPERATION=MOMENT` (a moment map) and
`OPERATION=PV` (a position-velocity diagram). SKAVA never touches the
bytes: its DataLink advertises the chosen node's services for each dataset
(`node-soda-sync`, `node-soda-async`, see [DataLink](datalink)), with the
replica's own `ID`, and SKAVA's own `/soda/sync` **redirects** (303) a
request to that node's service. `/soda/execute` is a non-standard proxy
cutout kept for clients that cannot follow the DataLink descriptors.
```

## Endpoints

```{list-table}
:header-rows: 1
:widths: 25 18 57

* - Endpoint
  - Status
  - Notes
* - ``GET /soda/sync``
  - redirect / validation
  - ``303`` to the SODA service of the node that holds the dataset in
    place (the ranked first with a co-located backend), the replica's own
    ``ID`` substituted and the request's parameters carried over. When no
    node can process the dataset in place: a JSON descriptor (parameter
    validation + routing decision), no pixels.
* - ``POST /soda/execute``
  - real cutout / fallback
  - Streams ``application/fits`` when a node holding the dataset has a
    co-located VisIVO backend + ``file://`` replica (first in ranking
    order); otherwise returns a staging handoff JSON job.
* - node ``/soda/async``
  - on the node
  - The UWS job list of the node's backend (``PHASE=RUN``, ``ABORT``,
    results, error, destruction), advertised in DataLink as
    ``node-soda-async``; SKAVA has no job list of its own.
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

Delegation goes to the first replica, in ranking order, whose node has
``visivo_backend_url`` set and whose access URL is ``file://`` — the same rule
DataLink uses to advertise the cutout, so an advertised cutout is one that
runs. A reachable backend that fails the
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

This is the answer when no node can process the dataset in place; otherwise
`/soda/sync` redirects to the node's SODA service, which answers with the
pixels.

### `/soda/execute` execution flow

1. SKAVA resolves the dataset and its ranked replicas.
2. The first replica that is a `file://` copy on a node with a co-located
   VisIVO backend is chosen; SKAVA POSTs the cutout request to that node's
   `/v1/datasets/cutout`. `X-Soda-Executed-On` names the node.
3. The backend opens the FITS locally, applies `POS`/`BAND` with astropy,
   and returns the subset; SKAVA streams it back as `application/fits`
   with `X-Soda-Applied` / `X-Soda-Executed-On` headers.
4. If no co-located backend is available, SKAVA returns a metadata-cache
   staging handoff JSON instead.

Asynchronous SODA is the node's: a client that follows the DataLink
descriptor `node-soda-async` creates a UWS job on the node's backend
(`POST /soda/async` with the SODA parameters and `PHASE=RUN`), polls its
phase, and reads the product from its result link; `OPERATION=MOMENT` and
`OPERATION=PV` run a moment map and a position-velocity diagram the same
way. The VisIVO Visual Analytics desktop drives these jobs for the
operations it offers next to the data.

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
