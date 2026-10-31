# Production deployment

Step-by-step hardening of the dev Docker Compose setup into something
fit for an operational SRC. We don't prescribe a specific
orchestrator — the same checklist applies whether you ship SKAVA on
Compose, Kubernetes, Nomad, or a single SystemD-managed Docker
service.

## Checklist at a glance

1. [TLS termination at a reverse proxy](#1-tls-at-the-edge)
2. [Secrets from a secret manager, never inline](#2-secrets)
3. [PostgreSQL HA / managed instance](#3-postgresql)
4. [Persistent volume backups](#4-backups)
5. [Log shipping](#5-logs)
6. [Prometheus scrape + alerts](#6-metrics)
7. [Rolling upgrades](#7-upgrades)
8. [Admin user lifecycle](#8-admin-users)
9. [Capacity planning](#9-capacity)
10. [Disaster recovery test](#10-disaster-recovery-test)

## 1. TLS at the edge

The api container speaks plain HTTP on port 8000. Put nginx /
Traefik / Envoy in front. The repository ships ready-made variants
(`docker/nginx/nginx.prod.conf` behind Caddy, `nginx.tls.conf` with its
own TLS, `skava.vhost.example.conf` for an existing proxy — see
[Docker](docker.md#production-overrides-ready-made)). Minimal nginx
fragment:

```nginx
server {
    listen 443 ssl http2;
    server_name skava.inaf.it;

    ssl_certificate     /etc/letsencrypt/live/skava.inaf.it/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/skava.inaf.it/privkey.pem;

    # HSTS — 1 year, opt-in. Remove if you also serve dashboards on
    # subdomains without HTTPS.
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Body size — large enough for CSV bulk uploads (publisher push).
    client_max_body_size 64M;

    location / {
        proxy_pass         http://skava-api:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

Set the corresponding SKAVA env vars:

```yaml
environment:
  SKAVA_PUBLIC_BASE_URL: https://skava.inaf.it
  ADMIN_SESSION_COOKIE_SECURE: "true"
```

## 2. Secrets

Never inline a secret in ``docker-compose.yml`` or in a Git-tracked
``.env`` file. Recommended patterns:

* **Docker Compose**: use Docker Secrets backed by a HashiCorp Vault
  agent, or mount the secrets as files and reference with the
  ``_FILE`` env-var suffix supported by the official postgres image.
* **Kubernetes**: ``Secret`` objects, mounted as env or files; ideally
  sync'd from Vault / AWS SM via External Secrets Operator.
* **Bare host**: SystemD ``EnvironmentFile=`` pointing at a file with
  ``0600`` perms owned by root.

The secrets to manage:

* ``ADMIN_SESSION_SECRET``
* ``INTERNAL_API_KEY``
* PostgreSQL credentials
* ``SKAVA_ACCESS_TOKENS`` and ``SKAVA_VISIVO_BACKEND_TOKEN``, if used
* TLS private key (for the proxy, not SKAVA)

OIDC needs no secret on the SKAVA side: it only reads the IAM's
public key set.

## 3. PostgreSQL

The shipped Compose stack runs a single Postgres 16 container. That is
fine for testbed / single-tenant SRC use. For production, use a
managed instance (AWS RDS, GCP CloudSQL, INAF-Garr DBaaS, …) or a
PostgreSQL cluster with synchronous replication.

Point SKAVA at it by changing ``SKAVA_DATABASE_URL``:

```yaml
environment:
  SKAVA_DATABASE_URL: postgresql+psycopg://skava@db-prod.svc:5432/skava?sslmode=require
```

Remove the ``db`` service from Compose, or leave it as a dev fallback.
Tune the pool:

* ``SKAVA_DB_POOL_SIZE=20`` (matches a small SRC's concurrent admin +
  publisher load; the staging compose file uses this)
* ``SKAVA_DB_MAX_OVERFLOW=30``
* ``SKAVA_DB_POOL_RECYCLE=1800`` (avoid stale connections through
  middlebox firewalls)

## 4. Backups

```bash
docker exec skava-postgres-staging pg_dump -U skava -d skava \
    --format=custom --file=/tmp/skava-$(date +%Y%m%d).dump
```

Automate with cron (every 6 h) + retention. Ship the dumps off-host
to S3 / Backblaze / a sibling SRC. The audit log alone is a
compliance artefact you don't want to lose.

Document the **restore drill** procedure in your team runbook and
run it quarterly.

## 5. Logs

SKAVA emits structured JSON on stdout. Ship them with one of:

* **Loki + Promtail** — same Grafana stack as metrics; great for
  cross-service log search.
* **Elastic Stack** — Filebeat → Elasticsearch + Kibana.
* **Cloud aggregators** — CloudWatch (AWS), Stackdriver (GCP).

Key fields to alert on:

* ``level=ERROR``
* ``logger=skava.admin.audit`` lines with ``action=auth.login_failed``
  at a rate > N/min
* ``logger=skava.request status_code=5xx`` rate spike
* ``logger=skava.ingestion message=ingestion_record_skipped``
* ``logger=skava.telemetry message=node_probe_failed`` (a node's
  backend stopped answering)
* ``logger=skava.federation`` warnings (a sibling catalogue failing)

## 6. Metrics

The api exposes Prometheus metrics at ``/metrics``. The production
nginx configs answer 403 on ``/metrics``, so scrape the container on
the internal network:

```yaml
- job_name: skava
  metrics_path: /metrics
  static_configs:
    - targets: ["skava-discovery:8000"]
```

The published metrics are HTTP request counts and latency histograms
by method + path, ranking decisions per chosen node, fallbacks, DB
errors, and the node prober's outcomes and round trips — see
[Operations / monitoring](../operations/monitoring.md) for the full list.

Recommended alerts:

* p95 latency > 1 s for ``/discovery/search`` over 5 min
* any increase of ``skava_db_errors_total``
* node probes failing (``skava_node_probes_total{outcome="failed"}``)
* heartbeat (``up{job="skava"} == 0`` for 2 min)

## 7. Upgrades

* Pin the image tag in production (for example ``skava-api:v0.1.2``), never use
  ``latest``.
* Run Alembic migrations as part of the deploy; the entrypoint
  already runs ``alembic upgrade head`` on startup, which is a no-op
  when the schema is current.
* For zero-downtime upgrades, deploy a second replica with the new
  image, wait for healthchecks, then drain the old one.
* Keep one minor version old image around for rollback.

See [Operations / upgrades](../operations/upgrades.md) for a detailed
upgrade runbook.

## 8. Admin users

* Bootstrap the first admin with ``python -m app.admin.cli create-user
  --role admin --username <opname>`` (prompts for the password).
* Use ``--role ingester`` for publisher-CLI operators (so they can
  trigger ingestion via the UI without full admin rights).
* Use ``--role viewer`` for support / monitoring read-only access.
* Decommission a user with ``python -m app.admin.cli deactivate
  --username <name>`` — keeps the audit history intact.

## 9. Capacity

A single SKAVA api process handles a few hundred discovery queries
per second on a 4-vCPU host. PostgreSQL is the bottleneck before
SKAVA is. Scale-out options when one process isn't enough:

* Add api replicas behind the reverse proxy — SKAVA is stateless
  apart from PostgreSQL. Give every replica the same
  ``ADMIN_SESSION_SECRET``, and note that each replica with
  ``SKAVA_TELEMETRY_INTERVAL_SECONDS`` > 0 runs its own prober.
* `/soda/execute` already runs the cutout on the node's co-located
  VisIVO backend, so SKAVA only waits for it (bounded by
  `SKAVA_SODA_BACKEND_TIMEOUT_SECONDS`) and proxies the result.
* Use read replicas for discovery if you saturate the primary.

## 10. Disaster recovery test

Schedule a quarterly drill:

1. Restore the latest backup into a fresh PostgreSQL instance.
2. Bring up a SKAVA api container against it.
3. Validate that admin login still works, discovery returns
   expected counts, and the publisher CLI can run a dry-run.
4. Document the time-to-recovery; iterate to bring it under 30 min.

```{seealso}
[Operations / backup](../operations/backup.md) for the actual scripts
and [Operations / monitoring](../operations/monitoring.md) for the
Prometheus / Grafana setup.
```
