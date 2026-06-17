from pydantic import BaseModel

from app.schemas.datalink import (
    CapabilitiesDescriptor,
    DataLinkResponse,
    DatasetDescriptor,
    LinkDescriptor,
    PrimaryAccessDescriptor,
    RoutingDescriptor,
    ServiceDescriptor,
)


class AccessResponse(BaseModel):
    # Legacy fields preserved for existing clients.
    obs_id: str
    best_node: str
    access_url: str
    access_mode: str
    supported_operations: list[str]
    supports_soda: bool
    supports_datalink: bool

    # DataLink-like JSON envelope for future VO-compliant evolution.
    dataset: DatasetDescriptor
    routing: RoutingDescriptor
    primary_access: PrimaryAccessDescriptor
    links: list[LinkDescriptor]
    service_descriptors: list[ServiceDescriptor]
    capabilities: CapabilitiesDescriptor
    datalink: DataLinkResponse | None = None
