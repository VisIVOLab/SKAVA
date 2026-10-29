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
VISIVO_BACKEND_STATUS_PATH = "/v1/node/status"

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

# The ID of the PARAM holding the dataset identifier in the {links} table.
_PRIMARY_ID_REF = "primaryID"


def _cell(value: object | None) -> str:
    return f"<TD>{escape(str(value)) if value is not None else ''}</TD>"


def _attr(value: object | None) -> str:
    # Attribute values are double-quoted: escape the quote too.
    return escape(str(value), {'"': "&quot;"}) if value is not None else ""


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
    # DataLink 1.1 §3.2.9-10, which the SRCNet DataLink also carries:
    # whether the link needs authentication ("false" | "optional" | "true")
    # and whether the caller of this response is authorized for it.
    ('link_auth', 'char', 'meta.code', None),
    ('link_authorized', 'boolean', 'meta.code', None),
    ('node_id', 'char', 'meta.id', None),
    # SKAVA's routing decision on the "#this" rows (the replicas, best node
    # first): why the policy ranked that replica where it is, and its cost
    # (lower is better). The JSON envelope carries the same in routing.replicas.
    ('rank_reason', 'char', 'meta.note', None),
    # A cost, not an ordinal rank: no UCD word says that.
    ('score', 'double', None, None),
]


def _datalink_field(name: str, datatype: str, ucd: str | None, unit: str | None) -> str:
    arraysize = ' arraysize="*"' if datatype == 'char' else ''
    ucd_attr = f' ucd="{ucd}"' if ucd else ''
    unit_attr = f' unit="{unit}"' if unit else ''
    return (
        f'<FIELD name="{name}" datatype="{datatype}"{arraysize}'
        f'{ucd_attr}{unit_attr}/>'
    )


def _datalink_row(
    *, oid, access_url, service_def, semantics, description, content_type,
    content_length, node_id, link_auth=None, link_authorized=None,
    rank_reason=None, score=None,
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
        + _cell(link_auth)
        + _cell(None if link_authorized is None else ("true" if link_authorized else "false"))
        + _cell(node_id)
        + _cell(rank_reason)
        + _cell(score)
        + "</TR>"
    )


def datalink_to_votable(datalink: DataLinkResponse, auth_required: bool = False) -> str:
    """Serialise a DataLink response as a conformant IVOA DataLink VOTable.

    Emits the standard ``{links}`` results table plus a service-descriptor
    RESOURCE (``utype="adhoc:service"``) for the SODA cutout operation, so
    tools like pyvo/TOPCAT can invoke ``/soda/execute`` with POS/BAND/TIME
    against this dataset.
    """
    oid = datalink.dataset.obs_id
    rows: list[str] = []
    base_url = settings.public_base_url.rstrip("/")
    # SKAVA's own links need what SKAVA itself requires; the caller passed that
    # check to get this response, so it is authorized for them. A replica on a
    # node's storage is the node's business: unknown here, left null.
    own_auth = "true" if auth_required else "false"

    def own(url: str | None) -> bool:
        return bool(url) and url.startswith(base_url)

    # The routing decision, by node: a replica's "#this" row carries it.
    ranked = {rep.code: rep for rep in datalink.routing.replicas}

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
        # "self" / "datalink" point back at this DataLink document (as JSON):
        # in a DataLink VOTable "#this" means the dataset itself, so a client
        # would take them for copies of the file.
        if link.rel in ("self", "datalink"):
            continue
        semantics = _SEMANTICS_BY_REL.get(link.rel, "#this")
        content_length = (
            datalink.primary_access.access_estsize
            if link.rel == "direct-download"
            else None
        )
        replica = ranked.get(link.node_id) if semantics == "#this" else None
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
                link_auth=own_auth if own(link.href) else None,
                link_authorized=True if own(link.href) else None,
                rank_reason=replica.rank_reason if replica else None,
                score=replica.score if replica else None,
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
        # The status document is public by default on a VisIVO backend and
        # accepts the backend's token: "optional" where the backend's API
        # requires one, so a client knows a token is in play for that node.
        rows.append(
            _datalink_row(
                oid=oid,
                access_url=f"{desc.endpoint.rstrip('/')}{VISIVO_BACKEND_STATUS_PATH}",
                service_def=None,
                semantics="#auxiliary",
                description=f"VisIVO compute backend co-located with node {desc.node_code}: "
                            "status and capacity",
                content_type="application/json",
                content_length=None,
                node_id=desc.node_code,
                link_auth="optional" if desc.requires_auth else "false",
            )
        )

    # The node's own SODA services (cutout sync and async) and the processing
    # operations it offers (moment, PV), each a row pointing at a service
    # descriptor RESOURCE: only when a node can process this dataset in place,
    # and with the node's own access rule (its backend's token, not SKAVA's).
    services = [d for d in datalink.service_descriptors
                if d.service_type in _NODE_SERVICES and d.enabled and d.input_params]
    for desc in services:
        rows.append(
            _datalink_row(
                oid=oid,
                access_url=None,
                service_def=desc.service_id,
                semantics=_NODE_SERVICES[desc.service_type],
                description=desc.description,
                content_type="application/fits",
                content_length=None,
                node_id=desc.node_code,
                link_auth="true" if desc.requires_auth else "false",
            )
        )

    field_xml = "\n      ".join(
        _datalink_field(name, dt, ucd, unit) for name, dt, ucd, unit in _DATALINK_FIELDS
    )
    row_xml = "\n          ".join(rows)
    service_resources = "".join(_service_resource(desc) for desc in services)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">
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
  </RESOURCE>{service_resources}
