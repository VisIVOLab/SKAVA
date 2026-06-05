# Audit log

Every mutating action in the admin UI and every CLI mutation writes
a row to the `audit_log` table. This page documents what gets
captured, how to inspect it today, and what's coming in Phase 3.

## What gets captured

```sql
CREATE TABLE audit_log (
    id            BIGSERIAL PRIMARY KEY,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    actor_label   VARCHAR(128) NOT NULL,
    action        VARCHAR(64) NOT NULL,
    target_type   VARCHAR(32),
    target_id     VARCHAR(64),
    ip_address    VARCHAR(45),
    user_agent    VARCHAR(255),
    request_id    VARCHAR(64),
    changes_json  JSONB
);
CREATE INDEX idx_audit_action  ON audit_log(action);
CREATE INDEX idx_audit_target  ON audit_log(target_type, target_id);
CREATE INDEX idx_audit_actor   ON audit_log(actor_user_id);
CREATE INDEX idx_audit_when    ON audit_log(occurred_at DESC);
```

Field-by-field:

```{list-table}
:header-rows: 1
:widths: 22 78

* - Column
  - Meaning
* - ``occurred_at``
  - UTC timestamp set by ``DEFAULT now()``. Application code never
    forges this.
* - ``actor_user_id``
  - FK to ``users``. ``NULL`` for anonymous events (failed login from
    a never-existed username) and for CLI calls.
* - ``actor_label``
  - Snapshot string captured at write time so the row stays readable
    after the user is deleted or renamed. Format:
    ``username (id=N)`` for sessions, ``<cli>`` for CLI mutations,
    ``<anonymous IP>`` for pre-auth events.
* - ``action``
  - Dot-separated verb path. Convention: ``<entity>.<verb>``.
    Examples: ``dataset.create``, ``node.update``, ``user.role_change``,
    ``auth.login_failed``, ``cli.create_user``.
* - ``target_type`` / ``target_id``
  - Entity identifier. For row-level changes ``target_id`` is the
    primary key; for ``auth.login_failed`` it's the attempted
    username.
* - ``ip_address``
  - Origin IP. Behind a reverse proxy you'll see the proxy's IP
    unless ``X-Forwarded-For`` is honoured (Phase 4: set
    ``trusted_hosts`` config).
* - ``user_agent``
  - First 255 chars of the ``User-Agent`` header. Empty for CLI.
* - ``request_id``
  - Mirrors the request_id from ``RequestContextMiddleware``, so an
    audit row joins back to the surrounding log lines.
* - ``changes_json``
  - Optional structured diff. Convention: ``{"before": {...},
    "after": {...}}`` for updates, ``{"after": {...}}`` for creates,
    ``{"before": {...}}`` for deletes, ``null`` for read-only events
    (login, view audit).
```

## How rows are written

Two entry points in code:

* ``log_action(db, request, actor=user, action="...", ...)`` —
  direct call inside a handler. Use when you want full control over
  the captured fields (e.g. capturing field-level diffs).
* ``@audited(action="...", target_type="...")`` — decorator on a
  route handler. Derives the target id from the returned entity's
  ``.id`` attribute when the handler returns one; lets you override
  via ``request.state.audit_target_id``.

Both go through the same service function. The append-only
guarantee is a code convention: nothing in ``app/`` does ``UPDATE``
or ``DELETE`` against the table.

## Inspecting today (Phase 1+2)

The admin UI Dashboard shows the latest 10 rows on the landing
page. For richer queries, drop to PostgreSQL until the Phase 3
audit page lands:

```bash
docker compose exec db psql -U skava -d skava
```

```sql
-- Recent activity (last hour)
SELECT occurred_at, actor_label, action, target_type, target_id
FROM   audit_log
WHERE  occurred_at > now() - interval '1 hour'
ORDER  BY occurred_at DESC;

-- What did user X do this week
SELECT occurred_at, action, target_type, target_id, changes_json
FROM   audit_log
WHERE  actor_user_id = (SELECT id FROM users WHERE username = 'yourname')
   AND occurred_at > now() - interval '7 days'
ORDER  BY occurred_at DESC;

-- Failed login bursts
SELECT date_trunc('minute', occurred_at) AS minute,
       count(*) AS attempts,
       array_agg(DISTINCT ip_address) AS ips
FROM   audit_log
WHERE  action = 'auth.login_failed'
  AND  occurred_at > now() - interval '24 hours'
GROUP  BY 1
HAVING count(*) > 5
ORDER  BY 1 DESC;

-- Diff a single change
SELECT changes_json
FROM   audit_log
WHERE  action = 'node.update' AND target_id = '4'
ORDER  BY occurred_at DESC LIMIT 1;
```

## Coming in Phase 3

A `/admin/audit/` page with:

* filters: actor, action prefix, target type+id, date range
* JSON-formatted before/after diffs rendered as a side-by-side view
* one-click "show me everything around this request_id" deep-link
  that joins audit + structured logs
* CSV export with the same filters applied

## Retention

There's no built-in retention policy. The recommended pattern is:

1. Nightly `pg_dump` of the table to cold storage (so you don't lose
   the audit history when you ``DELETE``).
2. Quarterly ``DELETE FROM audit_log WHERE occurred_at <
   now() - INTERVAL '365 days';`` to keep the live table small.

Adjust the window per your compliance posture. INAF-internal SRC
sites are likely fine with 365 days.

## Privacy

The audit log contains user IDs and IPs. Treat the table as personal
data and apply your local SRC privacy policy. Common controls:

* deny direct DB read access to non-admins (PostgreSQL roles)
* redact IP last-octet before export
* honour subject-access requests via a templated query

Phase 4 will add a `--redact-ip` toggle on the CSV export.
