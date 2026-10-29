# Components

Module-by-module breakdown of what lives where and what each piece
contracts with the rest of the system. Treat this as an index when
reading the codebase.

## `app/main.py` — FastAPI app factory

Single entry point. Builds the FastAPI app, wires middleware and
exception handlers, includes the per-concern routers and mounts the
admin UI through `register_admin(app)`.

* Lifespan: `wait_for_db()` (fail fast on a bad database), then, when
  `SKAVA_TELEMETRY_INTERVAL_SECONDS` is above zero, the node prober
  (`run_prober`) as a background task, cancelled on shutdown.
* Middleware (outer → inner):
  * `SessionMiddleware` — signed cookie for the admin UI
  * `RequestContextMiddleware` — request_id + structured log binding
* Exception handlers:
  * `SKAVAError` → uniform JSON error envelope (with any headers the
    error carries, e.g. the `WWW-Authenticate` challenge)
  * `RequestValidationError` → 400 `invalid_query` with detail list
  * `HTTPException` → the same envelope with `http_<status>`
  * generic `Exception` → 500 with redacted message

The admin UI registers its own `HTTPException` handler that renders an
HTML error page for admin paths.

## `app/config.py` — settings

`Settings` is a Pydantic `BaseSettings` with the `SKAVA_` prefix
(plus the aliases `INTERNAL_API_KEY` and `IAM_WELLKNOWN_ENDPOINT`).
Every value can be overridden by environment variable or `.env`. The
full list is in [env-vars reference](../reference/env-vars.md).

Key fields:

* `database_url` — SQLAlchemy URL
* `public_base_url` — used to construct fully-qualified links in
  DataLink responses
* `internal_api_key` — required for `/internal/*`
* `access_tokens` — optional comma-separated static bearer tokens for
  the public endpoints (`access_token_set` is the parsed set)
* `oidc_wellknown`, `oidc_audience`, `oidc_issuer`,
  `oidc_public_wellknown`, `oidc_jwks_uri` — OIDC tokens from an SRCNet
  IAM
* `federated_src_urls`, `federation_timeout_seconds` — sibling SKAVA
  instances for `/federation/search`
* `visivo_backend_token`, `soda_backend_timeout_seconds` — calls to the
  nodes' VisIVO backends
* `ranking_policy` (`static` | `resource_aware`), `telemetry_*`,
  `ranking_weight_*`, `ranking_memory_factor` — routing and the prober

The admin UI has its own `AdminSettings` (`app/admin/config.py`,
`ADMIN_` prefix).

## `app/db.py` — database session

* `Base` — the SQLAlchemy `DeclarativeBase` all models inherit from
* `engine` — SQLAlchemy 2.x Engine, built at import from the settings
* `SessionLocal` — `sessionmaker(autocommit=False, autoflush=False)`
* `get_db()` — FastAPI dependency yielding a session and closing on
  return
* `wait_for_db()` — startup retry loop, called from the
  `lifespan` context manager

Migrations are Alembic revisions in `migrations/versions/`
(`0001_initial` … `0009_add_node_telemetry`).

## Other top-level modules

| Module | Role |
|---|---|
| `errors.py` | `SKAVAError` and its subclasses (400 / 404 / 503 / backend errors). |
| `metrics.py` | Prometheus counters and gauges (requests, ranking decisions, fallbacks, DB errors, node probes and round trips) served at `/metrics`. |
| `logging_utils.py` | JSON log formatter and the request_id context variable. |
| `spatial_index.py` | Deterministic sky-cell key (`order8:raN:decM`) stored with each dataset for `SPATIAL_CELL` filtering. |
| `validation.py` | Small POS / interval validators. |
| `seed.py`, `seed_d22.py` | `python -m app.seed` entry points for the demo and D2.2 fixtures. |

## `app/models/` — ORM

| Model | File | Notes |
|---|---|---|
| `Dataset`, `DatasetReplica`, `Node` | `dataset.py`, `replica.py`, `node.py` | Catalogue spine. `Node` also holds `visivo_backend_url`, `visivo_backend_requires_auth` and the last probe (`probe_ok`, `probe_rtt_ms`, `probe_error`, `telemetry_json`, `telemetry_at`). |
| `IngestionJob` | `ingestion_job.py` | One row per CSV / JSON ingestion call. |
| `StagingJob` | `staging_job.py` | Metadata-cache staging handoffs (`/staging/jobs`, `/soda/execute` fallback). |
| `TapJob` | `tap_job.py` | TAP async jobs. |
| `User`, `AuditLog` | `user.py`, `audit_log.py` | Admin UI subsystem. |

