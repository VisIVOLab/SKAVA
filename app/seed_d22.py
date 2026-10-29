# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""CLI entrypoint to seed the D2.2 representative datasets.

Usage::

    python -m app.seed_d22

Idempotent — repeated invocations remove the previous d22-* datasets and
reinsert the canonical catalogue.
"""
from app.db import SessionLocal
from app.services.seed_d22 import seed_d22


if __name__ == "__main__":
    with SessionLocal() as db:
        counts = seed_d22(db)
        print(f"D2.2 seed completed — {counts['datasets']} datasets, "
              f"{counts['replicas']} replicas inserted.")
