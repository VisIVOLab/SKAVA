# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Admin CLI: bootstrap initial user, password resets, role changes.

Usage from inside the api container (docker compose):

    # Create the first admin user (interactive password prompt)
    docker compose exec api python -m app.admin.cli create-user \\
        --username fabio --role admin --email fabio.vitello@inaf.it

    # Reset a user's password
    docker compose exec api python -m app.admin.cli reset-password \\
        --username fabio

    # Change a user's role
    docker compose exec api python -m app.admin.cli set-role \\
        --username fabio --role ingester

    # List all users
    docker compose exec api python -m app.admin.cli list-users

Designed to be safe to re-run: ``create-user`` errors out if the user
already exists rather than silently overwriting, and every mutation
writes an audit row with ``actor=None`` and ``action=cli.<verb>``.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.admin.auth.password import (
    PasswordPolicyError,
    hash_password,
    validate_password_policy,
)
from app.db import SessionLocal
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole


def _prompt_password(prompt: str = "Password") -> str:
    while True:
        pw = getpass.getpass(f"{prompt}: ")
        if not pw:
            print("Password cannot be empty.", file=sys.stderr)
            continue
        try:
            validate_password_policy(pw)
        except PasswordPolicyError as exc:
            print(f"  ✗ {exc}", file=sys.stderr)
            continue
        confirm = getpass.getpass(f"{prompt} (confirm): ")
        if confirm != pw:
            print("  ✗ Passwords do not match.", file=sys.stderr)
            continue
        return pw


def _audit(db, action: str, *, target_user: User | None, changes: dict | None = None) -> None:
    db.add(AuditLog(
        actor_user_id=None,
        actor_label="<cli>",
        action=f"cli.{action}",
        target_type="user",
        target_id=str(target_user.id) if target_user else None,
        changes_json=changes,
    ))


def cmd_create_user(args: argparse.Namespace) -> int:
    role = UserRole(args.role)
    with SessionLocal() as db:
        existing = db.scalar(
            select(User).where(func.lower(User.username) == args.username.lower())
        )
        if existing is not None:
            print(f"✗ User {args.username!r} already exists.", file=sys.stderr)
            return 2

        password = args.password or _prompt_password()
        try:
            validate_password_policy(password)
        except PasswordPolicyError as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 2

        user = User(
            username=args.username,
            email=args.email,
            full_name=args.full_name,
            role=role.value,
            password_hash=hash_password(password),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.flush()
        _audit(db, "create_user", target_user=user,
               changes={"username": user.username, "role": user.role})
        db.commit()
        print(f"✓ Created user {user.username} (id={user.id}, role={user.role})")
    return 0


def cmd_reset_password(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(func.lower(User.username) == args.username.lower())
        )
        if user is None:
            print(f"✗ User {args.username!r} not found.", file=sys.stderr)
            return 2
        password = args.password or _prompt_password("New password")
        try:
            validate_password_policy(password)
        except PasswordPolicyError as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 2
        user.password_hash = hash_password(password)
        _audit(db, "reset_password", target_user=user)
        db.commit()
        print(f"✓ Password reset for {user.username}")
    return 0


def cmd_set_role(args: argparse.Namespace) -> int:
    new_role = UserRole(args.role)
    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(func.lower(User.username) == args.username.lower())
        )
        if user is None:
            print(f"✗ User {args.username!r} not found.", file=sys.stderr)
            return 2
        old_role = user.role
        user.role = new_role.value
        _audit(db, "set_role", target_user=user,
               changes={"before": old_role, "after": new_role.value})
        db.commit()
        print(f"✓ {user.username}: role {old_role} → {new_role.value}")
    return 0


def cmd_list_users(_: argparse.Namespace) -> int:
    with SessionLocal() as db:
        users = list(db.scalars(select(User).order_by(User.username)))
        if not users:
            print("(no users — bootstrap one with `create-user`)")
            return 0
        print(f"{'ID':>4}  {'USERNAME':<24} {'ROLE':<10} {'ACTIVE':<6} EMAIL")
        for u in users:
            print(
                f"{u.id:>4}  {u.username:<24} {u.role:<10} "
                f"{'yes' if u.is_active else 'no':<6} {u.email or '-'}"
            )
    return 0


def cmd_deactivate(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(func.lower(User.username) == args.username.lower())
        )
        if user is None:
            print(f"✗ User {args.username!r} not found.", file=sys.stderr)
            return 2
        user.is_active = False
        _audit(db, "deactivate", target_user=user)
        db.commit()
        print(f"✓ Deactivated {user.username}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.admin.cli", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create-user", help="Create a new admin user.")
    p.add_argument("--username", required=True)
    p.add_argument("--email", default=None)
    p.add_argument("--full-name", default=None, dest="full_name")
    p.add_argument("--role", default="admin", choices=[r.value for r in UserRole])
    p.add_argument("--password", default=None,
                   help="Inline password (omit for interactive prompt — recommended).")
    p.set_defaults(fn=cmd_create_user)

    p = sub.add_parser("reset-password", help="Reset a user's password.")
    p.add_argument("--username", required=True)
    p.add_argument("--password", default=None)
    p.set_defaults(fn=cmd_reset_password)

    p = sub.add_parser("set-role", help="Change a user's role.")
    p.add_argument("--username", required=True)
    p.add_argument("--role", required=True, choices=[r.value for r in UserRole])
    p.set_defaults(fn=cmd_set_role)

    p = sub.add_parser("list-users", help="Show all users.")
    p.set_defaults(fn=cmd_list_users)

    p = sub.add_parser("deactivate", help="Mark a user as inactive (audit-preserving).")
    p.add_argument("--username", required=True)
    p.set_defaults(fn=cmd_deactivate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
