from sqlalchemy.orm import Session

from app.schemas.access import AccessResponse
from app.services.datalink_service import DataLinkService


class AccessService:
    def __init__(self, db: Session):
        self.db = db

    def resolve(self, obs_id: str) -> AccessResponse | None:
        datalink = DataLinkService(self.db).resolve(obs_id)
        if not datalink:
            return None

        return AccessResponse(
            obs_id=obs_id,
            best_node=datalink.routing.best_node,
            access_url=datalink.primary_access.access_url,
            access_mode="remote-routing",
            supported_operations=["download", "cutout:TBD", "band_subset:TBD", "time_subset:TBD"],
            supports_soda=True,
            supports_datalink=datalink.capabilities.supports_datalink,
            dataset=datalink.dataset,
            routing=datalink.routing,
            primary_access=datalink.primary_access,
            links=datalink.links,
            service_descriptors=datalink.service_descriptors,
            capabilities=datalink.capabilities,
            datalink=datalink,
        )
