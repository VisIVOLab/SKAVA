# Data flow

Three ways data gets into SKAVA, and the ways clients, VO tools and
the Computing Broker get it out.

## Inbound — how datasets reach the catalogue

### 1. skava-publisher CLI *(recommended)*

```{mermaid}
flowchart LR
    A[Node filesystem] -->|scan + extract headers| B[skava-publisher]
    B -->|POST /internal/ingestion/run| C[(SKAVA)]
```

The publisher runs on the node, reads the file headers in place, and
sends ObsCore-shaped JSON to SKAVA's internal ingestion API.

* Bytes never leave the node — only ~2 KB of JSON per dataset.
* State is tracked in a per-node SQLite file → second run skips
  unchanged files.
* Idempotent: re-publishing the same file updates the existing row.

Details: [Publisher / overview](../publisher/overview.md).

### 2. Admin UI bulk upload *(small batches, one-off)*

```{mermaid}
flowchart LR
    A[Browser: CSV / JSON] -->|/admin/upload| B[Admin UI]
    B -->|IngestionJobService, in-process| C[(SKAVA)]
```

Same downstream pipeline as the publisher: the upload form calls the
ingestion service the `/internal/ingestion/*` endpoints use directly,
in-process (no API key involved), behind the admin session, with a dry
run before the real run.

### 3. Admin UI single-record entry *(one-by-one)*

```{mermaid}
flowchart LR
    A[Browser: edit.html form] -->|POST /admin/datasets/new| B[Admin UI]
    B -->|inserts directly| C[(SKAVA)]
```

A FITS pre-fill helper (`/admin/datasets/extract-from-fits`) reads the
primary HDU header to populate the form fields. Use this for one-off manual additions; for thousands of
records prefer the publisher.

## Outbound — how clients retrieve metadata + data

### Discovery + DataLink (90 % of clients)

```{mermaid}
sequenceDiagram
    Client->>SKAVA: GET /discovery/search?...
    SKAVA-->>Client: paged list of ObsCore records
    Client->>SKAVA: GET /datalink/{obs_id}
    SKAVA-->>Client: ranked replicas + access_url + service_descriptors
    Client->>Storage: fetch the file at access_url
```

Both answers carry SKAVA's routing decision: the replicas in ranking
order with a `rank_reason` each (and a `score` under the resource-aware
policy), and, in DataLink, the replicas set aside under
`routing.excluded` with the reason.

Storage may be:

* an HTTP archive (`https://archive.inaf.it/...fits`) — classical flow
* a `file://` URL → only usable if the client runs on the same node
* a `visivo-backend` service descriptor → the client routes compute
  there instead of fetching the file
* the node's SODA descriptors (`node-soda-sync`, `node-soda-async`,
  `visivo-moment`, `visivo-pv`) → the client asks the node for a subset
  or a product, and only that travels

### VisIVO compute-next-to-data

```{mermaid}
sequenceDiagram
    Client->>SKAVA: GET /datalink/{obs_id}
    SKAVA-->>Client: visivo-backend descriptor → backend URL
    Client->>VisIVO_backend: POST /v1/datasets/open_skava
    VisIVO_backend->>Storage: fits.open(local path)
    Client<<->>VisIVO_backend: subsequent moment / cutout / region requests
```

The file never leaves the SRC. See
[compute-next-to-data](compute-next-to-data.md) for the full discussion.

### TAP / DataLink / SODA for VO tools

```{mermaid}
sequenceDiagram
    participant V as VO client (pyvo, TOPCAT)
    participant S as SKAVA
    participant N as Node SODA service
    V->>S: GET /tap/tables, /tap/capabilities (VOSI)
    V->>S: TAP sync ADQL query on ivoa.ObsCore
    S-->>V: VOTable
    V->>S: GET /datalink/{obs_id}?RESPONSEFORMAT=votable
    S-->>V: links table + service descriptors (node SODA, moment, PV)
    V->>S: GET /soda/sync?ID=…&POS=…
    S-->>V: 303 See Other → node /soda/sync
    V->>N: SODA sync, or a UWS job at /soda/async
    N-->>V: the cutout / moment map / PV diagram (FITS)
```

