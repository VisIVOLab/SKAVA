# Core concepts

Mental model SKAVA uses for the rest of the documentation. Reading
this first prevents the most common confusions on the issue tracker.

## Discovery service, not a data store

SKAVA stores **records about data**: ObsCore-shape metadata, who hosts
the file, which protocol can fetch it. It never holds the bytes. Files
live on the node that produced them; SKAVA points at them with an
`access_url`.

```
SKAVA                    ─── stores ───►  metadata, access URLs, node telemetry
Node (SRC)               ─── stores ───►  the FITS / HDF5 files
VisIVO backend           ─── computes ─►  on the node, reading files in place
VisIVO Visual Analytics  ─── opens ────►  via SKAVA → routed backend
Computing Broker         ─── places ───►  batch jobs via SKAVA → node backend
```

## Dataset

The basic unit in SKAVA's catalogue, identified by a stable
`obs_id`. One row per **logical dataset** — the same scientific
product, regardless of how many node-local copies exist.

Dataset fields are ObsCore-aligned plus a few SKAVA-specific
columns (provenance, license, DOI, …). See
[ObsCore fields reference](../reference/obscore-fields.md) for the full
list.

## Replica

A physical copy of a dataset on a specific Node. One Dataset can have
many Replicas (e.g. an original on `INAF-CT` and a mirror on
`SARAO-CT`). Replicas carry the per-node specifics:

* `node_id` — which Node hosts this copy
* `remote_path` — path on that node's filesystem
* `access_endpoint` — URL the consumer should use to fetch the file
* `status` — `available` for a usable copy; any other value sets the
  replica aside
* `is_public` — visibility flag

DataLink and discovery rank the replicas with the configured policy and
serve the best one in `routing.best_node`. Each ranked replica carries
a `rank_reason` (and a `score` under the resource-aware policy); the
replicas set aside are listed in `routing.excluded` with the reason.

## Ranking policy

`SKAVA_RANKING_POLICY` picks one of two policies:

* `static` (default) — orders replicas by the latency, load and
  capability scores the operator declared on each Node.
* `resource_aware` — orders them by what each node's VisIVO backend
  reports. A prober (every `SKAVA_TELEMETRY_INTERVAL_SECONDS`, or on
  demand through `POST /internal/telemetry/probe`) measures the round
  trip of the backend's `/v1/ping` and reads its `/v1/node/status`
  (CPU pressure, free memory, queued tasks per worker, finders). A
  replica is excluded when its backend did not answer the last probe or
  its node lacks the memory the dataset needs; the rest are ordered by
  a weighted cost of round trip, CPU pressure, queue and memory share.
  Nodes without fresh telemetry follow, in the static order.

## Node

A site / data centre in the federation. Properties:

* `code` — short stable ID (e.g. `POWER9`, `INAF-CT`)
* `base_url` — declarative endpoint of the site (kept here for
  reference; the per-file URL is on the Replica)
* `is_enabled` / `is_available` — operator toggles
* `latency_score`, `load_score`, `capability_score` — declared ranking
  inputs (static policy)
* `visivo_backend_url` *(optional)* — when set, SKAVA emits a
  `visivo-backend` service descriptor pointing at this URL, telling
  VisIVO Visual Analytics clients they can route compute to this node;
  it is also what the prober reads telemetry from
* `visivo_backend_requires_auth` — whether that backend wants its own
  token (published as `requires_auth`)

## Service descriptor

An IVOA-style hint in the DataLink response that tells clients what
protocols / endpoints serve this dataset. SKAVA emits:

* `access-resolution` — the canonical DataLink endpoint
* `soda-sync` — SKAVA's `/soda/sync`: a 303 redirect to the node's SODA
  service when a node can process the dataset in place, otherwise
  validation and routing JSON
* `soda-async` — always disabled: SKAVA runs no jobs, asynchronous SODA
  is the node's (`node-soda-async`)
* `cutout` — the non-standard `/soda/execute` proxy (enabled when a
  ranked node has a co-located VisIVO backend and a `file://` replica)
