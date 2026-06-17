# Data flow

Three ways data gets into SKAVA, three ways it gets out.

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

Details: [Publisher / overview](../publisher/overview).

### 2. Admin UI bulk upload *(small batches, one-off)*

```{mermaid}
flowchart LR
    A[Browser: CSV / JSON] -->|/admin/upload| B[Admin UI]
    B -->|wraps /internal/ingestion/run| C[(SKAVA)]
```

Same downstream pipeline as the publisher; the admin UI just exposes
it behind a session-authenticated drag-drop form. Phase 2c on the
admin roadmap.

### 3. Admin UI single-record entry *(one-by-one)*

```{mermaid}
flowchart LR
    A[Browser: edit.html form] -->|POST /admin/datasets/new| B[Admin UI]
    B -->|inserts directly| C[(SKAVA)]
```

A FITS pre-fill helper reads the primary HDU header to populate the
form fields. Use this for one-off manual additions; for thousands of
records prefer the publisher.

## Outbound — how clients retrieve metadata + data

### Discovery + DataLink (90 % of clients)

```{mermaid}
sequenceDiagram
    Client->>SKAVA: GET /discovery/search?...
    SKAVA-->>Client: paged list of ObsCore records
    Client->>SKAVA: GET /datalink/{obs_id}
    SKAVA-->>Client: access_url + service_descriptors
    Client->>Storage: fetch the file at access_url
```

Storage may be:

* an HTTP archive (`https://archive.inaf.it/...fits`) — classical flow
* a `file://` URL → only usable if the client runs on the same node
* a `visivo-backend` service descriptor → the client routes compute
  there instead of fetching the file

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
[compute-next-to-data](compute-next-to-data) for the full discussion.

### TAP / DataLink for VO tools

```{mermaid}
sequenceDiagram
    TOPCAT->>SKAVA: TAP sync ADQL query
    SKAVA-->>TOPCAT: VOTable
    Aladin->>SKAVA: DataLink (#this) for selected row
    SKAVA-->>Aladin: VOTable resource with access URL
```

ObsCore-aligned, so generic VO tools (TOPCAT, Aladin, …) read SKAVA
the same way they read any IVOA-compliant archive.

## Federation (planned)

```{mermaid}
flowchart TB
    Client --> SKAVA_IT
    subgraph fed["Federated query"]
        SKAVA_IT[(SKAVA INAF)]
        SKAVA_ZA[(SKAVA SARAO)]
        SKAVA_AU[(SKAVA AusSRC)]
    end
    SKAVA_IT -->|fan-out| SKAVA_ZA
    SKAVA_IT -->|fan-out| SKAVA_AU
    SKAVA_IT -- merged result --> Client
```

A future federation router will let one SKAVA instance fan a query
out to sibling instances, merge results, and present them under a
single envelope. Roadmap.

## Ingestion job lifecycle

Every `/internal/ingestion/run` call is recorded as a row in
`ingestion_jobs` with totals and per-record errors. The job goes
through three states:

```{mermaid}
stateDiagram-v2
    [*] --> validating: file accepted
    validating --> running: validation passed
    validating --> failed: schema invalid
    running --> succeeded: all records ingested
    running --> partial: some records skipped
    running --> failed: DB-level error
    succeeded --> [*]
    partial --> [*]
    failed --> [*]
```

Jobs are visible in the admin UI under the History tab (Phase 3).

```{seealso}
[Internal ingestion API](../api/ingestion) — the request/response
contract used by all three inbound paths.
```
