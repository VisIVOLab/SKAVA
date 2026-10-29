# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
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
    # Why the ranking policy put this replica where it is, its cost under the
    # policy (lower is better; None for the static policy) and how old the node
    # telemetry it used was.
    rank_reason: str | None = None
    score: float | None = None
    telemetry_age_s: float | None = None


class ExcludedReplica(BaseModel):
    """A replica the policy set aside, with the reason."""

    code: str
    reason: str


class DatalinkDescriptor(BaseModel):
    service: str
    standard_hint: str
    operations: list[str]


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
    spatial_index_order: int | None = None
    spatial_index_cell: str | None = None
    # What tells two products under one obs_id apart (the federation's merge
    # and the ingestion's replica check compare them).
    access_estsize: int | None = None
    checksum: str | None = None
    doi: str | None = None
    pid: str | None = None
    citation: str | None = None
    license: str | None = None
