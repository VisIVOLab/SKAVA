from pydantic import BaseModel


class NodeReplica(BaseModel):
    code: str
    name: str
    is_enabled: bool
    is_available: bool
    latency_score: float | None = None
    load_score: float | None = None
    capability_score: float | None = None
    access_endpoint: str


class DatalinkDescriptor(BaseModel):
    service: str
    standard_hint: str
    operations: list[str]
    # TODO: add richer DataLink fields and ID semantics when a standard DataLink service is implemented.


class DatasetMetadata(BaseModel):
    obs_id: str
    obs_collection: str | None = None
    obs_title: str | None = None
    dataproduct_type: str | None = None
    calib_level: int | None = None
    target_name: str | None = None
    facility_name: str | None = None
    instrument_name: str | None = None
    s_ra: float | None = None
    s_dec: float | None = None
    s_fov: float | None = None
    t_min: float | None = None
    t_max: float | None = None
    em_min: float | None = None
    em_max: float | None = None
