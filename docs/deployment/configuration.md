# Configuration

Everything SKAVA reads at runtime comes from a Pydantic
`BaseSettings` instance. Each value can be set via environment
variable. This page is the canonical list; the same names appear in
`docker-compose.yml`, Kubernetes ConfigMaps, and CI secrets.

## Core SKAVA settings

Defined in `app/config.py`. All are prefixed `SKAVA_`, except the
two that also accept an unprefixed name (`INTERNAL_API_KEY`,
`IAM_WELLKNOWN_ENDPOINT`). A `.env` file in the working directory is
read as well.

```{list-table}
:header-rows: 1
:widths: 28 18 14 40

* - Env var
  - Type
  - Default
  - Purpose
* - `SKAVA_ENV`
  - `dev` \| `staging` \| `production`
  - `dev`
  - Controls strict-mode validations. `staging` and `production`
    require `SKAVA_DATABASE_URL` and `SKAVA_PUBLIC_BASE_URL`;
    `production` requires `SKAVA_PUBLIC_BASE_URL` to start with
    `https://`.
* - `SKAVA_APP_NAME`
  - str
  - `SKAVA Data Discovery Service`
  - Title of the FastAPI application (OpenAPI docs).
* - `SKAVA_DATABASE_URL`
  - SQLAlchemy URL
  - dev: `postgresql+psycopg://skava:skava@localhost:5432/skava`
  - Required outside `dev`. e.g. `postgresql+psycopg://user:pass@host:5432/db`.
* - `SKAVA_PUBLIC_BASE_URL`
  - URL
  - dev: `http://localhost:8000`
  - Required outside `dev`. Used to construct fully-qualified URLs in
    DataLink responses (e.g. `https://skava.inaf.it`).
* - `SKAVA_LOG_LEVEL`
  - `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`
  - `INFO`
  - Root logger level. SKAVA emits structured JSON logs.
* - `INTERNAL_API_KEY`
  - str
  - —
  - Shared secret for `/internal/*` endpoints (`X-Internal-Api-Key`
    header). When unset, every `/internal/*` call is refused with 401.
    Generate with `openssl rand -hex 32`.
* - `SKAVA_INTERNAL_API_KEY`
  - str
  - —
  - Alias for `INTERNAL_API_KEY`. Either is accepted.
* - `SKAVA_ACCESS_TOKENS`
  - comma-list
  - empty
  - Static bearer tokens for the **public** endpoints. When neither
    these nor OIDC are configured, discovery is open.
* - `SKAVA_VISIVO_BACKEND_TOKEN`
  - str
  - empty
  - Token sent (as `X-Visivo-Token`) to a node's VisIVO backend that
    requires auth: by `/soda/execute` when it delegates a cutout
    (compute-next-to-data) and by the telemetry prober.
* - `SKAVA_SODA_BACKEND_TIMEOUT_SECONDS`
  - float ≥ 1
  - `120`
  - Synchronous timeout for that delegated cutout.
* - `SKAVA_RUN_SEED`
  - bool
  - `true`
  - Entrypoint flag. Set `false` in production to skip demo seeding;
    load real metadata via the ingestion API / publisher instead. The
    seed only runs when the `nodes` table is empty.
* - `SKAVA_SEED_RESET`
  - bool
  - `false`
  - Makes the seed wipe the catalogue and re-insert the demo fixtures.
    Development only.
```

## OIDC bearer tokens

SKAVA accepts OIDC access tokens issued by an SRCNet-style IAM (INDIGO
IAM, Keycloak) next to the static `SKAVA_ACCESS_TOKENS`. The token is
checked against the issuer's key set (asymmetric algorithms only), its
expiry and issuer, and the audience when one is configured. See
[security](security.md).

```{list-table}
:header-rows: 1
:widths: 35 15 50

* - Env var
  - Default
  - Purpose
* - `IAM_WELLKNOWN_ENDPOINT` (alias `SKAVA_OIDC_WELLKNOWN`)
  - unset
  - The issuer's discovery document. Setting it (or
    `SKAVA_OIDC_JWKS_URI`) turns OIDC on and makes the public
    endpoints require a token.
* - `SKAVA_OIDC_AUDIENCE`
  - unset
  - Audience the token must carry (e.g. `skava`); not checked when
    unset.
