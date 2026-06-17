# Configuration

Everything SKAVA reads at runtime comes from a Pydantic
`BaseSettings` instance. Each value can be set via environment
variable. This page is the canonical list; the same names appear in
`docker-compose.yml`, Kubernetes ConfigMaps, and CI secrets.

## Core SKAVA settings

Defined in `app/config.py`. All are prefixed `SKAVA_`.

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
  - Controls strict-mode validations. `production` requires
    `SKAVA_PUBLIC_BASE_URL` to start with `https://`.
* - `SKAVA_DATABASE_URL`
  - SQLAlchemy URL
  - —
  - Required. e.g. `postgresql+psycopg://user:pass@host:5432/db`.
* - `SKAVA_PUBLIC_BASE_URL`
  - URL
  - —
  - Used to construct fully-qualified URLs in DataLink responses
    (e.g. `https://skava.inaf.it`).
* - `SKAVA_LOG_LEVEL`
  - `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`
  - `INFO`
  - Root logger level. SKAVA emits structured JSON logs by default.
* - `INTERNAL_API_KEY`
  - str (≥ 8 chars)
  - —
  - Required for `/internal/*` endpoints. Generate with
    `openssl rand -hex 32`.
* - `SKAVA_INTERNAL_API_KEY`
  - str
  - —
  - Alias for `INTERNAL_API_KEY`. Either is accepted.
* - `SKAVA_ACCESS_TOKENS`
  - comma-list
  - `""`
  - Optional bearer tokens for **public** endpoints. Empty means
    discovery is open.
* - `SKAVA_FEDERATED_SRC_URLS`
  - comma-list
  - `""`
  - Sibling SKAVA URLs for federation fan-out (roadmap).
* - `SKAVA_FEDERATION_TIMEOUT_SECONDS`
  - float
  - `2.0`
  - Per-sibling timeout when fanning out federation queries.
```

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
  - `5`
  - Extra connections beyond pool_size.
* - `SKAVA_DB_POOL_TIMEOUT`
  - `30`
  - Seconds to wait for a free connection.
* - `SKAVA_DB_POOL_RECYCLE`
  - `1800`
  - Seconds before a connection is recycled (avoids stale
    connections through firewalls).
* - `SKAVA_DB_CONNECT_RETRIES`
  - `30`
  - Boot-time connection retries.
* - `SKAVA_DB_CONNECT_RETRY_DELAY`
  - `2`
  - Seconds between retries.
```

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
  - **Required in production.** Random 64+ char value used to sign
    session cookies. Generate with `openssl rand -hex 32`. When unset
    SKAVA generates a per-boot value and logs a warning.
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
* - `ADMIN_BRAND_NAME`
  - `SKAVA Admin`
  - Header brand string.
* - `ADMIN_LOGIN_RATE_LIMIT_PER_MINUTE`
  - `6`
  - Reserved for Phase 4 rate-limiter.
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
[operations / backup](../operations/backup).

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
internal_api_key
  Field required [type=missing, input_value={...}, input_type=dict]
```

This is on purpose — a half-configured SKAVA is worse than a refusing
SKAVA.
