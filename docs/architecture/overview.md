# Architecture overview

SKAVA is a single FastAPI service backed by PostgreSQL, packaged in a
container, designed to be deployed once per SRC site and federated
horizontally with sibling instances when more than one site
participates. This page is the high-level map; the next pages drill
down per concern.

## Process layout

```{mermaid}
flowchart TB
    subgraph host["Single SKAVA host"]
        Uvicorn["uvicorn (FastAPI app.main:app)"]
        Postgres[(PostgreSQL)]
        Uvicorn --- Postgres
    end
    Browser["Admin UI browser"] -->|HTTPS, session cookie| Uvicorn
    Pubcli["skava-publisher CLI"] -->|HTTPS + X-Internal-Api-Key| Uvicorn
    VisIVOclient["VisIVO Visual Analytics"] -->|HTTPS, discovery + DataLink| Uvicorn
    Other["other VO clients<br/>(TAP / DataLink / SODA)"] --> Uvicorn
    Broker["Computing Broker"] -->|DataLink: where to place a job| Uvicorn
    Uvicorn -->|"prober: /v1/ping, /v1/node/status"| Backends["VisIVO backends<br/>on the nodes"]
    Uvicorn -->|"/federation/search fan-out,<br/>caller's token"| Siblings["sibling SKAVA instances"]
    Uvicorn -->|"OIDC discovery + JWKS"| IAM["SRCNet IAM"]
```

The prober is an asyncio task started in the app's lifespan when
`SKAVA_TELEMETRY_INTERVAL_SECONDS` is above zero; it stores what each
node's backend reports on the node row, which the resource-aware
ranking policy reads.

A single SKAVA instance handles:

* **public** (open by default; bearer token when static tokens or an
  IAM are configured): `/discovery/*`, `/datalink/*`, `/access/*`,
  `/soda/*`, `/tap/*` (sync, async, VOSI `tables` and `capabilities`),
  `/provenance/*`, `/staging/*`
* **service** (always open): `/availability`, `/capabilities`,
  `/health/db`, `/metrics`
* **internal** (API-key auth): `/internal/ingestion/*`,
  `/internal/telemetry` and `/internal/telemetry/probe`
* **federated**: `/federation/*`, the local catalogue and the configured
  sibling instances asked together, merged on `obs_id`
  ([Federation API](../api/federation.md))
* **admin** (session auth): `/admin/*` with HTML + HTMX

## Module layout

```
app/
├── main.py                # FastAPI app factory, middleware, lifespan (prober)
├── config.py              # Pydantic Settings — env-vars → typed object
├── db.py                  # SQLAlchemy engine + sessionmaker
├── errors.py              # SKAVAError hierarchy → JSON error envelope
├── metrics.py             # Prometheus counters / histograms
├── logging_utils.py       # structured logging, request_id
├── spatial_index.py       # sky-cell index key used by discovery
├── validation.py
├── seed.py, seed_d22.py   # entry points for the demo / D2.2 seeds
├── models/                # ORM models (Dataset, Node, DatasetReplica, User,
│                          #   IngestionJob, StagingJob, TapJob, AuditLog)
├── schemas/               # Pydantic request/response models
├── routers/               # one FastAPI router per concern
│   ├── discovery.py
│   ├── datalink.py
│   ├── soda.py
│   ├── tap.py
│   ├── access.py
│   ├── federation.py
│   ├── provenance.py
│   ├── staging.py
│   ├── system.py
│   ├── telemetry.py
│   └── internal_ingestion.py
├── services/              # business logic, kept out of routers
│   ├── datalink_service.py
│   ├── discovery_service.py
│   ├── federation_service.py
│   ├── telemetry_service.py
│   ├── soda_service.py / soda_execution_service.py
│   └── …
├── ranking/               # routing policies: static and resource_aware
├── ingestion/             # CSV / JSON parsing + validation pipeline
├── admin/                 # admin UI subpackage
│   ├── auth/              # local password, RBAC, session
│   ├── audit/             # @audited decorator + service
│   ├── routers/           # auth, dashboard, nodes, datasets, upload, history
│   ├── services/          # FITS header extractor
│   ├── templates/         # Jinja2 + HTMX
│   └── static/
├── middleware/
│   └── request_context.py # request_id + structured-log binding
├── security/
│   ├── internal_api_key.py # API key, access tokens, ivoa_bearer challenge
│   └── oidc.py            # OIDC token validation against the IAM
└── vo/                    # ADQL, DataLink, SODA, TAP schema, VOTable
```

