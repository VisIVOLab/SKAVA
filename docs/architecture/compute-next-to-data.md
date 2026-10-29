# Compute next to data

The defining architectural choice in SKAVA's data-access flow:
**bytes don't travel, compute does**. A multi-GB cube stays on the
node that produced it; the client uses SKAVA discovery to figure out
which compute backend is co-located with that node, then drives that
backend remotely with small JSON requests.

```{contents}
:local:
:depth: 2
```

## Why

A traditional archive flow looks like this:

```
client → archive HTTP → download GB of FITS → open locally → compute
```

For 50 GB cubes published by SKA pathfinders that is a non-starter:

* it saturates the user's home bandwidth
* it pins the user's laptop disk
* it forbids interactive workflows (every operation re-downloads)
* it doesn't scale to multi-tenant SRC use

The "compute next to data" model collapses the download:

```
client → SKAVA discovery (2 KB JSON)
client → VisIVO backend on the SRC: "open obs_id X" (200 B)
        ↓ backend reads the file from local FS
        ↓ backend computes the requested product
client ← compute result (e.g. cutout PNG, moment FITS, ~1 MB)
```

Total wire traffic per session: kilobytes for control, megabytes for
results, never the underlying file.

## The five-step flow

```{mermaid}
sequenceDiagram
    participant U as VisIVO Visual Analytics
    participant S as SKAVA
    participant B as VisIVO backend<br/>(on the SRC node)
    participant F as Local filesystem<br/>(on the SRC node)

    U->>S: GET /datalink/{obs_id}
    Note over S: looks up dataset,<br/>ranks replicas (policy +<br/>node telemetry),<br/>emits service_descriptors
    S-->>U: { primary_access, service_descriptors }<br/>incl. visivo-backend descriptor

    Note over U: matches descriptor<br/>against registered backends

    U->>B: POST /v1/datasets/open_skava<br/>{ obs_id, access_url }
    B->>F: fits.open("/data/...")  (local I/O, no HTTP)
    F-->>B: HDU header + arrays (memory-mapped)
    B-->>U: { dataset_id, kind, geometry, … }

    Note over U: viewer opens with<br/>dataset_id; subsequent<br/>moments / cutouts /<br/>etc. hit B with that id
```

## What each layer knows

```{list-table}
:header-rows: 1
:widths: 22 38 40

* - Layer
  - Knows
  - Does NOT know
* - VisIVO Visual Analytics
  - SKAVA URL, registered backends (URL + token + node code)
  - which file the SRC actually stores; how the backend implements
    `open_skava`
* - SKAVA
  - dataset catalogue, replica → node map, visivo_backend_url per
    node; each backend's last reported round trip, CPU pressure,
    free memory, queue and finders (from the prober)
  - what the backend does after receiving an obs_id; whether the
    file is currently readable
* - VisIVO backend
  - its own filesystem; how to dispatch on a `file://` access URL;
    a `VISIVO_DATA_ROOT` / `VISIVO_DATA_ROOTS` jail
  - the SKAVA URL; what other nodes exist
* - Filesystem
  - the bytes
  - everything else
```

This narrow contract is what makes the model federation-ready: every
node deploys its own backend; SKAVA only needs the backend's URL (and,
for the resource-aware policy, the backend's `/v1/ping` and
`/v1/node/status`).

## Routing decision in the desktop client

When the user clicks **Open** on a SKAVA result, the desktop runs
`pickBackendForSkavaDataset()` over the `visivo-backend` descriptors,
in SKAVA's ranked order:

1. **Exact URL match** — `descriptor.endpoint == registered.url`
   (trim trailing `/`).
2. **Node code match** — `descriptor.node_code == registered.srcCode`.
3. **Nothing matched** → fall back to download via the local backend
   (the legacy archive flow).

When (1) or (2) hits, the desktop calls
`POST /v1/datasets/open_skava` on the matched backend with
`{ obs_id, access_url }`, where `access_url` is that node's own
`file://` replica. The backend opens locally and returns.

The status bar shows a coloured badge:

* **grey "Backend: Local"** — fallback download path, or pure
  local-file open
* **blue "Backend: <node name>"** — compute-next-to-data path; its
  tooltip shows SKAVA's `rank_reason` for that node

## Why the client supplies `access_url`

The original design had the backend query SKAVA on every open. We
simplified to: **the client already did the discovery query, it
already has the access URL — just forward it**. Result:

