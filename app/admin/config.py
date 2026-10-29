# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Admin-UI specific configuration.

Lives separately from ``app/config.py`` to keep the admin concerns
(session secret, brand colour, password policy) decoupled from the
core SKAVA service config.

Every value is overridable via ``ADMIN_*`` environment variables.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ADMIN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Session ────────────────────────────────────────────────────────
    # The secret is REQUIRED in production. In dev a random value is
    # generated at startup with a loud warning so sessions invalidate on
    # every reload but the app still boots.
    session_secret: str | None = Field(default=None)
    session_cookie_name: str = "skava_admin_session"
    session_max_age_seconds: int = 60 * 60 * 8  # 8 hours
    session_cookie_secure: bool = Field(
        default=False,
        description=(
            "Default False so local HTTP dev works out of the box "
            "(browsers do not send Secure cookies over HTTP, breaking "
            "the CSRF round-trip with a 403). "
            "PRODUCTION DEPLOYMENTS MUST SET "
            "``ADMIN_SESSION_COOKIE_SECURE=true`` so the session cookie "
            "carries the Secure attribute and cannot leak over a "
            "downgraded HTTP connection."
        ),
    )

    # ── Password policy ────────────────────────────────────────────────
    password_min_length: int = 12
    password_require_mixed_case: bool = True
    password_require_digit: bool = True
    password_require_symbol: bool = False
    bcrypt_rounds: int = Field(
        default=12,
        ge=10,
        le=14,
        description="Higher = slower login, more brute-force resistant. "
                     "12 ≈ 250 ms on modern CPU. >14 hurts UX.",
    )

    # ── CSRF ───────────────────────────────────────────────────────────
    csrf_token_name: str = "csrf_token"

    # ── Brand ──────────────────────────────────────────────────────────
    # INAF light blue. Keep here so a future white-label deployment can
    # rebrand without editing templates.
    brand_color: str = "#70b5e3"
    brand_color_dark: str = "#3a6e8c"
    brand_name: str = "SKAVA Admin"

    # ── Login rate limit ───────────────────────────────────────────────
    login_rate_limit_per_minute: int = 6


admin_settings = AdminSettings()