Database migrations live in `migrations/` (Alembic, `alembic.ini` at
the repository root).

## Request lifecycle

```{mermaid}
sequenceDiagram
    participant C as Client
    participant M as Middleware
    participant R as Router
    participant DB as PostgreSQL

    C->>M: HTTPS request
    Note over M: SessionMiddleware<br/>(parse signed cookie<br/>— used by the admin UI)
    Note over M: RequestContextMiddleware<br/>(take or generate request_id,<br/>start structured log)
    M->>R: dispatch to endpoint
    R->>DB: session.scalar / .execute
    DB-->>R: rows
    R-->>M: Response (Pydantic→JSON or Jinja2→HTML)
    M-->>C: HTTPS response (+ X-Request-ID header)
```

Exception handlers convert raised exceptions into a uniform JSON
envelope (`{ "error": { "code", "message", "details" }, "request_id" }`).
The admin UI has its own HTTPException handler that re-renders into a
branded error page when the client accepts `text/html`.

## Data model (ER summary)

```{mermaid}
erDiagram
    NODES ||--o{ DATASET_REPLICAS : hosts
    DATASETS ||--o{ DATASET_REPLICAS : has
    USERS ||--o{ AUDIT_LOG : performs
    INGESTION_JOBS ||--o{ DATASETS : produces
```

* **datasets** — one row per logical observation. ObsCore-shaped.
* **nodes** — federation members; each may also expose a VisIVO
  backend, and carries the last probe's result (`probe_ok`,
  `probe_rtt_ms`, `telemetry_json`, `telemetry_at`).
* **dataset_replicas** — many-to-many connector between datasets and
  nodes, with per-location specifics.
* **ingestion_jobs** — every CSV / JSON / API ingestion is recorded
  with totals + per-record errors. Admin-visible history.
* **staging_jobs** — the metadata-cache handoffs recorded by
  `/staging/jobs` and by `/soda/execute` when no node can cut.
* **tap_jobs** — TAP async jobs (`/tap/async`).
* **users** — admin-UI accounts.
* **audit_log** — append-only mutation log.

The full schema is in [Configuration / database](../deployment/configuration.md#database).

## What's deliberately out of scope

* **Data storage**. SKAVA never stores FITS / HDF5 bytes; access URLs
  point at the node that does. `/access/{obs_id}` returns the routed
  access descriptor (JSON), not the file. The one exception is the
  non-standard `/soda/execute` proxy, which relays a cutout the node
  computed.
* **Identity management**. SKAVA validates tokens issued by the SRCNet
  IAM (or static tokens); it does not issue them. Public endpoints are
  open unless one of the two is configured.
* **Compute itself**. Cutouts, moments, PV diagrams and source finding
  run on co-located VisIVO backends (the node's SODA service, its UWS
  jobs, or tasks the Computing Broker starts). SKAVA routes and
  places.

## Current limits

* **SKAVA's own SODA** — `/soda/sync` is a router: it redirects to the
  node's SODA service or answers with routing JSON. SKAVA runs no SODA
  async jobs itself; those are the node's.
* **TAP** — an ADQL subset over `ivoa.ObsCore`; `/tap/async` jobs are
  recorded and executed at submission and reported as JSON.
* **Federation** — each site ranks its own replicas; the merged answer
  is not re-ranked across sites.
* **Admin UI** — local accounts only; the IAM is not used for admin
  sign-in.

```{seealso}
[Compute next to data](compute-next-to-data.md) for the routing model in
detail and [Components](components.md) for the per-module contract.
```
