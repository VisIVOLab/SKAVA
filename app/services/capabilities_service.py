from app.schemas.system import CapabilitiesResponse, CapabilityInterface, CapabilityStandard


# VOSI-inspired JSON capabilities for the production VO-aligned service.
def get_capabilities() -> CapabilitiesResponse:
    return CapabilitiesResponse(
        service="SKAVA Data Discovery and Access",
        profile="VO-aligned Production Service",
        version="0.2.0",
        vosi={"availability": "/availability", "capabilities": "/capabilities"},
        interfaces=[
            CapabilityInterface(
                name="availability",
                path="/availability",
                method="GET",
                description="Service availability with DB checks and optional node summary.",
                params=["include_nodes"],
            ),
            CapabilityInterface(
                name="db_health",
                path="/health/db",
                method="GET",
                description="Database reachability check.",
                params=[],
            ),
            CapabilityInterface(
                name="metrics",
                path="/metrics",
                method="GET",
                description="Prometheus metrics endpoint.",
                params=[],
            ),
            CapabilityInterface(
                name="discovery_search",
                path="/discovery/search",
                method="GET",
                description="ObsCore-inspired discovery endpoint.",
                params=["POS", "BAND", "TIME", "COLLECTION", "DPTYPE", "obs_id"],
            ),
            CapabilityInterface(
                name="discovery_dataset",
                path="/discovery/dataset/{obs_id}",
                method="GET",
                description="Retrieve metadata, available replicas and best node for one observation.",
                params=["obs_id"],
            ),
            CapabilityInterface(
                name="datalink_descriptor",
                path="/datalink/{obs_id}",
                method="GET",
                description="Canonical DataLink-like JSON descriptor endpoint.",
                params=["obs_id"],
            ),
            CapabilityInterface(
                name="soda_sync",
                path="/soda/sync",
                method="GET",
                description="SODA sync stub endpoint: validates subset requests and resolves routing, without executing server-side subsetting yet.",
                params=["ID", "POS", "BAND", "TIME", "RESPONSEFORMAT"],
            ),
            CapabilityInterface(
                name="access_compatibility",
                path="/access/{obs_id}",
                method="GET",
                description="Compatibility facade over /datalink/{obs_id} preserving legacy access contract.",
                params=["obs_id"],
            ),
        ],
        standards=[
            CapabilityStandard(name="ObsCore", ivoa_id="ivo://ivoa.net/std/ObsCore", support_level="aligned"),
            CapabilityStandard(name="DataLink", ivoa_id="ivo://ivoa.net/std/DataLink", support_level="precursor"),
            CapabilityStandard(name="SODA", ivoa_id="ivo://ivoa.net/std/SODA", support_level="precursor"),
            CapabilityStandard(name="TAP/ObsTAP", ivoa_id="ivo://ivoa.net/std/TAP", support_level="planned"),
        ],
        compliance_note="Production VO-aligned service. ObsCore discovery and access routing are operational; full TAP/DataLink/SODA standard server compliance is not claimed.",
    )
