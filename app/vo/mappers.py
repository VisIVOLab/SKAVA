from app.config import settings
from app.models.dataset import Dataset
from app.models.replica import DatasetReplica
from app.schemas.common import DatalinkDescriptor, DatasetMetadata, NodeReplica


def to_dataset_metadata(dataset: Dataset) -> DatasetMetadata:
    return DatasetMetadata(
        obs_id=dataset.obs_id,
        obs_collection=dataset.obs_collection,
        obs_title=dataset.obs_title,
        dataproduct_type=dataset.dataproduct_type,
        calib_level=dataset.calib_level,
        target_name=dataset.target_name,
        facility_name=dataset.facility_name,
        instrument_name=dataset.instrument_name,
        s_ra=dataset.s_ra,
        s_dec=dataset.s_dec,
        s_fov=dataset.s_fov,
        t_min=dataset.t_min,
        t_max=dataset.t_max,
        em_min=dataset.em_min,
        em_max=dataset.em_max,
        spatial_index_order=dataset.spatial_index_order,
        spatial_index_cell=dataset.spatial_index_cell,
        doi=dataset.doi,
        pid=dataset.pid,
        citation=dataset.citation,
        license=dataset.license,
    )


def to_node_replica(replica: DatasetReplica, decision=None) -> NodeReplica:
    """``decision``: the policy's RankedReplica for it, when there is one."""
    return NodeReplica(
        code=replica.node.code,
        name=replica.node.name,
        is_enabled=replica.node.is_enabled,
        is_available=replica.node.is_available,
        latency_score=replica.node.latency_score,
        load_score=replica.node.load_score,
        capability_score=replica.node.capability_score,
        access_endpoint=replica.access_endpoint,
        rank_reason=decision.reason if decision is not None else None,
        score=decision.score if decision is not None else None,
        telemetry_age_s=(round(decision.telemetry_age_s, 1)
                         if decision is not None and decision.telemetry_age_s is not None else None),
    )


def build_access_url(obs_id: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/access/{obs_id}"


def build_datalink_url(obs_id: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/datalink/{obs_id}"


def soda_cutout_available(ranked_replicas) -> bool:
    """Whether /soda/execute can really cut this dataset: some ranked replica
    is a file:// copy on a node that runs a co-located VisIVO backend. The one
    rule shared by DataLink, /access and discovery, and the same condition
    SodaExecutionService delegates on — otherwise it only records a staging job."""
    return any(
        getattr(rep.node, "visivo_backend_url", None)
        and (rep.access_endpoint or "").startswith("file://")
        for rep in ranked_replicas
    )


def node_soda_target(ranked_replicas):
    """The replica a node can process in place, and its node: the first, in
    ranking order, that is a file:// copy on a node running a VisIVO backend
    (the rule of soda_cutout_available). None when there is none."""
    for rep in ranked_replicas:
        if getattr(rep.node, "visivo_backend_url", None) and (rep.access_endpoint or "").startswith("file://"):
            return rep
    return None


def supported_operations(cutout_available: bool) -> list[str]:
    """Operations this deployment can perform on a dataset — never placeholders."""
    ops = ["download"]
    if cutout_available:
        # Spatial (POS) and spectral (BAND) only: the node's cutout engine
        # accepts TIME but does not slice in time, so a time subset is not
        # offered until it does.
        ops += ["cutout", "band_subset"]
    return ops


def build_datalink_descriptor(access_url: str, cutout_available: bool = False) -> DatalinkDescriptor:
    return DatalinkDescriptor(
        service=access_url,
        standard_hint="DataLink/SODA precursor",
        operations=supported_operations(cutout_available),
    )
