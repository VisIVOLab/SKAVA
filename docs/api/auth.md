# Authentication

SKAVA exposes three categories of endpoint, each with its own
authentication scheme.

## Public discovery — usually open

* `/discovery/*`
* `/datalink/*`
* `/access/*`
* `/soda/*`
* `/tap/*`
* `/vosi/*`
* `/system/*`

**By default**: no authentication. Anyone can query.

**Optional bearer token**: set
``SKAVA_ACCESS_TOKENS=tok1,tok2,...`` to require a valid token on
every request. Clients pass it as either header:

```
Authorization: Bearer <token>
```

or:

```
X-SKAVA-Access-Token: <token>
```

Missing or wrong → 401.

Rotate by adding the new token, distributing it to clients, then
removing the old one. The list is a whitelist, so multiple tokens
co-exist seamlessly.

## Internal ingestion — API key

* `/internal/ingestion/dry-run`
* `/internal/ingestion/run`
* `/internal/ingestion/history`
* `/internal/ingestion/history/{job_id}`

Required header on every call:

```
X-Internal-Api-Key: <value of INTERNAL_API_KEY env var>
```

The key:

* must match the server-configured `INTERNAL_API_KEY` exactly
* must be ≥ 8 chars (validated at SKAVA boot)
* is logged at INFO level when wrong (failed-login pattern surfaces
  in your log aggregator)

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
production set it to a stable ``openssl rand -hex 32`` value; in
dev a per-boot random is generated with a loud warning.

CSRF: every form embeds a per-session HMAC token that is validated
on POST. The header `X-CSRF-Token` is accepted as an alternative
for HTMX / fetch callers.

## OIDC bearer tokens (SRCNet IAM)

Set ``IAM_WELLKNOWN_ENDPOINT`` (the variable SRCNet services use) to the
IAM's discovery document and SKAVA accepts, on the public endpoints, an
access token that IAM issued: the signature is verified against the
issuer's key set (asymmetric algorithms only), the token must not have
expired, and it must carry the issuer and, when ``SKAVA_OIDC_AUDIENCE`` is
set, that audience. Static tokens keep working next to it.

A request without a valid token gets ``401`` with the IVOA SSO challenge:

```
WWW-Authenticate: Bearer realm="SKAVA", ivoa_bearer standard_id="ivo://ivoa.net/sso#BearerToken", access_url="https://iam.example/.well-known/openid-configuration"
```

so a client (the VisIVO Visual Analytics desktop does this) can find the
IAM, sign in and retry. Two settings cover an IAM the service reaches on a
name other than the public one: ``SKAVA_OIDC_ISSUER`` is the issuer the
tokens carry, ``SKAVA_OIDC_PUBLIC_WELLKNOWN`` the discovery URL told to the
clients in the challenge. ``SKAVA_OIDC_JWKS_URI`` overrides where the key
set is fetched from.

The federated search ([Federation API](federation)) asks the sibling
instances with the caller's token, so one sign-in covers the federation;
an instance that requires no token still passes the token it was given
along. The admin UI keeps its local-password sessions; service accounts
(publisher CLI, pipelines) keep using `INTERNAL_API_KEY`.

## What's NOT authenticated

* Health / capability endpoints (`/system/health`,
  `/vosi/capabilities`) — intentionally always open so monitoring
  can probe them.
* The `/access/{obs_id}` redirector — its target's access policy is
  decided by the storage layer, not SKAVA.

## Reverse-proxy concerns

If you put nginx / Traefik / Envoy in front:

* Don't strip the `X-Internal-Api-Key` header.
* Don't strip the `Authorization` header.
* Set `proxy_set_header X-Forwarded-For` so SKAVA's audit log can
  capture the real client IP.

Future enhancement: a `SKAVA_TRUSTED_PROXIES` config that tells the
audit logger to honour the X-Forwarded-For header (today it logs the
last hop IP).

## Auth in tests

`tests/conftest.py` registers a `test_internal_key` fixture and a
`test_admin_user` fixture that bootstrap minimal credentials in the
test PostgreSQL. Use them when adding integration tests:

```python
def test_publish(client, test_internal_key):
    r = client.post("/internal/ingestion/run",
                    headers={"X-Internal-Api-Key": test_internal_key},
                    files={"file": ("m.csv", b"...", "text/csv")})
    assert r.status_code == 200
```
