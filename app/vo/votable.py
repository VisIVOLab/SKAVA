from html import escape

from app.config import settings
from app.schemas.datalink import DataLinkResponse
from app.schemas.discovery import DiscoveryResult

VOTABLE_MEDIA_TYPE = "application/x-votable+xml"

# IVOA DataLink semantics vocabulary terms (http://www.ivoa.net/rdf/datalink/core).
# Map SKAVA's internal link ``rel`` values onto the standard #-prefixed terms
# so the VOTable is consumable by pyvo / TOPCAT as a real DataLink document.
# Path, under a co-located VisIVO backend's base URL, of the document the
# DataLink row for that backend points at (status, workers, capacity; JSON).
VISIVO_BACKEND_STATUS_PATH = "/v1/health"

_SEMANTICS_BY_REL = {
    "self": "#this",
    "direct-download": "#this",
    "alternate-replica": "#this",
    "preview": "#preview",
    "metadata": "#auxiliary",
    "datalink": "#this",
    "soda-sync": "#cutout",
    "soda-async": "#cutout",
}

# The service descriptor RESOURCE id referenced by the {links} service_def
# column for the SODA cutout operation.
_CUTOUT_SERVICE_ID = "skava_soda_cutout"
_PRIMARY_ID_REF = "primaryID"


def _cell(value: object | None) -> str:
    return f"<TD>{escape(str(value)) if value is not None else ''}</TD>"


def _attr(value: object | None) -> str:
    return escape(str(value)) if value is not None else ""


def _field(name: str, datatype: str) -> str:
    if datatype == "char":
        return f'<FIELD name="{name}" datatype="{datatype}" arraysize="*"/>'
    return f'<FIELD name="{name}" datatype="{datatype}"/>'


# Standard IVOA DataLink {links} response columns, in canonical order, with
# the UCDs/datatypes mandated by the DataLink 1.x specification. ``node_id``
# is a SKAVA extension carried after the standard columns (clients that only
# understand the standard shape ignore trailing FIELDs).
_DATALINK_FIELDS = [
    ('ID', 'char', 'meta.id;meta.main', None),
    ('access_url', 'char', 'meta.ref.url', None),
    ('service_def', 'char', 'meta.ref', None),
    ('error_message', 'char', 'meta.code.error', None),
    ('semantics', 'char', 'meta.code', None),
    ('description', 'char', 'meta.note', None),
    ('content_type', 'char', 'meta.code.mime', None),
    ('content_length', 'long', 'phys.size;meta.file', 'byte'),
    ('node_id', 'char', 'meta.id', None),
]


def _datalink_field(name: str, datatype: str, ucd: str, unit: str | None) -> str:
    arraysize = ' arraysize="*"' if datatype == 'char' else ''
    unit_attr = f' unit="{unit}"' if unit else ''
    return (
        f'<FIELD name="{name}" datatype="{datatype}"{arraysize}'
        f' ucd="{ucd}"{unit_attr}/>'
    )


def _datalink_row(
    *, oid, access_url, service_def, semantics, description, content_type,
    content_length, node_id,
) -> str:
    return (
        "<TR>"
        + _cell(oid)
        + _cell(access_url)
        + _cell(service_def)
        + _cell(None)  # error_message — empty on success rows
        + _cell(semantics)
        + _cell(description)
        + _cell(content_type)
        + _cell(content_length)
        + _cell(node_id)
        + "</TR>"
    )


