# Backup

All of SKAVA's persistent state lives in PostgreSQL. Backing it up
is a straightforward `pg_dump` job; the audit log makes restore
drills a non-negotiable quarterly exercise.

## What to back up

```{list-table}
:header-rows: 1
:widths: 30 70

* - State
  - Where
* - Catalogue (datasets / nodes / replicas)
  - ``datasets``, ``nodes``, ``dataset_replicas`` tables
* - Ingestion job history
  - ``ingestion_jobs`` table
* - Admin users
  - ``users`` table
* - Audit log
  - ``audit_log`` table — compliance-relevant, do NOT lose
* - Config (env vars)
  - **NOT in the DB** — back up your secret manager / docker-compose
    file separately
* - Source code
  - Git repo — already replicated by GitHub
* - SIF images
  - Container registry — already replicated
* - state.db on each publisher node
  - **NOT in SKAVA** — back up the publisher hosts' state files
    separately, or accept rebuilding from scratch on a restore
```

## pg_dump baseline

```bash
docker compose exec db pg_dump \
    -U skava -d skava \
    --format=custom \
    --file=/tmp/skava-$(date +%Y%m%d-%H%M).dump

docker compose exec db cat /tmp/skava-2026-06-05-1300.dump \
    > /backups/skava-2026-06-05-1300.dump
```

Ship the file off-host (S3, Backblaze, sibling SRC).

## Automated daily script

```bash
#!/usr/bin/env bash
# /usr/local/bin/skava-backup.sh — cron daily

set -euo pipefail

STAMP=$(date +%Y%m%d-%H%M)
DUMP=/var/backups/skava/skava-${STAMP}.dump
mkdir -p "$(dirname "$DUMP")"

docker compose -f /etc/skava/docker-compose.yml exec -T db \
    pg_dump -U skava -d skava --format=custom > "$DUMP.tmp"
mv "$DUMP.tmp" "$DUMP"

# Off-host copy
aws s3 cp "$DUMP" s3://inaf-skava-backups/

# Retention — keep 30 days locally
find /var/backups/skava -name "*.dump" -mtime +30 -delete
```

```cron
0 2 * * * /usr/local/bin/skava-backup.sh >> /var/log/skava-backup.log 2>&1
```

## Restore

To a fresh PostgreSQL:

```bash
# 1. Start a new postgres alongside production
docker run --rm -d --name skava-restore \
    -e POSTGRES_DB=skava -e POSTGRES_USER=skava -e POSTGRES_PASSWORD=skava \
    -p 5433:5432 postgres:16

# 2. Wait, then restore
sleep 10
cat skava-2026-06-05-1300.dump | docker exec -i skava-restore \
    pg_restore -U skava -d skava --clean --no-acl --no-owner

# 3. Inspect
docker exec -it skava-restore psql -U skava -d skava \
    -c "SELECT count(*) FROM datasets;"
```

To the production DB (with downtime):

```bash
docker compose down api
docker compose exec db pg_restore \
    -U skava -d skava --clean --no-acl --no-owner \
    /tmp/skava-2026-06-05-1300.dump
docker compose up -d api
```

## Continuous archiving (PostgreSQL WAL)

For higher RPO requirements (< 24 h), configure WAL archiving:

```ini
# postgresql.conf
wal_level = replica
archive_mode = on
archive_command = 'aws s3 cp %p s3://inaf-skava-wal/%f'
```

Combined with `pg_basebackup`, this allows point-in-time recovery
to any second in the retention window. Out of scope for this
overview — see the PostgreSQL backup chapter.

## Quarterly DR drill

Schedule on the team calendar:

1. Restore the latest dump into a fresh PostgreSQL.
2. Bring up a SKAVA api container against it on port 8001 (so it
   doesn't collide with production).
3. Validate:
   * admin login works
   * ``/discovery/search`` returns expected counts
   * a publisher dry-run completes
   * a /datalink lookup matches what production returns
4. Time the whole exercise. Aim to bring it under 30 min.
5. Update the runbook with any frictions.

If the drill fails, the restore would also fail during a real
incident. Fix immediately.

## Backup of admin secrets

Configuration (env vars) is not in the DB. Make sure your secret
manager (Vault, AWS Secrets Manager, sealed-secrets in Kubernetes)
has its own backup story. A pg_dump alone is not a recovery plan if
you also lose ``ADMIN_SESSION_SECRET`` and ``INTERNAL_API_KEY``.

## Encryption at rest

PostgreSQL itself doesn't encrypt at rest by default. Options:

* Cloud-managed Postgres (RDS, CloudSQL) ships with disk encryption
  enabled — verify it's on.
* Self-hosted: LUKS-encrypt the volume.
* Per-table column encryption is overkill for SKAVA's data.

For backup files, encrypt before shipping off-host:

```bash
pg_dump ... | gpg --encrypt --recipient skava-ops > skava.dump.gpg
```

## Retention policies

```{list-table}
:header-rows: 1
:widths: 28 40 32

* - Class
  - Hot
  - Cold
* - Daily dumps
  - 30 days locally
  - 365 days in S3
* - Audit-log row archives
  - in the table for 365 days
  - in S3 for compliance horizon
* - WAL segments (if archiving)
  - 7 days
  - 90 days
* - Backups before a destructive migration
  - tagged separately, retain ≥ 2 weeks
  - none
```

Adjust to your SRC's compliance horizon.
