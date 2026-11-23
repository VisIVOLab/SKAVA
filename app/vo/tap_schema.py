# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""VOSI ``/tables`` tableset for the TAP ObsCore profile.

Generic VO tools (TOPCAT, pyvo) load this document to discover the
queryable ``ivoa.ObsCore`` table and its columns — names, datatypes, UCDs
and units — before building ADQL. Exposing it (together with the geometry
+ range ADQL support in :mod:`app.vo.adql`) is what lifts SKAVA from
"ObsCore-aligned" to genuinely "ObsTAP-interoperable" for the supported
column subset.

The column list mirrors the queryable whitelist in :mod:`app.vo.adql` and
carries the standard ObsCore UCDs/units so the tableset is meaningful to
VO clients.
"""
from __future__ import annotations

from html import escape
from typing import NamedTuple

TABLESET_MEDIA_TYPE = "application/xml"

class ObsCoreColumn(NamedTuple):
    """One column of ``ivoa.ObsCore`` as SKAVA serves it: the same record
    describes the column in VOSI ``/tables`` and in every query result, so the
    two cannot disagree (taplint compares them)."""
    name: str
    tap_type: str        # VODataService TAPType
    votable_type: str    # VOTable FIELD datatype
    ucd: str
    unit: str
    utype: str           # ObsCore 1.1 utype, empty for SKAVA's own columns
    description: str


# In result order: what ``SELECT *`` returns. UCDs, units and utypes are those
# of ObsCore 1.1 (Table 3) for the standard columns; the last four are SKAVA's.
OBSCORE_COLUMNS: list[ObsCoreColumn] = [
    ObsCoreColumn("obs_id", "VARCHAR", "char", "meta.id", "", "obscore:DataID.observationID",
                  "Dataset identifier"),
    ObsCoreColumn("obs_collection", "VARCHAR", "char", "meta.id", "", "obscore:DataID.Collection",
                  "Collection / survey name"),
    ObsCoreColumn("obs_title", "VARCHAR", "char", "meta.title;obs", "", "obscore:DataID.Title",
                  "Human-readable dataset title"),
    ObsCoreColumn("dataproduct_type", "VARCHAR", "char", "meta.code.class", "",
                  "obscore:ObsDataset.dataProductType", "Data product type (image, cube, ...)"),
    ObsCoreColumn("calib_level", "INTEGER", "int", "meta.code;obs.calib", "", "obscore:ObsDataset.calibLevel",
                  "Calibration level (0-4)"),
    ObsCoreColumn("target_name", "VARCHAR", "char", "meta.id;src", "", "obscore:Target.name",
                  "Astronomical target name"),
    ObsCoreColumn("facility_name", "VARCHAR", "char", "meta.id;instr.tel", "",
                  "obscore:Provenance.ObsConfig.Facility.name", "Facility / telescope name"),
    ObsCoreColumn("instrument_name", "VARCHAR", "char", "meta.id;instr", "",
                  "obscore:Provenance.ObsConfig.Instrument.name", "Instrument name"),
    ObsCoreColumn("s_ra", "DOUBLE", "double", "pos.eq.ra", "deg",
                  "obscore:Char.SpatialAxis.Coverage.Location.Coord.Position2D.Value2.C1",
                  "Central right ascension (ICRS)"),
    ObsCoreColumn("s_dec", "DOUBLE", "double", "pos.eq.dec", "deg",
                  "obscore:Char.SpatialAxis.Coverage.Location.Coord.Position2D.Value2.C2",
                  "Central declination (ICRS)"),
    ObsCoreColumn("s_fov", "DOUBLE", "double", "phys.angSize;instr.fov", "deg",
                  "obscore:Char.SpatialAxis.Coverage.Bounds.Extent.diameter", "Field-of-view angular diameter"),
    ObsCoreColumn("t_min", "DOUBLE", "double", "time.start;obs.exposure", "d",
                  "obscore:Char.TimeAxis.Coverage.Bounds.Limits.StartTime", "Observation start (MJD)"),
    ObsCoreColumn("t_max", "DOUBLE", "double", "time.end;obs.exposure", "d",
                  "obscore:Char.TimeAxis.Coverage.Bounds.Limits.StopTime", "Observation end (MJD)"),
    ObsCoreColumn("em_min", "DOUBLE", "double", "em.wl;stat.min", "m",
                  "obscore:Char.SpectralAxis.Coverage.Bounds.Limits.LoLimit", "Minimum wavelength (vacuum)"),
    ObsCoreColumn("em_max", "DOUBLE", "double", "em.wl;stat.max", "m",
                  "obscore:Char.SpectralAxis.Coverage.Bounds.Limits.HiLimit", "Maximum wavelength (vacuum)"),
    ObsCoreColumn("access_url", "VARCHAR", "char", "meta.ref.url", "", "obscore:Access.Reference",
                  "The dataset's DataLink document, which names the copy and the services to use"),
    ObsCoreColumn("access_format", "VARCHAR", "char", "meta.code.mime", "", "obscore:Access.Format",
                  "Format of access_url (a DataLink document)"),
    ObsCoreColumn("access_estsize", "BIGINT", "long", "phys.size;meta.file", "kbyte", "obscore:Access.Size",
                  "Estimated size of the dataset"),
    ObsCoreColumn("spatial_index_cell", "VARCHAR", "char", "meta.id", "", "",
                  "SKAVA sky-cell key (equal-angle bins)"),
    ObsCoreColumn("doi", "VARCHAR", "char", "meta.ref.doi", "", "", "Digital Object Identifier"),
    ObsCoreColumn("pid", "VARCHAR", "char", "meta.ref", "", "", "Persistent identifier"),
]

OBSCORE_COLUMN_NAMES = [column.name for column in OBSCORE_COLUMNS]


def _column_xml(column: ObsCoreColumn) -> str:
    unit_xml = f"\n        <unit>{escape(column.unit)}</unit>" if column.unit else ""
    ucd_xml = f"\n        <ucd>{escape(column.ucd)}</ucd>" if column.ucd else ""
    utype_xml = f"\n        <utype>{escape(column.utype)}</utype>" if column.utype else ""
    return (
        "      <column>\n"
        f"        <name>{escape(column.name)}</name>\n"
        f"        <description>{escape(column.description)}</description>"
        f"{unit_xml}{ucd_xml}{utype_xml}\n"
        f'        <dataType xsi:type="vod:TAPType">{escape(column.tap_type)}</dataType>\n'
        "      </column>"
    )


def obscore_tableset() -> str:
    """Return the VOSI tableset XML describing ``ivoa.ObsCore``."""
    columns_xml = "\n".join(_column_xml(col) for col in OBSCORE_COLUMNS)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<vosi:tableset
    xmlns:vosi="http://www.ivoa.net/xml/VOSITables/v1.0"
    xmlns:vod="http://www.ivoa.net/xml/VODataService/v1.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <schema>
    <name>ivoa</name>
    <description>IVOA ObsCore-aligned metadata exposed by SKAVA.</description>
    <table type="output">
      <name>ivoa.ObsCore</name>
      <description>ObsCore-style observation metadata. Queryable via the SKAVA TAP profile with equality/range predicates and the CONTAINS cone-search geometry.</description>
{columns_xml}
    </table>
  </schema>
</vosi:tableset>
"""


