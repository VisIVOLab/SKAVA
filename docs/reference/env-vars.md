# Environment variables

Single-page index of every env var read by SKAVA, the publisher, and
the VisIVO backend (the latter only insofar as it touches SKAVA
routing). Sorted alphabetically within each table.

## SKAVA core (`SKAVA_*`)

Read by `app/config.py` (pydantic settings, prefix `SKAVA_`, also from a
`.env` file).

```{list-table}
:header-rows: 1
:widths: 32 14 14 40

* - Name
  - Type
  - Default
  - Notes
* - ``SKAVA_ACCESS_TOKENS``
  - comma list
  - unset
  - Static bearer tokens. When set (or OIDC is configured), the public catalogue endpoints require a valid token.
* - ``SKAVA_APP_NAME``
  - str
  - ``SKAVA Data Discovery Service``
  - OpenAPI title.
* - ``SKAVA_DATABASE_URL``
  - SQLAlchemy URL
  - dev: ``postgresql+psycopg://skava:skava@localhost:5432/skava``
  - Required in ``staging``/``production`` (startup fails without it).
* - ``SKAVA_DB_CONNECT_RETRIES``
  - int (≥ 1)
  - 10
  - Boot-time DB connect retries.
* - ``SKAVA_DB_CONNECT_RETRY_DELAY``
  - float (s)
  - 1.5
  - Wait between retries.
* - ``SKAVA_DB_MAX_OVERFLOW``
  - int
  - 20
  - Pool overflow beyond ``pool_size``.
* - ``SKAVA_DB_POOL_RECYCLE``
  - int (s, ≥ 30)
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
  - ``dev`` \| ``staging`` \| ``production``. Outside ``dev`` the database and public base URLs are required; ``production`` requires ``https://``.
* - ``SKAVA_FEDERATED_SRC_URLS``
  - comma list
  - unset
  - Sibling SKAVA base URLs asked by ``/federation/search``.
* - ``SKAVA_FEDERATION_TIMEOUT_SECONDS``
  - float (≥ 0.1)
  - 2.0
  - HTTP timeout per sibling.
* - ``SKAVA_LOG_LEVEL``
  - enum
  - ``INFO``
  - ``DEBUG`` \| ``INFO`` \| ``WARNING`` \| ``ERROR``.
* - ``SKAVA_OIDC_AUDIENCE``
  - str
  - unset
  - Audience an OIDC token must carry; unset = not checked.
* - ``SKAVA_OIDC_ISSUER``
  - str
  - unset
  - Issuer the tokens carry, when it differs from the one the discovery document reports (IAM reached on a private name).
* - ``SKAVA_OIDC_JWKS_URI``
  - URL
  - unset
  - Override the key-set location. Setting it alone also enables OIDC validation.
* - ``SKAVA_OIDC_PUBLIC_WELLKNOWN``
  - URL
  - ``IAM_WELLKNOWN_ENDPOINT``
  - Discovery URL given to clients in the ``ivoa_bearer`` 401 challenge.
* - ``SKAVA_PUBLIC_BASE_URL``
  - URL
  - dev: ``http://localhost:8000``
  - Used to mint absolute URLs (DataLink, access, TAP capabilities). Required outside ``dev``; ``https://`` in production.
* - ``SKAVA_RANKING_MEMORY_FACTOR``
  - float
  - 1.0
  - Memory a dataset needs on a node, as a multiple of its ``access_estsize``.
* - ``SKAVA_REPLICA_IDENTITY``
  - enum
  - ``checksum``
  - How a new node proves it holds a copy: ``checksum`` (equal checksums
    required, fail-closed) \| ``metadata`` (accepted unless checksum, size or
    type contradict). Applies to ingestion and to the federated merge.
* - ``SKAVA_RANKING_POLICY``
  - enum
  - ``resource_aware``
  - ``resource_aware`` (node telemetry; nodes without fresh telemetry keep the declared order) \| ``static`` (declared node scores only).
* - ``SKAVA_RANKING_WEIGHT_CPU``
  - float
  - 1.0
  - ``resource_aware`` cost per % of CPU pressure.
* - ``SKAVA_RANKING_WEIGHT_MEMORY``
  - float
  - 50.0
  - Cost per unit of needed / free memory.
* - ``SKAVA_RANKING_WEIGHT_QUEUE``
  - float
  - 20.0
  - Cost per queued + running task per worker.
* - ``SKAVA_RANKING_WEIGHT_RTT``
  - float
  - 1.0
  - Cost per ms of probe round trip.
* - ``SKAVA_RUN_SEED``
  - bool
  - ``true``
  - Read by ``docker/entrypoint.sh``. Set ``false`` to skip demo seeding on container start (recommended in production — load real metadata via the ingestion API / publisher instead).
* - ``SKAVA_SEED_RESET``
  - bool
  - ``false``
  - When seeding runs, force the destructive seed (wipes user data). Orthogonal to ``SKAVA_RUN_SEED`` (which gates whether seeding runs).
* - ``SKAVA_SODA_BACKEND_TIMEOUT_SECONDS``
  - float (≥ 1)
  - ``120``
  - Synchronous timeout when ``/soda/execute`` delegates a cutout to a node's co-located VisIVO backend.
* - ``SKAVA_TELEMETRY_INTERVAL_SECONDS``
  - float
  - 10
  - Node prober period. ``0`` = no background prober; telemetry is then refreshed only by ``POST /internal/telemetry/probe`` and by the nodes' own reports.
* - ``SKAVA_TELEMETRY_PING_SAMPLES``
  - int (1-20)
  - 3
  - Round-trip samples per probe.
* - ``SKAVA_TELEMETRY_TIMEOUT_SECONDS``
  - float
  - 3.0
  - Timeout of one probe request.
* - ``SKAVA_TELEMETRY_TTL_SECONDS``
  - float
  - 60.0
  - Telemetry older than this is not trusted by ``resource_aware`` (the node is ranked as unmeasured).
* - ``SKAVA_VISIVO_BACKEND_TOKEN``
  - str
  - unset
  - Token sent as ``X-Visivo-Token`` to nodes whose backend requires auth (``/soda/execute`` delegation and the telemetry prober).
```