</VOTABLE>
"""


# Node services published as DataLink service descriptors, with the
# semantics of their rows: a SODA subset is "#cutout", a computed product
# (moment map, PV diagram) is "#proc".
_NODE_SERVICES = {
    "node-soda-sync": "#cutout",
    "node-soda-async": "#cutout",
    "visivo-moment": "#proc",
    "visivo-pv": "#proc",
}

# PARAM metadata of the service inputs: the SODA 1.0 parameters as the
# standard types them (so a VO client sends BAND as two doubles, not as the
# text of a tuple), and the custom operation inputs in the same style.
_PARAM_META = {
    "ID": {"datatype": "char", "arraysize": "*"},
    "POS": {"datatype": "char", "arraysize": "*", "ucd": "phys.angArea;obs"},
    "CIRCLE": {"datatype": "double", "arraysize": "3", "xtype": "circle", "unit": "deg",
               "ucd": "phys.angArea;obs"},
    "POLYGON": {"datatype": "double", "arraysize": "*", "xtype": "polygon", "unit": "deg",
                "ucd": "phys.angArea;obs"},
    "BAND": {"datatype": "double", "arraysize": "2", "xtype": "interval", "unit": "m",
             "ucd": "em.wl;stat.interval"},
    "TIME": {"datatype": "double", "arraysize": "2", "xtype": "interval", "unit": "d",
             "ucd": "time.interval;obs.exposure"},
    "OPERATION": {"datatype": "char", "arraysize": "*"},
    # Scalars carry arraysize="1": an empty scalar PARAM parses as a null
    # value, which VO clients cannot fill in; an empty one-element array does.
    "MOMENT": {"datatype": "int", "arraysize": "1"},
    "CHANNELS": {"datatype": "int", "arraysize": "2", "xtype": "interval"},
    "THRESHOLD": {"datatype": "double", "arraysize": "1"},
    "PVPATH": {"datatype": "double", "arraysize": "*", "unit": "deg"},
    "PVWIDTH": {"datatype": "int", "arraysize": "1"},
}


def _service_resource(desc) -> str:
    """A DataLink service descriptor RESOURCE for one node service.

    Fixed parameters (the replica's ID on that node, the OPERATION) carry their
    value; the others are left for the caller to fill. Element order follows
    the VOTable schema: DESCRIPTION first, then the PARAMs and the GROUP.
    """
    params = []
    for name in desc.supported_parameters:
        if name == "RESPONSEFORMAT":
            continue
        meta = _PARAM_META.get(name, {"datatype": "char", "arraysize": "*"})
        attrs = "".join(f' {key}="{_attr(value)}"' for key, value in meta.items())
        value = (desc.input_params or {}).get(name, "")
        params.append(f'<PARAM name="{name}"{attrs} value="{_attr(value)}"/>')
    standard = (f'\n    <PARAM name="standardID" datatype="char" arraysize="*" value="{_attr(desc.standard_id)}"/>'
                if desc.standard_id else "")
    inputs = "\n      ".join(params)
    return f"""
  <RESOURCE type="meta" ID="{_attr(desc.service_id)}" utype="adhoc:service">
    <DESCRIPTION>{escape(desc.description or "")}</DESCRIPTION>{standard}
    <PARAM name="accessURL" datatype="char" arraysize="*" value="{_attr(desc.access_url)}"/>
    <GROUP name="inputParams">
      {inputs}
    </GROUP>
  </RESOURCE>"""


# ObsCore content type that tells a VO client "access_url is a DataLink
# document, follow it" (ObsCore 1.1 §3.3 / DataLink §3.2).
DATALINK_ACCESS_FORMAT = "application/x-votable+xml;content=datalink"


def discovery_results_to_votable(results: list[DiscoveryResult]) -> str:
    # The ObsCore columns SKAVA holds, by their standard names. access_url is
    # the dataset's DataLink document (with access_format saying so), the
    # ObsCore convention for datasets whose access needs a resolution step —
    # here, which node and which replica.
    meta_fields = [
        ("obs_id", "char"), ("obs_collection", "char"), ("obs_title", "char"),
        ("dataproduct_type", "char"), ("calib_level", "int"),
        ("target_name", "char"), ("facility_name", "char"), ("instrument_name", "char"),
        ("s_ra", "double"), ("s_dec", "double"), ("s_fov", "double"),
        ("t_min", "double"), ("t_max", "double"), ("em_min", "double"), ("em_max", "double"),
    ]
    fields = meta_fields + [("access_url", "char"), ("access_format", "char")]
    base = settings.public_base_url.rstrip("/")
    rows = []
    for result in results:
        metadata = result.metadata
        cells = [_cell(getattr(metadata, name, None)) for name, _ in meta_fields]
        cells.append(_cell(f"{base}/datalink/{metadata.obs_id}?RESPONSEFORMAT=votable"))
        cells.append(_cell(DATALINK_ACCESS_FORMAT))
        rows.append("<TR>" + "".join(cells) + "</TR>")

    field_xml = "\n".join(_field(name, datatype) for name, datatype in fields)
    row_xml = "\n".join(rows)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">
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
