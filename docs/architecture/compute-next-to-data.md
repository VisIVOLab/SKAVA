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
  - its own filesystem, under a data root that contains the `file://`
    paths the node publishes; how to open a `file://` access URL
  - what other nodes exist; the catalogue (unless it reports its
    telemetry to it)
* - Filesystem
  - the bytes
  - everything else
```

This narrow contract is what makes the model federation-ready: every
node deploys its own backend; SKAVA only needs the backend's URL (and,
for the resource-aware policy, the backend's `/v1/ping` and
`/v1/node/status`).

## Routing decision in the client

SKAVA lists the options; the client chooses. The DataLink answer carries
one `visivo-backend` descriptor per ranked node with a backend, in ranking
order, each with the node's `endpoint` and `node_code`, and the replica of
each node under `routing.replicas`. A client opens the dataset on the first
node it can use, with that node's own replica (a `file://` path on the
node), and falls back to the next one if that node refuses. What a client
reads, and how the VisIVO Visual Analytics desktop uses it, is in
[Clients](../clients/overview.md).

## Why the client supplies `access_url`

The original design had the backend query SKAVA on every open. We
simplified to: **the client already did the discovery query, it
already has the access URL — just forward it**. Result:

* Opening a dataset needs nothing from SKAVA on the backend's side: no
  query to the catalogue, no catalogue URL in its configuration. (A backend
  the catalogue cannot reach may be configured to report its status to it;
  that is the only call from a node to SKAVA, and it is optional.)
* One less HTTP round-trip on every open.
* Backend is testable in isolation with synthetic
  `(obs_id, access_url)` tuples.

The backend, not SKAVA, decides what a client may open: it requires its
own token and opens only files under its data root.

## Security model

A client hands the backend an access URL, so the backend guards its own
filesystem: its token, its data root, the file types it accepts. On SKAVA's
side, one thing must agree with the catalogue: the backend's data root must
contain the `file://` paths the node publishes, or the backend refuses to
open them. The backend's rules and settings are documented by VisIVO:
[Running the backend as an SRC node](https://visivo.readthedocs.io/en/latest/deployment/src-node.html).

## Comparison with the fallback download path

When a client can use none of the advertised backends, it falls back to
the classic archive flow: it downloads the file from an `http(s)` access
URL and opens it locally. This path keeps SKAVA useful for sites that run
no VisIVO backend (legacy archives, mirrors), at the cost of one large
download per open. A `file://` access URL has no such fallback: the file
exists only on its node, and only a service on that node can read it.

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
request, cuts or computes next to the file (under the same access rules
as an open), and writes job results to its workspace. SKAVA itself runs no SODA jobs;
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
  - VisIVO Visual Analytics
  - the node's backend API
* - SODA for VO clients
  - SKAVA (`/soda/sync`, 303 redirect), then the client
  - node `/soda/sync`, `/soda/async` (UWS)
* - SODA proxy
  - SKAVA (`/soda/execute`)
  - `/v1/datasets/cutout`
* - Desktop cutout, moment and PV
  - VisIVO Visual Analytics
  - node `/soda/async` (UWS); the product stays on the node
* - Batch source finding
  - Computing Broker (placement from SKAVA's DataLink)
  - `/v1/node/status` (finders, memory), then `/v1/datasets/open_skava`
    and `/v1/tasks/sourcefind`
```

When no node can process the dataset in place, `/soda/sync` answers
with validation and routing JSON, and `/soda/execute` degrades to a
metadata-cache staging handoff (the desktop button reports that a
co-located backend is required). See the [SODA API](../api/soda.md).

```{admonition} Known limits
:class: note

The node SODA URL is always derived from the node's VisIVO backend: the
`node-soda-sync` and `node-soda-async` descriptors point at the node's
`visivo_backend_url` followed by `/soda`, and their fixed `ID` is the
replica's `file://` access endpoint. The `/soda/sync` redirect uses the
same pair. Redirecting to a SODA service a site already runs (for example
the ViaLactea Knowledge Base's `vlkb-soda`) is intended but not
implemented: it needs a SODA URL configured per node, and the replica's
identifier in the form that service resolves (an ObsCore identifier or an
IVOID) instead of a local path.
```

### Batch jobs through the Computing Broker

A Computing Broker places batch jobs (a source finder such as SoFiA-2)
with SKAVA's ranking as its input: it reads the dataset's DataLink,
walks the ranked replicas, and takes the first node whose backend
reports the requested finder and enough free memory in
`/v1/node/status`, recording why every other candidate was left. The
job then runs as a task on that node, next to the file. The testbed's
`broker` service is a stand-in for the SRCNet broker.

## How to enable this on a new node

1. Deploy a VisIVO backend on the node, able to read the data directory,
   with a data root that contains the paths you will publish and the node's
   code as its node code. How is documented by VisIVO:
   [Running the backend as an SRC node](https://visivo.readthedocs.io/en/latest/deployment/src-node.html)
   (and, on a cluster,
   [Running the backend on a SLURM cluster](https://visivo.readthedocs.io/en/latest/deployment/hpc-slurm.html)).
2. In SKAVA's admin UI (`/admin/nodes/`), edit the Node and set
   `VisIVO backend URL` to the deployed backend's URL (and mark that it
   requires a token if it does; SKAVA then sends
   `SKAVA_VISIVO_BACKEND_TOKEN` to it).
3. Publish the node's files with `file://` access URLs (the
   publisher's `file_serve_url_pattern`, e.g.
   `file:///data/cubes/{relpath}`) so the node can process them in
   place.
4. From now on every DataLink response for a dataset replicated on
   that node carries the `visivo-backend` descriptor, and the node's
   SODA, moment and PV descriptors when the node holds the selected
   `file://` replica.

No schema migration is needed. The prober (on by default, every 10 s)
starts reading the node's telemetry on its next cycle. If the catalogue
cannot reach the backend, the node reports its state itself
([Telemetry API](../api/telemetry.md#node-reports); see also
[Registering a node SKAVA cannot reach](../operations/node-behind-firewall.md)).

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
[Clients](../clients/overview.md) for what a client reads from SKAVA, and
[Components / VisIVO backend](components.md#out-of-process-the-visivo-backend) for the
calls SKAVA makes to a backend. How the backend loads cubes too large for a
client is documented by VisIVO:
[Large cube loading](https://visivo.readthedocs.io/en/latest/large-cube-loading.html).
```
