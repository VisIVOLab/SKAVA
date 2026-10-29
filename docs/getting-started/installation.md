# Installation

This page brings up a full SKAVA stack — discovery API + PostgreSQL +
Admin UI — on a single host using Docker Compose. Production
deployments are covered in [Deployment / production](../deployment/production.md).

## Requirements

* **Docker** 24+ and the **Compose plugin** (`docker compose ...`).
  Older standalone `docker-compose` works too but the commands below
  use the v2 syntax.
* **Git**.
* **8 GB RAM** comfortable for the demo seed; SKAVA itself uses < 200 MB.
* **Ports 8000** (API) and **5432** (PostgreSQL) free on the host.
  Reassign in `docker-compose.yml` if needed.

## Clone and start

```bash
git clone https://github.com/VisIVOLab/SKAVA.git
cd SKAVA

docker compose -f docker-compose.yml up -d --build
```

The `up` command builds the API image, starts PostgreSQL, runs the
Alembic migrations (in `migrations/`), runs the demo seed (only on a
fresh DB — subsequent restarts preserve user data; set
`SKAVA_RUN_SEED=false` to skip it), and finally launches `uvicorn` on
port 8000.

Watch the logs:

```bash
docker compose -f docker-compose.yml logs -f api
```

You should see, in order:

```
Waiting for database to be ready...
Database ready (attempt 1).
Running migrations...
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade ... -> 0009_add_node_telemetry
Seeding data...
[seed] Skipping seed: 3 node(s) already present.   ← on warm DB
Starting API...
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## Smoke test

```bash
curl -s "http://localhost:8000/availability?include_nodes=true" | python -m json.tool
```

Expected:

```json
{
  "status": "ok",
  "service": "skava-discovery",
  "database": {"status": "ok", "database": "reachable"},
  "nodes": {"total_nodes": 3, "enabled_nodes": 3, "available_nodes": 3}
}
```

A short discovery query confirms the seed loaded:

```bash
curl -s "http://localhost:8000/discovery/search?limit=2" | python -m json.tool
```

You should see a `results` array with two entries (the seed has seven
demo datasets, `dataset-1` … `dataset-7`, on nodes `A`, `B` and `C`).

## Set the internal API key

The internal endpoints (`/internal/ingestion/*`, used by the publisher
CLI, and `/internal/telemetry*`) require an API key in the
`X-Internal-Api-Key` header. The default `docker-compose.yml` sets a
development value (`dev-mac-key-not-for-prod-rotate-me-please`); replace
it in the `api: environment:` block:

```yaml
    environment:
      INTERNAL_API_KEY: <openssl rand -hex 32>
```

Replace the placeholder with the output of `openssl rand -hex 32`. (The
admin UI's CSV upload runs the same ingestion service in-process and
does not need the key.)
Recreate the container so the new env var is picked up:

```bash
docker compose -f docker-compose.yml up -d
```

## Bootstrap the first admin user

The admin UI lives at `/admin`. To get in you need at least one user
with the `admin` role. Use the CLI inside the api container:

```bash
docker compose -f docker-compose.yml exec -it api \
    python -m app.admin.cli create-user \
        --username yourname --role admin --email you@inaf.it
```

You'll be prompted for a password (policy: ≥ 12 chars, mixed case,
≥ 1 digit). On success:

```
✓ Created user yourname (id=1, role=admin)
```

Visit <http://localhost:8000/admin/login> and sign in. The dashboard
shows the seed counts and your profile.

## Next steps

* [Quickstart: query the federation](quickstart.md) — the actual API
  surface.
* [Publisher overview](../publisher/overview.md) — register your own
  datasets without manually editing rows.
* [Configuration](../deployment/configuration.md) — every environment
  variable in one place.

## Common installation issues

```{list-table}
:header-rows: 1
:widths: 35 65

* - Symptom
  - Fix
* - `Cannot start service api: address already in use`
  - Port 8000 is taken on the host. Change the `ports:` mapping in
    docker-compose.yml or stop the conflicting process.
* - `OperationalError: connection to server ... failed`
  - PostgreSQL hasn't fully started yet. The api container retries
    30 times with 2 s backoff; if it still fails, run
    `docker compose logs db` to inspect.
* - Admin login returns 401 even with the right password
  - The session cookie may be cached with the `Secure` flag from a
    previous run. Open the browser DevTools → Application → Cookies
    → clear `skava_admin_session`, then retry.
* - "Skipping seed" on first start
  - Means the DB volume has data from a previous install. Use
    `docker compose down -v` to drop the volume if you really want a
    fresh seed.
```

```{seealso}
[Troubleshooting](../operations/troubleshooting.md) for a longer list of
runtime errors.
```
