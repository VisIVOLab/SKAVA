from app.models.replica import DatasetReplica
from app.ranking.base import RankingPolicy


class DefaultRankingPolicy(RankingPolicy):
    def eligible(self, replicas: list[DatasetReplica]) -> list[DatasetReplica]:
        return [rep for rep in replicas if rep.node.is_enabled and rep.node.is_available]

    def rank(self, replicas: list[DatasetReplica]) -> list[DatasetReplica]:
        eligible = self.eligible(replicas)
        if not eligible:
            return []
        return sorted(
            eligible,
            key=lambda r: (
                r.node.latency_score if r.node.latency_score is not None else float("inf"),
                -(r.node.capability_score if r.node.capability_score is not None else float("-inf")),
            ),
        )

    def choose(self, replicas: list[DatasetReplica]) -> DatasetReplica:
        ranked = self.rank(replicas)
        if not ranked:
            raise ValueError("No eligible replicas available")
        return ranked[0]
