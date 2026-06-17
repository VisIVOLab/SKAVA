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
    VisIVOclient["VisIVO desktop"] -->|HTTPS, public discovery + DataLink| Uvicorn
    Other["other VO clients<br/>(TAP / DataLink)"] --> Uvicorn
```

A single SKAVA instance handles:

* **public**: `/discovery/*`, `/datalink/*`, `/access/*`, `/soda/*`,
  `/tap/*`, `/vosi/*`
* **internal** (API-key auth): `/internal/ingestion/*`
* **federated** *(planned)*: `/federation/*` for sibling-to-sibling
  queries
* **admin** (session auth): `/admin/*` with HTML + HTMX

## Module layout

```
app/
├── main.py                # FastAPI app factory + middleware wiring
├── config.py              # Pydantic Settings — env-vars → typed object
├── db.py                  # SQLAlchemy engine + sessionmaker
├── models/                # ORM models (Dataset, Node, Replica, User,
│                          #             IngestionJob, AuditLog, …)
├── schemas/               # Pydantic request/response models
├── routers/               # one FastAPI router per public concern
│   ├── discovery.py
│   ├── datalink.py
│   ├── soda.py
│   ├── tap.py
│   ├── access.py
│   ├── federation.py
│   ├── provenance.py
│   ├── staging.py
│   ├── system.py
│   └── internal_ingestion.py
├── services/              # business logic, kept out of routers
│   ├── datalink_service.py
│   ├── ranking.py
│   ├── seed.py
│   └── …
├── ingestion/             # CSV / JSON parsing + validation pipeline
├── admin/                 # admin UI subpackage (Phase 1+ scope)
│   ├── auth/              # local password + future OIDC
│   ├── audit/             # @audited decorator + service
│   ├── routers/           # auth, dashboard, nodes, datasets
│   ├── services/          # FITS extractor, …
│   ├── templates/         # Jinja2 + HTMX
│   └── static/
├── middleware/
│   └── request_context.py # request_id + structured-log binding
├── security/
│   ├── internal_api_key.py
│   └── access_token.py
└── vo/                    # VO-format serialisers (VOTable, etc.)
```

## Request lifecycle

```{mermaid}
sequenceDiagram
    participant C as Client
    participant M as Middleware
    participant R as Router
    participant DB as PostgreSQL

    C->>M: HTTPS request
    Note over M: RequestContextMiddleware<br/>(generate request_id,<br/>start structured log)
    Note over M: SessionMiddleware<br/>(parse signed cookie<br/>— admin only)
    M->>R: dispatch to endpoint
    R->>DB: session.scalar / .execute
    DB-->>R: rows
    R-->>M: Response (Pydantic→JSON or Jinja2→HTML)
    M-->>C: HTTPS response (+ request_id header)
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
* **nodes** — federation members; each may also expose a VisIVO backend.
* **dataset_replicas** — many-to-many connector between datasets and
  nodes, with per-location specifics.
* **ingestion_jobs** — every CSV / JSON / API ingestion is recorded
  with totals + per-record errors. Admin-visible history.
* **users** — admin-UI accounts.
* **audit_log** — append-only mutation log.

The full schema is in [Configuration / database](../deployment/configuration#database).

## What's deliberately out of scope

* **Data storage**. SKAVA never stores FITS / HDF5 bytes; access URLs
  point at the node that does. The `access://` path
  (`/access/{obs_id}`) is a short HTTP-side redirector, not a file
  proxy.
* **Authentication of public discovery**. Public endpoints are open
  by default; tokens are only required for `/internal/*` and the
  admin UI. A future feature toggle will add bearer-token auth on
  discovery for sites that want it.
* **Compute itself**. Cutouts and analytics run on co-located VisIVO
  backends. SKAVA just routes.

## What's still in flux

* **SODA execution** — the sync endpoint validates and routes; actual
  cutout materialisation is on the roadmap.
* **Federation fan-out** — `/federation/*` endpoints are stubs.
* **TAP async + full ADQL** — sync subset works today.
* **Admin UI Phase 3+** — audit history viewer, dashboard counts
  with time series, exports.
* **OIDC for the admin UI** — local password is the only auth backend
  in Phase 1.

```{seealso}
[Compute next to data](compute-next-to-data) for the routing model in
detail and [Components](components) for the per-module contract.
```
