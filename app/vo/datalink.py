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
            title="Preview (none)",
            description="No preview link is published here; a VisIVO backend next to the data can render previews once the dataset is opened there.",
        ),
        LinkDescriptor(
            rel="metadata",
            href=None,
            content_type="application/json",
            title="Metadata (none)",
            description="No separate metadata document: the metadata is served by /discovery/dataset/{obs_id}.",
        ),
        LinkDescriptor(
            rel="datalink",
            href=self_url,
            content_type="application/json",
            title="This DataLink document",
            description="This document as JSON; RESPONSEFORMAT=votable gives the IVOA DataLink VOTable.",
        ),
        LinkDescriptor(
            rel="soda-sync",
            href=f"{settings.public_base_url.rstrip('/')}/soda/sync",
            content_type="application/json",
            title="SODA sync endpoint",
            description="SODA sync: redirected (303) to the first ranked node that can cut the dataset in place; without one, validated here and answered with the routing.",
        ),
        # No soda-async link: SKAVA runs no jobs itself, asynchronous SODA is
        # the node's service, advertised by the node descriptors below; a
        # link a client can follow must not lead to a 404.
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
    soda_execution_available: bool = False,
    node_soda=None,
    dataproduct_type: str | None = None,
) -> list[ServiceDescriptor]:
    """Build the service_descriptors[] array for the DataLink response.

    The first descriptors are the always-present capability descriptors
    (access resolution, SKAVA's SODA sync redirect, the disabled SKAVA
    soda-async entry, the cutout entry). Per-node ``visivo-backend`` descriptors are appended
    when any of the supplied ``nodes`` has its ``visivo_backend_url``
    populated. The desktop client uses those entries to route compute
    requests to the SRC's local backend instead of downloading the file.

    See docs/distributed-backend-design.md (VisIVO Visual Analytics repository) for the design.
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
            description=("Redirects a SODA request (HTTP 303) to the SODA service of the first "
                         "ranked node that can cut the dataset in place, which validates and cuts it."
                         if node_soda is not None else
                         "Validates a SODA request and answers with its routing; no node can "
                         "process this dataset in place."),
        ),
        ServiceDescriptor(
            service_type="soda-async",
            service_id="skava-soda-async",
            access_url=f"{base_url}/soda/async",
            standard_id="ivo://ivoa.net/std/SODA#async-1.0",
            supported_parameters=["ID", "POS", "BAND", "TIME"],
            enabled=False,
            description=("SKAVA runs no jobs itself: asynchronous SODA is the node's service "
                         "(node-soda-async)."),
        ),
        ServiceDescriptor(
            service_type="cutout",
            service_id="skava-cutout",
            access_url=f"{base_url}/soda/execute",
            # Not a SODA endpoint (POST, query parameters, JSON fallback): the
            # standard service is the node's own, advertised below.
            standard_id=None,
            supported_parameters=["ID", "POS", "BAND", "TIME"],
            enabled=soda_execution_available,
            description=(
                "SKAVA's proxy to the node's cutout (POST); standard clients use node-soda-sync."
                if soda_execution_available
                else "Cutout/subset execution requires a node with a co-located "
                "VisIVO backend serving a file:// replica."
            ),
        ),
    ]

    # The SODA service of the node that holds the selected replica: the file
    # is processed where it is, and only the subset or product travels.
    if node_soda is not None:
        node = node_soda.node
        soda = node.visivo_backend_url.rstrip("/") + "/soda"
        common = dict(node_code=node.code, requires_auth=bool(node.visivo_backend_requires_auth),
                      enabled=node.is_enabled and node.is_available)
        fixed = {"ID": node_soda.access_endpoint}
        descriptors += [
            ServiceDescriptor(
                service_type="node-soda-sync", service_id=f"soda-sync-{node.code.lower()}",
                access_url=f"{soda}/sync", standard_id="ivo://ivoa.net/std/SODA#sync-1.0",
                supported_parameters=["ID", "POS", "CIRCLE", "POLYGON", "BAND", "TIME", "RESPONSEFORMAT"],
                description=f"SODA cutout on node {node.code}, next to the data.",
                input_params=fixed, **common),
            ServiceDescriptor(
                service_type="node-soda-async", service_id=f"soda-async-{node.code.lower()}",
                access_url=f"{soda}/async", standard_id="ivo://ivoa.net/std/SODA#async-1.0",
                supported_parameters=["ID", "POS", "CIRCLE", "POLYGON", "BAND", "TIME", "RESPONSEFORMAT"],
                description=f"SODA cutout as an asynchronous (UWS) job on node {node.code}.",
                input_params=fixed, **common),
            ServiceDescriptor(
                service_type="visivo-moment", service_id=f"moment-{node.code.lower()}",
                access_url=f"{soda}/async", standard_id="ivo://ivoa.net/std/SODA#async-1.0",
                supported_parameters=["ID", "OPERATION", "MOMENT", "CHANNELS", "THRESHOLD"],
                description=f"Moment map computed on node {node.code} (SODA async job, OPERATION=MOMENT).",
                input_params={**fixed, "OPERATION": "MOMENT"}, **common),
            ServiceDescriptor(
                service_type="visivo-pv", service_id=f"pv-{node.code.lower()}",
                access_url=f"{soda}/async", standard_id="ivo://ivoa.net/std/SODA#async-1.0",
                supported_parameters=["ID", "OPERATION", "PVPATH", "PVWIDTH"],
                description=(f"Position-velocity diagram computed on node {node.code} "
                             "(SODA async job, OPERATION=PV)."),
                input_params={**fixed, "OPERATION": "PV"}, **common),
        ]
        # Moments and PV diagrams need a spectral axis: only a cube gets them.
        if (dataproduct_type or "").strip().lower() != "cube":
            descriptors = [d for d in descriptors if d.service_type not in ("visivo-moment", "visivo-pv")]

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


def build_capabilities(soda_execution_available: bool = False,
                       node_soda_available: bool = False) -> CapabilitiesDescriptor:
    """Build the DataLink capability flags for a dataset.

    ``soda_execution_available`` is True when at least one ranked node for
    the dataset exposes a co-located VisIVO backend, i.e. ``/soda/execute``
    can compute a real byte-level cutout instead of a staging handoff. When
    no such node exists the flags stay False (capability-honest: the SODA
    endpoint is declared, but execution is not available for this dataset).
    """
    return CapabilitiesDescriptor(
        supports_datalink=True,
        supports_soda_sync=soda_execution_available,
        supports_soda_async=node_soda_available,
        supports_cutout=soda_execution_available,
        supports_preview=False,
        supports_soda_sync_endpoint=True,
        supports_soda_sync_execution=soda_execution_available,
        supports_soda_async_endpoint=node_soda_available,
        supports_soda_async_execution=node_soda_available,
    )
