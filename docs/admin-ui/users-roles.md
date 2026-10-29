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
  - read all, mutate datasets / nodes / replicas, upload
    manifests on the Upload page
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

The rules come from `ADMIN_PASSWORD_MIN_LENGTH`,
`ADMIN_PASSWORD_REQUIRE_MIXED_CASE`, `ADMIN_PASSWORD_REQUIRE_DIGIT` and
`ADMIN_PASSWORD_REQUIRE_SYMBOL` (off by default); the 72-byte limit is
fixed.

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
* - ``create-user --username … [--role …] [--email …] [--full-name …] [--password …]``
  - Add a new user. ``--role`` defaults to ``admin``. ``--password``
    is for scripted runs; omit it for an interactive prompt
    (recommended). Refuses if the username already exists.
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

Usernames are matched case-insensitively.

All CLI mutations write to the audit log with ``actor_label="<cli>"``
and an action named ``cli.<verb>`` (``cli.create_user``,
``cli.reset_password``, ``cli.set_role``, ``cli.deactivate``), so a
forensics audit can tell UI actions from CLI actions.

## Password rotation

There is no in-UI "change my password" form; passwords are changed
with the CLI:

```bash
docker compose exec -it api \
    python -m app.admin.cli reset-password --username yourname
```

The new password is hashed with the current ``ADMIN_BCRYPT_ROUNDS``
factor (default 12; older hashes are upgraded at the next login).
A password reset does **not** end existing sessions: the cookie holds
the user id only, so a session that is already signed in stays valid
until it expires (``ADMIN_SESSION_MAX_AGE_SECONDS``, 8 h by default)
or the user signs out. To cut a user off at once, ``deactivate`` the
account. Role changes, on the other hand, apply on the next request,
because the user row is reloaded from the database every time.

## Account lifecycle

```{mermaid}
stateDiagram-v2
    [*] --> active: create-user
    active --> deactivated: deactivate
    deactivated --> active: --is_active set back via SQL
                              (no CLI command)
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

## OIDC

The admin UI authenticates with local passwords only
(``app/admin/auth/local.py``); there is no OIDC sign-in for
``/admin``. OIDC is supported by the catalogue's API, which validates
bearer tokens independently of the admin accounts (see
[Authentication](../api/auth.md)).

The publisher CLI does not use an admin account at all: it calls the
ingestion API with the ``X-Internal-Api-Key`` shared secret.

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

## Audit visibility

The [History](history.md) page answers "what did user X do this week":
type the username in the **Actor** filter (a substring match on the
``username (id=N)`` label), set the date range, and export the result
as CSV. CLI actions carry the actor ``<cli>``.
