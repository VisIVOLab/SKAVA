# Docker Compose deployment

Single-host deployment with Docker Compose. Suitable for development,
testbeds and small production sites.

## docker-compose.yml structure

The shipped `docker-compose.yml` declares two services:

```yaml
services:
  db:
    image: postgres:16
    container_name: skava-db
    environment:
      POSTGRES_DB: skava
      POSTGRES_USER: skava
      POSTGRES_PASSWORD: skava
    ports:
      - "5432:5432"          # remove in production — DB should be host-internal
    volumes:
      - skava_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U skava -d skava"]

  api:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: skava-api
    environment:
      SKAVA_ENV: dev
      SKAVA_DATABASE_URL: postgresql+psycopg://skava:skava@db:5432/skava
      SKAVA_PUBLIC_BASE_URL: http://localhost:8000
      SKAVA_LOG_LEVEL: DEBUG
      INTERNAL_API_KEY: dev-mac-key-not-for-prod-rotate-me-please   # dev value
    ports:
      - "8000:8000"
    depends_on:
      db: { condition: service_healthy }
    command: ["/srv/app/docker/entrypoint.sh"]
    volumes:
      - ./docker/entrypoint.sh:/srv/app/docker/entrypoint.sh

volumes:
  skava_pgdata:
```

The dev stack sets no `ADMIN_SESSION_SECRET`: the admin UI then generates
a per-process secret and logs a warning (sessions do not survive a
restart). Add one to `environment:` if that gets in the way.

Production deployments customise this — see
[production](production.md).

## Production overrides (ready-made)

The repo ships compose overrides and nginx configs so you don't have to
hand-roll a production stack. Start from `docker-compose.staging.yml`
(services `postgres`, `skava-discovery` and `reverse-proxy` — nginx 1.27 on
host port 8080 — on an internal network, with rate limiting) and add a
production override on top. First create the secrets file:

```bash
cp .env.prod.example .env.prod      # fill POSTGRES_PASSWORD, INTERNAL_API_KEY,
                                    # ADMIN_SESSION_SECRET, SKAVA_PUBLIC_BASE_URL (https)
```

`docker-compose.prod.yml` and `docker-compose.selfhost-tls.yml` set
`SKAVA_ENV=production`, pass the secrets from `.env.prod`, harden the
containers (`no-new-privileges`, `cap_drop`, `read_only` + tmpfs, mem/pids
limits) and set `SKAVA_RUN_SEED=false` (no demo data — load real metadata
via the ingestion API / publisher).

The overrides pass only the variables listed in `.env.prod.example`
(`INTERNAL_API_KEY`, `ADMIN_SESSION_SECRET`, `SKAVA_ACCESS_TOKENS`,
`SKAVA_VISIVO_BACKEND_TOKEN`, `SKAVA_SODA_BACKEND_TIMEOUT_SECONDS`, …).
OIDC (`IAM_WELLKNOWN_ENDPOINT`, `SKAVA_OIDC_*`), federation
(`SKAVA_FEDERATED_SRC_URLS`) and routing/telemetry
(`SKAVA_RANKING_POLICY`, `SKAVA_TELEMETRY_*`, when they differ from the
defaults) settings must be added to the
`skava-discovery` service's `environment:` block when you use them — see
[configuration](configuration.md).

```{list-table}
:header-rows: 1
:widths: 30 70

* - Override
  - When to use
* - `docker-compose.prod.yml`
  - You terminate TLS with your own front proxy. nginx is published on
    `127.0.0.1:8080`; put **Caddy** (`docker/Caddyfile`, automatic HTTPS) or
    any TLS terminator in front. Uses `docker/nginx/nginx.prod.conf`
    (`/metrics` blocked, `/admin` rate-limited).
* - `docker-compose.selfhost-tls.yml`
  - **80/443 are already taken** (e.g. another stack on the host). SKAVA
    terminates its **own** TLS on host port `8443` reusing an existing
    Let's Encrypt cert. Uses `docker/nginx/nginx.tls.conf` + mounts
    `/etc/letsencrypt` read-only. Use it **instead of**
    `docker-compose.prod.yml`, not with it.
* - `docker-compose.shared-proxy.yml`
  - Run **behind an existing reverse proxy**. Layered on top of
    `docker-compose.prod.yml`; start only `postgres` and `skava-discovery`
    (not the bundled nginx). SKAVA publishes no host ports; it joins the
    proxy's external Docker network (`gateway_net`, whose `name:` you set
    to the proxy's network) so the proxy reaches `skava-discovery:8000`.
    Add the vhost from `docker/nginx/skava.vhost.example.conf` to that
    proxy.
```

Example — self-hosted TLS on port 8443:

```bash
docker compose -f docker-compose.staging.yml -f docker-compose.selfhost-tls.yml \
    --env-file .env.prod up -d --build
```

