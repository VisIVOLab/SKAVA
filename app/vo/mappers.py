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
    )


def to_node_replica(replica: DatasetReplica) -> NodeReplica:
    return NodeReplica(
        code=replica.node.code,
        name=replica.node.name,
        is_enabled=replica.node.is_enabled,
        is_available=replica.node.is_available,
        latency_score=replica.node.latency_score,
        load_score=replica.node.load_score,
        capability_score=replica.node.capability_score,
        access_endpoint=replica.access_endpoint,
    )


def build_access_url(obs_id: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/access/{obs_id}"


def build_datalink_url(obs_id: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/datalink/{obs_id}"


def build_datalink_descriptor(access_url: str) -> DatalinkDescriptor:
    return DatalinkDescriptor(
        service=access_url,
        standard_hint="DataLink/SODA precursor",
        operations=["download", "cutout:TBD", "band_subset:TBD", "time_subset:TBD"],
    )