All models inherit from `app.db.Base` (DeclarativeBase). Use
`Mapped[...]` annotations + `mapped_column()` everywhere.

## `app/routers/` — HTTP surface

One file per concern. Routers are thin; business logic lives in
`app/services/`. "Token" means `require_access_token`: open by default,
a bearer token (static or OIDC) when either is configured.

| Router | Purpose | Auth |
|---|---|---|
| `discovery.py` | `/discovery/search` + `/discovery/dataset/{obs_id}` | token |
| `datalink.py` | `/datalink/{obs_id}`: ranked replicas, links and service descriptors, as JSON or DataLink VOTable | token |
| `soda.py` | `/soda/sync`: 303 to the node's SODA service, or validation + routing JSON; `/soda/execute`: non-standard proxy to the node's cutout | token |
| `tap.py` | `/tap/sync`, `/tap/async`, VOSI `/tap/tables` and `/tap/capabilities` | token (VOSI open) |
| `access.py` | `/access/{obs_id}`: routed access descriptor (JSON) | token |
| `federation.py` | `/federation/search` (local + siblings, merged on `obs_id`), `/federation/sources` | token, forwarded to siblings |
| `provenance.py` | per-dataset provenance lookup | token |
| `staging.py` | `/staging/jobs`: record and read metadata-cache staging jobs | token |
| `system.py` | `/availability`, `/capabilities`, `/health/db`, `/metrics` | none |
| `telemetry.py` | `/internal/telemetry` (what the policy sees), `/internal/telemetry/probe` (probe now) | `X-Internal-Api-Key` |
| `internal_ingestion.py` | `/internal/ingestion/dry-run`, `/run`, `/history` | `X-Internal-Api-Key` |

## `app/services/` — business logic

| Service | Role |
|---|---|
| `datalink_service.py` | rank replicas with the configured policy, pick the primary, build the DataLink envelope (`routing` with `policy` and `excluded`, links, `service_descriptors`, capabilities). |
| `discovery_service.py`, `discovery_filters.py` | ObsCore search with POS / BAND / TIME / collection / type / sky-cell filters; ranked replicas per result. |
| `access_service.py` | `/access` descriptor built from the DataLink answer. |
| `soda_service.py` | `/soda/sync` validation + routing when no node can cut. |
| `soda_execution_service.py` | `/soda/execute`: delegate the cutout to the node's `/v1/datasets/cutout`. |
| `staging_service.py` | metadata-cache staging jobs. |
| `tap_service.py` | ADQL subset over `ivoa.ObsCore`, sync and async. |
| `federation_service.py` | concurrent fan-out to siblings with the caller's token; merge on `obs_id` with `also_at`; per-source status. |
| `telemetry_service.py` | the prober: `/v1/ping` round trip and `/v1/node/status` of each node's backend, stored on the node row. |
| `capabilities_service.py`, `health_service.py` | `/capabilities` and `/availability`, `/health/db`. |
| `ingestion_job_service.py` | drive a CSV / JSON ingestion end-to-end with job record + summary. |
| `seed.py` / `seed_d22.py` | demo and D2.2 fixtures, idempotent. |

## `app/ranking/` — routing policies

| Module | Role |
|---|---|
| `base.py` | `RankingPolicy` (implements `explain()`: every replica, eligible first, each with a reason), `RankedReplica`, and the operator exclusions (replica not available / not public, node disabled / unavailable). |
| `default.py` | `DefaultRankingPolicy`, name `static`: declared latency, then load, then capability. |
| `resource_aware.py` | `ResourceAwareRankingPolicy`: excludes nodes whose backend did not answer the last probe or lacks the memory the dataset needs; orders the rest by a weighted cost of round trip, CPU pressure, tasks per worker and memory share; unmeasured nodes follow in static order. |
| `__init__.py` | `get_policy()` from `SKAVA_RANKING_POLICY`. |

## `app/ingestion/` — parsing pipeline

```
parsers/csv_parser.py           → list[dict]
parsers/json_parser.py          → list[dict]
validators/metadata_validator.py → list[error]
normalizers/obscore_normalizer.py → normalised ObsCore record
services/ingest_service.py      → IngestionSummary
cli.py                          → command-line ingestion of a manifest
```

