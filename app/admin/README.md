# SKAVA Admin UI

Production-grade in-process admin console for the SKAVA Data Discovery
service. Mounted at `/admin/*` in the same FastAPI app as the public
API — no separate process, no separate database, single deployment
artefact.

## Status

Phase 1 (this commit): authentication, RBAC, audit log, dashboard
skeleton. Subsequent phases add CRUD for nodes/datasets, bulk
ingestion via the existing `/internal/ingestion/run` endpoint, an
audit-history page, exports, i18n, and tests.

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Auth + RBAC + audit + dashboard skeleton | ✅ this PR |
| 2 | CRUD: nodes, datasets, bulk upload UI | ☐ |
| 3 | History viewer + dashboard counts + export | ☐ |
| 4 | i18n + a11y polish + test suite + CI gates | ☐ |
| 5 | Docs + runbook + onboarding | ☐ |

## Architecture

```
app/admin/
├── auth/               # session/local-password + RBAC guards
├── audit/              # append-only audit log + @audited decorator
├── routers/            # one file per logical section
├── templates/          # Jinja2 server-rendered HTML
├── static/admin.css    # small CSS on top of Tailwind CDN
├── config.py           # ADMIN_* env-var settings (session, brand, …)
├── csrf.py             # form CSRF token + protection dep
├── templating.py       # Jinja2 environment + flash messages helper
├── router.py           # top-level APIRouter + error handlers + mount
└── cli.py              # `python -m app.admin.cli ...` admin tasks
```

Browser layer is HTMX + Tailwind CDN — server-rendered HTML, no SPA
build, no JSON-API parallel layer to keep in sync.

## Auth model

* Local username + bcrypt password (Phase 1 default).
* Session cookies signed with `ADMIN_SESSION_SECRET` via Starlette's
  `SessionMiddleware`. Session validity = 8 h by default.
* Three roles: `admin`, `ingester`, `viewer`. `admin` implicitly
  satisfies every `require_role(...)` guard.
* OIDC is **not** wired in Phase 1 but the module layout reserves
  `app/admin/auth/oidc.py` so adding it doesn't touch existing routes.
* Every state-changing form submission requires a CSRF token; the
  token is HMAC-derived from the session secret + per-session salt.

## Audit log

Every login attempt and every mutating action writes one row to
`audit_log` with:

* `actor_user_id` + readable `actor_label` snapshot
* `action` (dot-separated verb path, e.g. `dataset.create`)
* `target_type` / `target_id`
* `ip_address`, `user_agent`, `request_id`
* optional structured `changes_json`

Rows are append-only. Application code never updates or deletes; cold
archival + retention is handled by an external policy.

## Deployment

### 1. Configure environment

Set these in the api container (e.g. via `.env` or compose `environment:`):

```
ADMIN_SESSION_SECRET=<openssl rand -hex 32>  # REQUIRED — random 64 hex chars
ADMIN_SESSION_COOKIE_SECURE=true             # REQUIRED in production (HTTPS).
                                              # Default is false so local HTTP
                                              # dev works without TLS; setting
                                              # to true on plain HTTP makes the
                                              # browser drop the session
                                              # cookie and login fails with 403.
ADMIN_BCRYPT_ROUNDS=12                       # 12 is default; 14 = ~1s login
```

### 2. Apply the migration

```bash
docker compose -f docker-compose.local.yml exec api \
    alembic upgrade head
```

This creates the `users` and `audit_log` tables.

### 3. Bootstrap the first admin

```bash
docker compose -f docker-compose.local.yml exec -it api \
    python -m app.admin.cli create-user \
        --username fabio --role admin --email fabio.vitello@inaf.it
# prompts for the password interactively
```

### 4. Open the admin

Browse to `http://localhost:8000/admin/login`, sign in with the
bootstrapped credentials, and you land on the dashboard.

## CLI tasks

| Command | Purpose |
|---|---|
| `create-user --username … --role …` | Bootstrap or add a new user |
| `reset-password --username …` | Reset a user's password |
| `set-role --username … --role …` | Change a user's role |
| `list-users` | Show every user with role and active flag |
| `deactivate --username …` | Mark inactive (preserves audit history) |

All CLI mutations write an audit row with `actor_label="<cli>"`.

## Security checklist

| Concern | Mitigation |
|---|---|
| Password storage | bcrypt via passlib, cost 12 |
| Timing-based username enumeration | dummy hash on miss |
| Session theft | signed cookies; `SameSite=Lax`; `Secure` in prod |
| CSRF | HMAC token in every form, validated middleware-side |
| Open redirect on login `?next=` | `_safe_next()` allows only `/admin/*` paths |
| Privilege escalation | RBAC guards on every mutating route |
| Brute-force login | rate limit (Phase 4) + audit `auth.login_failed` |
| Audit tampering | append-only; no UPDATE/DELETE from app code |
| Stale sessions after deactivation | user loaded fresh on every request |

## Adding a new admin page (Phase 2 prototype)

1. Add a router file under `app/admin/routers/`, e.g. `nodes.py`.
2. Use the `current_user_required` + `require_role(...)` deps to gate.
3. Use `render(request, "nodes/list.html", ctx)` for output.
4. Wrap mutating actions with `@audited(action="node.create",
   target_type="node")`.
5. Include the router from `app/admin/router.py`.
6. Drop the matching templates into `app/admin/templates/nodes/`.

That's it — no DI wiring, no frontend build, no new JSON endpoints.
