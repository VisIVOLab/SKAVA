from abc import ABC, abstractmethod

from app.models.replica import DatasetReplica


class RankingPolicy(ABC):
    @abstractmethod
    def choose(self, replicas: list[DatasetReplica]) -> DatasetReplica:
        raise NotImplementedError
