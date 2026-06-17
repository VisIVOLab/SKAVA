# Users and roles

How to bootstrap the first admin, add additional users, and assign
the role each one needs.

## Roles

```{list-table}
:header-rows: 1
:widths: 18 25 57

* - Role
  - Implicit grants
  - Typical user
* - **admin**
  - everything else
  - Site administrators, on-call engineers.
* - **ingester**
  - read all, mutate datasets / nodes / replicas, trigger
    ingestion runs
  - Data managers, publisher CLI operators.
* - **viewer**
  - read all
  - Scientists, support staff, monitoring users.
```

Every `require_role(...)` guard implicitly accepts `admin`, so a
single admin account can do anything regardless of explicit role
checks on a route.

## Bootstrap the first user

There are no built-in users on a fresh install. Create one via the
CLI inside the api container:

```bash
docker compose -f docker-compose.yml exec -it api \
    python -m app.admin.cli create-user \
        --username yourname --role admin --email you@inaf.it
```

You'll be prompted for a password. Policy:

* minimum 12 characters
* must contain upper- AND lower-case letters
* must contain at least one digit
* must NOT exceed 72 bytes (bcrypt limit)

On success:

```
✓ Created user yourname (id=1, role=admin)
```

Visit `/admin/login` and sign in.

## CLI commands

```{list-table}
:header-rows: 1
:widths: 35 65

* - Command
  - Purpose
* - ``create-user --username … --role … [--password …]``
  - Add a new user. ``--password`` is for scripted runs; omit it for
    an interactive prompt (recommended).
* - ``reset-password --username … [--password …]``
  - Reset a user's password. Same interactive default.
* - ``set-role --username … --role …``
  - Change a user's role. Writes a ``cli.set_role`` audit row with
    ``before`` / ``after``.
* - ``list-users``
  - Print every user with id, role, active flag, email.
* - ``deactivate --username …``
  - Mark a user inactive — the row stays for audit referential
    integrity, but sessions invalidate immediately and login is
    refused.
```

All CLI mutations write to the audit log with ``actor_label="<cli>"``
so a forensics audit can tell apart UI vs CLI vs API actions.

## Password rotation

There's no in-UI "change my password" form yet (Phase 3 scope).
Until then:

```bash
docker compose exec -it api \
    python -m app.admin.cli reset-password --username yourname
```

The new password is hashed with the current ``ADMIN_BCRYPT_ROUNDS``
factor; old sessions immediately become invalid because the user's
``last_login_at`` is consulted on every request and the cookie holds
the user id only.

## Account lifecycle

```{mermaid}
stateDiagram-v2
    [*] --> active: create-user
    active --> deactivated: deactivate
    deactivated --> active: --is_active set back via SQL
                              (no CLI command yet)
    active --> reset_password: forgot password
    reset_password --> active
```

Deactivation:

* user's ``is_active=false``
* every existing session is rejected on the next request (the
  request loader checks ``user.is_active`` fresh from DB)
* login attempts return the generic "invalid username or password"
  message — no leak of "this account exists but is locked"

The user's audit history stays in place forever.

## Future: OIDC

Phase 1 ships local password only. The auth subsystem is structured
so an OIDC backend (Garr AAI, eduGAIN, ORCID, Keycloak) can be added
without touching existing routes:

* ``app/admin/auth/local.py`` stays as the local-password backend
* ``app/admin/auth/oidc.py`` (scaffolded, not implemented) will host
  the OIDC client
* both expose the same ``authenticate(...)`` signature and write the
  same session shape

Service accounts (publisher CLI) keep using local credentials even
when the human flow moves to OIDC.

## What's in the DB

```sql
SELECT id, username, role, is_active, last_login_at FROM users;
```

```
 id |  username  |   role    | is_active |     last_login_at
----+------------+-----------+-----------+-------------------------
  1 | yourname   | admin     | t         | 2026-06-05 17:30:12+00
  2 | publisher  | ingester  | t         | 2026-06-05 14:00:01+00
  3 | obsoperator| viewer    | t         |
```

The ``password_hash`` column is intentionally hidden from the
``list-users`` CLI output.

## Audit visibility (Phase 3)

When the audit history page lands, every action with ``actor_user_id
= <your id>`` will be filterable so you can produce a "what did user
X do this week" report on demand.
