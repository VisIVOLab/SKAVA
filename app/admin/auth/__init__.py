# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Authentication subsystem for the SKAVA Admin UI.

Backends are kept in their own files so that adding a new one (e.g.
OIDC) does not require touching the existing local-password code:

* ``local.py``  — username + bcrypt password (current default)
* ``session.py`` — Starlette signed-cookie session integration +
                   current_user FastAPI dependency
* ``rbac.py``   — role-based authorisation guards
* ``password.py`` — bcrypt hashing + policy validation
"""
