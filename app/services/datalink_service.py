import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.errors import NoAvailableNodesError
from app.metrics import record_fallback_event, record_ranking_decision
from app.models.dataset import Dataset
from app.models.replica import DatasetReplica
from app.ranking.default import DefaultRankingPolicy
from app.schemas.datalink import DataLinkResponse, DatasetDescriptor, PrimaryAccessDescriptor, RoutingDescriptor
from app.vo.datalink import build_access_links, build_capabilities, build_service_descriptors
from app.vo.mappers import build_datalink_url, to_node_replica

logger = logging.getLogger("skava.datalink")


class DataLinkService:
    def __init__(self, db: Session):
        self.db = db
        self.policy = DefaultRankingPolicy()

    # Allowed URL schemes for a replica to be considered "healthy"
    # (and therefore selectable). SKAVA is scheme-agnostic at the
    # catalogue level — consumers decide which they can fetch.
    _HEALTHY_SCHEMES = ("http://", "https://", "file://", "ftp://", "sftp://")

    @classmethod
    def _replica_access_healthy(cls, replica: DatasetReplica) -> bool:
        return bool(
            replica.status == "available"
            and replica.is_public
            and replica.access_endpoint
            and replica.access_endpoint.startswith(cls._HEALTHY_SCHEMES)
        )

    def resolve(self, obs_id: str) -> DataLinkResponse | None:
        start = time.perf_counter()
        dataset = self.db.scalar(select(Dataset).where(Dataset.obs_id == obs_id))
        if not dataset:
            return None

        replicas = list(
            self.db.scalars(
                select(DatasetReplica)
                .options(joinedload(DatasetReplica.node))
                .where(DatasetReplica.dataset_id == dataset.id)
            ).all()
        )

        ranked = self.policy.rank(replicas)
        if not ranked:
            raise NoAvailableNodesError(f"No available nodes for dataset '{obs_id}'")

        selected = ranked[0]
        if not self._replica_access_healthy(selected):
            record_fallback_event("primary_endpoint_unhealthy")
            logger.warning(
                "datalink_fallback",
                extra={
                    "selected_dataset": obs_id,
                    "failed_primary_node": selected.node.code,
                },
            )
            selected = None
            for candidate in ranked[1:]:
                if self._replica_access_healthy(candidate):
                    selected = candidate
                    break

        if not selected:
            raise NoAvailableNodesError(f"No available nodes for dataset '{obs_id}'")

        record_ranking_decision(selected.node.code)
        datalink_url = build_datalink_url(obs_id)

        response = DataLinkResponse(
            dataset=DatasetDescriptor(
                obs_id=dataset.obs_id,
                obs_collection=dataset.obs_collection,
                dataproduct_type=dataset.dataproduct_type,
            ),
            routing=RoutingDescriptor(
                best_node=selected.node.code,
                replicas=[to_node_replica(rep) for rep in ranked],
            ),
            primary_access=PrimaryAccessDescriptor(
                access_url=selected.access_endpoint,
                access_format=dataset.access_format,
                access_estsize=dataset.access_estsize,
            ),
            links=build_access_links(dataset, selected, ranked, datalink_url),
            # Pass the ranked replicas' nodes to the service descriptor
            # builder so it can emit one ``visivo-backend`` descriptor per
            # node that has its ``visivo_backend_url`` populated. Order is
            # preserved: the best-ranked node comes first, which the
            # desktop client uses as the preferred routing target.
            service_descriptors=build_service_descriptors(
                    obs_id,
                    nodes=[rep.node for rep in ranked]),
            capabilities=build_capabilities(),
        )

        logger.info(
            "datalink_selection",
            extra={
                "selected_dataset": obs_id,
                "replicas": [rep.node.code for rep in ranked],
                "chosen_node": selected.node.code,
                "execution_time_ms": round((time.perf_counter() - start) * 1000, 3),
            },
        )

        return response
