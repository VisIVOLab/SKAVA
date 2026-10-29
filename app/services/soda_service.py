# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from app.schemas.soda import (
    SodaNextStepDescriptor,
    SodaOperationDescriptor,
    SodaRequestDescriptor,
    SodaRoutingDescriptor,
    SodaSyncResponse,
)
from app.services.datalink_service import DataLinkService
from app.vo.mappers import build_datalink_url
from app.vo.query_params import CirclePos, NumericInterval
from app.vo.soda import normalize_interval, normalize_pos


class SodaService:
    def __init__(self, datalink_service: DataLinkService):
        self.datalink_service = datalink_service

    def resolve_sync_stub(
        self,
        *,
        dataset_id: str,
        pos: CirclePos | None,
        band: NumericInterval | None,
        time_value: NumericInterval | None,
        responseformat: str | None,
    ) -> SodaSyncResponse | None:
        datalink = self.datalink_service.resolve(dataset_id)
        if not datalink:
            return None

        return SodaSyncResponse(
            status="accepted",
            mode="soda-sync-stub",
            dataset=datalink.dataset,
            routing=SodaRoutingDescriptor(
                best_node=datalink.routing.best_node,
                access_url=datalink.primary_access.access_url,
                replicas=datalink.routing.replicas,
            ),
            request=SodaRequestDescriptor(
                ID=dataset_id,
                POS=normalize_pos(pos),
                BAND=normalize_interval(band),
                TIME=normalize_interval(time_value),
                RESPONSEFORMAT=responseformat,
            ),
            operation=SodaOperationDescriptor(
                type="subset",
                supports_execution=False,
                message=("No node can cut this dataset in place: the request was validated and the routing "
                         "resolved, but no subset was made."),
            ),
            next_step=SodaNextStepDescriptor(
                planned_backend=("the SODA service of a node with a VisIVO backend holding a file:// replica; "
                                 "none is registered for this dataset"),
                datalink=build_datalink_url(dataset_id),
            ),
        )

