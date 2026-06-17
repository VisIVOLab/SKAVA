# Upgrades

How to roll SKAVA forward without downtime, and how to roll back
when a release misbehaves.

## Release cadence

SKAVA follows semantic versioning (semver):

* **major** — breaking API or schema changes, e.g. retiring an
  endpoint or changing a column type. We try to bundle these.
* **minor** — new endpoints, new admin pages, new optional config.
  Backwards-compatible.
* **patch** — bug fixes, security patches, log message clarifications.

Migrations land in minor and patch releases as needed; each one is
designed to be applied without service downtime.

## Migration model

* SKAVA uses Alembic. Every migration is forward and backward
  compatible **for one minor version** — i.e. SKAVA v0.2 can run
  against either v0.2 schema or v0.1 schema (read-only on the
  obsolete columns).
* The entrypoint script runs ``alembic upgrade head`` at every
  container start. New api containers therefore always pull the
  schema up.

## Standard upgrade (downtime-tolerant)

For SRCs with maintenance windows:

```bash
# 1. Drain inbound traffic at the reverse proxy (502 / maintenance page).
# 2. Backup
docker compose exec db pg_dump -U skava -d skava --format=custom \
    --file=/tmp/preupgrade.dump

# 3. Pull the new image
docker compose pull api

# 4. Recreate api container — runs Alembic on boot
docker compose up -d api

# 5. Smoke test
curl -fsS http://localhost:8000/system/health | jq

# 6. Re-enable traffic at the proxy
```

Total downtime: < 1 min for an empty queue, a few minutes if there
are large pending Alembic migrations.

## Zero-downtime upgrade

For continuous SRCs:

```{mermaid}
sequenceDiagram
    participant LB as Load balancer
    participant Old as api v0.1.3 (existing)
    participant New as api v0.1.4 (rolling)
    participant DB  as PostgreSQL

    Note over Old,New: 1. Spin up new replica with new image
    New->>DB: alembic upgrade head (new migrations)
    DB-->>New: schema at head
    Note over Old,New: 2. Both replicas serve traffic (schema compatible)
    LB->>Old: request
    LB->>New: request
    Note over Old,New: 3. Drain old replica
    Old-->>LB: deregister
    Note over Old,New: 4. Stop old replica
    Note over LB,New: 5. Only new replica left
```

Prerequisites:

* Schema migrations in the new release are **additive only**
  (release notes will say if not).
* The reverse proxy / orchestrator supports rolling deploys.
* You have ≥ 2 replicas.

## Rolling back

```bash
# Roll the image back. Schema stays at the new head.
docker compose down api
docker compose pull api:v0.1.3
docker compose up -d api
```

Alembic migrations are not auto-reverted. If the new release added
columns and you rolled back, the old code simply ignores them — no
data loss.

For a hostile schema change (rare; flagged in release notes), the
release ships a downgrade migration:

```bash
docker compose exec api alembic downgrade -1
```

Always test the downgrade on a staging DB before applying to
production.

## Upgrade checklist

```{list-table}
:header-rows: 1
:widths: 60 40

* - Step
  - Owner
* - 1. Read release notes; flag any "BREAKING" or
    "manual migration required" items.
  - admin
* - 2. Backup PostgreSQL (always — see :doc:`backup`).
  - admin
* - 3. Update ``docker-compose.yml`` / Helm chart image tag.
  - admin
* - 4. Pull the new image (``docker compose pull`` / ``helm pull``).
  - automated
* - 5. Restart api containers; verify the
    ``alembic upgrade head`` line in logs.
  - admin
* - 6. ``curl /system/health`` + a sample
    ``curl /discovery/search?limit=1`` to validate.
  - admin
* - 7. Run a publisher dry-run against the upgraded instance.
  - ingester
* - 8. Watch ``skava_http_requests_total`` 5xx rate for 15 min;
    rollback if it spikes.
  - on-call
```

## Migration-specific gotchas

```{list-table}
:header-rows: 1
:widths: 28 72

* - Migration
  - Notes
* - ``0008 add_admin_users_and_audit``
  - Adds the admin subsystem. No effect on existing API behaviour.
    Run ``python -m app.admin.cli create-user --role admin`` to
    bootstrap.
* - ``0007 add_visivo_backend``
  - Two new columns on ``nodes``. Defaults to empty, so existing
    deployments without a VisIVO backend keep working unchanged.
* - ``0006 production_readiness``
  - Indexes on hot paths. Migration takes O(n log n) on big DBs;
    run during maintenance windows for catalogues > 1 M rows.
* - earlier migrations
  - schema-stable; safe to roll forward without ceremony.
```

## Publisher CLI upgrades

The publisher is a separate package with its own version. SKAVA's
internal ingestion API maintains backwards compatibility for at
least two minor versions, so:

* New publisher + old SKAVA = works.
* Old publisher + new SKAVA = works.

Update the SIF image on each node at your own pace; it doesn't have
to lockstep with the SKAVA release.

## Apptainer image upgrades

```bash
# On the data node
cd /srv/skava-source
git pull
cd tools/skava-publisher
apptainer build --fakeroot publisher.sif.new apptainer/publisher.def
mv publisher.sif.new /opt/skava/publisher.sif
systemctl restart skava-publisher.timer
```

Always keep the previous SIF available for instant rollback:

```bash
mv /opt/skava/publisher.sif /opt/skava/publisher-prev.sif
```

## When NOT to upgrade

* During an ingestion run (wait for it to complete; the publisher's
  state.db keeps the next one short).
* During SKA night-shift observations if your SRC pulls from them
  live.
* Friday afternoons. The classic.
