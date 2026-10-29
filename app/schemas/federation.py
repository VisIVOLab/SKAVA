# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.discovery import DiscoveryResult


class FederationSource(BaseModel):
    """One catalogue the federated search asked: the local one, or a sibling."""

    base_url: str
    status: Literal["local", "ok", "error", "timeout", "unauthorized"]
    returned: int = 0
    total: int | None = None
    elapsed_ms: float | None = None
    error: str | None = None


class AlsoAt(BaseModel):
    """A sibling that catalogues a dataset the merged answer already lists,
    with that sibling's own decision for it."""

    source: str
    best_node: str
    access_url: str
    replicas: int


class FederatedResult(DiscoveryResult):
    source: str
    also_at: list[AlsoAt] = Field(default_factory=list)
    # Set when another source lists a different product under the same
    # obs_id: the two are returned apart, never merged as copies.
    identity_conflict: str | None = None


class FederatedSearchResponse(BaseModel):
    results: list[FederatedResult]
    returned: int
    limit: int
    sources: list[FederationSource]
    duplicates_merged: int
    identity_conflicts: int = 0
    identity_unverified: int = 0
