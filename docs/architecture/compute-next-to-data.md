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
    participant U as VisIVO desktop
    participant S as SKAVA
    participant B as VisIVO backend<br/>(on the SRC node)
    participant F as Local filesystem<br/>(on the SRC node)

    U->>S: GET /datalink/{obs_id}
    Note over S: looks up dataset,<br/>picks best replica,<br/>emits service_descriptors
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
* - VisIVO desktop
  - SKAVA URL, registered backends (URL + token + node code)
  - which file the SRC actually stores; how the backend implements
    `open_skava`
* - SKAVA
  - dataset catalogue, replica → node map, visivo_backend_url per
    node
  - what the backend does after receiving an obs_id; whether the
    file is currently readable
* - VisIVO backend
  - its own filesystem; how to dispatch on a `file://` access URL;
    a `VISIVO_DATA_ROOT` jail
  - the SKAVA URL; what other nodes exist
* - Filesystem
  - the bytes
  - everything else
```

This narrow contract is what makes the model federation-ready: every
node deploys its own backend; SKAVA only needs the backend's URL.

## Routing decision in the desktop client

When the user clicks **Open** on a SKAVA result, the desktop runs
`pickBackendForSkavaDataset()`:

1. **Exact URL match** — `descriptor.endpoint == registered.url`
   (trim trailing `/`).
2. **Node code match** — `descriptor.node_code == registered.srcCode`.
3. **Nothing matched** → fall back to download via the local backend
   (the legacy archive flow).

When (1) or (2) hits, the desktop calls
`POST /v1/datasets/open_skava` on the matched backend with
`{ obs_id, access_url }`. The backend opens locally and returns.

The status bar shows a coloured badge:

* **grey "Local"** — fallback download path, or pure local-file open
* **blue "Backend: <node name>"** — compute-next-to-data path

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
  - Bearer-token auth on the backend (`_auth = Depends(verify_token)`).
* - Path traversal via crafted `file://` URL
  - `VISIVO_DATA_ROOT` jail + `Path.resolve()` canonicalisation.
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

Production deployments **must** set `VISIVO_DATA_ROOT`. Without it
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

## Server-side variant: SODA cutout execution

The flow above is **client-driven**: the VisIVO desktop picks the backend
and opens the dataset. The same compute-next-to-data contract also powers a
**server-driven** path for VO/SODA clients that don't run the desktop.

When a VO tool (or any client) calls `POST /soda/execute?ID=…&POS=…&BAND=…`,
SKAVA itself plays the role the desktop plays above:

```
VO client → SKAVA /soda/execute
            ↓ resolves best node + file:// replica
            ↓ POST /v1/datasets/cutout to the node's VisIVO backend
            ↓ backend fits.open() + astropy cutout, returns subset
VO client ← application/fits (streamed through SKAVA)
```

The byte-level work still happens on the node (the backend reuses the same
`VISIVO_DATA_ROOT` jail and `file://` resolver as `open_skava`); only the
small cutout transits the network. The difference is *who* orchestrates:

```{list-table}
:header-rows: 1
:widths: 28 36 36

* - Path
  - Orchestrator
  - Backend endpoint
* - Desktop open + interactive compute
  - VisIVO desktop (`pickBackendForSkavaDataset`)
  - `/v1/datasets/open_skava` (+ moments / region / channel)
* - SODA cutout for VO clients
  - SKAVA (`/soda/execute`)
  - `/v1/datasets/cutout`
* - Desktop "SODA subset" action
  - VisIVO desktop (SKAVA Discovery tab)
  - `/v1/datasets/cutout` (`save_to_workspace=true`, opened in place)
```

The desktop **"SODA subset"** button resolves the dataset's DataLink, prompts
for a POS/BAND region (prefilled from the ObsCore metadata), runs the cutout on
the matched co-located backend with `save_to_workspace=true`, and opens the
resulting FITS in place — the cutout never transits to the client. It sits
alongside the unchanged VLKB-specific cutout flow.

When the node has no co-located backend, SKAVA's `/soda/execute` degrades to a
metadata-cache staging handoff (and the desktop button reports that a
co-located backend is required). See [SODA execution](../soda_execution).

## How to enable this on a new node

1. Deploy a VisIVO backend on the node (`apptainer/backend-conda.def`
   or `backend.def`). Make sure it can read the data directory.
2. Set `VISIVO_DATA_ROOT=/data` (or wherever) in the container env
   for security.
3. In SKAVA's admin UI (`/admin/nodes/`), edit the Node and set
   `VisIVO backend URL` to the deployed backend's URL.
4. From now on every DataLink response for a dataset replicated on
   that node carries the descriptor.

That's it — desktop clients pick it up automatically. No SKAVA-side
change, no schema migration.

## Multi-node example

```{mermaid}
flowchart TB
    Client["VisIVO desktop"]
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

The same dataset is replicated on three nodes. SKAVA picks the
best-ranked one with a backend (INAF-CT). If INAF-CT goes down, the
ranking demotes it on the next query and the desktop transparently
routes to SARAO-CT. If both backends are gone, the desktop falls
back to a download from `INAF-PUB`.

## Operational consequences

* **No file egress from the SRC at user-open time.** Bandwidth
  accounting is dominated by compute results, not raw data.
* **No client-side caching of FITS.** Reopening a dataset
  re-establishes a backend session but never re-downloads.
* **GPUs land where they matter.** Putting a Blackwell-class GPU at
  one node and a Power9 at another lets the desktop route GPU-heavy
  ops to the GPU node automatically (when SKAVA's ranking is
  configured to prefer it).
* **Storage staging is local.** Moving a dataset onto a faster tier
  is a node-internal operation; SKAVA just records the new path.

```{seealso}
[Backend routing in the desktop client](../client-integration/backend-routing)
for the matching algorithm details, and
[Components / VisIVO backend](components#visivo-backend) for the
backend's protocol surface.
```
