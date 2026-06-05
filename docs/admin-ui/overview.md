# Admin UI overview

`/admin` is a server-rendered web admin built into the same FastAPI
process as the public discovery API. It uses Jinja2 templates +
HTMX for partial updates + Tailwind (CDN) for styling — no Node
build step, no separate frontend deployment.

## What it does

| Page | Purpose |
|---|---|
| **Dashboard** | counts (datasets / nodes / users / audit rows), recent activity, your profile |
| **Datasets** | paginated search + filter, single-record detail with replicas, edit form with FITS pre-fill |
| **Nodes** | CRUD on federation members; VisIVO backend URL configuration |
| **Upload** | drag-drop CSV / JSON for bulk ingestion |
| **History** (Phase 3) | filterable audit log + ingestion job list |
| **Users** (Phase 3) | manage local admin users + roles |

What it deliberately doesn't do:

* Replace the publisher CLI for at-scale ingestion. The admin UI is
  for inspection, hand edits, approvals.
* Provide a "fake JSON API". Every endpoint serves HTML.
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
[Architecture / components — app/admin/](../architecture/components#app-admin-admin-ui).

## Authentication

Phase 1 ships with **local username + bcrypt password**. The login
flow:

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

A future phase will add OIDC (Garr AAI, eduGAIN). The local-password
backend stays as a fallback for service accounts.

## Look & feel

* INAF brand colour (`#70b5e3`) primary, configurable via
  `ADMIN_BRAND_COLOR` env var.
* Tailwind CSS via Play CDN (no build step). For air-gapped
  deployments, swap the CDN line in `templates/base.html` for a
  bundled tarball.
* Dark mode follows the user's OS preference (Furo's behaviour).
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
  - Daily: trigger ingestion runs, check audit history for failures,
    fix one bad record by hand if needed.
* - **viewer**
  - Inspect what's in the catalogue, copy a DataLink URL into
    TOPCAT, browse provenance.
```

## Tour

Each section has its own page:

* [Users & roles](users-roles) — bootstrap, role management, password
  policy.
* [Nodes](nodes) — register federation members and their VisIVO
  backend.
* [Datasets](datasets) — browse / search / edit, including the
  small-file FITS pre-fill.
* [Audit](audit) — what gets logged and how to query it.
