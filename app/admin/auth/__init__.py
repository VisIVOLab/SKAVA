"""Authentication subsystem for the SKAVA Admin UI.

Backends are kept in their own files so that adding a new one (e.g.
OIDC) does not require touching the existing local-password code:

* ``local.py``  — username + bcrypt password (current default)
* ``session.py`` — Starlette signed-cookie session integration +
                   current_user FastAPI dependency
* ``rbac.py``   — role-based authorisation guards
* ``password.py`` — bcrypt hashing + policy validation
"""