Each step is independently testable. The CSV / JSON parsers accept
both file paths (CLI) and raw bytes (API uploads).

## `app/admin/` — admin UI

Self-contained subpackage. Lives at `/admin/*`. Layout:

* `auth/` — `local.py` (password sign-in), `password.py` (bcrypt +
  policy), `rbac.py` (`require_role`), `session.py` (session deps and
  secret)
* `audit/` — `@audited` decorator and the audit service
* `routers/` — `auth.py`, `dashboard.py`, `nodes.py`, `datasets.py`,
  `upload.py`, `history.py`
* `services/` — `fits_extract.py` for the form pre-fill
* `csrf.py`, `csv_export.py`, `templating.py`, `config.py`
* `templates/` — Jinja2 + HTMX
* `static/` — small CSS layer over the Tailwind CDN
* `cli.py` — `python -m app.admin.cli create-user / reset-password /
  set-role / list-users / deactivate`

Mounted by `app/admin/router.py`'s `register_admin(app)` from
`app/main.py`.

## `app/middleware/request_context.py`

`RequestContextMiddleware` takes the caller's `X-Request-ID` or
generates a UUID, stores it in a `contextvars` variable so every log
line emitted during the request can pick it up, and returns it in the
`X-Request-ID` response header.

## `app/security/`

* `internal_api_key.py` — `require_internal_api_key` (matches the
  `X-Internal-Api-Key` header against `settings.internal_api_key`);
  `require_access_token` for the public endpoints (a static token from
  `SKAVA_ACCESS_TOKENS` or an OIDC token, in `Authorization: Bearer` or
  `X-Skava-Access-Token`; open when neither is configured), whose 401
  carries the `ivoa_bearer` challenge naming the IAM;
  `presented_token` (the token forwarded to federation siblings) and
  `token_reference` (a hashed name for job records).
* `oidc.py` — validates OIDC access tokens: signature against the
  issuer's JWKS (asymmetric algorithms only), expiry, issuer and,
  when set, audience; discovery document and keys fetched lazily and
  cached.

## `app/vo/`

| Module | Role |
|---|---|
| `datalink.py` | links, service descriptors (SKAVA's, the node's SODA / moment / PV, `visivo-backend`) and capability flags. |
| `votable.py` | VOTable serialisation: TAP results and the DataLink `{links}` document with service-descriptor resources. |
| `adql.py` | the ADQL subset (WHERE parsing, geometry) for TAP. |
| `tap_schema.py` | VOSI tableset and TAP capabilities documents. |
| `soda.py`, `parsers.py`, `query_params.py` | POS / BAND / TIME parsing and SODA parameter normalisation. |
| `mappers.py` | ORM → schema mapping, and the rule for when a node can process a dataset in place. |

## Out-of-process: the publisher CLI

The publisher (`tools/skava-publisher/`) is a **separate Python
package**. It does not import any `app.*` module — it talks to SKAVA
only over HTTP via the internal-ingestion API. This keeps the runtime
boundary clean and lets the publisher be deployed inside an
Apptainer container with its own Python interpreter, independent of
SKAVA's version.

## Out-of-process: the VisIVO backend

The VisIVO backend (the `backend/` of
[`VisIVOLab/VisIVO-next`](https://github.com/VisIVOLab/VisIVO-next),
VisIVO Visual Analytics) is the compute side of compute-next-to-data.
SKAVA only knows its URL (stored on each Node row) and calls it over
HTTP: `/v1/ping` and `/v1/node/status` for the prober,
`/v1/datasets/cutout` for `/soda/execute`, and it points clients at the
node's `/soda/sync` and `/soda/async`. It never imports the backend's
code.

## Out-of-process: the VisIVO Visual Analytics desktop client

Qt 6 + VTK 9 desktop app. Routes through SKAVA discovery for any
dataset opened via the SKAVA tab, and signs in to the IAM when a
catalogue answers with the `ivoa_bearer` challenge. See
[client integration](../client-integration/visivo-desktop.md).

## Out-of-process: the testbed

`testbed/` is a docker-compose federation on one machine: two SKAVA
catalogues (one open, one requiring the IAM's tokens), Keycloak as
IAM, a Computing Broker stand-in (`broker_mock/`) and four VisIVO
backend nodes with different memory, CPU and network limits. See
[The testbed](../development/testbed.md).