CAPABILITIES_MEDIA_TYPE = "application/xml"
# The row limits the sync query applies (TapService._limits and the
# routes' MAXREC bound): what the capabilities document advertises.
TAP_DEFAULT_ROWS = 100
TAP_MAX_ROWS = 1000


def tap_capabilities_xml(base_url: str, auth_required: bool = False) -> str:
    """The VOSI capabilities document of the TAP service: what a VO client
    (pyvo's ``TAPService.capabilities``, TOPCAT) reads at ``/tap/capabilities``
    to learn the service's standard, its interface and its query language."""
    base = escape(base_url.rstrip("/"))
    # VOResource: an interface with no securityMethod is used anonymously; one
    # that needs a token says so with the SSO standard it accepts (SSO 2.0).
    security = ('\n      <securityMethod standardID="ivo://ivoa.net/sso#BearerToken"/>'
                if auth_required else "")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<vosi:capabilities
    xmlns:vosi="http://www.ivoa.net/xml/VOSICapabilities/v1.0"
    xmlns:vs="http://www.ivoa.net/xml/VODataService/v1.1"
    xmlns:tr="http://www.ivoa.net/xml/TAPRegExt/v1.0"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <capability standardID="ivo://ivoa.net/std/TAP" xsi:type="tr:TableAccess">
    <interface xsi:type="vs:ParamHTTP" role="std" version="1.1">
      <accessURL use="base">{base}/tap</accessURL>{security}
    </interface>
    <language>
      <name>ADQL</name>
      <version ivo-id="ivo://ivoa.net/std/ADQL#v2.1">2.1</version>
      <description>ADQL 2.1, the ObsCore profile: equality and range predicates on the queryable columns and a CONTAINS(POINT, CIRCLE) cone</description>
    </language>
    <outputFormat>
      <mime>application/x-votable+xml</mime>
      <alias>votable</alias>
    </outputFormat>
    <outputFormat>
      <mime>application/json</mime>
      <alias>json</alias>
    </outputFormat>
    <outputLimit>
      <default unit="row">{TAP_DEFAULT_ROWS}</default>
      <hard unit="row">{TAP_MAX_ROWS}</hard>
    </outputLimit>
  </capability>
  <capability standardID="ivo://ivoa.net/std/VOSI#capabilities">
    <interface xsi:type="vs:ParamHTTP" role="std">
      <accessURL use="full">{base}/tap/capabilities</accessURL>
    </interface>
  </capability>
  <capability standardID="ivo://ivoa.net/std/VOSI#tables">
    <interface xsi:type="vs:ParamHTTP" role="std">
      <accessURL use="full">{base}/tap/tables</accessURL>
    </interface>
  </capability>
  <capability standardID="ivo://ivoa.net/std/VOSI#availability">
    <interface xsi:type="vs:ParamHTTP" role="std">
      <accessURL use="full">{base}/tap/availability</accessURL>
    </interface>
  </capability>
</vosi:capabilities>
"""


AVAILABILITY_MEDIA_TYPE = "application/xml"


def availability_xml(available: bool, note: str | None = None) -> str:
    """The VOSI availability document of the TAP service."""
    note_xml = f"\n  <vosi:note>{escape(note)}</vosi:note>" if note else ""
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<vosi:availability xmlns:vosi="http://www.ivoa.net/xml/VOSIAvailability/v1.0">\n'
            f"  <vosi:available>{'true' if available else 'false'}</vosi:available>{note_xml}\n"
            "</vosi:availability>\n")
