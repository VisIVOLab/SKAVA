# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""What STILTS taplint checks on the TAP profile: result metadata that agrees
with VOSI /tables, the select list, OVERFLOW, DALI error documents, LANG
variants, VOSI availability and the securityMethod of the interface."""
import xml.etree.ElementTree as ET

import pytest

from app.vo.tap_schema import OBSCORE_COLUMN_NAMES, OBSCORE_COLUMNS, tap_capabilities_xml

NS = {"v": "http://www.ivoa.net/xml/VOTable/v1.3"}


def _votable(client, query, **params):
    r = client.get("/tap/sync", params={"QUERY": query, **params})
    return r, ET.fromstring(r.content)


def _fields(root):
    return root.findall(".//v:TABLE/v:FIELD", NS)


def _status(root):
    return [(i.get("value"), (i.text or "").strip()) for i in root.findall("./v:RESOURCE/v:INFO", NS)
            if i.get("name") == "QUERY_STATUS"]


def test_select_star_returns_every_declared_column_with_its_metadata(client):
    r, root = _votable(client, "SELECT * FROM ivoa.ObsCore")
    assert r.status_code == 200
    fields = _fields(root)
    assert [f.get("name") for f in fields] == OBSCORE_COLUMN_NAMES
    declared = {c.name: c for c in OBSCORE_COLUMNS}
    for field in fields:
        column = declared[field.get("name")]
        assert field.get("ucd") == column.ucd
        assert field.get("unit") == (column.unit or None)
        assert field.get("utype") == (column.utype or None)
    tables = ET.fromstring(client.get("/tap/tables").content)
    assert [c.findtext("name") for c in tables.iter("column")] == OBSCORE_COLUMN_NAMES


def test_select_list_is_honoured_in_order(client):
    r, root = _votable(client, "SELECT TOP 3 s_dec, o.obs_id FROM ivoa.ObsCore AS o")
    assert r.status_code == 200
    assert [f.get("name") for f in _fields(root)] == ["s_dec", "obs_id"]
    rows = root.findall(".//v:TR", NS)
    assert rows and all(len(tr.findall("v:TD", NS)) == 2 for tr in rows)


def test_select_list_aliases_name_the_output(client):
    r, root = _votable(client, "SELECT TOP 2 obs_id AS id, s_ra ra FROM ivoa.ObsCore")
    assert r.status_code == 200
    fields = _fields(root)
    assert [f.get("name") for f in fields] == ["id", "ra"]
    assert fields[1].get("ucd") == "pos.eq.ra"


@pytest.mark.parametrize("query", ["SELECT COUNT(*) FROM ivoa.ObsCore", "SELECT obs_id + 1 FROM ivoa.ObsCore",
                                   "SELECT obs_id AS a, s_ra AS a FROM ivoa.ObsCore",
                                   "SELECT no_such_column FROM ivoa.ObsCore", "SELECT DISTINCT obs_id FROM ivoa.ObsCore"])
def test_unsupported_select_lists_get_a_dali_error(client, query):
    r, root = _votable(client, query)
    assert r.status_code == 400
    assert r.headers["content-type"].startswith("application/x-votable+xml")
    assert _status(root)[0][0] == "ERROR"


def test_overflow_is_marked_after_the_table_when_maxrec_cuts(client):
    r, root = _votable(client, "SELECT * FROM ivoa.ObsCore", MAXREC="1")
    assert r.status_code == 200
    assert [s for s, _ in _status(root)] == ["OK", "OVERFLOW"]
    resource = root.find("./v:RESOURCE", NS)
    tags = [child.tag.split("}")[1] for child in resource]
    assert tags.index("INFO", tags.index("TABLE")) > tags.index("TABLE")


def test_top_is_not_an_overflow(client):
    _, root = _votable(client, "SELECT TOP 1 * FROM ivoa.ObsCore")
    assert [s for s, _ in _status(root)] == ["OK"]


def test_maxrec_caps_a_larger_top_and_says_so(client):
    _, root = _votable(client, "SELECT TOP 5 * FROM ivoa.ObsCore", MAXREC="1")
    assert len(root.findall(".//v:TR", NS)) == 1
    assert [s for s, _ in _status(root)] == ["OK", "OVERFLOW"]
    _, root = _votable(client, "SELECT TOP 1 * FROM ivoa.ObsCore", MAXREC="5")
    assert len(root.findall(".//v:TR", NS)) == 1
    assert [s for s, _ in _status(root)] == ["OK"]


def test_maxrec_zero_returns_metadata_only(client):
    r, root = _votable(client, "SELECT obs_id FROM ivoa.ObsCore", MAXREC="0")
    assert r.status_code == 200
    assert [f.get("name") for f in _fields(root)] == ["obs_id"]
    assert root.findall(".//v:TR", NS) == []
    assert "OVERFLOW" in [s for s, _ in _status(root)]


@pytest.mark.parametrize("params", [{"MAXREC": "abc"}, {"MAXREC": "5000"}, {"LANG": "SQL"},
                                    {"REQUEST": "getCapabilities"}, {"RESPONSEFORMAT": "csv"}])
def test_bad_parameters_get_a_dali_error(client, params):
    r, root = _votable(client, "SELECT * FROM ivoa.ObsCore", **params)
    assert r.status_code == 400
    assert _status(root)[0][0] == "ERROR"


def test_missing_query_gets_a_dali_error(client):
    r = client.get("/tap/sync")
    assert r.status_code == 400
    assert _status(ET.fromstring(r.content))[0][0] == "ERROR"


def test_post_errors_are_dali_documents_too(client):
    r = client.post("/tap/sync", data={"QUERY": "SELECT * FROM ivoa.ObsCore WHERE a = 1 OR b = 2"})
    assert r.status_code == 400
    assert _status(ET.fromstring(r.content))[0][0] == "ERROR"


def test_json_errors_keep_the_envelope(client):
    r = client.get("/tap/sync", params={"QUERY": "SELECT foo FROM ivoa.ObsCore", "FORMAT": "json"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_query"


@pytest.mark.parametrize("lang", ["ADQL", "ADQL-2.0", "ADQL-2.1", "adql"])
def test_adql_language_variants(client, lang):
    r, _ = _votable(client, "SELECT TOP 1 obs_id FROM ivoa.ObsCore", LANG=lang)
    assert r.status_code == 200


def test_vosi_availability(client):
    r = client.get("/tap/availability")
    assert r.status_code == 200
    root = ET.fromstring(r.content)
    assert root.findtext("{http://www.ivoa.net/xml/VOSIAvailability/v1.0}available") == "true"
    caps = client.get("/tap/capabilities").text
    assert "ivo://ivoa.net/std/VOSI#availability" in caps and "/tap/availability" in caps


def test_security_method_is_declared_only_when_a_token_is_required():
    assert "securityMethod" not in tap_capabilities_xml("https://example.org")
    caps = ET.fromstring(tap_capabilities_xml("https://example.org", auth_required=True))
    methods = [m.get("standardID") for m in caps.iter("securityMethod")]
    assert methods == ["ivo://ivoa.net/sso#BearerToken"]


def test_datalink_votable_has_the_datalink_content_type(client):
    r = client.get("/datalink", params={"ID": "dataset-3"})
    assert r.headers["content-type"] == "application/x-votable+xml;content=datalink"
    r = client.get("/datalink/dataset-3", params={"RESPONSEFORMAT": "votable"})
    assert r.headers["content-type"] == "application/x-votable+xml;content=datalink"
