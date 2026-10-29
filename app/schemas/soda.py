# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel

from app.schemas.common import NodeReplica
from app.schemas.datalink import DatasetDescriptor


class SodaRoutingDescriptor(BaseModel):
    best_node: str
    access_url: str
    replicas: list[NodeReplica]


class SodaRequestDescriptor(BaseModel):
    ID: str
    POS: str | None = None
    BAND: str | None = None
    TIME: str | None = None
    RESPONSEFORMAT: str | None = None


class SodaOperationDescriptor(BaseModel):
    type: str
    supports_execution: bool
    message: str


class SodaNextStepDescriptor(BaseModel):
    planned_backend: str
    datalink: str


class SodaSyncResponse(BaseModel):
    status: str
    mode: str
    dataset: DatasetDescriptor
    routing: SodaRoutingDescriptor
    request: SodaRequestDescriptor
    operation: SodaOperationDescriptor
    next_step: SodaNextStepDescriptor