def datalink_to_votable(datalink: DataLinkResponse) -> str:
    """Serialise a DataLink response as a conformant IVOA DataLink VOTable.

    Emits the standard ``{links}`` results table plus a service-descriptor
    RESOURCE (``utype="adhoc:service"``) for the SODA cutout operation, so
    tools like pyvo/TOPCAT can invoke ``/soda/execute`` with POS/BAND/TIME
    against this dataset.
    """
    oid = datalink.dataset.obs_id
    rows: list[str] = []

    # One {links} row per access link (download / preview / alternates).
    for link in datalink.links:
        if not link.href:
            continue
        # The SODA sync stub validates a request and answers with routing
        # JSON, not data: in a VOTable a "#cutout" row means "this returns the
        # cutout", so the stub stays in the JSON envelope only. The real
        # cutout is the service-descriptor row below.
        if link.rel in ("soda-sync", "soda-async"):
            continue
        semantics = _SEMANTICS_BY_REL.get(link.rel, "#this")
        content_length = (
            datalink.primary_access.access_estsize
            if link.rel == "direct-download"
            else None
        )
        rows.append(
            _datalink_row(
                oid=oid,
                access_url=link.href,
                service_def=None,
                semantics=semantics,
                description=link.description,
                content_type=link.content_type,
                content_length=content_length,
                node_id=link.node_id,
            )
        )

    # One row per VisIVO compute backend co-located with a replica, best node
    # first (the same order as the JSON service_descriptors), so VO clients
    # see where the dataset can be analysed in place. A DataLink access_url
    # must be a retrievable resource and content_type its real format: the
    # row points at the backend's health/capacity document (JSON), not at the
    # API root, which serves nothing. "#auxiliary" is the standard term for a
    # related resource; node_id says which node.
    for desc in datalink.service_descriptors:
        if desc.service_type != "visivo-backend" or not desc.enabled or not desc.endpoint:
            continue
        auth = " (requires the node backend's token)" if desc.requires_auth else ""
        rows.append(
            _datalink_row(
                oid=oid,
                access_url=f"{desc.endpoint.rstrip('/')}{VISIVO_BACKEND_STATUS_PATH}",
                service_def=None,
                semantics="#auxiliary",
                description=f"VisIVO compute backend co-located with node {desc.node_code}: "
                            f"status and capacity{auth}",
                content_type="application/json",
                content_length=None,
                node_id=desc.node_code,
            )
        )

    # The SODA cutout row and its service RESOURCE only when a cutout can
    # actually run for this dataset (a node with a VisIVO backend serving a
    # file:// replica): advertising an operation that 502s helps nobody.
    cutout = bool(datalink.capabilities.supports_cutout)
    if cutout:
        rows.append(
            _datalink_row(
                oid=oid,
                access_url=None,
                service_def=_CUTOUT_SERVICE_ID,
                semantics="#cutout",
                description="Server-side SODA cutout (compute-next-to-data).",
                content_type="application/fits",
                content_length=None,
                node_id=None,
            )
        )

    field_xml = "\n      ".join(
        _datalink_field(name, dt, ucd, unit) for name, dt, ucd, unit in _DATALINK_FIELDS
    )
    row_xml = "\n          ".join(rows)
    base_url = settings.public_base_url.rstrip("/")
    cutout_resource = _cutout_service_resource(base_url) if cutout else ""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.4">
  <RESOURCE type="results">
    <INFO name="QUERY_STATUS" value="OK"/>
    <TABLE name="datalink">
      <PARAM name="ID" datatype="char" arraysize="*" value="{_attr(oid)}" ID="{_PRIMARY_ID_REF}"/>
      {field_xml}
      <DATA>
        <TABLEDATA>
          {row_xml}
        </TABLEDATA>
      </DATA>
    </TABLE>
  </RESOURCE>{cutout_resource}
</VOTABLE>
"""


def _cutout_service_resource(base_url: str) -> str:
    return f"""
  <RESOURCE type="meta" ID="{_CUTOUT_SERVICE_ID}" utype="adhoc:service">
    <PARAM name="standardID" datatype="char" arraysize="*" value="ivo://ivoa.net/std/SODA#sync-1.0"/>
    <PARAM name="accessURL" datatype="char" arraysize="*" value="{base_url}/soda/execute"/>
    <GROUP name="inputParams">
      <PARAM name="ID" datatype="char" arraysize="*" ref="{_PRIMARY_ID_REF}" value=""/>
      <PARAM name="POS" datatype="char" arraysize="*" value="" ucd="phys.angArea;obs"/>
      <PARAM name="BAND" datatype="char" arraysize="*" value="" ucd="em.wl"/>
      <PARAM name="TIME" datatype="char" arraysize="*" value="" ucd="time.interval"/>
    </GROUP>
  </RESOURCE>"""


def discovery_results_to_votable(results: list[DiscoveryResult]) -> str:
    fields = [
        ("obs_id", "char"),
        ("obs_collection", "char"),
        ("dataproduct_type", "char"),
        ("s_ra", "double"),
        ("s_dec", "double"),
        ("t_min", "double"),
        ("t_max", "double"),
        ("em_min", "double"),
        ("em_max", "double"),
        ("access_url", "char"),
    ]
    rows = []
    for result in results:
        metadata = result.metadata
        rows.append(
            "<TR>"
            + "".join(
                [
                    _cell(metadata.obs_id),
                    _cell(metadata.obs_collection),
                    _cell(metadata.dataproduct_type),
                    _cell(metadata.s_ra),
                    _cell(metadata.s_dec),
                    _cell(metadata.t_min),
                    _cell(metadata.t_max),
                    _cell(metadata.em_min),
                    _cell(metadata.em_max),
                    _cell(result.access_url),
                ]
            )
            + "</TR>"
        )

    field_xml = "\n".join(_field(name, datatype) for name, datatype in fields)
    row_xml = "\n".join(rows)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.4">
  <RESOURCE type="results">
    <INFO name="QUERY_STATUS" value="OK"/>
    <TABLE name="ivoa.ObsCore">
      {field_xml}
      <DATA>
        <TABLEDATA>
          {row_xml}
        </TABLEDATA>
      </DATA>
    </TABLE>
  </RESOURCE>
</VOTABLE>
"""
