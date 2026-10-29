# Authentication

SKAVA exposes three categories of endpoint, each with its own
authentication scheme.

## Public catalogue — open unless tokens are configured

* `/discovery/*`
* `/datalink/*`
* `/access/*`
* `/soda/*`
* `/tap/sync`, `/tap/async*`
* `/staging/*`
* `/provenance/*`
* `/federation/*`

**By default**: no authentication. Anyone can query.

**Required token**: as soon as static tokens
(``SKAVA_ACCESS_TOKENS=tok1,tok2,...``) or OIDC (see below) are
configured, every request to these endpoints needs a valid token.
Clients pass it as either header:

```
Authorization: Bearer <token>
```

or:

```
X-SKAVA-Access-Token: <token>
```

(`X-SKAVA-Access-Token` wins when both are sent.) Missing or wrong →
401 `unauthorized`, with a `WWW-Authenticate` challenge.

Rotate static tokens by adding the new token, distributing it to
clients, then removing the old one. The list is a whitelist, so
multiple tokens co-exist seamlessly.

## Internal endpoints — API key

* `/internal/ingestion/dry-run`
* `/internal/ingestion/run`
* `/internal/ingestion/history`
* `/internal/ingestion/history/{job_id}`
* `/internal/telemetry` and `/internal/telemetry/probe`

Required header on every call:

```
X-Internal-Api-Key: <value of INTERNAL_API_KEY env var>
```

The key must match the server-configured `INTERNAL_API_KEY` (or
`SKAVA_INTERNAL_API_KEY`) exactly. When neither is set, every internal
call is refused with 401. No length is enforced: choose a long random
value (`openssl rand -hex 32`).

Treat it as a service-to-service shared secret. Rotate yearly.

## Admin UI — session cookie

* `/admin/*`

Session-based authentication backed by a bcrypt-hashed username +
password. Flow:

1. ``GET /admin/login`` returns the form with a CSRF token.
2. ``POST /admin/login`` validates credentials, sets a signed cookie
   `skava_admin_session`, and 303-redirects to the original URL.
3. Every subsequent request reads the cookie, looks up the user by
   id, and re-checks ``is_active`` to honour deactivations in real
   time.
4. ``POST /admin/logout`` clears the cookie.

The session secret comes from ``ADMIN_SESSION_SECRET``. In
production set it to a stable ``openssl rand -hex 32`` value. When it
is unset a per-process random value is generated with a loud warning
(in any ``SKAVA_ENV``: nothing refuses to start), so sessions do not
survive a restart.

CSRF: every form embeds a per-session HMAC token that is validated
on POST. The header `X-CSRF-Token` is accepted as an alternative
for HTMX / fetch callers.

## OIDC bearer tokens (SRCNet IAM)

Set ``IAM_WELLKNOWN_ENDPOINT`` (the variable SRCNet services use; the
alias ``SKAVA_OIDC_WELLKNOWN`` also works) to the IAM's discovery
document and SKAVA accepts, on the public endpoints, an access token
that IAM issued: the signature is verified against the issuer's key set
(asymmetric algorithms only: RS256/384/512, ES256/384, PS256), the token
must carry `exp` and `iat` and not have expired (30 s leeway), it must
carry the issuer and, when ``SKAVA_OIDC_AUDIENCE`` is set, that audience.
The discovery document and key set are fetched on first use and cached;
an unknown key id triggers a refetch, so key rotation is picked up.
Static tokens keep working next to it: a presented token is first looked
up in ``SKAVA_ACCESS_TOKENS``, and only a JWT-shaped one is then checked
against the IAM.

A request without a valid token gets ``401`` with the IVOA SSO challenge:

```
WWW-Authenticate: Bearer realm="SKAVA", ivoa_bearer standard_id="ivo://ivoa.net/sso#BearerToken", access_url="https://iam.example/.well-known/openid-configuration"
```

so a client (the VisIVO Visual Analytics desktop does this) can find the
IAM, sign in and retry. When no discovery URL is configured the
challenge is the plain `Bearer realm="SKAVA"`. Two settings cover an IAM
the service reaches on a name other than the public one:
``SKAVA_OIDC_ISSUER`` is the issuer the tokens carry,
``SKAVA_OIDC_PUBLIC_WELLKNOWN`` the discovery URL told to the clients in
the challenge. ``SKAVA_OIDC_JWKS_URI`` overrides where the key set is
fetched from (setting it alone also enables OIDC validation, without
issuer check).

### Tokens forwarded and recorded

Two dependencies read the caller's token:

* `require_access_token` enforces the rule above on every public
  endpoint. On an open instance it returns nothing, whatever the caller
  sent.
* `presented_token` returns the token as presented, unverified. It is
  used only where SKAVA acts on the caller's behalf: the federated search
  ([Federation API](federation.md)) asks the sibling instances with it, so
  one sign-in covers the federation, and an instance that requires no
  token still passes along the token it was given (the siblings verify
  it).

A token is never stored. Where a job records who asked for it (staging
jobs and the `/soda/execute` staging handoff as `requested_by`, TAP async
jobs as `submitted_by`), SKAVA stores `token_reference(token)`:
`token:` followed by the first 16 hex digits of its SHA-256, or `null`
on an open instance.

The admin UI keeps its local-password sessions; service accounts
(publisher CLI, pipelines) keep using `INTERNAL_API_KEY`.

## What's NOT authenticated

* System endpoints: `/availability`, `/health/db`, `/metrics`,
  `/capabilities` — always open so monitoring can probe them.
* The TAP VOSI documents `/tap/capabilities` and `/tap/tables`, so VO
  clients can read the service description before signing in.
* The bytes behind a replica's `access_url`: their access policy is
  decided by the storage layer or the node, not SKAVA.

## Reverse-proxy concerns

If you put nginx / Traefik / Envoy in front:

* Don't strip the `X-Internal-Api-Key` header.
* Don't strip the `Authorization` header.
* The admin audit log records the connecting address as seen by the
  application (`request.client.host`); `X-Forwarded-For` is not read,
  so behind a proxy it records the last hop unless the ASGI server is
  started with proxy-header handling (`uvicorn --proxy-headers
  --forwarded-allow-ips=...`).

## Auth in tests

`tests/conftest.py` sets `INTERNAL_API_KEY=test-internal-key` before the
app is imported, and provides an `admin_user` fixture (an `admin`-role
user in the test database) and an `admin_client` fixture (a `TestClient`
already logged in through the real login form). Use them when adding
integration tests:

```python
def test_publish(client):
    r = client.post("/internal/ingestion/run",
                    headers={"X-Internal-Api-Key": "test-internal-key"},
                    files={"file": ("m.csv", b"...", "text/csv")})
    assert r.status_code == 200
```
