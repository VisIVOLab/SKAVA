# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""SKAVA Admin UI — production-grade in-process admin console.

See ``app/admin/README.md`` for architecture, deployment and operational
notes.

This package is mounted at ``/admin`` in ``app/main.py``. Calling code
should not import implementation details from here; the only public
surface is ``app.admin.router.router`` (the FastAPI APIRouter) and
``app.admin.bootstrap.bootstrap_admin`` (called once at startup).
"""
