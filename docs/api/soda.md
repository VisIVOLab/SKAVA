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
(`node-soda-sync`, `node-soda-async`, see [DataLink](datalink.md)), with the
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
  - real cutout / fallback (non-standard)
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
    "https://skava.inaf.it/soda/execute?ID=tb-cube-l&POS=CIRCLE%20150.0%20-30.0%200.1&BAND=0.2142%200.2150" \
    -o tb-cube-l_cutout.fits
# Response headers on success:
#   Content-Type: application/fits
#   X-Soda-Applied: pos,band
#   X-Soda-Executed-On: BIG
```

Delegation goes to the first replica, in ranking order, whose node has
``visivo_backend_url`` set and whose access URL is ``file://`` — the same rule
DataLink uses to advertise the cutout, so an advertised cutout is one that
runs. `/soda/execute` takes the parameters in the query string and
accepts only the `CIRCLE` form of `POS`. A backend that is unreachable,
times out (`SKAVA_SODA_BACKEND_TIMEOUT_SECONDS`) or fails the cutout
returns ``502 backend_execution_failed``; the token in
`SKAVA_VISIVO_BACKEND_TOKEN` is forwarded as `X-Visivo-Token` when the
node's backend requires one. See
[Compute next to data](../architecture/compute-next-to-data.md) for the design.

## Sync request

```bash
curl -s -i "https://skava.inaf.it/soda/sync?ID=tb-cube-l&CIRCLE=150.0%20-30.0%200.1&BAND=0.2142%200.2150"
# HTTP/1.1 303 See Other
# location: http://node-big:8000/soda/sync?ID=file%3A%2F%2F%2Fdata%2Fcubes%2Ftb-cube-l.fits&CIRCLE=150.0+-30.0+0.1&BAND=0.2142+0.2150
```

A SODA client that follows redirects (`curl -L`, pyvo) receives the FITS
cutout from the node, which applies its own access rule (its backend's
token) to the redirected request.

### Parameters

All parameters are query parameters.

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
  - obs_id of the dataset; replaced by the replica's own ``ID`` in
    the redirect.
* - ``POS``
  - str
  - no
  - SODA geometry. Forwarded as given on a redirect (the node accepts
    ``CIRCLE``, ``RANGE`` and ``POLYGON``); without a node only
    ``CIRCLE ra dec radius`` (degrees) is accepted.
* - ``CIRCLE``
  - str ``"ra dec radius"``
  - no
  - SODA 1.0 ``CIRCLE`` parameter, degrees.
* - ``POLYGON``
  - str ``"ra1 dec1 ra2 dec2 …"``
  - no
  - SODA 1.0 ``POLYGON`` parameter. Only served by a node; refused with
    400 when no node can process the dataset in place.
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
  - Forwarded on a redirect. Without a node, one of
    ``application/fits``, ``image/fits``, ``application/octet-stream``,
    ``application/json``.
```

At most one of `POS`, `CIRCLE`, `POLYGON` may be given (400 otherwise).

### `/soda/sync` response without a node (validation descriptor)

```json
{
    "status": "accepted",
    "mode": "soda-sync-stub",
    "dataset": {"obs_id": "demo-0001", "obs_collection": "demo", "dataproduct_type": "image"},
    "routing": {"best_node": "IT-01", "access_url": "https://data.example.org/demo-0001.fits", "replicas": ["…"]},
    "request": {"ID": "demo-0001", "POS": "CIRCLE 83.6 22.0 0.1", "BAND": null, "TIME": null, "RESPONSEFORMAT": null},
    "operation": {"type": "subset", "supports_execution": false, "message": "…"},
    "next_step": {"planned_backend": "…", "datalink": "https://skava.inaf.it/datalink/demo-0001"}
}
```

This is the answer only when no node can process the dataset in place
(no `file://` replica on a node with a co-located VisIVO backend);
otherwise `/soda/sync` redirects to the node's SODA service, which
answers with the pixels.

### `/soda/execute` execution flow

1. SKAVA resolves the dataset and its ranked replicas.
2. The first replica that is a `file://` copy on a node with a co-located
   VisIVO backend is chosen; SKAVA POSTs the cutout request to that node's
   `/v1/datasets/cutout`. `X-Soda-Executed-On` names the node.
3. The backend opens the FITS locally, applies `POS`/`BAND` with astropy,
   and returns the subset; SKAVA streams it back as `application/fits`
   with `X-Soda-Applied` / `X-Soda-Executed-On` headers.
   `TIME` is forwarded but the node's cutout engine does not slice in
   time.
4. If no co-located backend is available, SKAVA records a metadata-cache
   staging job and returns it as JSON (`job_id`, `status`, `request`,
   `requested_by`, …) with an `operation` block
   (`execution_profile: "metadata-cache-handoff"`). `requested_by` is a
   non-reversible reference to the caller's token (`token:<sha256
   prefix>`), never the token itself.

Asynchronous SODA is the node's: a client that follows the DataLink
descriptor `node-soda-async` creates a UWS job on the node's backend
(`POST /soda/async` with the SODA parameters and `PHASE=RUN`), polls its
phase, and reads the product from its result link; `OPERATION=MOMENT` and
`OPERATION=PV` run a moment map and a position-velocity diagram the same
way. The VisIVO Visual Analytics desktop drives these jobs for the
operations it offers next to the data.

## Use from VO tools

Aladin, TOPCAT and pyvo read the service descriptors in the DataLink
VOTable (`utype="adhoc:service"`, `standardID = SODA#sync-1.0` and
`SODA#async-1.0`). They point at the node's own SODA services, with
`ID` fixed to the replica's identifier, so a cutout from these tools
runs on the node directly, without passing through SKAVA.

## Errors

```{list-table}
:header-rows: 1
:widths: 18 82

* - Status
  - When
* - 200
  - `/soda/sync`: validation descriptor (no node can cut the dataset).
    `/soda/execute`: streamed cutout, or staging-handoff JSON when no
    co-located backend.
* - 303
  - `/soda/sync`: redirect to the node's SODA service.
* - 400
  - Missing ``ID``, more than one spatial constraint, malformed
    ``POS``/``BAND``/``TIME``, ``POLYGON`` without a node, unsupported
    ``RESPONSEFORMAT``.
* - 401
  - Tokens are required and the request has none or an invalid one.
* - 404
  - obs_id unknown.
* - 502
  - ``backend_execution_failed`` — node backend unreachable, timed out,
    or returned an error for the cutout.
* - 503
  - ``no_available_nodes`` — no eligible replica for the dataset.
```

Errors raised by the node's own SODA service (after a redirect) follow
DALI: `text/plain` bodies starting with `UsageError:` or `FatalError:`.

## See also

* [DataLink API](datalink.md) where the SODA service descriptor lives.
* [Architecture / overview](../architecture/overview.md) for why
  routing is decoupled from execution.
