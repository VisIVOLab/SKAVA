# Security

SKAVA's threat model and the controls that mitigate each class of
attack. Pair this page with the
[Configuration reference](configuration.md) for the env-vars you'll be
setting.

## Threat model

SKAVA sits in front of a database of metadata and federates access
URLs to scientific files. The defenders' goals, in priority order:

1. Catalogue integrity — wrong rows would mislead downstream science.
2. Authentication of mutating actions — only authorised operators
   should change Nodes / Datasets / Replicas.
3. Confidentiality of credentials — internal API keys, session
   secrets, the users' bearer tokens.
4. Availability — public discovery should keep responding under
   normal SRC load.
5. Audit — every mutation must be attributable.

Out of scope at this layer (delegated to other components):

* Confidentiality of the **data files themselves**. SKAVA only knows
  URLs; if a file has restricted visibility, that is enforced by the
  storage layer or by the node's VisIVO backend, which opens only files
  under its data root.
* DDoS at the network edge. Use a reverse proxy (nginx, Envoy,
  Cloudflare) for that.

## Authentication surfaces

```{list-table}
:header-rows: 1
:widths: 22 30 48

* - Surface
  - Mechanism
  - Notes
* - Public endpoints (``/discovery``, ``/datalink``, ``/tap`` queries, ``/soda``,
    ``/access``, ``/provenance``, ``/staging``, ``/federation``)
  - none by default; a token is required as soon as static tokens
    (``SKAVA_ACCESS_TOKENS``) or OIDC (``IAM_WELLKNOWN_ENDPOINT``) are
    configured. Sent as ``Authorization: Bearer`` or
    ``X-SKAVA-Access-Token``.
  - For proof-of-concept sites we recommend leaving discovery open.
    Production SRCs may turn it on per IVOA / SKAO policy. A 401
    carries an ``ivoa_bearer`` challenge naming the IAM when OIDC is
    on. The system endpoints (``/availability``, ``/health/db``,
    ``/capabilities``, ``/metrics``) stay open.
* - Internal ingestion (``/internal/*``)
  - ``X-Internal-Api-Key`` shared secret
  - Rotate yearly. Treat as a service-to-service credential, not a
    user credential.
* - Admin UI (``/admin/*``)
  - signed session cookie + bcrypt password + CSRF token
  - Local users only (roles ``admin``, ``ingester``, ``viewer``),
    separate from the IAM.
* - Federation (``/federation/*``)
  - the caller's token
  - The federated search forwards the token the caller presented,
    unverified, to each sibling in ``SKAVA_FEDERATED_SRC_URLS``; each
    sibling enforces its own policy. Siblings are trusted by
    configuration only.
* - Node backends (from SKAVA)
  - ``X-Visivo-Token`` = ``SKAVA_VISIVO_BACKEND_TOKEN``
  - Sent to nodes registered with "requires auth", by
    ``/soda/execute`` and the telemetry prober.
* - Node reports (``/internal/telemetry/report``)
  - ``X-Skava-Node-Token``, one per node, derived from the internal key
  - The only ``/internal/*`` endpoint that does not take the internal
    key. A token speaks for one node; rotating the internal key revokes
    them all. See [Telemetry API](../api/telemetry.md#the-node-token).
```

## OIDC tokens

When ``IAM_WELLKNOWN_ENDPOINT`` is set, SKAVA fetches the IAM's
discovery document and key set (cached; a key rotation is picked up
on an unknown key id) and accepts a JWT that:

* is signed with an asymmetric algorithm (RS*, ES256/384, PS256 —
  never HS*) by a key in that set,
* carries ``exp`` and ``iat`` and has not expired (30 s leeway),
* was issued by the discovery document's issuer (or
  ``SKAVA_OIDC_ISSUER``),
* carries ``SKAVA_OIDC_AUDIENCE`` in ``aud`` when that is set.

Set the audience in production so a token issued for another service
is not accepted. Static ``SKAVA_ACCESS_TOKENS`` keep working alongside.
SKAVA never stores a presented token: jobs record only a short hash of
it (``token:<sha256 prefix>``). See
[configuration](configuration.md#oidc-bearer-tokens) for every setting.

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
* - ``SKAVA_VISIVO_BACKEND_TOKEN``
  - the node backend's token
  - Same handling as ``INTERNAL_API_KEY``.
```

## Path safety on the VisIVO backend

A client hands a node's backend the `file://` access URL it got from
SKAVA, so the backend must refuse paths outside the node's data. It does so
with its own token and data root, documented by VisIVO:
[Running the backend as an SRC node](https://visivo.readthedocs.io/en/latest/deployment/src-node.html).
What must agree with the catalogue: the data root must contain every
`file://` path the node publishes, and nothing else the node wants kept
private.

## Audit

Every mutating action in the admin UI, every login attempt
(``auth.login`` / ``auth.login_failed``) and every mutating admin CLI
call (``cli.<verb>``) writes a row to ``audit_log`` with:

* who performed the action (user id + display label snapshot)
* what was changed (``action`` verb path, ``target_type`` / id)
* when (UTC, indexed)
* from where (IP, user agent, request id)
* optional structured diff (``before`` / ``after``)

The table is append-only at the application layer — nothing in
SKAVA's code ever ``UPDATE``s or ``DELETE``s rows. Retention is left
to the operator (a cron ``pg_dump`` to cold storage + a periodic
``DELETE WHERE occurred_at < NOW() - INTERVAL '365 days'``).

## What SKAVA does not do

```{list-table}
:header-rows: 1
:widths: 35 65

* - Concern
  - Status
* - Rate limit on login
  - After ``ADMIN_LOGIN_RATE_LIMIT_PER_MINUTE`` failed sign-ins in a
    minute from one client address, further attempts get HTTP 429 with
    ``Retry-After`` before the password is checked (audit action
    ``auth.login_throttled``). The count is per process. The production
    nginx configs (``nginx.prod.conf``, ``nginx.tls.conf``) also limit
    ``/admin`` to 5 r/s per client (burst 10).
* - Rate limit on public endpoints
  - Done at the reverse proxy: the shipped nginx configs allow 30 r/s
    per client (burst 60).
* - Refresh-token revocation
  - N/A (sessions only).
* - CSP / Permissions-Policy headers
  - Not set by SKAVA. The production nginx configs add
    ``X-Content-Type-Options``, ``X-Frame-Options`` and
    ``Referrer-Policy``; add CSP at the reverse proxy.
* - SSO (OIDC) for the admin UI
  - Not available: OIDC covers the public API only; the admin UI uses
    local accounts.
* - 2FA
  - Not available for the admin UI.
* - Encrypted columns in PostgreSQL
  - Not used. PostgreSQL TDE / column-level encryption are the
    operator's responsibility.
```

## Disclosure

To report a security issue privately, email **security@skava.inaf.it**
(monitored). Please do not file public GitHub issues for
vulnerabilities.