ObsCore-aligned, so generic VO tools read SKAVA the same way they read
any IVOA-compliant archive; the testbed's `make conformance` checks
this with pyvo.

### Batch jobs through the Computing Broker

```{mermaid}
sequenceDiagram
    Client->>Broker: POST /v1/jobs (finder, dataset, resources)
    Broker->>SKAVA: GET /datalink/{obs_id}
    SKAVA-->>Broker: ranked replicas + visivo-backend descriptors
    Broker->>VisIVO_backend: GET /v1/node/status (finders, free memory)
    Broker->>VisIVO_backend: open_skava, then POST /v1/tasks/sourcefind
    Client->>Broker: GET /v1/jobs/{id} (placement, status, result)
```

The broker takes the first ranked node that has the finder and the
memory the job needs; the job's placement lists every candidate and
why it was taken or left. The testbed ships a stand-in for the SRCNet
broker.

## Node telemetry

```{mermaid}
flowchart LR
    P[SKAVA prober] -->|"GET /v1/ping (round trip)"| B[VisIVO backend]
    P -->|"GET /v1/node/status"| B
    P -->|probe_ok, rtt, telemetry_json| N[(nodes table)]
    N --> R[resource-aware ranking]
```

Every `SKAVA_TELEMETRY_INTERVAL_SECONDS` (or on
`POST /internal/telemetry/probe`) SKAVA probes each enabled node that
has a backend and stores the result on the node row; a measurement
older than `SKAVA_TELEMETRY_TTL_SECONDS` is not trusted. A node can
also report its state itself, and the newer observation wins; how the
prober and the reports interact is in [Telemetry API](../api/telemetry.md).

## Federation

```{mermaid}
flowchart TB
    Client -->|"/federation/search + bearer token"| SKAVA_IT
    subgraph fed["Federated query"]
        SKAVA_IT[(SKAVA INAF)]
        SKAVA_ZA[(SKAVA SARAO)]
        SKAVA_AU[(SKAVA AusSRC)]
    end
    SKAVA_IT -->|"/discovery/search, the caller's token"| SKAVA_ZA
    SKAVA_IT -->|"/discovery/search, the caller's token"| SKAVA_AU
    SKAVA_IT -- "merged on obs_id, local first; also_at per sibling" --> Client
```

The instance asked answers from its own catalogue and asks every configured
sibling's `/discovery/search` concurrently, with the caller's token (one IAM
across SRCNet). The answers are merged on the logical dataset identity: a
dataset the local catalogue lists keeps the local decision, and a sibling that
also lists it appears under `also_at` with its own best node and access URL; a
dataset only a sibling has is listed with that sibling as its `source`. A
sibling that fails, times out or refuses the token is reported per source and
does not fail the search. See [Federation API](../api/federation.md).

## Ingestion job lifecycle

Every `/internal/ingestion/dry-run` and `/internal/ingestion/run` call
(and every admin upload) whose file parses is recorded as a row in
`ingestion_jobs` with its summary: totals, and the records skipped with
their validation errors. A file that cannot be parsed is refused with
a 400 before any job is created, and only one job runs at a time (a
second gets a 409).

```{mermaid}
stateDiagram-v2
    [*] --> running: file parsed
    running --> dry_run: dry run finished
    running --> succeeded: records ingested (invalid ones skipped)
    running --> failed: unexpected error, rolled back
    dry_run --> [*]
    succeeded --> [*]
    failed --> [*]
```

Jobs are listed by `GET /internal/ingestion/history`; admin uploads
also leave a row in the audit log shown under the admin UI's History
tab.

```{seealso}
[Internal ingestion API](../api/ingestion.md) — the request/response
contract used by all three inbound paths.
```
