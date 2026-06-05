# Components

Module-by-module breakdown of what lives where and what each piece
contracts with the rest of the system. Treat this as an index when
reading the codebase.

## `app/main.py` — FastAPI app factory

Single entry point. Builds the FastAPI app, wires middleware and
exception handlers, includes the per-concern routers, mounts the
admin router and static files, and (optionally) registers OpenAPI
hooks.

* Middleware (outer → inner):
  * `SessionMiddleware` — signed cookie for the admin UI
  * `RequestContextMiddleware` — request_id + structured log binding
* Exception handlers:
  * `SKAVAError` → uniform JSON error envelope
  * `RequestValidationError` → 400 with detail list
  * generic `Exception` → 500 with redacted message

## `app/config.py` — settings

`PublisherConfig` is a Pydantic `BaseSettings`. Every value can be
overridden by environment variable. The full list is in
[env-vars reference](../reference/env-vars).

Key fields:

* `database_url` — SQLAlchemy URL
* `internal_api_key` — required for `/internal/*`
* `access_token_set` — optional bearer tokens for public endpoints
* `public_base_url` — used to construct fully-qualified links in
  DataLink responses

## `app/db.py` — database session

* `engine` — SQLAlchemy 2.x Engine, lazily constructed
* `SessionLocal` — `sessionmaker(autocommit=False, autoflush=False)`
* `get_db()` — FastAPI dependency yielding a session and closing on
  return
* `wait_for_db()` — startup retry loop, called from the
  `lifespan` context manager

## `app/models/` — ORM

| Model | File | Notes |
|---|---|---|
| `Dataset`, `DatasetReplica`, `Node` | `dataset.py`, `replica.py`, `node.py` | Catalogue spine. |
| `IngestionJob` | `ingestion_job.py` | One row per CSV / JSON / API ingestion call. |
| `StagingJob` | `staging_job.py` | Background staging-tier moves (future). |
| `TapJob` | `tap_job.py` | Async TAP jobs (future). |
| `User`, `AuditLog` | `user.py`, `audit_log.py` | Admin UI subsystem. |

All models inherit from `app.db.Base` (DeclarativeBase). Use
`Mapped[...]` annotations + `mapped_column()` everywhere.

## `app/routers/` — HTTP surface

One file per public concern. Routers are thin; business logic lives in
`app/services/`.

| Router | Purpose | Auth |
|---|---|---|
| `discovery.py` | search + per-dataset detail | none |
| `datalink.py` | resolve obs_id → access URL + descriptors | none |
| `soda.py` | SODA sync / async stubs | none |
| `tap.py` | sync ADQL subset | none |
| `access.py` | `/access/{obs_id}` short-link redirector | none |
| `federation.py` | fan-out to sibling instances (stub) | none |
| `provenance.py` | per-dataset provenance lookup | none |
| `staging.py` | trigger staging-tier moves (stub) | none |
| `system.py` | `/system/health`, `/system/version`, metrics | none |
| `internal_ingestion.py` | bulk + dry-run ingestion | `X-Internal-Api-Key` |

## `app/services/` — business logic

| Service | Role |
|---|---|
| `datalink_service.py` | rank replicas, pick primary, build the full DataLink envelope including `service_descriptors`. |
| `ranking.py` | scoring policy used by DataLink. |
| `ingestion_job_service.py` | drive a CSV / JSON ingestion end-to-end with audit + summary. |
| `seed.py` / `seed_d22.py` | demo and D2.2 fixtures, idempotent. |

## `app/ingestion/` — parsing pipeline

```
parsers/csv_parser.py    → list[dict]
parsers/json_parser.py   → list[dict]
validators/...           → list[error]
normalizers/...          → IngestionRecord
services/ingest_service.py → IngestionSummary
```

Each step is independently testable. The CSV / JSON parsers accept
both file paths (CLI) and raw bytes (API uploads).

## `app/admin/` — admin UI

Self-contained subpackage. Lives at `/admin/*`. Layout:

* `auth/` — local-password + future OIDC; CSRF helper; session deps
* `audit/` — `@audited` decorator and `log_action()`
* `routers/` — `auth.py`, `dashboard.py`, `nodes.py`, `datasets.py`
* `services/` — `fits_extract.py` for the form pre-fill
* `templates/` — Jinja2 + HTMX
* `static/` — small CSS layer over the Tailwind CDN
* `cli.py` — `python -m app.admin.cli create-user / reset-password / …`

Mounted by `app/admin/router.py`'s `register_admin(app)` from
`app/main.py`.

## `app/middleware/request_context.py`

`RequestContextMiddleware` generates a UUID request_id, stuffs it in
`contextvars` so every log line emitted during the request can pick it
up, and sets it as the `X-Request-Id` response header.

## `app/security/`

* `internal_api_key.py` — `require_internal_api_key` dependency.
  Lifts the configured key from `settings.internal_api_key` and
  matches against the `X-Internal-Api-Key` header.
* `access_token.py` — optional bearer-token auth for public
  endpoints. Off by default.

## `app/vo/`

VO-format serialisers (VOTable today; STC-S, MOC for future use).

## Out-of-process: the publisher CLI

The publisher (`tools/skava-publisher/`) is a **separate Python
package**. It does not import any `app.*` module — it talks to SKAVA
only over HTTP via the internal-ingestion API. This keeps the runtime
boundary clean and lets the publisher be deployed inside an
Apptainer container with its own Python interpreter, independent of
SKAVA's version.

## Out-of-process: the VisIVO backend

The VisIVO backend (separate repo
[`VisIVOLab/ViaLacteaVisualAnalytics`](https://github.com/VisIVOLab/ViaLacteaVisualAnalytics))
is the compute side of compute-next-to-data. SKAVA only knows its URL
(stored on each Node row); it never imports the backend's code.

## Out-of-process: the VisIVO desktop client

Qt 6 + VTK 9 desktop app. Routes through SKAVA discovery for any
dataset opened via the SKAVA tab. See
[client integration](../client-integration/visivo-desktop).
