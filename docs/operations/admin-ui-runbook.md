# Admin UI — operations runbook

Operational tasks that go with running the SKAVA admin UI in
production: first-login, user lifecycle, audit retention, common
incident response. Aimed at a duty operator with shell + DB access.

```{contents}
:local:
:depth: 2
```

## First login after deployment

The admin UI ships with **no users in the database**. Users are
managed with the admin CLI (`app/admin/cli.py`); the UI has no user
management pages.

```bash
# In the running container / venv
docker compose exec api python -m app.admin.cli create-user \
    --username root \
    --email root@example.org \
    --role admin
# Prompts for password interactively; validates against the policy
# (12+ chars, mixed case, digit) before writing. --password skips
# the prompt (scripts; the testbed's `make admin` uses it).
```

Repeat for the rest of the team (`--role ingester` or `viewer`).
`list-users` shows who exists.

## User lifecycle

```{list-table}
:header-rows: 1
:widths: 30 70

* - Action
  - How
* - Disable a leaver
  - ``python -m app.admin.cli deactivate --username …`` (sets
    ``is_active=false``; audit row ``cli.deactivate``). The user's
    rows stay, so the audit history keeps pointing at them; their
    sessions stop working on the next request.
* - Rotate password
  - ``python -m app.admin.cli reset-password --username …``; the
    password is re-hashed in place (audit row ``cli.reset_password``).
* - Promote viewer → ingester
  - ``python -m app.admin.cli set-role --username … --role ingester``.
    Effect is immediate on the user's next request — no session reset
    needed because RBAC is checked per request.
* - List active admins
  - SQL: ``SELECT username, email, last_login_at FROM users WHERE
    is_active AND role='admin' ORDER BY last_login_at DESC``.
```

## Audit log retention

The `audit_log` table is append-only at the application layer and
grows indefinitely. Recommended policy: keep 18 months hot, archive
beyond.

```bash
# Daily cold-archive (runs in the DB container or any psql host)
PGPASSWORD=... pg_dump -Fc -t audit_log skava \
  > /archive/skava-audit-$(date -u +%Y%m%d).dump

# Monthly hot-prune (after the archive succeeds for that month)
psql skava -c "
  DELETE FROM audit_log
  WHERE occurred_at < now() - interval '18 months';
"
```

For ad-hoc auditor requests, the UI's CSV export ({doc}`../admin-ui/history`)
covers up to 100,000 rows per filter. For larger ranges export from
psql with `\copy ... TO 'audit.csv' CSV HEADER`.

## Recovering from "I lost the only admin password"

No SQL needed: anyone with shell access to the api container resets
it with the CLI.

```bash
docker compose exec api python -m app.admin.cli reset-password --username root
```

The CLI writes the audit entry `cli.reset_password` (actor `<cli>`).
If the account was deactivated, there is no CLI verb to reactivate
it: create a new admin with `create-user`, or set `is_active = true`
on the row in SQL.

## Common incidents

### "All admin actions failing with 403 forbidden"

Likely cause: the user's `is_active` was flipped to `false` or their
role was downgraded. Check:

```sql
SELECT username, role, is_active FROM users WHERE username='…';
```

### "CSRF token mismatch on every form"

Usually means the operator opened the admin UI in two tabs at
different times — the session-bound CSRF secret rotated between
them. Resolution: log out + log in in both tabs.

If the symptom is *consistent*, check that `ADMIN_SESSION_COOKIE_SECURE`
matches the actual transport (must be `False` for plain HTTP dev,
`True` for HTTPS).
Also check that `ADMIN_SESSION_SECRET` is set: without it each process
generates its own secret, so a restart (or a second worker) invalidates
every form.

### "History page shows '0 entries' but I know we just did things"

Two possible causes, in order of likelihood:

1. The DB was reset/migrated and the audit table truncated. Check
   `SELECT count(*) FROM audit_log` directly.
2. The mutating route that should have written an audit row didn't
   call `log_action()` — file a bug; every mutating route should call
   it. The {doc}`../admin-ui/history` page lists the routes already
   wired up.

### "Bulk upload returned dry-run summary but no records were created"

`/admin/upload` defaults to **Dry run**. Choose *Run* under "Run mode"
and re-submit. The dry run is still in the audit log under
`ingestion.upload.dry_run` (the real run is `ingestion.upload`).

## Read-only pages at a glance

```{list-table}
:header-rows: 1
:widths: 30 35 35

* - Feature
  - URL
  - Audit action
* - Audit history viewer
  - ``/admin/history/``
  - (read-only, no audit row)
* - Audit detail
  - ``/admin/history/<id>``
  - (read-only)
* - CSV export — audit
  - ``/admin/history/export.csv``
  - (read-only)
* - CSV export — datasets
  - ``/admin/datasets/export.csv``
  - (read-only)
* - Dashboard 7-day trend
  - ``/admin/`` (above the activity table)
  - n/a
```

See also:

* {doc}`../admin-ui/overview` — high-level architecture
* {doc}`../admin-ui/history` — audit page UX + filter semantics
* {doc}`../admin-ui/upload` — bulk upload
* {doc}`troubleshooting` — generic SKAVA incidents (not admin-specific)
