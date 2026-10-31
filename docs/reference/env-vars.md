# Environment variables

Every environment variable read by SKAVA and by its publisher, with type,
default and meaning. This page is the reference;
[Configuration](../deployment/configuration.md) explains how the settings
work together. The VisIVO Visual Analytics backend on a node has its own
variables, documented by VisIVO
([Configuration](https://visivo.readthedocs.io/en/latest/configuration.html));
the few that must agree with the catalogue are listed
[below](#visivo-backend-what-must-agree).

## SKAVA (`SKAVA_*`)

Read by `app/config.py` (pydantic settings, prefix `SKAVA_`, also from a
`.env` file in the working directory). Two settings also accept an
unprefixed name, the one the SRCNet services use. Invalid values stop the
service at startup.

### Service

```{list-table}
:header-rows: 1
:widths: 32 14 14 40

* - Name
  - Type
  - Default
  - Notes
* - ``SKAVA_ENV``
  - enum
  - ``dev``
  - ``dev`` \| ``staging`` \| ``production``. Outside ``dev``,
    ``SKAVA_DATABASE_URL`` and ``SKAVA_PUBLIC_BASE_URL`` are required;
    ``production`` requires ``SKAVA_PUBLIC_BASE_URL`` to start with
    ``https://``.
* - ``SKAVA_APP_NAME``
  - str
  - ``SKAVA Data Discovery Service``
  - Title of the application (OpenAPI docs).
* - ``SKAVA_DATABASE_URL``
  - SQLAlchemy URL
  - dev: ``postgresql+psycopg://skava:skava@localhost:5432/skava``
  - Required outside ``dev``, e.g.
    ``postgresql+psycopg://user:pass@host:5432/db``.
* - ``SKAVA_PUBLIC_BASE_URL``
  - URL
  - dev: ``http://localhost:8000``
  - The base of the absolute URLs SKAVA mints (DataLink, access, TAP
    capabilities), e.g. ``https://skava.inaf.it``. Required outside
    ``dev``; ``https://`` in production.
* - ``SKAVA_LOG_LEVEL``
  - enum
  - ``INFO``
  - ``DEBUG`` \| ``INFO`` \| ``WARNING`` \| ``ERROR``. Root logger level;
    logs are structured JSON.
* - ``SKAVA_RUN_SEED``
  - bool
  - ``true``
  - Read by ``docker/entrypoint.sh``. Seeds the demo fixtures at
    container start, only when the ``nodes`` table is empty. Set
    ``false`` in production and load real metadata through the
    publisher or the ingestion API.
* - ``SKAVA_SEED_RESET``
  - bool
  - ``false``
  - When seeding runs, wipe the catalogue and re-insert the demo
    fixtures even if nodes exist. Development only. Orthogonal to
    ``SKAVA_RUN_SEED``, which decides whether seeding runs.
```

### Access and authentication

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
  - Static bearer tokens. When set (or OIDC is configured), the public
    catalogue endpoints require a valid token.
* - ``INTERNAL_API_KEY`` (or ``SKAVA_INTERNAL_API_KEY``)
  - str
  - unset
  - Shared secret for the ``/internal/*`` endpoints
    (``X-Internal-Api-Key``); unset means every internal call answers 401.
    Also the key the per-node telemetry tokens are derived from. No
    minimum length is enforced: use ``openssl rand -hex 32``.
* - ``IAM_WELLKNOWN_ENDPOINT`` (or ``SKAVA_OIDC_WELLKNOWN``)
  - URL
  - unset
  - The IAM's OIDC discovery document. Setting it turns OIDC on: JWT
    access tokens issued by that IAM are accepted on the public
    endpoints next to ``SKAVA_ACCESS_TOKENS``, and a token is required.
* - ``SKAVA_OIDC_AUDIENCE``
  - str
  - unset
  - Audience an OIDC token must carry (e.g. ``skava``); unset means not
    checked.
* - ``SKAVA_OIDC_ISSUER``
  - str
  - from discovery
  - Issuer the tokens carry, when it differs from the one the discovery
    document reports (IAM reached on a private name).
* - ``SKAVA_OIDC_JWKS_URI``
  - URL
  - from discovery
  - Override of the key-set location (air-gapped setups, tests). Setting
    it alone also enables OIDC validation, without issuer check.
* - ``SKAVA_OIDC_PUBLIC_WELLKNOWN``
  - URL
  - ``IAM_WELLKNOWN_ENDPOINT``
  - Discovery URL given to clients in the ``ivoa_bearer`` challenge of a
    401.
```

### Federation

```{list-table}
:header-rows: 1
:widths: 32 14 14 40

* - Name
  - Type
  - Default
  - Notes
* - ``SKAVA_FEDERATED_SRC_URLS``
  - comma list
  - unset
  - Base URLs of sibling SKAVA catalogues, asked by
    ``/federation/search`` and listed by ``/federation/sources``.
* - ``SKAVA_FEDERATION_TIMEOUT_SECONDS``
  - float (≥ 0.1)
  - 2.0
  - HTTP timeout per sibling; a sibling that does not answer in time is
    reported as ``timeout``.
```

### Routing and node telemetry

```{list-table}
:header-rows: 1
:widths: 32 14 14 40

* - Name
  - Type
  - Default
  - Notes
* - ``SKAVA_RANKING_POLICY``
  - enum
  - ``resource_aware``
  - ``resource_aware`` (ranks by node telemetry; nodes without fresh
    telemetry keep the declared order) \| ``static`` (declared node
    scores only).
* - ``SKAVA_RANKING_WEIGHT_RTT``
  - float (≥ 0)
  - 1.0
  - ``resource_aware`` cost per ms of probe round trip.
* - ``SKAVA_RANKING_WEIGHT_CPU``
  - float (≥ 0)
  - 1.0
  - Cost per % of CPU pressure.
* - ``SKAVA_RANKING_WEIGHT_QUEUE``
  - float (≥ 0)
  - 20.0
  - Cost per queued + running task per worker.
* - ``SKAVA_RANKING_WEIGHT_MEMORY``
  - float (≥ 0)
  - 50.0
  - Cost of the share of the node's free memory the dataset would take.
* - ``SKAVA_RANKING_MEMORY_FACTOR``
  - float (≥ 0)
  - 1.0
  - Memory a dataset needs on a node, as a multiple of its
    ``access_estsize``.
* - ``SKAVA_REPLICA_IDENTITY``
  - enum
  - ``checksum``
  - How a new node proves it holds a copy: ``checksum`` (equal checksums
    required, fail-closed) \| ``metadata`` (accepted unless checksum,
    size or type contradict). Applies to ingestion and to the federated
    merge.
* - ``SKAVA_TELEMETRY_INTERVAL_SECONDS``
  - float (≥ 0)
  - 10
  - Prober period. ``0`` = no background prober; telemetry is then
    refreshed only by ``POST /internal/telemetry/probe`` and by the
    nodes' own reports.
* - ``SKAVA_TELEMETRY_TTL_SECONDS``
  - float (> 0)
  - 60.0
  - Telemetry older than this is not trusted by ``resource_aware`` (the
    node is ranked as unmeasured), and a node's report keeps the prober
    away for this long.
* - ``SKAVA_TELEMETRY_TIMEOUT_SECONDS``
  - float (> 0)
  - 3.0
  - Timeout of one probe request.
* - ``SKAVA_TELEMETRY_PING_SAMPLES``
  - int (1-20)
  - 3
  - ``/v1/ping`` samples per probe; the median is kept.
```

### Node backends

```{list-table}
:header-rows: 1
:widths: 32 14 14 40

* - Name
  - Type
  - Default
  - Notes
* - ``SKAVA_VISIVO_BACKEND_TOKEN``
  - str
  - unset
  - Token sent as ``X-Visivo-Token`` to nodes whose backend requires
    auth, by ``/soda/execute`` and by the telemetry prober.
* - ``SKAVA_SODA_BACKEND_TIMEOUT_SECONDS``
  - float (≥ 1)
  - 120
  - Timeout of the cutout ``/soda/execute`` delegates to a node's
    backend.
```

### Database pool

```{list-table}
:header-rows: 1
:widths: 32 14 14 40

* - Name
  - Type
  - Default
  - Notes
* - ``SKAVA_DB_POOL_SIZE``
  - int (≥ 1)
  - 10
  - SQLAlchemy pool size.
* - ``SKAVA_DB_MAX_OVERFLOW``
  - int (≥ 0)
  - 20
  - Connections beyond the pool size.
* - ``SKAVA_DB_POOL_TIMEOUT``
  - int (s, ≥ 1)
  - 30
  - Wait for a free connection.
* - ``SKAVA_DB_POOL_RECYCLE``
  - int (s, ≥ 30)
  - 1800
  - Recycle connections older than this (avoids stale connections
    through firewalls).
* - ``SKAVA_DB_CONNECT_RETRIES``
  - int (≥ 1)
  - 10
  - Database connection attempts at startup.
* - ``SKAVA_DB_CONNECT_RETRY_DELAY``
  - float (s, ≥ 0.1)
  - 1.5
  - Wait between attempts.
```

## Admin UI

Read by `app/admin/config.py` (prefix `ADMIN_`).

```{list-table}
:header-rows: 1
:widths: 36 14 12 38

* - Name
  - Type
  - Default
  - Notes
* - ``ADMIN_SESSION_SECRET``
  - str
  - random per process
  - **Set in production** (e.g. ``openssl rand -hex 32``). Signs the
    session cookies. When unset a transient value is generated with a
    warning, in any environment; sessions then do not survive a restart
    and do not work across several workers.
* - ``ADMIN_SESSION_COOKIE_NAME``
  - str
  - ``skava_admin_session``
  - Cookie name.
* - ``ADMIN_SESSION_MAX_AGE_SECONDS``
  - int
  - 28800
  - Cookie lifetime (8 h).
* - ``ADMIN_SESSION_COOKIE_SECURE``
  - bool
  - false
  - Adds the ``Secure`` attribute. **Set true in production** (HTTPS).
    Default false so local HTTP development works.
* - ``ADMIN_BCRYPT_ROUNDS``
  - int (10-14)
  - 12
  - bcrypt cost factor.
* - ``ADMIN_PASSWORD_MIN_LENGTH``
  - int
  - 12
  - Minimum password length.
* - ``ADMIN_PASSWORD_REQUIRE_MIXED_CASE``
  - bool
  - true
  - Require upper and lower case.
* - ``ADMIN_PASSWORD_REQUIRE_DIGIT``
  - bool
  - true
  - Require a digit.
* - ``ADMIN_PASSWORD_REQUIRE_SYMBOL``
  - bool
  - false
  - Require a punctuation character.
* - ``ADMIN_CSRF_TOKEN_NAME``
  - str
  - ``csrf_token``
  - Form field name of the CSRF token.
* - ``ADMIN_LOGIN_RATE_LIMIT_PER_MINUTE``
  - int
  - 6
  - Failed sign-ins allowed per client address per minute; beyond it
    ``/admin/login`` answers 429 until the oldest failure is a minute
    old. 0 disables it. Per process; the shipped nginx configurations
    also rate-limit ``/admin``.
* - ``ADMIN_BRAND_NAME``
  - str
  - ``SKAVA Admin``
  - Header brand text.
* - ``ADMIN_BRAND_COLOR``
  - hex
  - ``#70b5e3``
  - Primary brand colour (INAF blue).
* - ``ADMIN_BRAND_COLOR_DARK``
  - hex
  - ``#3a6e8c``
  - Hover / dark accent.
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
  - unset
  - Path to the YAML config (alternative to ``--config``).
* - ``SKAVA_INTERNAL_API_KEY``
  - unset
  - Substituted into ``${SKAVA_INTERNAL_API_KEY}`` in the YAML.
```

## VisIVO backend: what must agree

The VisIVO Visual Analytics backend on a node is configured by VisIVO's own
variables
([Configuration](https://visivo.readthedocs.io/en/latest/configuration.html),
[Running the backend as an SRC node](https://visivo.readthedocs.io/en/latest/deployment/src-node.html)).
SKAVA reads none of them; four values must agree with the catalogue:

* the backend's token is what ``SKAVA_VISIVO_BACKEND_TOKEN`` holds, when the
  node is registered as requiring one;
* its data roots contain the ``file://`` locations the node publishes;
* its node code is the node's ``code`` here;
* for a node that reports its own telemetry, its node token is the one
  ``python -m app.security.node_token <code>`` prints (see
  [Telemetry API](../api/telemetry.md#the-node-token)).

## CI

If you run the test suite directly:

* ``PYTHONDONTWRITEBYTECODE=1``
* ``PYTHONUNBUFFERED=1``
* `tests/conftest.py` sets `SKAVA_DATABASE_URL` (in-memory SQLite),
  `SKAVA_PUBLIC_BASE_URL`, `SKAVA_ENV=dev` and `INTERNAL_API_KEY`
  itself; no env to set
