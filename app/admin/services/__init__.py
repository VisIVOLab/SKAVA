# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Pure-logic helpers used by the admin routers.

Routers stay thin (parse form, call service, render template) and the
real work lives here. Keeps the modules independently testable —
``fits_extract`` for example has no FastAPI / DB dependencies and can
be unit-tested with raw bytes.
"""
