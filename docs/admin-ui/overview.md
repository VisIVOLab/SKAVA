# Admin UI overview

`/admin` is a server-rendered web admin built into the same FastAPI
process as the public discovery API. It uses Jinja2 templates +
HTMX for partial updates + Tailwind (CDN) for styling — no Node
build step, no separate frontend deployment.

## What it does

| Page | Purpose |
|---|---|
| **Dashboard** | counts (datasets / nodes / users / audit rows), 7-day activity trend, top actors and actions, datasets per node, recent activity, your profile |
| **Datasets** | paginated search + filter, CSV export, single-record detail with replicas, edit form with FITS pre-fill |
| **Nodes** | CRUD on federation members; VisIVO backend URL configuration |
| **Upload** | CSV / JSON manifest upload for bulk ingestion (dry run or run) |
| **History** | filterable audit log, per-entry detail, CSV export |

There is no user-management page: admin accounts and roles are
managed with the [admin CLI](users-roles.md).

What it deliberately doesn't do:

* Replace the publisher CLI for at-scale ingestion. The admin UI is
  for inspection, hand edits and small manifest uploads.
* Provide a "fake JSON API". Every page serves HTML; the only
  non-HTML responses are the CSV exports and the JSON returned by
  the FITS pre-fill helper to its own form.
* Run untrusted JavaScript. Server-rendered, HTMX swaps only.

## Architecture

```{mermaid}
flowchart LR
    Browser --> SessionMiddleware
    SessionMiddleware --> AdminRouter
    AdminRouter --> RBACDep[require_role]
    RBACDep --> Handler
    Handler --> DB[(PostgreSQL)]
    Handler --> Template[Jinja2 template]
    Template --> Browser
```

* **Session cookie**: HMAC-signed via Starlette's `SessionMiddleware`,
  default 8 h lifetime.
* **CSRF**: per-session token included in every form, validated on
  POST/PUT/PATCH/DELETE before the handler runs.
* **RBAC**: three roles (`admin`, `ingester`, `viewer`); enforced via
  the `require_role()` FastAPI dependency.
* **Audit**: every mutating route writes a row to `audit_log`.

The full code map is in
[Architecture / components — app/admin/](../architecture/components.md#appadmin--admin-ui).

## Authentication

The admin UI signs users in with a **local username + bcrypt
password**. The login flow:

```{mermaid}
sequenceDiagram
    User->>Browser: open /admin/
    Browser->>SKAVA: GET /admin/
    SKAVA-->>Browser: 303 → /admin/login?next=/admin/
    Browser->>SKAVA: GET /admin/login
    SKAVA-->>Browser: form (CSRF token embedded)
    User->>Browser: submit username + password
    Browser->>SKAVA: POST /admin/login
    SKAVA->>SKAVA: bcrypt verify, mark session
    SKAVA-->>Browser: 303 → /admin/ (Set-Cookie)
    Browser->>SKAVA: GET /admin/
    SKAVA-->>Browser: dashboard.html
```

The admin UI has no OIDC sign-in. OIDC bearer tokens are accepted by
the catalogue's API (see [Authentication](../api/auth.md)), not by
`/admin`: admin accounts are local and are created with the CLI.
Failed logins are recorded in the audit log as `auth.login_failed`;
after `ADMIN_LOGIN_RATE_LIMIT_PER_MINUTE` of them in a minute from one
client address, the login answers 429 without checking the password
(`auth.login_throttled`).

## Look & feel

* INAF brand colour (`#70b5e3`) primary, configurable via
  `ADMIN_BRAND_COLOR` (and `ADMIN_BRAND_COLOR_DARK`,
  `ADMIN_BRAND_NAME`) env vars.
* Tailwind CSS via Play CDN and HTMX from unpkg (no build step). For
  air-gapped deployments, swap the CDN lines in `templates/base.html`
  for bundled copies.
* Light theme only; there is no dark mode.
* Accessibility baseline: keyboard navigation, visible focus rings,
  ARIA live regions on flash messages, WCAG AA contrast.

## How operators use it

```{list-table}
:header-rows: 1
:widths: 25 75

* - Role
  - Typical journey
* - **admin**
  - Bootstrap a new SRC: add Node, run publisher CLI from the SRC,
    verify the records appear, hand the catalogue URL to scientists.
* - **ingester**
  - Daily: upload manifests, check audit history for failures,
    fix one bad record by hand if needed.
* - **viewer**
  - Inspect what's in the catalogue, copy a DataLink URL into
    TOPCAT, browse provenance.
```

## Tour

Each section has its own page:

* [Users & roles](users-roles.md) — bootstrap, role management, password
  policy.
* [Nodes](nodes.md) — register federation members and their VisIVO
  backend.
* [Datasets](datasets.md) — browse / search / edit, including the
  small-file FITS pre-fill.
* [Bulk upload](upload.md) — CSV / JSON manifests from the browser.
* [History](history.md) — the audit log viewer and CSV export.
* [Audit](audit.md) — what gets logged and how to query it.
