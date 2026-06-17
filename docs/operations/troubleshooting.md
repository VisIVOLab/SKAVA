# Troubleshooting

Catalogue of common errors and how to resolve them. Bookmark this
page; on-call browses it the most.

## Quick decision tree

* Can't load any SKAVA URL? → [API unreachable](#api-unreachable)
* Discovery returns empty / wrong results? → [Discovery anomalies](#discovery-anomalies)
* Publisher CLI fails? → [Publisher issues](#publisher-issues)
* Admin UI login broken? → [Admin UI auth](#admin-ui-auth)
* Desktop client routing wrong? → [Routing issues](#routing-issues)
* 5xx responses? → [5xx errors](#5xx)
* Slow responses? → [Slow discovery](#slow-discovery)
* Ingestion failures? → [Ingestion errors](#ingestion-errors)

(api-unreachable)=
## API unreachable

```{list-table}
:header-rows: 1
:widths: 35 65

* - Symptom
  - Fix
* - ``curl /system/health`` → ``Connection refused``
  - Container not running. ``docker compose ps``; ``logs api``.
* - ``Cannot start service api: address already in use``
  - Port 8000 taken on host. ``lsof -i :8000``; stop the conflicting
    process or remap.
* - ``api`` healthy but external clients can't reach it
  - Reverse proxy / firewall. Test from inside the host first;
    ``curl http://localhost:8000/system/health``.
```

(discovery-anomalies)=
## Discovery anomalies

```{list-table}
:header-rows: 1
:widths: 35 65

* - Symptom
  - Fix
* - ``/discovery/search?limit=3`` returns ``"results": null``
  - You probably hit the wrong path. The endpoint is
    ``/discovery/search``, not ``/discovery`` (which 404s).
* - All records missing the ``visivo-backend`` descriptor
  - The Node row's ``visivo_backend_url`` is empty. Set it in
    ``/admin/nodes/{id}/edit``.
* - Records show up in ``/discovery`` but ``/datalink/{obs_id}``
    returns 404
  - Stale cache somewhere. Curl directly bypassing any CDN; restart
    api if persistent.
* - ``"unknown node X"`` per record on ingestion
  - The publisher's ``node.code`` doesn't match any Node row in
    SKAVA. Create the Node in admin first.
* - Cone search returns zero but you know data is in the cone
  - Spatial index possibly not populated. Re-publish; or fix the
    publisher to set ``s_ra`` / ``s_dec`` correctly.
```

(publisher-issues)=
## Publisher issues

### Key length 0 / 401 from SKAVA

```bash
export SKAVA_INTERNAL_API_KEY=$(docker compose -f ~/SKAVA/docker-compose.yml \
    exec api printenv INTERNAL_API_KEY | tr -d '\r\n')
echo "len: ${#SKAVA_INTERNAL_API_KEY}"
```

If the length is 0, the env var isn't set in the SKAVA api container.
Add ``INTERNAL_API_KEY: <hex>`` to ``docker-compose.yml`` under the
``api: environment:`` block, then ``docker compose up -d`` (NOT just
``restart`` — restart doesn't pick up env-var changes).

### `access_url must start with http:// or https://`

You're hitting an older SKAVA that requires HTTP URLs in
``access_url``. Upgrade SKAVA to a release that accepts any
scheme (since `0.1.0`), or change ``file_serve_url_pattern`` to
http(s).

### `Validation failed: SKAVA returned 401: Invalid or missing internal API key`

Header name mismatch. SKAVA expects ``X-Internal-Api-Key``. Older
publisher releases sent ``X-Internal-Key``. Upgrade the publisher
to ≥ 0.1.0.

### Build of the Apptainer image fails on ppc64le with `llvmlite`

Known: SKAVA's stack on ppc64le has version-juggling pain with
LLVM. Either:

* Build the conda-based variant (``backend-conda.def``) which uses
  pre-compiled wheels from conda-forge.
* Drop the `numba` requirement from the publisher's
  ``pyproject.toml`` (the FITS extractor doesn't actually use it).

(admin-ui-auth)=
## Admin UI auth

### "internal_error" on `/admin/login`

Check ``docker compose logs api`` for the traceback. Common causes:

* `TypeError: unhashable type: 'dict'` → upgrade SKAVA; older
  versions of ``templating.py`` use the deprecated
  ``TemplateResponse(template, ctx)`` signature.
* `TemplateNotFound: 'login.html'` → admin templates not in the
  image. Verify the image was built with package-data including
  ``app/admin/templates/*.html`` (handled in current
  ``pyproject.toml``).

### Login form 403 on every submit

CSRF mismatch. Usually because ``ADMIN_SESSION_SECRET`` is being
generated fresh on every request:

```bash
docker compose logs api | grep "ADMIN_SESSION_SECRET not set"
```

Set the env var to a stable value (``openssl rand -hex 32``).

### Wrong password rejects login but right password also fails

If you're on local HTTP and ``ADMIN_SESSION_COOKIE_SECURE=true``, the
browser won't send back the session cookie → CSRF fails →
403. Either:

* Set ``ADMIN_SESSION_COOKIE_SECURE=false`` for local dev.
* Run SKAVA behind HTTPS.

(routing-issues)=
## Routing issues (desktop client)

```{list-table}
:header-rows: 1
:widths: 36 64

* - Symptom
  - Diagnosis
* - Badge stays grey "Backend: Local" despite a registered backend
  - URL mismatch. Compare the descriptor's ``endpoint`` (from
    ``/datalink/{obs_id}``) with the Remote Backend's URL byte-for-
    byte.
* - "open_url requires http(s) URL"
  - Routing fell back to download but the access URL is ``file://``.
    The visivo_backend_url on the Node isn't matching, or no Remote
    Backend is configured at all.
* - Backend returns 401
  - Token mismatch. The backend prints its token at startup; copy it
    into Settings → Remote Backends.
* - Backend returns "Resolved path … outside VISIVO_DATA_ROOT"
  - The file lives outside the configured jail. Adjust
    ``VISIVO_DATA_ROOT`` or move the file.
```

(5xx)=
## 5xx errors

Every 5xx response includes a ``request_id``. Grep your logs:

```bash
docker compose logs api | grep <request_id>
```

You'll find the exception traceback. Common roots:

* DB connection lost → restart DB; check pool config.
* OOM in a worker → bump container memory; check the request that
  killed it.
* Bad input not caught by validators → file an issue with the
  request body.

(slow-discovery)=
## Slow discovery

```{list-table}
:header-rows: 1
:widths: 35 65

* - Symptom
  - Fix
* - p95 ``/discovery/search`` > 1 s
  - Check ``skava_db_pool_connections`` — pool exhausted? Bump
    ``SKAVA_DB_POOL_SIZE``.
* - p95 ``/datalink/{obs_id}`` > 500 ms
  - Probably the replica ranking joining ``nodes`` on every call.
    Cache hits help; if you see this consistently file an issue.
* - One specific query is slow
  - Run ``EXPLAIN ANALYZE`` in psql against the underlying
    SQL (visible in the structured log at DEBUG).
* - All queries equally slow
  - PostgreSQL itself overloaded. Check vacuum / autovacuum;
    consider read replicas.
```

(ingestion-errors)=
## Ingestion errors

```{list-table}
:header-rows: 1
:widths: 35 65

* - Error in ``summary.validation_errors[]``
  - Fix
* - ``Missing required field: <X>``
  - Add it to the manifest. CSV header missing? Re-export.
* - ``unknown node POWER9``
  - Create the Node in ``/admin/nodes/`` first.
* - ``s_ra must be in [0, 360]``
  - Source file has wrong RA; fix the extractor or the manifest.
* - ``access_url must include a scheme``
  - The URL is bare. Add ``http://`` / ``file://`` / etc.
* - ``t_min must be <= t_max``
  - Range inverted; check the time extraction.
```

For a bulk failure of all records:

```bash
docker compose logs api | grep skava.ingestion
```

You'll see the per-record errors in the structured log. If the
publisher's state.db marked them as ``failed``, ``--force`` re-runs
them after the fix.

## Asking for help

When opening an issue:

* SKAVA version (`/system/health` → `version`)
* publisher CLI version (`skava-publisher --version`)
* desktop client version (Help → About)
* curl reproducer (anonymise tokens)
* relevant structured log lines with `request_id`

The triage time goes from "back and forth for days" to "fix
immediately" with this info attached.
