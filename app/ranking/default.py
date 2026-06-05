from app.models.replica import DatasetReplica
from app.ranking.base import RankingPolicy


def _score(value: float | None, default: float) -> float:
    return value if value is not None else default


class DefaultRankingPolicy(RankingPolicy):
    def eligible(self, replicas: list[DatasetReplica]) -> list[DatasetReplica]:
        return [
            rep
            for rep in replicas
            if getattr(rep, "status", "available") == "available"
            and getattr(rep, "is_public", True)
            and rep.node.is_enabled
            and rep.node.is_available
        ]

    def rank(self, replicas: list[DatasetReplica]) -> list[DatasetReplica]:
        eligible = self.eligible(replicas)
        if not eligible:
            return []
        return sorted(
            eligible,
            key=lambda r: (
                _score(getattr(r.node, "latency_score", None), float("inf")),
                _score(getattr(r.node, "load_score", None), float("inf")),
                -_score(getattr(r.node, "capability_score", None), float("-inf")),
            ),
        )

    def choose(self, replicas: list[DatasetReplica]) -> DatasetReplica:
        ranked = self.rank(replicas)
        if not ranked:
            raise ValueError("No eligible replicas available")
        return ranked[0]
