# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel

from app.schemas.common import DatalinkDescriptor, DatasetMetadata, NodeReplica


class DiscoveryResult(BaseModel):
    metadata: DatasetMetadata
    replicas: list[NodeReplica]
    best_node: str
    access_url: str
    datalink_descriptor: DatalinkDescriptor | None = None


class DiscoverySearchResponse(BaseModel):
    results: list[DiscoveryResult]
    total: int
    limit: int
    offset: int
    returned: int
