"""Audit subsystem — append-only log of mutating actions.

Two public entry points:

* ``log_action()``     — direct call from a handler when you want full
                          control over the captured fields (e.g. when
                          logging a "view sensitive page" event).
* ``@audited()``       — decorator on route handlers that derives the
                          action name from the route and snapshots
                          before/after state automatically.

Audit rows are written in the same transaction as the audited change
when possible; the decorator handles commit/rollback for you.
"""
from app.admin.audit.service import log_action  # noqa: F401
from app.admin.audit.decorator import audited  # noqa: F401