* Backend has zero dependency on SKAVA. No `httpx`, no env var
  `VISIVO_SKAVA_URL`, no networking from the SRC inward.
* One less HTTP round-trip on every open.
* Backend is testable in isolation with synthetic
  `(obs_id, access_url)` tuples.

The trust model is: only authenticated clients can call `open_skava`,
and `VISIVO_DATA_ROOT` is a server-side path jail that prevents a
malicious access URL from exposing files outside the data tree.

## Security model

```{list-table}
:header-rows: 1
:widths: 35 65

* - Threat
  - Mitigation
* - Unauthenticated open
  - Token auth on the backend (`X-Visivo-Token` header, checked by
    `verify_token`).
* - Path traversal via crafted `file://` URL
  - `VISIVO_DATA_ROOT` / `VISIVO_DATA_ROOTS` jail + `Path.resolve()`
    canonicalisation.
* - Symlink escape
  - `Path.resolve()` follows symlinks before the jail check; an evil
    symlink resolves to its real target, which fails the
    `relative_to(root)` test.
* - Wrong file format
  - `_is_supported_dataset(path)` whitelist (`.fits`, `.fit`, `.h5`, …).
* - Hostname spoofing in `file://`
  - reject `file://otherhost/...`; only empty or `localhost` are
    accepted.
```

Production deployments **must** set `VISIVO_DATA_ROOT` (or
`VISIVO_DATA_ROOTS`). Without it
the only barrier between a hostile authenticated client and arbitrary
filesystem reads is the extension whitelist.

## Comparison with the fallback download path

When no `visivo-backend` descriptor matches a registered backend, the
desktop falls back to the classic archive flow:

```
desktop → local backend → /v1/datasets/open_url { url=http://archive/...fits }
                          ↓ http GET (downloads to cache)
                          ↓ fits.open(cache)
                          ↓ return geometry
```

This path is intentionally preserved so SKAVA stays useful for sites
that don't run a VisIVO backend (legacy archives, mirrors). Cost: one
big download per open, then a normal viewer experience.

## Server-side variant: the node's SODA services

The flow above is **client-driven**: the VisIVO Visual Analytics desktop
picks the backend and opens the dataset. The same compute-next-to-data
contract also serves VO clients that don't run the desktop, through
the node's own IVOA SODA services, which SKAVA advertises in DataLink
(`node-soda-sync`, `node-soda-async`, and for cubes `visivo-moment` and
`visivo-pv`) whenever a ranked node holds a `file://` replica and runs
a co-located backend.

```
VO client → SKAVA GET /soda/sync?ID=…&POS=…
            ↓ resolves the node that can process the dataset in place
VO client ← 303 See Other → node /soda/sync?ID=<the node's replica>&POS=…
VO client → node /soda/sync      (SODA sync: the cutout, as FITS)
VO client → node /soda/async     (UWS job: OPERATION=CUTOUT | MOMENT | PV)
```

SKAVA never handles the bytes on this path: the node validates the
request, cuts or computes next to the file (with the same
`VISIVO_DATA_ROOT` jail and `file://` resolver as `open_skava`), and
writes job results to its workspace. SKAVA itself runs no SODA jobs;
its `soda-async` descriptor stays disabled and points clients to the
node's.

`POST /soda/execute` is a **non-standard proxy** kept for clients that
want one call: SKAVA posts the request to the node's
`/v1/datasets/cutout` and streams the resulting `application/fits`
back (`X-Soda-Executed-On` names the node).

```{list-table}
:header-rows: 1
:widths: 28 36 36

* - Path
  - Orchestrator
  - Backend endpoint
* - Desktop open + interactive compute
  - VisIVO Visual Analytics (`pickBackendForSkavaDataset`)
  - `/v1/datasets/open_skava` (+ moments / region / channel)
* - SODA for VO clients
  - SKAVA (`/soda/sync`, 303 redirect), then the client
  - node `/soda/sync`, `/soda/async` (UWS)
* - SODA proxy
  - SKAVA (`/soda/execute`)
  - `/v1/datasets/cutout`
* - Desktop "SODA subset" action
  - VisIVO Visual Analytics (SKAVA Discovery tab)
  - node `/soda/async` job when advertised, else `/v1/datasets/cutout`
    (`save_to_workspace=true`); the result is opened in place
* - Batch source finding
  - Computing Broker (placement from SKAVA's DataLink)
  - `/v1/node/status` (finders, memory), then `/v1/datasets/open_skava`
    and `/v1/tasks/sourcefind`
```

The desktop **"SODA subset"** button resolves the dataset's DataLink,
prompts for a POS/BAND region (prefilled from the ObsCore metadata),
runs the cutout on the node that holds the data and opens the resulting
FITS in place — the cutout never transits to the client. It sits
alongside the unchanged VLKB-specific cutout flow.

When no node can process the dataset in place, `/soda/sync` answers
with validation and routing JSON, and `/soda/execute` degrades to a
metadata-cache staging handoff (the desktop button reports that a
co-located backend is required). See the [SODA API](../api/soda.md).

### Batch jobs through the Computing Broker

A Computing Broker places batch jobs (a source finder such as SoFiA-2)
with SKAVA's ranking as its input: it reads the dataset's DataLink,
walks the ranked replicas, and takes the first node whose backend
reports the requested finder and enough free memory in
`/v1/node/status`, recording why every other candidate was left. The
job then runs as a task on that node, next to the file. The testbed's
`broker` service is a stand-in for the SRCNet broker.

## How to enable this on a new node

1. Deploy a VisIVO backend on the node (`apptainer/backend-conda.def`
   or `backend.def` in the VisIVO Visual Analytics repository). Make
   sure it can read the data directory.
2. Set `VISIVO_DATA_ROOT=/data` (or `VISIVO_DATA_ROOTS`) in the
   container env for security.
3. In SKAVA's admin UI (`/admin/nodes/`), edit the Node and set
   `VisIVO backend URL` to the deployed backend's URL (and mark that it
   requires a token if it does; SKAVA then sends
   `SKAVA_VISIVO_BACKEND_TOKEN` to it).
