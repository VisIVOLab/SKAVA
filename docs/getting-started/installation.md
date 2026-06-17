# Installation

This page brings up a full SKAVA stack — discovery API + PostgreSQL +
Admin UI — on a single host using Docker Compose. Production
deployments are covered in [Deployment / production](../deployment/production).

## Requirements

* **Docker** 24+ and the **Compose plugin** (`docker compose ...`).
  Older standalone `docker-compose` works too but the commands below
  use the v2 syntax.
* **Git**.
* **8 GB RAM** comfortable for the demo seed; SKAVA itself uses < 200 MB.
* **Port 8000** free on the host. Reassign in `docker-compose.yml` if needed.

## Clone and start

```bash
git clone https://github.com/VisIVOLab/SKAVA.git
cd SKAVA

docker compose -f docker-compose.yml up -d --build
```

The `up` command builds the API image, starts PostgreSQL, runs Alembic
migrations, runs the seed (only on a fresh DB — subsequent restarts
preserve user data), and finally launches `uvicorn` on port 8000.

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
INFO  [alembic.runtime.migration] Running upgrade ... -> 0008_add_admin_users_and_audit
Seeding data...
[seed] Skipping seed: 3 node(s) already present.   ← on warm DB
Starting API...
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## Smoke test

```bash
curl -s http://localhost:8000/system/health | python -m json.tool
```

Expected:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "uptime_seconds": 12.3,
  ...
}
```

A short discovery query confirms the seed loaded:

```bash
curl -s "http://localhost:8000/discovery/search?limit=2" | python -m json.tool
```

You should see a `results` array with two entries.

## Set the internal API key

The internal-ingestion endpoints (used by the publisher CLI and the
admin UI's CSV upload) require an API key. The default
`docker-compose.yml` does not set one — open it and add to the `api:
environment:` block:

```yaml
    environment:
      INTERNAL_API_KEY: <openssl rand -hex 32>
```

Replace the placeholder with the output of `openssl rand -hex 32`.
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

* [Quickstart: query the federation](quickstart) — the actual API
  surface.
* [Publisher overview](../publisher/overview) — register your own
  datasets without manually editing rows.
* [Configuration](../deployment/configuration) — every environment
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
[Troubleshooting](../operations/troubleshooting) for a longer list of
runtime errors.
```
