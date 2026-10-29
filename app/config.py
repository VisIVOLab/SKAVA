# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SKAVA Data Discovery Service"
    env: Literal["dev", "staging", "production"] = "dev"

    database_url: str | None = None
    public_base_url: str | None = None

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    internal_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INTERNAL_API_KEY", "SKAVA_INTERNAL_API_KEY"),
    )
    access_tokens: str | None = None
    # ── OIDC bearer tokens (SRCNet IAM: INDIGO IAM / Keycloak) ───────────
    # The issuer's discovery document; the same variable name the SRCNet
    # architecture uses for its services (IAM_WELLKNOWN_ENDPOINT). When set,
    # a JWT signed by that issuer is accepted alongside the static tokens.
    # ``oidc_audience``: the audience SKAVA expects (a token exchanged for
    # SKAVA, as SRCNet services do via the Auth API); unset = not checked.
    # ``oidc_jwks_uri``: override the key set location (tests, air-gapped).
    oidc_wellknown: str | None = Field(
        default=None,
        validation_alias=AliasChoices("IAM_WELLKNOWN_ENDPOINT", "SKAVA_OIDC_WELLKNOWN"),
    )
    oidc_audience: str | None = None
    oidc_jwks_uri: str | None = None
    # ``oidc_issuer``: the issuer the tokens carry, when it is not the one the
    # discovery document reports (an IAM reached by the service on a private
    # name but by the users on its public one). ``oidc_public_wellknown``: the
    # discovery URL told to clients in the ivoa_bearer challenge, when the
    # service itself fetches it elsewhere; defaults to ``oidc_wellknown``.
    oidc_issuer: str | None = None
    oidc_public_wellknown: str | None = None
    federated_src_urls: str | None = None
    federation_timeout_seconds: float = Field(default=2.0, ge=0.1)

    # ── SODA execution (compute-next-to-data delegation) ─────────────────
    # When a dataset's best node exposes a co-located VisIVO backend
    # (Node.visivo_backend_url), /soda/execute delegates the byte-level
    # cutout there. The bearer token is forwarded when the node's backend
    # requires auth; the timeout bounds the synchronous wait.
    visivo_backend_token: str | None = None
    soda_backend_timeout_seconds: float = Field(default=120.0, ge=1.0)

    # ── Routing: ranking policy and node telemetry ───────────────────────
    # ``static`` ranks by the scores declared on each node; ``resource_aware``
    # ranks by what the nodes' backends report (see app/ranking/resource_aware.py).
    # The prober runs every ``telemetry_interval_seconds`` (0 = never: the
    # telemetry is then only refreshed through POST /internal/telemetry/probe);
    # a measurement older than ``telemetry_ttl_seconds`` is not trusted.
    ranking_policy: Literal["static", "resource_aware"] = "resource_aware"
    # How a record from a new node proves it holds a copy of a catalogued
    # product: "checksum" (equal SHA-256 checksums required; without them it
    # is refused, fail-closed) or "metadata" (accepted unless checksum, size
    # or type contradict, for curated catalogues whose obs_id convention is
    # trusted). The federated search merges listings by the same rule.
    replica_identity: Literal["checksum", "metadata"] = "checksum"
    telemetry_interval_seconds: float = Field(default=10.0, ge=0.0)
    telemetry_ttl_seconds: float = Field(default=60.0, gt=0.0)
    telemetry_timeout_seconds: float = Field(default=3.0, gt=0.0)
    telemetry_ping_samples: int = Field(default=3, ge=1, le=20)
    # Resource-aware cost, in millisecond-equivalents per unit of each term:
    # round trip (per ms), CPU pressure (per %), queued+running tasks per
    # worker, and the share of the node's free memory the dataset would take.
    ranking_weight_rtt: float = Field(default=1.0, ge=0.0)
    ranking_weight_cpu: float = Field(default=1.0, ge=0.0)
    ranking_weight_queue: float = Field(default=20.0, ge=0.0)
    ranking_weight_memory: float = Field(default=50.0, ge=0.0)
    # Memory a dataset needs on the node, as a multiple of its size.
    ranking_memory_factor: float = Field(default=1.0, ge=0.0)

    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=20, ge=0)
    db_pool_timeout: int = Field(default=30, ge=1)
    db_pool_recycle: int = Field(default=1800, ge=30)
    db_connect_retries: int = Field(default=10, ge=1)
    db_connect_retry_delay: float = Field(default=1.5, ge=0.1)

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SKAVA_", extra="ignore")

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        if not self.database_url:
            if self.env == "dev":
                self.database_url = "postgresql+psycopg://skava:skava@localhost:5432/skava"
            else:
                raise ValueError("SKAVA_DATABASE_URL is required for staging/production environments")

        if not self.public_base_url:
            if self.env == "dev":
                self.public_base_url = "http://localhost:8000"
            else:
                raise ValueError("SKAVA_PUBLIC_BASE_URL is required for staging/production environments")

        if self.env == "production" and self.public_base_url.startswith("http://"):
            raise ValueError("SKAVA_PUBLIC_BASE_URL must use https:// in production")

        return self

    @property
    def access_token_set(self) -> set[str]:
        if not self.access_tokens:
            return set()
        return {token.strip() for token in self.access_tokens.split(",") if token.strip()}

    @property
    def federated_sources(self) -> list[str]:
        if not self.federated_src_urls:
            return []
        return [url.strip().rstrip("/") for url in self.federated_src_urls.split(",") if url.strip()]


settings = Settings()
