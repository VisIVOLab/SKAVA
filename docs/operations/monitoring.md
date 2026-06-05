# Monitoring

SKAVA exposes Prometheus metrics, structured JSON logs, and a
health endpoint. This page connects them to a production
observability stack.

## Health endpoint

```
GET /system/health
```

Always public. Response:

```json
{
    "status": "ok",
    "version": "0.1.0",
    "uptime_seconds": 12345.6,
    "db_ok": true
}
```

Use this for load-balancer healthchecks and Kubernetes
liveness/readiness probes:

```yaml
livenessProbe:
  httpGet:
    path: /system/health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 30
readinessProbe:
  httpGet:
    path: /system/health
    port: 8000
  periodSeconds: 5
```

## Prometheus metrics

```
GET /system/metrics
```

Standard Prometheus exposition format. Scrape config:

```yaml
- job_name: skava
  metrics_path: /system/metrics
  static_configs:
    - targets: ["skava-api:8000"]
  scrape_interval: 15s
```

### Published metrics

```{list-table}
:header-rows: 1
:widths: 38 12 50

* - Metric
  - Type
  - Labels / meaning
* - ``skava_http_requests_total``
  - counter
  - Labels: ``method``, ``route``, ``status``. Cumulative request
    count.
* - ``skava_http_request_duration_seconds``
  - histogram
  - Per-route latency. Buckets: 5 ms → 10 s.
* - ``skava_active_sessions``
  - gauge
  - Admin UI sessions currently valid.
* - ``skava_db_pool_connections``
  - gauge
  - Labels: ``state`` (active / idle / overflow).
* - ``skava_ingestion_jobs_total``
  - counter
  - Labels: ``status`` (succeeded / failed / partial).
* - ``skava_ingestion_records_total``
  - counter
  - Labels: ``outcome`` (inserted / updated / skipped).
* - ``skava_audit_writes_total``
  - counter
  - Labels: ``action_prefix``.
* - ``skava_app_info``
  - gauge
  - Constant 1 with labels ``version``, ``env``.
```

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
              sum(rate(skava_http_request_duration_seconds_bucket{route="/discovery/search"}[5m]))
              by (le)) > 1
    for:   10m
    annotations:
      summary: "p95 discovery latency over 1s for 10 min"

  - alert: SkavaDBPoolSaturated
    expr:  skava_db_pool_connections{state="active"}
              == on(instance) skava_db_pool_connections{state="max"}
    for:   3m
    annotations:
      summary: "DB connection pool exhausted"

  - alert: SkavaIngestionFailure
    expr:  rate(skava_ingestion_jobs_total{status="failed"}[1h]) > 0
    annotations:
      summary: "Ingestion job(s) failed in the last hour"

  - alert: SkavaAuthFailureSpike
    expr:  rate(skava_audit_writes_total{action_prefix="auth.login_failed"}[5m])
              > 5
    for:   2m
    annotations:
      summary: "Login failure spike — possible brute force"
```

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
    "query_params": {"limit": "10", "dataproduct_type": "image"},
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
  - One line per request: method, route, status, duration_ms.
* - ``skava.admin.auth``
  - Login events (success + failure).
* - ``skava.admin.audit``
  - One line per audit row (mirrors the DB row).
* - ``skava.ingestion``
  - Per-job summary + per-record errors.
* - ``skava.skava``
  - DataLink ranking decisions.
```

## Grafana dashboard

A starter dashboard ships at `contrib/grafana/skava.json`. Panels:

* Requests/s by route
* p50 / p95 / p99 latency per route
* DB pool utilisation
* Ingestion jobs over 24 h
* Failed-login rate
* Audit writes per action_prefix
* Discovery results returned (proxy for catalogue size)

Import via Grafana → + → Import → paste JSON.

## Tracing (optional)

Outside Phase 1's scope but recommended for production. SKAVA's
``request_id`` header is the natural correlation point — every
log line and audit row carries it. Wiring it through to a tracing
backend (Tempo, Jaeger, OpenTelemetry Collector) is a thin layer of
middleware away.

The roadmap covers an opt-in OpenTelemetry instrumentation in
Phase 4.

## What's NOT instrumented yet

* Per-route memory profiling. Use ``py-spy`` ad-hoc.
* Per-user request rate (would need a user dimension on the metrics
  — privacy review needed first).
* SQL slow-query logging from the SKAVA side (PostgreSQL itself does
  this via ``log_min_duration_statement``).

## On-call runbook quick links

* "SKAVA returning 5xx" — [Troubleshooting → 5xx](troubleshooting#5xx)
* "Discovery slow" — [Troubleshooting → slow discovery](troubleshooting#slow-discovery)
* "Ingestion failing" — [Troubleshooting → ingestion errors](troubleshooting#ingestion-errors)
