# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel


class DatabaseHealthResponse(BaseModel):
    status: str
    database: str


class AvailabilitySummary(BaseModel):
    total_nodes: int
    enabled_nodes: int
    available_nodes: int


class AvailabilityResponse(BaseModel):
    status: str
    service: str
    database: DatabaseHealthResponse
    nodes: AvailabilitySummary | None = None


class CapabilityInterface(BaseModel):
    name: str
    path: str
    method: str
    description: str
    params: list[str]


class CapabilityStandard(BaseModel):
    name: str
    ivoa_id: str
    support_level: str


class CapabilitiesResponse(BaseModel):
    service: str
    profile: str
    version: str
    vosi: dict[str, str]
    interfaces: list[CapabilityInterface]
    standards: list[CapabilityStandard]
    compliance_note: str