## Unprefixed names

Some settings are read under the name the SRCNet services use, with a
`SKAVA_` alias:

* `INTERNAL_API_KEY` or `SKAVA_INTERNAL_API_KEY` — either is
  accepted. Required for `/internal/*` endpoints (unset = every
  internal call answers 401). No minimum length is enforced.
* `IAM_WELLKNOWN_ENDPOINT` or `SKAVA_OIDC_WELLKNOWN` — the IAM's OIDC
  discovery document. When set, JWT access tokens issued by that IAM are
  accepted on the public endpoints alongside `SKAVA_ACCESS_TOKENS`
  (see [Authentication](../api/auth.md)).

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
* - ``ADMIN_CSRF_TOKEN_NAME``
  - str
  - ``csrf_token``
  - Form field name of the CSRF token.
* - ``ADMIN_LOGIN_RATE_LIMIT_PER_MINUTE``
  - int
  - 6
  - Failed admin sign-ins per client address per minute before `/admin/login` answers 429 (0 disables).
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
  - str
  - random per process
  - **Set in production** (e.g. ``openssl rand -hex 32``). When unset a
    transient value is generated with a warning, in any environment;
    sessions then do not survive a restart.
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

Read by the VisIVO backend running on a node, where they matter to SKAVA
(`/v1/datasets/open_skava`, the node SODA service, the `/v1/node/status`
document the prober reads):

```{list-table}
:header-rows: 1
:widths: 32 14 54

* - Name
  - Default
  - Notes
* - ``VISIVO_DATA_ROOT`` / ``VISIVO_DATA_ROOTS``
  - —
  - **Strongly recommended in production.** Path jail for the
    ``file://`` replicas the node opens (``open_skava``, SODA ``ID``).
    ``VISIVO_DATA_ROOTS`` takes several directories (``os.pathsep``
    separated); either is honoured.
* - ``VISIVO_TOKEN``
  - random
  - Token clients (and SKAVA, via ``SKAVA_VISIVO_BACKEND_TOKEN``) must
    present as ``X-Visivo-Token``.
* - ``VISIVO_TOKENS``
  - —
  - Additional accepted tokens (comma/whitespace separated). A backend
    with ``VISIVO_TOKENS`` set serves no filesystem path until
    ``VISIVO_DATA_ROOTS`` is declared.
* - ``VISIVO_WORKERS``
  - 4
  - ``ProcessPoolExecutor`` size (reported as ``workers.total``).
* - ``VISIVO_SESSION_TTL``
  - 1800 s
  - Idle session expiry.
* - ``VISIVO_NODE_STATUS_PUBLIC``
  - 1
  - ``0`` makes ``/v1/node/status`` require the token.
* - ``VISIVO_NODE_CODE``
  - —
  - Node code reported in ``/v1/node/status``.
* - ``VISIVO_NODE_GPU``
  - —
  - Declares whether the node has a GPU (``1``/``0``), reported in the
    status document.
* - ``VISIVO_SOFIA_BIN``
  - ``sofia2`` / ``sofia`` on PATH
  - SoFiA-2 executable for node-side source finding.
* - ``VISIVO_FINDER_TIMEOUT_S``
  - 3600
  - Maximum run time of a source finder.
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
* `tests/conftest.py` sets `SKAVA_DATABASE_URL` (in-memory SQLite),
  `SKAVA_PUBLIC_BASE_URL`, `SKAVA_ENV=dev` and `INTERNAL_API_KEY`
  itself; no env to set
