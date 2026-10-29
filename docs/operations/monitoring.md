# Monitoring

SKAVA exposes Prometheus metrics, structured JSON logs, and
health endpoints. This page connects them to a production
observability stack.

## Health endpoints

```
GET /health/db
GET /availability[?include_nodes=true]
```

Both are public. `/health/db` runs `SELECT 1`:

```json
{"status": "ok", "database": "reachable"}
```

`/availability` (the VOSI availability resource) adds the node summary
when asked:

```json
{
    "status": "ok",
    "service": "skava-discovery",
    "database": {"status": "ok", "database": "reachable"},
    "nodes": {"total_nodes": 4, "enabled_nodes": 4, "available_nodes": 4}
}
```

Both answer **503** when the database is unreachable. `/availability`
reports `"status": "degraded"` when `include_nodes=true` and no
enabled node is available. Behind the shipped nginx, `/healthz`
answers `ok` from the proxy itself (it does not reach SKAVA).

Use `/health/db` for load-balancer healthchecks and Kubernetes
liveness/readiness probes (the staging compose file's healthcheck does):

```yaml
livenessProbe:
  httpGet:
    path: /health/db
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 30
readinessProbe:
  httpGet:
    path: /health/db
    port: 8000
  periodSeconds: 5
```

## Prometheus metrics

```
GET /metrics
```

Standard Prometheus exposition format. The production nginx configs
block `/metrics` (403), so scrape the container on the internal
network:

```yaml
- job_name: skava
  metrics_path: /metrics
  static_configs:
    - targets: ["skava-discovery:8000"]
  scrape_interval: 15s
```

### Published metrics

Defined in `app/metrics.py`; the Python client's default process and
platform collectors are exported as well.

```{list-table}
:header-rows: 1
:widths: 38 12 50

* - Metric
  - Type
  - Labels / meaning
* - ``skava_http_requests_total``
  - counter
  - Labels: ``method``, ``endpoint`` (request path), ``status``.
    Cumulative request count.
* - ``skava_http_request_latency_seconds``
  - histogram
  - Labels: ``method``, ``endpoint``. Request latency (client default
    buckets, 5 ms → 10 s).
* - ``skava_ranking_decisions_total``
  - counter
  - Label: ``node``. One per routing decision (discovery, DataLink,
    ``/soda/execute``), by the node chosen.
* - ``skava_ranking_fallback_total``
  - counter
  - Label: ``reason``. DataLink fell back from the top-ranked replica
    (``primary_endpoint_unhealthy``).
* - ``skava_db_errors_total``
  - counter
  - Label: ``operation``. Database errors seen by the health check
    (``health_db``).
* - ``skava_node_probes_total``
  - counter
  - Labels: ``node``, ``outcome`` (``ok`` / ``failed``). Telemetry
    probes of each node's VisIVO backend.
* - ``skava_node_rtt_ms``
  - gauge
  - Label: ``node``. Median ``/v1/ping`` round trip at the last
    successful probe.
```

The probe metrics move only when the prober runs
(`SKAVA_TELEMETRY_INTERVAL_SECONDS` > 0, or
`POST /internal/telemetry/probe`). What each node last reported, and
the ranking policy in force, is in `GET /internal/telemetry`
(internal API key).

Note that `endpoint` is the raw path, so routes with a path parameter
(`/datalink/{obs_id}`) produce one series per dataset.

### Sample alert rules

```yaml
groups:
- name: skava
  rules:

  - alert: SkavaDown
    expr:  up{job="skava"} == 0
    for:   2m
    annotations:
      summary: "SKAVA API unreachable"

  - alert: SkavaHighLatency
    expr:  histogram_quantile(0.95,
              sum(rate(skava_http_request_latency_seconds_bucket{endpoint="/discovery/search"}[5m]))
              by (le)) > 1
    for:   10m
    annotations:
      summary: "p95 discovery latency over 1s for 10 min"

  - alert: SkavaServerErrors
    expr:  sum(rate(skava_http_requests_total{status=~"5.."}[5m])) > 0.1
    for:   5m
    annotations:
      summary: "SKAVA answering 5xx"

  - alert: SkavaDBErrors
    expr:  increase(skava_db_errors_total[10m]) > 0
    annotations:
      summary: "Database errors in the last 10 min"

  - alert: SkavaNodeProbeFailing
    expr:  increase(skava_node_probes_total{outcome="failed"}[5m]) > 0
           unless on(node) increase(skava_node_probes_total{outcome="ok"}[5m]) > 0
    for:   5m
    annotations:
      summary: "A node backend is not answering probes"

  - alert: SkavaRoutingFallbacks
    expr:  rate(skava_ranking_fallback_total[15m]) > 0
    for:   15m
    annotations:
      summary: "DataLink keeps falling back from the top-ranked node"
```

Failed admin logins are not a metric: they are audit rows
(`auth.login_failed`) and `skava.admin.audit` log lines — alert on
them from the log pipeline.

## Logs

JSON-structured to stdout. Sample:

```json
{
    "timestamp": "2026-06-05T13:01:33.808067+00:00",
    "level": "INFO",
    "logger": "skava.request",
    "message": "request_completed",
    "request_id": "97f25c08-…",
    "endpoint": "/discovery/search",
    "query_params": {"limit": "10", "DPTYPE": "image"},
    "status_code": 200,
    "execution_time_ms": 8.2
}
```

### Ship them

* **Loki + Promtail** — Grafana stack.
* **Elastic Stack** — Filebeat → Elasticsearch + Kibana.
* **CloudWatch** / **Stackdriver** — managed.

For Loki, add a labels block:

```yaml
scrape_configs:
- job_name: skava
  static_configs:
    - targets: [skava-api]
      labels:
        job:  skava
        env:  prod
  pipeline_stages:
    - json:
        expressions:
          level:     level
          logger:    logger
          request_id: request_id
    - labels:
        level:
        logger:
```

### Key logger names

```{list-table}
:header-rows: 1
:widths: 32 68

* - Logger
  - Purpose
* - ``skava.request``
  - One ``request_completed`` line per request: endpoint, query
    parameters, status code, ``execution_time_ms``.
* - ``skava.admin.auth``
  - Session warnings (e.g. ``ADMIN_SESSION_SECRET`` not set).
* - ``skava.admin.audit``
  - One line per audit row (mirrors the DB row), including
    ``auth.login`` / ``auth.login_failed``.
* - ``skava.ingestion``
  - ``ingestion_summary`` per job + ``ingestion_record_skipped`` per
    rejected record.
* - ``skava.discovery`` / ``skava.datalink``
  - Ranking decisions (``discovery_selection``,
    ``datalink_selection``) and fallbacks (``datalink_fallback``).
* - ``skava.soda.exec``
  - ``/soda/execute`` delegations to node backends.
* - ``skava.telemetry``
  - Prober failures (``node_probe_failed``, ``node_probe_cycle_failed``).
* - ``skava.federation``
  - A sibling catalogue that failed or timed out.
```

## Tracing (optional)

Not built in, but recommended for production. SKAVA's
``X-Request-ID`` header (taken from the request or generated, and
returned on the response) is the natural correlation point — every
log line and audit row carries it. Wiring it through to a tracing
backend (Tempo, Jaeger, OpenTelemetry Collector) is a thin layer of
middleware away.

## What is not instrumented

* Per-route memory profiling. Use ``py-spy`` ad-hoc.
* Per-user request rate (would need a user dimension on the metrics
  — privacy review needed first).
* SQL slow-query logging from the SKAVA side (PostgreSQL itself does
  this via ``log_min_duration_statement``).
* DB connection-pool usage, ingestion job counts and federation
  outcomes (use ``/admin/history`` and the federated response's
  per-source ``status`` instead).

## On-call runbook quick links

* "SKAVA returning 5xx" — [Troubleshooting → 5xx](troubleshooting.md#5xx-errors)
* "Discovery slow" — [Troubleshooting → slow discovery](troubleshooting.md#slow-discovery)
* "Ingestion failing" — [Troubleshooting → ingestion errors](troubleshooting.md#ingestion-errors)
