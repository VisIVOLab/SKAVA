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

from xml.sax.saxutils import escape

from html import escape

TABLESET_MEDIA_TYPE = "application/xml"

# (name, TAP datatype, ucd, unit, description)
_OBSCORE_COLUMNS: list[tuple[str, str, str, str, str]] = [
    ("obs_id", "VARCHAR", "meta.id;meta.main", "", "Dataset identifier"),
    ("obs_collection", "VARCHAR", "meta.id", "", "Collection / survey name"),
    ("obs_title", "VARCHAR", "meta.title", "", "Human-readable dataset title"),
    ("dataproduct_type", "VARCHAR", "meta.id", "", "Data product type (image, cube, …)"),
    ("calib_level", "INTEGER", "meta.code;obs.calib", "", "Calibration level (0-3)"),
    ("target_name", "VARCHAR", "meta.id;src", "", "Astronomical target name"),
    ("facility_name", "VARCHAR", "meta.id;instr.tel", "", "Facility / telescope name"),
    ("instrument_name", "VARCHAR", "meta.id;instr", "", "Instrument name"),
    ("s_ra", "DOUBLE", "pos.eq.ra", "deg", "Central right ascension (ICRS)"),
    ("s_dec", "DOUBLE", "pos.eq.dec", "deg", "Central declination (ICRS)"),
    ("s_fov", "DOUBLE", "phys.angSize;instr.fov", "deg", "Field-of-view angular diameter"),
    ("t_min", "DOUBLE", "time.start;obs.exposure", "d", "Observation start (MJD)"),
    ("t_max", "DOUBLE", "time.end;obs.exposure", "d", "Observation end (MJD)"),
    ("em_min", "DOUBLE", "em.wl;stat.min", "m", "Minimum wavelength"),
    ("em_max", "DOUBLE", "em.wl;stat.max", "m", "Maximum wavelength"),
    ("access_format", "VARCHAR", "meta.code.mime", "", "Access data format (MIME)"),
    ("access_estsize", "BIGINT", "phys.size;meta.file", "kbyte", "Estimated access size"),
    ("spatial_index_cell", "VARCHAR", "meta.id", "", "Lightweight HEALPix/MOC-ready cell key"),
    ("doi", "VARCHAR", "meta.ref.doi", "", "Digital Object Identifier"),
    ("pid", "VARCHAR", "meta.ref", "", "Persistent identifier"),
]


def _column_xml(name: str, datatype: str, ucd: str, unit: str, desc: str) -> str:
    unit_xml = f"\n        <unit>{escape(unit)}</unit>" if unit else ""
    ucd_xml = f"\n        <ucd>{escape(ucd)}</ucd>" if ucd else ""
    return (
        "      <column>\n"
        f"        <name>{escape(name)}</name>\n"
        f"        <description>{escape(desc)}</description>"
        f"{unit_xml}{ucd_xml}\n"
        f'        <dataType xsi:type="vod:TAPType">{escape(datatype)}</dataType>\n'
        "      </column>"
    )


def obscore_tableset() -> str:
    """Return the VOSI tableset XML describing ``ivoa.ObsCore``."""
    columns_xml = "\n".join(_column_xml(*col) for col in _OBSCORE_COLUMNS)
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
# The row limits the sync query applies (TapService._parse_limit and the
# routes' MAXREC bound): what the capabilities document advertises.
TAP_DEFAULT_ROWS = 100
TAP_MAX_ROWS = 1000


def tap_capabilities_xml(base_url: str) -> str:
    """The VOSI capabilities document of the TAP service: what a VO client
    (pyvo's ``TAPService.capabilities``, TOPCAT) reads at ``/tap/capabilities``
    to learn the service's standard, its interface and its query language."""
    base = escape(base_url.rstrip("/"))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<vosi:capabilities
    xmlns:vosi="http://www.ivoa.net/xml/VOSICapabilities/v1.0"
    xmlns:vs="http://www.ivoa.net/xml/VODataService/v1.1"
    xmlns:tr="http://www.ivoa.net/xml/TAPRegExt/v1.0"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <capability standardID="ivo://ivoa.net/std/TAP" xsi:type="tr:TableAccess">
    <interface xsi:type="vs:ParamHTTP" role="std" version="1.1">
      <accessURL use="base">{base}/tap</accessURL>
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
</vosi:capabilities>
"""