4. Publish the node's files with `file://` access URLs (the
   publisher's `file_serve_url_pattern`, e.g.
   `file:///data/cubes/{relpath}`) so the node can process them in
   place.
5. From now on every DataLink response for a dataset replicated on
   that node carries the `visivo-backend` descriptor, and the node's
   SODA, moment and PV descriptors when the node holds the selected
   `file://` replica.

That's it — desktop clients pick it up automatically. No schema
migration. The prober (on by default, every 10 s) starts reading the
node's telemetry on its next cycle. If the catalogue cannot reach the
backend, configure the node to report itself instead
([node reports](../deployment/configuration.md#node-reports-telemetry-pushed-by-the-node)).

## Multi-node example

```{mermaid}
flowchart TB
    Client["VisIVO Visual Analytics"]
    SKAVA[(SKAVA)]
    NodeIT["INAF-CT node<br/>VisIVO backend"]
    NodeZA["SARAO-CT node<br/>VisIVO backend"]
    NodePub["INAF-PUB archive<br/>(no backend)"]

    Client -- "1. GET /datalink/X" --> SKAVA
    SKAVA -- "2. best=INAF-CT,<br/>visivo-backend=https://inaf-ct/..." --> Client
    Client -- "3. POST open_skava" --> NodeIT
    NodeIT -- "4. fits.open(/data/X.fits)" --> NodeIT
    NodeIT -- "5. open result" --> Client

    style NodePub stroke-dasharray: 5 5
```

The same dataset is replicated on three nodes. SKAVA ranks the
replicas and lists INAF-CT first. Under the resource-aware policy, if
INAF-CT's backend stops answering the prober it is moved to
`routing.excluded` ("backend unreachable at the last probe") on the
next query, and the desktop routes to SARAO-CT, the next ranked node it
has registered; under the static policy the operator marks the node
unavailable. If no registered backend matches, the desktop falls back
to a download from `INAF-PUB`.

## Operational consequences

* **No file egress from the SRC at user-open time.** Bandwidth
  accounting is dominated by compute results, not raw data.
* **No client-side caching of FITS.** Reopening a dataset
  re-establishes a backend session but never re-downloads.
* **Load lands where there is room.** The resource-aware policy sends
  a dataset to the node with the lowest cost of round trip, CPU
  pressure, queue and memory share, and sets aside a node without
  the memory the dataset needs; every decision carries its reason.
* **Storage staging is local.** Moving a dataset onto a faster tier
  is a node-internal operation; SKAVA just records the new path.

```{seealso}
[Backend routing in the desktop client](../client-integration/backend-routing.md)
for the matching algorithm details, and
[Components / VisIVO backend](components.md#out-of-process-the-visivo-backend) for the
backend's protocol surface.
```
