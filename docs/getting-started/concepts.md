# Core concepts

Mental model SKAVA uses for the rest of the documentation. Reading
this first prevents the most common confusions on the issue tracker.

## Discovery service, not a data store

SKAVA stores **records about data**: ObsCore-shape metadata, who hosts
the file, which protocol can fetch it. It never holds the bytes. Files
live on the node that produced them; SKAVA points at them with an
`access_url`.

```
SKAVA              ─── stores ───►   metadata, access URLs
Node (SRC)         ─── stores ───►   the FITS / HDF5 files
VisIVO backend     ─── computes ──►  on the node, reading files in place
VisIVO desktop     ─── opens  ─────►  via SKAVA → routed backend
```

## Dataset

The basic unit in SKAVA's catalogue, identified by a stable
`obs_id`. One row per **logical dataset** — the same scientific
product, regardless of how many node-local copies exist.

Dataset fields are ObsCore-aligned plus a few SKAVA-specific
columns (provenance, license, DOI, …). See
[ObsCore fields reference](../reference/obscore-fields) for the full
list.

## Replica

A physical copy of a dataset on a specific Node. One Dataset can have
many Replicas (e.g. an original on `INAF-CT` and a mirror on
`SARAO-CT`). Replicas carry the per-node specifics:

* `node_id` — which Node hosts this copy
* `remote_path` — path on that node's filesystem
* `access_endpoint` — URL the consumer should use to fetch the file
* `status` — `available` | `quarantined` | `evicted`
* `is_public` — visibility flag

Discovery ranks replicas by latency, load and capability scores
configured per Node, and serves the best one in `routing.best_node`.

## Node

A site / data centre in the federation. Properties:

* `code` — short stable ID (e.g. `POWER9`, `INAF-CT`)
* `base_url` — declarative endpoint of the site (kept here for
  reference; the per-file URL is on the Replica)
* `is_enabled` / `is_available` — operator toggles
* `latency_score`, `load_score`, `capability_score` — ranking inputs
* `visivo_backend_url` *(optional)* — when set, SKAVA emits a
  `visivo-backend` service descriptor pointing at this URL, telling
  VisIVO desktop clients they can route compute to this node

## Service descriptor

An IVOA-style hint in the DataLink response that tells clients what
protocols / endpoints serve this dataset. SKAVA ships several:

* `access-resolution` — the canonical DataLink endpoint
* `soda-sync` — IVOA SODA validation/routing; `soda-async` reserved
* `cutout` — real cutout via `/soda/execute` (enabled when the dataset's
  node has a co-located VisIVO backend)
* `visivo-backend` *(SKAVA-specific)* — the URL of a VisIVO compute
  backend co-located with the dataset's best replica

Custom clients can add their own descriptors via plugins in a future
release.

## Compute next to data

Architectural principle: **bytes don't move, compute does**. When a
client wants to "open" a large dataset:

1. The client asks SKAVA where the data lives.
2. SKAVA tells it which node hosts the data, *and* which VisIVO backend
   on that node knows how to read it.
3. The client connects to that backend (a small HTTP call).
4. The backend opens the file from its own local filesystem and
   streams compute results back.

No file ever crosses the network at scale. The exception is the
fall-back path for clients with no co-located backend — they download
the file via plain HTTP, like a traditional archive.

The full diagram and trade-offs are in
[Compute next to data](../architecture/compute-next-to-data).

## Publisher

A CLI tool (``skava-publisher``) that runs **on each node**, walks
the local filesystem, extracts ObsCore metadata from FITS / HDF5 /
PSRFITS, and uploads JSON manifests to SKAVA's
`/internal/ingestion/run` endpoint.

The publisher is the right way to ingest data at scale: bytes stay
put, only metadata travels (~2 KB per dataset).

## Admin UI

A web admin at `/admin/` with:

* role-based access control (admin | ingester | viewer)
* CRUD for Nodes / Datasets / Replicas
* small-file FITS pre-fill (one-off, complements the publisher CLI)
* audit log

It is not an alternative to the publisher — it is a hand-edit /
inspection / approval surface alongside it.

## Federation

Multiple SKAVA instances at different SRC sites can federate
discoveries via the federation endpoints (in progress — see
[Architecture / overview](../architecture/overview)). Each SKAVA
keeps its own catalogue; federation amounts to fan-out queries with
result merging.

## Glossary cheat sheet

```{list-table}
:header-rows: 1
:widths: 25 75

* - Term
  - Meaning in SKAVA
* - SKA
  - Square Kilometre Array — the radio observatory the catalogue
    serves data for.
* - SRC
  - SKA Regional Centre. Each SRC runs (at minimum) data storage; in
    SKAVA's model, each SRC may also run a VisIVO backend.
* - IVOA
  - International Virtual Observatory Alliance. SKAVA's API surface
    aligns with their standards (ObsCore, TAP, DataLink, SODA).
* - ObsCore
  - IVOA metadata model for observation records. SKAVA's `datasets`
    table mirrors its required fields.
* - TAP
  - Table Access Protocol. SQL-ish ADQL queries over the catalogue.
* - DataLink
  - IVOA standard for resolving an observation id into access URLs.
* - SODA
  - Server-side Operations on Data Access — cutouts and subsetting.
* - VOSI
  - Virtual Observatory Service Interface — capabilities advertisement.
```

The longer [Glossary](../reference/glossary) lists every acronym
SKAVA uses.
