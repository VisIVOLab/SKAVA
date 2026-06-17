# Admin UI — operations runbook

Operational tasks that go with running the SKAVA admin UI in
production: first-login, user lifecycle, audit retention, common
incident response. Aimed at a duty operator with shell + DB access.

```{contents}
:local:
:depth: 2
```

## First login after deployment

The admin UI ships with **no users in the database**. The first user
must be created out-of-band via a one-shot script, then everything
else flows through the UI.

```bash
# In the running container / venv
python -m app.scripts.create_admin_user \
    --username root \
    --email root@example.org \
    --role admin
# Prompts for password interactively; validates against the policy
# (12+ chars, mixed case, digit) before writing.
```

After login, use the UI to create the rest of the team (Phase 5 adds
this section to the nav; until then, repeat the CLI for additional
users).

## User lifecycle

```{list-table}
:header-rows: 1
:widths: 30 70

* - Action
  - How
* - Disable a leaver
  - SQL: ``UPDATE users SET is_active=false, password_hash=NULL WHERE username='…'``.
    Their `actor_user_id` in the audit log is preserved by the
    `ON DELETE SET NULL` cascade, but `actor_label` snapshot stays
    readable.
* - Rotate password
  - Re-run the CLI script with the same username; the password is
    re-hashed in place.
* - Promote viewer → ingester
  - SQL: ``UPDATE users SET role='ingester' WHERE username='…'``.
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

```sql
-- emergency: reset role=admin user's password to a random temporary
UPDATE users
SET    password_hash = NULL,
       is_active     = true
WHERE  username = 'root';
```

Then re-run the CLI to set a new password. The temporary NULL hash
prevents login during the reset window; the audit entry for the
re-set is `auth.password_reset` (recorded by the CLI).

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

### "History page shows '0 entries' but I know we just did things"

Two possible causes, in order of likelihood:

1. The DB was reset/migrated and the audit table truncated. Check
   `SELECT count(*) FROM audit_log` directly.
2. The mutating route that should have written an audit row didn't
   call `log_action()` — file a bug; every mutating route should call
   it. The {doc}`../admin-ui/history` page lists the routes already
   wired up.

### "Bulk upload returned dry-run summary but no records were created"

`/admin/upload` defaults to **dry-run**. Untick the *Dry run* box and
re-submit. The original dry-run run is still in the audit log under
`ingestion.dry_run`.

## Phase 3 features at a glance

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
* {doc}`../admin-ui/upload` — Phase 2c bulk upload
* {doc}`troubleshooting` — generic SKAVA incidents (not admin-specific)
