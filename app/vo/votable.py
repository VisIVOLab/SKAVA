from html import escape

from app.schemas.datalink import DataLinkResponse
from app.schemas.discovery import DiscoveryResult

VOTABLE_MEDIA_TYPE = "application/x-votable+xml"


def _cell(value: object | None) -> str:
    return f"<TD>{escape(str(value)) if value is not None else ''}</TD>"


def _field(name: str, datatype: str) -> str:
    if datatype == "char":
        return f'<FIELD name="{name}" datatype="{datatype}" arraysize="*"/>'
    return f'<FIELD name="{name}" datatype="{datatype}"/>'


def datalink_to_votable(datalink: DataLinkResponse) -> str:
    fields = [
        ("ID", "char"),
        ("semantics", "char"),
        ("access_url", "char"),
        ("content_type", "char"),
        ("description", "char"),
        ("node_id", "char"),
    ]
    rows = []
    for link in datalink.links:
        if not link.href:
            continue
        rows.append(
            "<TR>"
            + "".join(
                [
                    _cell(datalink.dataset.obs_id),
                    _cell(link.rel),
                    _cell(link.href),
                    _cell(link.content_type),
                    _cell(link.description),
                    _cell(link.node_id),
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
    <TABLE name="datalink">
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
