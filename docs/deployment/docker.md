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
    healthcheck: …

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
      INTERNAL_API_KEY: <set me>
      ADMIN_SESSION_SECRET: <set me>
    ports:
      - "8000:8000"
    depends_on:
      db: { condition: service_healthy }

volumes:
  skava_pgdata:
```

Production deployments customise this — see
[production](production).

## Production overrides (ready-made)

The repo ships compose overrides and nginx configs so you don't have to
hand-roll a production stack. Start from `docker-compose.staging.yml`
(postgres + api + nginx, internal networks, rate limiting) and layer **one**
production override on top. First create the secrets file:

```bash
cp .env.prod.example .env.prod      # fill POSTGRES_PASSWORD, INTERNAL_API_KEY,
                                    # ADMIN_SESSION_SECRET, SKAVA_PUBLIC_BASE_URL (https)
```

All overrides set `SKAVA_ENV=production`, harden the containers
(`no-new-privileges`, `cap_drop`, `read_only` + tmpfs, mem/pids limits) and
set `SKAVA_RUN_SEED=false` (no demo data — load real metadata via the
ingestion API / publisher).

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
    terminates its **own** TLS on a free port (default `8443`) reusing an
    existing Let's Encrypt cert. Uses `docker/nginx/nginx.tls.conf` + mounts
    `/etc/letsencrypt` read-only.
* - `docker-compose.shared-proxy.yml`
  - Run **behind an existing reverse proxy**. SKAVA publishes no host ports;
    it joins the proxy's Docker network so the proxy reaches
    `skava-discovery:8000`. Add the vhost from
    `docker/nginx/skava.vhost.example.conf` to that proxy.
```

Example — self-hosted TLS on port 8443:

```bash
docker compose -f docker-compose.staging.yml -f docker-compose.selfhost-tls.yml \
    --env-file .env.prod up -d --build
```

See [production](production) for the full hardening checklist (TLS, secrets,
backups, monitoring).

## Dockerfile structure

Two-stage build: a `builder` stage that uses `pip wheel` to compile
SKAVA + dependencies, and a slim `runtime` stage that installs only
the resulting wheels and copies the migrations.

The resulting image is ~250 MB, single-architecture (default amd64).
For ppc64le or arm64 builds, add the appropriate `platforms:` block
to the buildx invocation; the Dockerfile itself has no
arch-specific code.

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
  - `curl -s localhost:8000/system/metrics | head`
```

## Live-reload during development

By default the api container bakes the source code into the image —
every edit needs a `docker compose build api`. For tight dev loops
add a bind mount:

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
slow VM), its own `wait_for_db()` loop retries 30 × 2 s before giving
up.

## Multi-instance with Compose

Single Compose stack runs one SKAVA. For multi-instance dev (e.g. to
test federation), copy the stack to a sibling directory and change:

* `container_name` (must be unique)
* the host port mappings (`8000`, `5432`)
* the volume name (`skava_pgdata` → `skava_pgdata_dev2`)

Real production multi-instance setups belong in Kubernetes — see
[production](production) for the path forward.

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
[Production hardening](production) — TLS, secrets manager, log
shipping, Prometheus scrape, automated backups.
```