* - `SKAVA_OIDC_JWKS_URI`
  - from discovery
  - Override of the key-set location (air-gapped setups, tests).
* - `SKAVA_OIDC_ISSUER`
  - from discovery
  - Issuer the tokens carry, when the service reaches the IAM under a
    different (private) name than the public one in the tokens.
* - `SKAVA_OIDC_PUBLIC_WELLKNOWN`
  - `IAM_WELLKNOWN_ENDPOINT`
  - Discovery URL advertised to clients in the `ivoa_bearer`
    challenge of a 401.
```

## Federation

```{list-table}
:header-rows: 1
:widths: 35 15 50

* - Env var
  - Default
  - Purpose
* - `SKAVA_FEDERATED_SRC_URLS`
  - empty
  - Comma-separated base URLs of sibling SKAVA catalogues.
    `GET /federation/search` asks each of them (with the caller's
    token) and merges the answers with the local one on `obs_id`;
    `GET /federation/sources` lists them.
* - `SKAVA_FEDERATION_TIMEOUT_SECONDS`
  - `2.0` (≥ 0.1)
  - Per-sibling timeout; a sibling that does not answer in time is
    reported as `timeout` in the response, the others still count.
```

## Routing and node telemetry

The ranking policy decides which replica's node DataLink, discovery
and `/soda/execute` route to. With `resource_aware`, SKAVA probes each
enabled node's co-located VisIVO backend (`/v1/ping` round trip,
`/v1/node/status` capacity) and ranks by what the nodes report.

```{list-table}
:header-rows: 1
:widths: 35 15 50

* - Env var
  - Default
  - Purpose
* - `SKAVA_RANKING_POLICY`
  - `static`
  - `static` ranks by the scores declared on each node;
    `resource_aware` ranks by the measured telemetry.
* - `SKAVA_TELEMETRY_INTERVAL_SECONDS`
  - `0`
  - Prober period. `0` disables the background prober; telemetry is
    then refreshed only by `POST /internal/telemetry/probe`.
* - `SKAVA_TELEMETRY_TTL_SECONDS`
  - `60`
  - A measurement older than this is not trusted by the policy.
* - `SKAVA_TELEMETRY_TIMEOUT_SECONDS`
  - `3`
  - HTTP timeout of each probe request.
* - `SKAVA_TELEMETRY_PING_SAMPLES`
  - `3` (1–20)
  - `/v1/ping` samples per probe; the median is kept.
* - `SKAVA_RANKING_WEIGHT_RTT`
  - `1.0`
  - Cost per millisecond of round trip.
* - `SKAVA_RANKING_WEIGHT_CPU`
  - `1.0`
  - Cost per percent of CPU pressure.
* - `SKAVA_RANKING_WEIGHT_QUEUE`
  - `20.0`
  - Cost per queued + running task per worker.
* - `SKAVA_RANKING_WEIGHT_MEMORY`
  - `50.0`
  - Cost of the share of the node's free memory the dataset would take.
* - `SKAVA_RANKING_MEMORY_FACTOR`
  - `1.0`
  - Memory a dataset needs on the node, as a multiple of its size.
```

`GET /internal/telemetry` (internal API key) shows the policy in force
and what each node last reported.

## Database pool

```{list-table}
:header-rows: 1
:widths: 35 15 50

* - Env var
  - Default
  - Purpose
* - `SKAVA_DB_POOL_SIZE`
  - `10`
  - SQLAlchemy pool size.
* - `SKAVA_DB_MAX_OVERFLOW`
  - `20`
  - Extra connections beyond pool_size.
* - `SKAVA_DB_POOL_TIMEOUT`
  - `30`
  - Seconds to wait for a free connection.
* - `SKAVA_DB_POOL_RECYCLE`
  - `1800`
  - Seconds before a connection is recycled (avoids stale
    connections through firewalls).
* - `SKAVA_DB_CONNECT_RETRIES`
  - `10`
  - Boot-time connection retries.
* - `SKAVA_DB_CONNECT_RETRY_DELAY`
  - `1.5`
  - Seconds between retries.
```

The staging compose file raises the pool to 20 + 30 overflow and the
retries to 20.

## Admin UI settings

Defined in `app/admin/config.py`. All are prefixed `ADMIN_`.

```{list-table}
:header-rows: 1
:widths: 32 15 53

* - Env var
  - Default
  - Purpose
