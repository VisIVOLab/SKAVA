# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from app.config import settings
from app.ranking.base import RankedReplica, RankingPolicy
from app.ranking.default import DefaultRankingPolicy
from app.ranking.resource_aware import ResourceAwareRankingPolicy


def get_policy() -> RankingPolicy:
    """The ranking policy this deployment uses (SKAVA_RANKING_POLICY)."""
    if settings.ranking_policy == "resource_aware":
        return ResourceAwareRankingPolicy()
    return DefaultRankingPolicy()


__all__ = ["DefaultRankingPolicy", "RankedReplica", "RankingPolicy", "ResourceAwareRankingPolicy", "get_policy"]
