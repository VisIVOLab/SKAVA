# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Sequence
import logging
import time

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.errors import NoAvailableNodesError
from app.metrics import record_ranking_decision
from app.models.dataset import Dataset
from app.models.replica import DatasetReplica
from app.ranking import get_policy
from app.schemas.discovery import DiscoveryResult, DiscoverySearchResponse
from app.services.discovery_filters import apply_band_filter, apply_pos_filter, apply_time_filter
from app.vo.mappers import (
    build_access_url,
    build_datalink_descriptor,
    soda_cutout_available,
    to_dataset_metadata,
    to_node_replica,
)
from app.vo.query_params import CirclePos, NumericInterval

logger = logging.getLogger("skava.discovery")


class DiscoveryService:
    def __init__(self, db: Session):
        self.db = db
        self.policy = get_policy()

    def _fetch_replicas(self, dataset_id: int) -> list[DatasetReplica]:
        stmt: Select[tuple[DatasetReplica]] = (
            select(DatasetReplica)
            .options(joinedload(DatasetReplica.node))
            .where(DatasetReplica.dataset_id == dataset_id)
        )
        return list(self.db.scalars(stmt).all())

    def _build_result(self, dataset: Dataset, replicas: list[DatasetReplica] | None = None) -> DiscoveryResult:
        start = time.perf_counter()
        replicas = replicas if replicas is not None else self._fetch_replicas(dataset.id)
        decisions = self.policy.explain(replicas, estsize_kb=dataset.access_estsize)
        by_replica = {id(d.replica): d for d in decisions}
        ranked = [d.replica for d in decisions if d.eligible]
        if not ranked:
            raise NoAvailableNodesError(f"No available nodes for dataset '{dataset.obs_id}'")

        best = ranked[0]
        record_ranking_decision(best.node.code)

        access_url = build_access_url(dataset.obs_id)
        result = DiscoveryResult(
            metadata=to_dataset_metadata(dataset),
            replicas=[to_node_replica(rep, by_replica.get(id(rep))) for rep in ranked],
            best_node=best.node.code,
            access_url=access_url,
            datalink_descriptor=build_datalink_descriptor(access_url, soda_cutout_available(ranked)),
        )

        logger.info(
            "discovery_selection",
            extra={
                "selected_dataset": dataset.obs_id,
                "replicas": [rep.node.code for rep in ranked],
                "chosen_node": best.node.code,
                "execution_time_ms": round((time.perf_counter() - start) * 1000, 3),
            },
        )
        return result

    def search(
        self,
        obs_id: str | None = None,
        pos: CirclePos | None = None,
        band: NumericInterval | None = None,
        time_value: NumericInterval | None = None,
        collection: str | None = None,
        dptype: str | None = None,
        spatial_cell: str | None = None,
        extra_conditions: list | None = None,
        pos_footprint: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> DiscoverySearchResponse:
        stmt = select(Dataset)

        if obs_id:
            stmt = stmt.where(Dataset.obs_id == obs_id)
        if collection:
            stmt = stmt.where(Dataset.obs_collection == collection)
        if dptype:
            stmt = stmt.where(Dataset.dataproduct_type == dptype)
        if spatial_cell:
            stmt = stmt.where(Dataset.spatial_index_cell == spatial_cell)

        # Pre-built column conditions (e.g. ADQL range/equality predicates
        # parsed by the TAP profile). Applied verbatim — callers are trusted
        # to pass SQLAlchemy expressions over the Dataset model.
        for condition in (extra_conditions or []):
            stmt = stmt.where(condition)

        stmt = apply_pos_filter(stmt, pos, footprint=pos_footprint)
        stmt = apply_band_filter(stmt, band)
        stmt = apply_time_filter(stmt, time_value)

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        stmt = (
            stmt.options(selectinload(Dataset.replicas).selectinload(DatasetReplica.node))
            .order_by(Dataset.obs_id)
            .limit(limit)
            .offset(offset)
        )

        datasets: Sequence[Dataset] = self.db.scalars(stmt).all()
        results: list[DiscoveryResult] = []
        for dataset in datasets:
            try:
                results.append(self._build_result(dataset, replicas=list(dataset.replicas)))
            except NoAvailableNodesError:
                # Ignore datasets without currently eligible replicas in search results.
                continue

        logger.info(
            "discovery_search",
            extra={
                "query_params": {
                    "obs_id": obs_id,
                    "POS": f"CIRCLE {pos.ra} {pos.dec} {pos.radius}" if pos else None,
                    "BAND": f"{band.min_value} {band.max_value}" if band else None,
                    "TIME": f"{time_value.min_value} {time_value.max_value}" if time_value else None,
                    "COLLECTION": collection,
                    "DPTYPE": dptype,
                    "SPATIAL_CELL": spatial_cell,
                    "limit": limit,
                    "offset": offset,
                },
                "total_candidates": total,
                "results_count": len(results),
            },
        )
        return DiscoverySearchResponse(results=results, total=total, limit=limit, offset=offset, returned=len(results))

    def get_dataset(self, obs_id: str) -> DiscoveryResult | None:
        dataset = self.db.scalar(select(Dataset).where(Dataset.obs_id == obs_id))
        if not dataset:
            return None
        return self._build_result(dataset)