Example — behind an existing proxy:

```bash
docker compose -f docker-compose.staging.yml -f docker-compose.prod.yml \
    -f docker-compose.shared-proxy.yml \
    --env-file .env.prod up -d --build postgres skava-discovery
```

The staging stack's `skava-discovery` healthcheck calls `/health/db`, and
nginx answers `/healthz` itself. In these stacks the service names differ
from the dev stack (`skava-discovery`, `postgres` instead of `api`, `db`),
so adapt the commands below accordingly.

See [production](production.md) for the full hardening checklist (TLS, secrets,
backups, monitoring).

## Dockerfile structure

`docker/Dockerfile` is a two-stage build on `python:3.11-slim`: a
`builder` stage that uses `pip wheel` to build SKAVA + dependencies,
and a `runtime` stage that installs only the resulting wheels, copies
`migrations/`, `alembic.ini` and `docker/entrypoint.sh`, and runs as the
unprivileged `skava` user. The entrypoint waits for the database, runs
`alembic upgrade head`, seeds the demo catalogue unless
`SKAVA_RUN_SEED=false`, then starts `uvicorn app.main:app` on port 8000.

The image is single-architecture (the host's by default); astropy and its
numpy/scipy dependencies account for most of its size. For ppc64le or
arm64 builds, pass `--platform` to the buildx invocation; the Dockerfile
itself has no arch-specific code.

## Operational commands

```{list-table}
:header-rows: 1
:widths: 35 65

* - Task
  - Command
* - Bring everything up
  - `docker compose up -d`
* - Tail API logs
  - `docker compose logs -f api`
* - Restart API only (Python edits)
  - `docker compose restart api`
* - Rebuild image then restart (deps changed)
  - `docker compose build api && docker compose up -d`
* - Run an Alembic migration manually
  - `docker compose exec api alembic upgrade head`
* - Open a psql shell in the DB
  - `docker compose exec db psql -U skava -d skava`
* - Stop everything but keep the DB volume
  - `docker compose down`
* - Drop everything **including the DB**
  - `docker compose down -v`
* - Stream Prometheus metrics
  - `curl -s localhost:8000/metrics | head`
```

## Live-reload during development

By default the api container bakes the source code into the image —
every edit needs a `docker compose build api`. For tight dev loops
add a bind mount next to the entrypoint mount the dev compose file
already has:

```yaml
  api:
    volumes:
      - ./docker/entrypoint.sh:/srv/app/docker/entrypoint.sh
      - ./app:/usr/local/lib/python3.11/site-packages/app  # ← dev only
```

Then host edits are visible immediately. A `docker compose restart api`
picks them up. **Remove this mount in production** — it bypasses
the immutable-image guarantee.

## Healthchecks and orderly startup

The `db` service has a `pg_isready` healthcheck. The `api` service
declares `depends_on: db: { condition: service_healthy }`, so
`docker compose up -d` waits until PostgreSQL is accepting
connections before starting the api process.

If the api container starts before the DB is ready (e.g. on a
slow VM), the entrypoint retries the connection 30 × 2 s before giving
up; the application's own startup check then retries
`SKAVA_DB_CONNECT_RETRIES` × `SKAVA_DB_CONNECT_RETRY_DELAY`
(10 × 1.5 s by default).

## Multi-instance with Compose

Single Compose stack runs one SKAVA. For federation work, the testbed
(`testbed/`, see [testing](../development/testing.md)) already runs two
federated catalogues, an IAM and four nodes on one machine. To run a
second plain stack by hand, copy it to a sibling directory and change:

* `container_name` (must be unique)
* the host port mappings (`8000`, `5432`)
* the volume name (`skava_pgdata` → `skava_pgdata_dev2`)

Real production multi-instance setups belong in Kubernetes — see
[production](production.md) for the path forward.

## Environment-variable overrides

Edit `docker-compose.yml`'s `environment:` block, **or** override per
shell:

```bash
SKAVA_LOG_LEVEL=INFO docker compose up -d
```

Compose substitutes shell variables in YAML at parse time. To use
a `.env` file, put it next to `docker-compose.yml` and reference
variables as `${VAR}` in the YAML.

## What gets persisted across restarts

```{list-table}
:header-rows: 1
:widths: 30 70

* - State
  - Persisted?
* - PostgreSQL data
  - **yes**, in the named volume `skava_pgdata`
* - Admin users + audit log
  - **yes** (rows in PostgreSQL)
* - Datasets / replicas / nodes
  - **yes**, plus the seed will NOT re-run on a non-empty DB
* - SKAVA app code
  - **no** — baked into the image
* - Logs in the container filesystem
  - **no** — use `docker logs` or send to an external aggregator
* - In-memory caches
  - **no**
```

```{seealso}
[Production hardening](production.md) — TLS, secrets manager, log
shipping, Prometheus scrape, automated backups.
```
