from pydantic import BaseModel

from app.schemas.common import NodeReplica


class DatasetDescriptor(BaseModel):
    obs_id: str
    obs_collection: str | None = None
    dataproduct_type: str | None = None


class RoutingDescriptor(BaseModel):
    best_node: str
    replicas: list[NodeReplica]


class PrimaryAccessDescriptor(BaseModel):
    access_url: str
    access_format: str | None = None
    access_estsize: int | None = None


class LinkDescriptor(BaseModel):
    rel: str
    href: str | None = None
    content_type: str | None = None
    title: str
    description: str | None = None
    node_id: str | None = None


class ServiceDescriptor(BaseModel):
    service_type: str
    service_id: str
    access_url: str
    standard_id: str | None = None
    supported_parameters: list[str]
    enabled: bool
    description: str


class CapabilitiesDescriptor(BaseModel):
    supports_datalink: bool
    supports_soda_sync: bool
    supports_soda_async: bool
    supports_cutout: bool
    supports_preview: bool
    supports_soda_sync_endpoint: bool
    supports_soda_sync_execution: bool
    supports_soda_async_endpoint: bool
    supports_soda_async_execution: bool


class DataLinkResponse(BaseModel):
    dataset: DatasetDescriptor
    routing: RoutingDescriptor
    primary_access: PrimaryAccessDescriptor
    links: list[LinkDescriptor]
    service_descriptors: list[ServiceDescriptor]
    capabilities: CapabilitiesDescriptor
