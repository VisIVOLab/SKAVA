# Security

SKAVA's threat model and the controls that mitigate each class of
attack. Pair this page with the
[Configuration reference](configuration) for the env-vars you'll be
setting.

## Threat model

SKAVA sits in front of a database of metadata and federates access
URLs to scientific files. The defenders' goals, in priority order:

1. Catalogue integrity — wrong rows would mislead downstream science.
2. Authentication of mutating actions — only authorised operators
   should change Nodes / Datasets / Replicas.
3. Confidentiality of credentials — internal API keys, session
   secrets, OIDC client secrets (future).
4. Availability — public discovery should keep responding under
   normal SRC load.
5. Audit — every mutation must be attributable.

Out of scope at this layer (delegated to other components):

* Confidentiality of the **data files themselves**. SKAVA only knows
  URLs; if a file has restricted visibility, that is enforced by the
  storage layer or the consumer (e.g. VisIVO backend's
  `VISIVO_DATA_ROOT` jail).
* DDoS at the network edge. Use a reverse proxy (nginx, Envoy,
  Cloudflare) for that.

## Authentication surfaces

```{list-table}
:header-rows: 1
:widths: 22 30 48

* - Surface
  - Mechanism
  - Notes
* - Public discovery (``/discovery``, ``/datalink``, ``/tap``, ``/soda``)
  - none by default; optional bearer-token whitelist via
    ``SKAVA_ACCESS_TOKENS``
  - For SKA-Pre proof-of-concept sites we recommend leaving discovery
    open. Production SRCs may turn it on per IVOA / SKAO policy.
* - Internal ingestion (``/internal/*``)
  - ``X-Internal-Api-Key`` shared secret
  - Rotate yearly. Treat as a service-to-service credential, not a
    user credential.
* - Admin UI (``/admin/*``)
  - signed session cookie + bcrypt password
  - Phase 1 only — local users. Phase 5 plans OIDC (Garr AAI /
    eduGAIN) without removing the local backend.
* - Federation (``/federation/*``, roadmap)
  - sibling-to-sibling allowlist + signed envelopes
  - Not yet enforced; design captured in
    [Architecture / overview](../architecture/overview).
```

## Transport security

* In production the api container **must** sit behind an HTTPS
  reverse proxy. The container itself speaks plain HTTP — TLS
  termination is the proxy's job.
* When TLS is on, set ``ADMIN_SESSION_COOKIE_SECURE=true`` so the
  session cookie is never sent over a downgraded HTTP request.
* Set ``SKAVA_PUBLIC_BASE_URL=https://...`` so the URLs SKAVA mints
  in DataLink responses are HTTPS, matching the proxy's certificate.

## Secrets

```{list-table}
:header-rows: 1
:widths: 32 18 50

* - Secret
  - Generated with
  - Storage recommendation
* - ``ADMIN_SESSION_SECRET``
  - ``openssl rand -hex 32``
  - Pass as env var via Kubernetes Secret / docker-compose ``.env``.
    Never commit. Rotate on suspected compromise — all sessions
    invalidate at once.
* - ``INTERNAL_API_KEY``
  - ``openssl rand -hex 32``
  - Same as above. Distribute to the publisher CLI via
    ``${SKAVA_INTERNAL_API_KEY}`` env substitution in its YAML
    config; the secret never lives on disk in plaintext.
* - DB password
  - ``openssl rand -hex 24``
  - Pass via ``POSTGRES_PASSWORD`` env var. In Kubernetes mount it
    from a Secret; do NOT inline in a ConfigMap.
* - Bearer tokens for ``SKAVA_ACCESS_TOKENS``
  - ``openssl rand -hex 32``
  - Distribute to each VO client OOB; rotate when an operator leaves.
```

## Path safety on the VisIVO backend

The ``open_skava`` endpoint accepts an ``access_url`` from the client.
A hostile client could try to read ``/etc/passwd``. Mitigations
(all enabled by default when env vars are set):

* **Bearer auth** on the endpoint. No anonymous calls.
* **Scheme jail**: only ``file://`` is honoured by ``open_skava``;
  the ``open_url`` endpoint serves the download path and accepts only
  ``http(s)://``.
* **Path jail**: ``VISIVO_DATA_ROOT`` makes the backend refuse paths
  outside the configured directory tree.
* **Symlink-aware** ``Path.resolve()`` before the jail check: a
  symlink to ``/etc/passwd`` resolves to ``/etc/passwd`` and fails
  ``relative_to(root)``.
* **Extension whitelist**: only ``.fits``, ``.fit``, ``.h5``,
  ``.hdf5`` etc. are accepted by ``_is_supported_dataset``.

Production deployments **must** set ``VISIVO_DATA_ROOT``.

## Audit

Every mutating action in the admin UI (and every CLI call) writes a
row to ``audit_log`` with:

* who performed the action (user id + display label snapshot)
* what was changed (``action`` verb path, ``target_type`` / id)
* when (UTC, indexed)
* from where (IP, user agent, request id)
* optional structured diff (``before`` / ``after``)

The table is append-only at the application layer — nothing in
SKAVA's code ever ``UPDATE``s or ``DELETE``s rows. Retention is left
to the operator (a cron ``pg_dump`` to cold storage + a periodic
``DELETE WHERE occurred_at < NOW() - INTERVAL '365 days'``).

## What SKAVA does not (yet) do

```{list-table}
:header-rows: 1
:widths: 35 65

* - Concern
  - Status / roadmap
* - Rate limit on login
  - Designed (``ADMIN_LOGIN_RATE_LIMIT_PER_MINUTE`` already in
    config), enforcement in Phase 4.
* - Rate limit on public endpoints
  - Out of scope — use the reverse proxy.
* - Refresh-token revocation
  - N/A (sessions only).
* - CSP / Permissions-Policy headers
  - Not set by SKAVA. Add at the reverse proxy.
* - SSO (OIDC)
  - Scaffolded module path (``app/admin/auth/oidc.py``) exists; not
    yet implemented.
* - 2FA
  - Roadmap; will plug into the local-password backend without
    disturbing OIDC.
* - Encrypted columns in PostgreSQL
  - Not used. PostgreSQL TDE / column-level encryption are the
    operator's responsibility.
```

## Disclosure

To report a security issue privately, email **security@skava.inaf.it**
(monitored). Please do not file public GitHub issues for
vulnerabilities.
