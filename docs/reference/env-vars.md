# Environment variables

Single-page index of every env var read by SKAVA, the publisher, and
the VisIVO backend (the latter only insofar as it touches SKAVA
routing). Sorted alphabetically.

## SKAVA core (`SKAVA_*`)

```{list-table}
:header-rows: 1
:widths: 32 14 14 40

* - Name
  - Type
  - Default
  - Notes
* - ``SKAVA_ACCESS_TOKENS``
  - comma list
  - ``""``
  - Bearer tokens that gate public endpoints when set.
* - ``SKAVA_DATABASE_URL``
  - SQLAlchemy URL
  - —
  - Required. ``postgresql+psycopg://user:pwd@host:port/db``.
* - ``SKAVA_DB_CONNECT_RETRIES``
  - int
  - 30
  - Boot-time DB connect retries.
* - ``SKAVA_DB_CONNECT_RETRY_DELAY``
  - int (s)
  - 2
  - Wait between retries.
* - ``SKAVA_DB_MAX_OVERFLOW``
  - int
  - 5
  - Pool overflow beyond ``pool_size``.
* - ``SKAVA_DB_POOL_RECYCLE``
  - int (s)
  - 1800
  - Recycle stale connections.
* - ``SKAVA_DB_POOL_SIZE``
  - int
  - 10
  - SQLAlchemy pool size.
* - ``SKAVA_DB_POOL_TIMEOUT``
  - int (s)
  - 30
  - Wait for a free connection.
* - ``SKAVA_ENV``
  - enum
  - ``dev``
  - ``dev`` \| ``staging`` \| ``production``. Strict-mode toggle.
* - ``SKAVA_FEDERATED_SRC_URLS``
  - comma list
  - ``""``
  - Sibling SKAVA URLs for federation fan-out (roadmap).
* - ``SKAVA_FEDERATION_TIMEOUT_SECONDS``
  - float
  - 2.0
  - Per-sibling timeout.
* - ``SKAVA_LOG_LEVEL``
  - enum
  - ``INFO``
  - ``DEBUG`` \| ``INFO`` \| ``WARNING`` \| ``ERROR``.
* - ``SKAVA_PUBLIC_BASE_URL``
  - URL
  - —
  - Used in DataLink envelope to mint absolute URLs.
* - ``SKAVA_RUN_SEED``
  - bool
  - ``true``
  - Read by ``docker/entrypoint.sh``. Set ``false`` to skip demo seeding
    entirely on container start (recommended in production — load real
    metadata via the ingestion API / publisher instead).
* - ``SKAVA_SEED_RESET``
  - bool
  - ``false``
  - When seeding runs, force the destructive seed (wipes user data).
    Orthogonal to ``SKAVA_RUN_SEED`` (which gates whether seeding runs).
* - ``SKAVA_SODA_BACKEND_TIMEOUT_SECONDS``
  - float
  - ``120``
  - Synchronous timeout when ``/soda/execute`` delegates a cutout to a
    node's co-located VisIVO backend (compute-next-to-data).
* - ``SKAVA_VISIVO_BACKEND_TOKEN``
  - str
  - ``""``
  - Bearer token forwarded (as ``X-Visivo-Token``) to a node's VisIVO
    backend on ``/soda/execute`` when that backend requires auth.
```

## Internal API key

* `INTERNAL_API_KEY` or `SKAVA_INTERNAL_API_KEY` — either is
  accepted. Required for `/internal/*` endpoints. ≥ 8 chars.

## Admin UI (`ADMIN_*`)

```{list-table}
:header-rows: 1
:widths: 36 14 12 38

* - Name
  - Type
  - Default
  - Notes
* - ``ADMIN_BCRYPT_ROUNDS``
  - int (10-14)
  - 12
  - bcrypt cost factor.
* - ``ADMIN_BRAND_COLOR``
  - hex
  - ``#70b5e3``
  - Primary brand colour.
* - ``ADMIN_BRAND_COLOR_DARK``
  - hex
  - ``#3a6e8c``
  - Hover / dark accent.
* - ``ADMIN_BRAND_NAME``
  - str
  - ``SKAVA Admin``
  - Header brand text.
* - ``ADMIN_LOGIN_RATE_LIMIT_PER_MINUTE``
  - int
  - 6
  - Reserved for Phase 4 rate limiter.
* - ``ADMIN_PASSWORD_MIN_LENGTH``
  - int
  - 12
  - Minimum chars.
* - ``ADMIN_PASSWORD_REQUIRE_DIGIT``
  - bool
  - true
  - —
* - ``ADMIN_PASSWORD_REQUIRE_MIXED_CASE``
  - bool
  - true
  - —
* - ``ADMIN_PASSWORD_REQUIRE_SYMBOL``
  - bool
  - false
  - —
* - ``ADMIN_SESSION_COOKIE_NAME``
  - str
  - ``skava_admin_session``
  - —
* - ``ADMIN_SESSION_COOKIE_SECURE``
  - bool
  - false
  - **Set true in production.** Default false so local HTTP dev works.
* - ``ADMIN_SESSION_MAX_AGE_SECONDS``
  - int
  - 28800
  - 8 h.
* - ``ADMIN_SESSION_SECRET``
  - str (≥ 32 chars)
  - random (dev only)
  - **Required in production.**
```

## Postgres container

Standard postgres image env:

* `POSTGRES_DB=skava`
* `POSTGRES_USER=skava`
* `POSTGRES_PASSWORD=...`

## Publisher CLI

Read by the publisher itself:

```{list-table}
:header-rows: 1
:widths: 32 14 54

* - Name
  - Default
  - Notes
* - ``SKAVA_PUBLISHER_CONFIG``
  - —
  - Path to the YAML config (alternative to ``--config``).
* - ``SKAVA_INTERNAL_API_KEY``
  - —
  - Substituted into ``${SKAVA_INTERNAL_API_KEY}`` in the YAML.
```

## VisIVO backend (compute next to data)

Read by the VisIVO backend when serving `/v1/datasets/open_skava`:

```{list-table}
:header-rows: 1
:widths: 32 14 54

* - Name
  - Default
  - Notes
* - ``VISIVO_DATA_ROOT``
  - —
  - **Strongly recommended in production.** Path jail for
    ``open_skava``.
* - ``VISIVO_TOKEN``
  - random
  - Bearer token the desktop client must present.
* - ``VISIVO_WORKERS``
  - 4
  - ``ProcessPoolExecutor`` size.
* - ``VISIVO_SESSION_TTL``
  - 1800 s
  - Idle session expiry.
```

## Apptainer-specific

When running through Apptainer, container env vars must be prefixed
``APPTAINERENV_`` to propagate from the host:

```bash
APPTAINERENV_VISIVO_DATA_ROOT=/data \
APPTAINERENV_CONDA_INSTALLER=mamba \
    apptainer run --bind /data:/data backend.sif
```

The recipe documents this in its `%help` block.

## CI

If you run the test suite directly:

* ``PYTHONDONTWRITEBYTECODE=1``
* ``PYTHONUNBUFFERED=1``
* tests use a hard-coded ephemeral postgres URL; no env to set