* - `ADMIN_SESSION_SECRET`
  - random (dev only)
  - **Set it in production.** Random value used to sign session
    cookies. Generate with `openssl rand -hex 32`. When unset SKAVA
    generates a per-process value and logs a warning: sessions are
    lost at every restart and do not work across several workers.
* - `ADMIN_SESSION_COOKIE_NAME`
  - `skava_admin_session`
  - Cookie name.
* - `ADMIN_SESSION_MAX_AGE_SECONDS`
  - `28800` (8 h)
  - Cookie lifetime.
* - `ADMIN_SESSION_COOKIE_SECURE`
  - `false`
  - Adds the `Secure` attribute. **Must be `true` in production
    (HTTPS).** Default `false` so local HTTP dev works without TLS.
* - `ADMIN_BCRYPT_ROUNDS`
  - `12`
  - bcrypt cost factor. 10–14 allowed.
* - `ADMIN_PASSWORD_MIN_LENGTH`
  - `12`
  - Minimum password length.
* - `ADMIN_PASSWORD_REQUIRE_MIXED_CASE`
  - `true`
  - Require upper + lower case.
* - `ADMIN_PASSWORD_REQUIRE_DIGIT`
  - `true`
  - Require at least one digit.
* - `ADMIN_PASSWORD_REQUIRE_SYMBOL`
  - `false`
  - Require at least one punctuation char.
* - `ADMIN_BRAND_COLOR`
  - `#70b5e3` (INAF blue)
  - Primary brand colour for HTML pages.
* - `ADMIN_BRAND_COLOR_DARK`
  - `#3a6e8c`
  - Darker variant of the brand colour.
* - `ADMIN_BRAND_NAME`
  - `SKAVA Admin`
  - Header brand string.
* - `ADMIN_LOGIN_RATE_LIMIT_PER_MINUTE`
  - `6`
  - Failed sign-ins allowed per client address per minute; beyond it,
    `/admin/login` answers 429 until the oldest failure is a minute old.
    0 disables it. Per process; the shipped nginx configs also
    rate-limit `/admin`.
```

## Database

PostgreSQL 16 is the supported backend. SQLite works for unit tests
but not for production (some migration steps are Postgres-only).

### Schema

Managed by Alembic in `migrations/`. The current chain:

```
0001 initial
└── 0002 search indexes
    └── 0003 ingestion metadata
        └── 0004 ingestion jobs table
            └── 0005 scientific query support
                └── 0006 production readiness
                    └── 0007 visivo_backend columns on nodes
                        └── 0008 admin users + audit log
                            └── 0009 node telemetry columns
```

Run `alembic upgrade head` inside the api container to apply all
migrations. The container entrypoint already does this on boot, so
manual invocation is only needed when authoring new migrations.

### Authoring a new migration

```bash
docker compose exec api alembic revision -m "add foo column"
# edit migrations/versions/000N_add_foo_column.py
docker compose exec api alembic upgrade head
```

### Backup

```bash
docker compose exec db pg_dump -U skava -d skava \
    --format=custom --file=/tmp/skava-$(date +%Y%m%d).dump

docker compose exec db cat /tmp/skava-2026-06-05.dump > skava-backup.dump
```

Restore:

```bash
docker compose exec -T db pg_restore -U skava -d skava --clean < skava-backup.dump
```

Production deployments should automate this — see
[operations / backup](../operations/backup.md).

## Logging

SKAVA emits structured JSON logs to stdout. Sample:

```json
{
    "timestamp": "2026-06-05T13:01:33.808067+00:00",
    "level": "INFO",
    "logger": "skava.request",
    "message": "request_completed",
    "request_id": "97f25c08-…",
    "endpoint": "/admin/login",
    "query_params": {},
    "status_code": 200,
    "execution_time_ms": 1.313
}
```

Ship to your log aggregator (Loki, Elasticsearch, CloudWatch, …) by
running the api container with `--log-driver=fluentd` /
`--log-driver=awslogs` etc., or run a sidecar that tails Docker's
stdout.

## Configuration validation

On boot SKAVA validates the config with Pydantic. Invalid values
crash the api container immediately with a precise message:

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
  Value error, SKAVA_PUBLIC_BASE_URL must use https:// in production [type=value_error, ...]
```

This is on purpose — a half-configured SKAVA is worse than a refusing
SKAVA.
