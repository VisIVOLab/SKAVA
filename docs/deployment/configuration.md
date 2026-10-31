# Configuration

SKAVA reads its settings from environment variables, through a pydantic
`BaseSettings` instance (`app/config.py` for the service, prefix `SKAVA_`;
`app/admin/config.py` for the admin UI, prefix `ADMIN_`). A `.env` file in
the working directory is read as well. The same names appear in
`docker-compose.yml`, Kubernetes ConfigMaps and CI secrets.

This page explains the settings by topic. Every variable, with its type,
default and limits, is listed once, in
[Environment variables](../reference/env-vars.md).

## The minimum for a deployment

Outside development, set `SKAVA_ENV` to `staging` or `production`. SKAVA
then refuses to start without a database URL (`SKAVA_DATABASE_URL`) and a
public base URL (`SKAVA_PUBLIC_BASE_URL`, the base of every absolute URL it
hands out in DataLink, access and TAP answers), and in `production` the base
URL must be `https://`. Set `SKAVA_RUN_SEED=false` so the container does not
load the demo fixtures, and load real metadata with the
[publisher](../publisher/overview.md). See
[Service settings](../reference/env-vars.md#service).

Two secrets complete the minimum: `INTERNAL_API_KEY`, which the publisher
and other services present on `/internal/*` (unset, every internal call is
refused), and `ADMIN_SESSION_SECRET`, which signs the admin UI's session
cookies (with `ADMIN_SESSION_COOKIE_SECURE=true` behind HTTPS). Generate
both with `openssl rand -hex 32`. See
[Access and authentication](../reference/env-vars.md#access-and-authentication)
and [Admin UI](../reference/env-vars.md#admin-ui).

## Access to the public endpoints

The public catalogue endpoints (discovery, DataLink, SODA, TAP, access,
staging, provenance, federation) are open until a token rule is
configured. Static tokens (`SKAVA_ACCESS_TOKENS`, a comma-separated list)
and OIDC tokens from an IAM can be used together; as soon as either is
configured, every request to those endpoints needs a valid token. See
[Authentication](../api/auth.md).

## OIDC bearer tokens

SKAVA accepts OIDC access tokens issued by an SRCNet-style IAM (INDIGO
IAM, Keycloak) next to the static `SKAVA_ACCESS_TOKENS`. Point
`IAM_WELLKNOWN_ENDPOINT` (alias `SKAVA_OIDC_WELLKNOWN`) at the IAM's
discovery document. The token is checked against the issuer's key set
(asymmetric algorithms only), its expiry and issuer, and the audience when
`SKAVA_OIDC_AUDIENCE` is set. When the service reaches the IAM on a
private name, `SKAVA_OIDC_ISSUER` gives the issuer the tokens carry and
`SKAVA_OIDC_PUBLIC_WELLKNOWN` the discovery URL told to clients in the
`ivoa_bearer` challenge; `SKAVA_OIDC_JWKS_URI` overrides where the key set
is fetched. See
[Access and authentication](../reference/env-vars.md#access-and-authentication)
and [security](security.md).

## Federation

`SKAVA_FEDERATED_SRC_URLS` lists the base URLs of sibling SKAVA
catalogues. `GET /federation/search` asks each of them with the caller's
token and merges their answers with the local one on `obs_id`;
`GET /federation/sources` lists them. A sibling that does not answer within
`SKAVA_FEDERATION_TIMEOUT_SECONDS` is reported as `timeout` and the others
still count. See [Federation](../reference/env-vars.md#federation) and the
[Federation API](../api/federation.md).

## Routing and node telemetry

The ranking policy decides which replica's node DataLink, discovery and
`/soda/execute` route to. `resource_aware`, the default, ranks the nodes on
what their co-located VisIVO backends report (round trip, CPU pressure,
queue, free memory) and keeps the declared order for nodes it cannot
measure; `static` ranks on the scores declared on each node only. The
weights of the cost, the prober's period, timeout and samples, and the age
beyond which telemetry is not trusted are all settings. So is
`SKAVA_REPLICA_IDENTITY`, which decides when a node's record counts as a
copy of a dataset another node holds: by default only with an equal
checksum, and the federated search merges by the same rule. See
[Routing and node telemetry](../reference/env-vars.md#routing-and-node-telemetry).

`GET /internal/telemetry` (internal API key) shows the policy in force and
what each node last reported; the prober and the node reports are
described in the [Telemetry API](../api/telemetry.md).

## Node backends

When a node's backend requires a token, SKAVA presents
`SKAVA_VISIVO_BACKEND_TOKEN` (as `X-Visivo-Token`) to it, from the prober
and from `/soda/execute`, which waits up to
`SKAVA_SODA_BACKEND_TIMEOUT_SECONDS` for the cutout it delegates. See
[Node backends](../reference/env-vars.md#node-backends). The backend's own
settings are documented by VisIVO; the values that must agree with the
catalogue are listed in
[VisIVO backend: what must agree](../reference/env-vars.md#visivo-backend-what-must-agree).

## Database pool

The `SKAVA_DB_*` settings size SQLAlchemy's connection pool and the
connection retries at startup. The staging compose file raises the pool to
20 + 30 overflow and the retries to 20. See
[Database pool](../reference/env-vars.md#database-pool).

## Admin UI settings

The `ADMIN_*` settings cover the session cookie, the password policy, the
bcrypt cost, the login rate limit and the branding. In production set
`ADMIN_SESSION_SECRET` to a stable value and `ADMIN_SESSION_COOKIE_SECURE`
to `true`. See [Admin UI](../reference/env-vars.md#admin-ui).

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

Back up the database with `pg_dump`, and automate it in production: the
commands, a daily script, restore and retention are in
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

## Node reports: telemetry pushed by the node

A node the prober cannot reach (behind a firewall, a NAT or an SSH tunnel)
can report its state itself, with its own token, and the prober leaves it
alone while the reports are fresh. The endpoint, the token and how reports
and probes interact are in the [Telemetry API](../api/telemetry.md#node-reports);
registering such a node is in
[Registering a node SKAVA cannot reach](../operations/node-behind-firewall.md).
