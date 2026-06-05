from app.config import settings
from app.models.dataset import Dataset
from app.models.node import Node
from app.models.replica import DatasetReplica
from app.schemas.datalink import CapabilitiesDescriptor, LinkDescriptor, ServiceDescriptor


def build_access_links(
    dataset: Dataset,
    selected: DatasetReplica,
    ranked_replicas: list[DatasetReplica],
    self_url: str,
) -> list[LinkDescriptor]:
    links: list[LinkDescriptor] = [
        LinkDescriptor(
            rel="self",
            href=self_url,
            content_type="application/json",
            title="Access descriptor",
            description="DataLink-like JSON descriptor for this dataset.",
        ),
        LinkDescriptor(
            rel="direct-download",
            href=selected.access_endpoint,
            content_type=dataset.access_format or "application/octet-stream",
            title="Primary direct download",
            description="Direct remote access endpoint for the selected node.",
            node_id=selected.node.code,
        ),
        LinkDescriptor(
            rel="preview",
            href=None,
            content_type="image/png",
            title="Preview placeholder",
            description="Preview service not yet implemented.",
        ),
        LinkDescriptor(
            rel="metadata",
            href=None,
            content_type="application/json",
            title="Metadata placeholder",
            description="Dedicated metadata endpoint not yet implemented.",
        ),
        LinkDescriptor(
            rel="datalink",
            href=self_url,
            content_type="application/json",
            title="DataLink-like entrypoint",
            description="Current JSON precursor; future DataLink serialization can map here.",
        ),
        LinkDescriptor(
            rel="soda-sync",
            href=f"{settings.public_base_url.rstrip('/')}/soda/sync",
            content_type="application/json",
            title="SODA sync endpoint",
            description="SODA sync stub endpoint with request validation and routing orchestration.",
        ),
        LinkDescriptor(
            rel="soda-async",
            href=f"{settings.public_base_url.rstrip('/')}/soda/async",
            content_type="application/json",
            title="SODA async placeholder",
            description="SODA async endpoint placeholder.",
        ),
    ]

    for replica in ranked_replicas:
        if replica.id == selected.id:
            continue
        links.append(
            LinkDescriptor(
                rel="alternate-replica",
                href=replica.access_endpoint,
                content_type=dataset.access_format or "application/octet-stream",
                title=f"Alternate replica on node {replica.node.code}",
                description="Alternate remote replica endpoint.",
                node_id=replica.node.code,
            )
        )

    return links


def build_service_descriptors(
    obs_id: str,
    nodes: list[Node] | None = None,
) -> list[ServiceDescriptor]:
    """Build the service_descriptors[] array for the DataLink response.

    The first descriptors are the always-present capability descriptors
    (access-resolution, soda-sync stub, soda-async placeholder, cutout
    placeholder). Per-node ``visivo-backend`` descriptors are appended
    when any of the supplied ``nodes`` has its ``visivo_backend_url``
    populated. The desktop client uses those entries to route compute
    requests to the SRC's local backend instead of downloading the file.

    See docs/distributed-backend-design.md §7 for the full design.
    """
    base_url = settings.public_base_url.rstrip("/")
    descriptors: list[ServiceDescriptor] = [
        ServiceDescriptor(
            service_type="access-resolution",
            service_id="skava-access-resolution",
            access_url=f"{base_url}/datalink/{obs_id}",
            standard_id="ivo://ivoa.net/std/DataLink#links-1.1",
            supported_parameters=["ID"],
            enabled=True,
            description="Dataset access resolution endpoint returning DataLink-like JSON.",
        ),
        ServiceDescriptor(
            service_type="soda-sync",
            service_id="skava-soda-sync",
            access_url=f"{base_url}/soda/sync",
            standard_id="ivo://ivoa.net/std/SODA#sync-1.0",
            supported_parameters=["ID", "POS", "BAND", "TIME", "RESPONSEFORMAT"],
            enabled=True,
            description="Operational SODA sync stub endpoint (validation/orchestration only, no server-side subsetting execution yet).",
        ),
        ServiceDescriptor(
            service_type="soda-async",
            service_id="skava-soda-async",
            access_url=f"{base_url}/soda/async",
            standard_id="ivo://ivoa.net/std/SODA#async-1.0",
            supported_parameters=["ID", "POS", "BAND", "TIME"],
            enabled=False,
            description="Planned asynchronous SODA subset service.",
        ),
        ServiceDescriptor(
            service_type="cutout",
            service_id="skava-cutout",
            access_url=f"{base_url}/soda/sync",
            standard_id="ivo://ivoa.net/std/SODA#sync-1.0",
            supported_parameters=["ID", "POS", "BAND", "TIME"],
            enabled=False,
            description="Future cutout/subset operations placeholder.",
        ),
    ]

    # Per-node VisIVO backend descriptors (distributed-backend pattern).
    for node in (nodes or []):
        if not node.visivo_backend_url:
            continue
        descriptors.append(ServiceDescriptor(
            service_type="visivo-backend",
            service_id=f"visivo-backend-{node.code.lower()}",
            access_url=node.visivo_backend_url,
            standard_id=None,
            supported_parameters=["ID"],
            enabled=node.is_enabled and node.is_available,
            description=(
                f"VisIVO compute backend co-located with node {node.code} "
                f"({node.name}). Desktop clients can open datasets "
                "directly on the SRC without downloading the file."),
            endpoint=node.visivo_backend_url,
            node_code=node.code,
            requires_auth=bool(node.visivo_backend_requires_auth),
            supports_kinds=["image", "cube", "dynspec"],
        ))
    return descriptors


def build_capabilities() -> CapabilitiesDescriptor:
    return CapabilitiesDescriptor(
        supports_datalink=True,
        supports_soda_sync=False,
        supports_soda_async=False,
        supports_cutout=False,
        supports_preview=False,
        supports_soda_sync_endpoint=True,
        supports_soda_sync_execution=False,
        supports_soda_async_endpoint=False,
        supports_soda_async_execution=False,
    )
