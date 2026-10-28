from pydantic import BaseModel

from app.schemas.common import ExcludedReplica, NodeReplica


class DatasetDescriptor(BaseModel):
    obs_id: str
    obs_collection: str | None = None
    dataproduct_type: str | None = None


class RoutingDescriptor(BaseModel):
    best_node: str
    replicas: list[NodeReplica]
    # The ranking policy that decided ("static" or "resource_aware") and the
    # replicas it set aside, with why.
    policy: str | None = None
    excluded: list[ExcludedReplica] = []


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
    # ── Optional fields used by service-type-specific descriptors ────────
    # When ``service_type == "visivo-backend"`` (distributed VisIVO backend
    # at an SRC node), the desktop client reads ``endpoint`` and
    # ``node_code`` to match the entry against its known-backends registry,
    # and ``requires_auth`` to decide whether to forward its bearer token.
    # These extra fields are ignored by clients that consume the standard
    # ServiceDescriptor shape.
    endpoint: str | None = None
    node_code: str | None = None
    requires_auth: bool | None = None
    supports_kinds: list[str] | None = None
    # Parameters whose value is fixed for this dataset and descriptor: for a
    # node's SODA service the ``ID`` is the replica's own identifier on that
    # node, and an operation descriptor fixes ``OPERATION``.
    input_params: dict[str, str] | None = None


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
