from pydantic import BaseModel

from app.schemas.common import DatalinkDescriptor, DatasetMetadata, NodeReplica


class DiscoveryResult(BaseModel):
    metadata: DatasetMetadata
    replicas: list[NodeReplica]
    best_node: str
    access_url: str
    datalink_descriptor: DatalinkDescriptor | None = None


class DiscoverySearchResponse(BaseModel):
    results: list[DiscoveryResult]