* `node-soda-sync`, `node-soda-async` — the SODA services (sync, and
  UWS jobs) of the node holding that replica, with the replica's `ID`
  fixed in `input_params`
* `visivo-moment`, `visivo-pv` — moment maps and position-velocity
  diagrams computed on that node as SODA async jobs
  (`OPERATION=MOMENT` / `PV`); cubes only
* `visivo-backend` *(SKAVA-specific)* — one per ranked node with a
  co-located VisIVO compute backend, best first

In the DataLink VOTable the node's services appear as service-descriptor
resources (`#cutout`, `#proc`), and each backend as an `#auxiliary` row
pointing at its `/v1/node/status`.

## Compute next to data

Architectural principle: **bytes don't move, compute does**. When a
client wants to "open" a large dataset:

1. The client asks SKAVA where the data lives.
2. SKAVA tells it which node hosts the data, *and* which VisIVO backend
   on that node knows how to read it, ranked by what the nodes report.
3. The client connects to that backend (a small HTTP call).
4. The backend opens the file from its own local filesystem and
   streams compute results back.

No file ever crosses the network at scale. The exception is the
fall-back path for clients with no co-located backend — they download
the file via plain HTTP, like a traditional archive.

The full diagram and trade-offs are in
[Compute next to data](../architecture/compute-next-to-data.md).

## Publisher

A CLI tool (``skava-publisher``) that runs **on each node**, walks
the local filesystem, extracts ObsCore metadata from FITS / HDF5 /
PSRFITS, and uploads JSON manifests to SKAVA's
`/internal/ingestion/run` endpoint.

The publisher is the right way to ingest data at scale: bytes stay
put, only metadata travels (~2 KB per dataset).

## Admin UI

A web admin at `/admin/` with:

* local accounts with role-based access control (admin | ingester |
  viewer), separate from the IAM
* CRUD for Nodes / Datasets / Replicas
* CSV / JSON manifest upload with dry run
* small-file FITS pre-fill (one-off, complements the publisher CLI)
* audit log and history, with CSV export

It is not an alternative to the publisher — it is a hand-edit /
inspection / approval surface alongside it.

## Federation

Multiple SKAVA instances at different SRC sites federate discovery
through `/federation/search`. Each SKAVA keeps its own catalogue and
ranks its own replicas; the instance asked queries every sibling listed
in `SKAVA_FEDERATED_SRC_URLS` concurrently, forwarding the caller's
token, and merges the answers on `obs_id` (a sibling that also lists a
dataset appears under `also_at`). A sibling that fails or refuses the
token is reported per source and does not fail the search. See
[Federation API](../api/federation.md).

## Authentication

Public endpoints are open by default. Setting static tokens
(`SKAVA_ACCESS_TOKENS`) or an SRCNet IAM (`IAM_WELLKNOWN_ENDPOINT`)
makes them require a bearer token; an OIDC access token is checked
against the issuer's key set, expiry, issuer and, optionally, audience.
A refused request gets a 401 with the IVOA `ivoa_bearer` challenge that
names the IAM, so a client knows where to sign in. `/internal/*` uses
the `X-Internal-Api-Key` header; the admin UI uses its own session.

## Computing Broker

Batch jobs (source finding with SoFiA-2, for example) are placed by an
SRCNet Computing Broker. The broker asks SKAVA's DataLink where a
dataset is, takes the ranked `visivo-backend` nodes in order, checks
each node's `/v1/node/status` for the requested finder and enough
memory, and runs the job as a task on the first that fits. The
[testbed](../development/testbed.md) ships a
stand-in for it.

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
  - Virtual Observatory Service Interface — availability, capabilities
    and table metadata (`/availability`, `/capabilities`,
    `/tap/capabilities`, `/tap/tables`).
* - IAM
  - The SRCNet identity service (INDIGO IAM, or Keycloak) that issues
    the OIDC tokens SKAVA accepts.
* - UWS
  - Universal Worker Service — the IVOA job pattern the node's
    asynchronous SODA service follows.
```

The longer [Glossary](../reference/glossary.md) lists every acronym
SKAVA uses.
