# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""TAP ObsCore profile: real ADQL geometry/range support + VOSI tables."""


def _json(client, query):
    resp = client.get("/tap/sync", params={"QUERY": query, "FORMAT": "json"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ids(payload):
    return [r["metadata"]["obs_id"] for r in payload["results"]]


def _meta(client, obs_id):
    payload = _json(client, f"SELECT * FROM ivoa.ObsCore WHERE obs_id = '{obs_id}'")
    assert payload["returned"] == 1
    return payload["results"][0]["metadata"]


# ── Spatial: CONTAINS cone search ───────────────────────────────────────────


def test_tap_cone_search_includes_matching_dataset(client):
    m = _meta(client, "dataset-3")
    ra, dec = m["s_ra"], m["s_dec"]
    q = (
        "SELECT * FROM ivoa.ObsCore WHERE 1 = CONTAINS("
        f"POINT('ICRS', s_ra, s_dec), CIRCLE('ICRS', {ra}, {dec}, 0.5))"
    )
    assert "dataset-3" in _ids(_json(client, q))


def test_tap_cone_search_excludes_far_region(client):
    q = (
        "SELECT * FROM ivoa.ObsCore WHERE 1 = CONTAINS("
        "POINT('ICRS', s_ra, s_dec), CIRCLE('ICRS', 10, 80, 0.01))"
    )
    assert "dataset-3" not in _ids(_json(client, q))


def test_tap_contains_reversed_form(client):
    m = _meta(client, "dataset-3")
    q = (
        "SELECT * FROM ivoa.ObsCore WHERE CONTAINS("
        f"POINT('ICRS', s_ra, s_dec), CIRCLE('ICRS', {m['s_ra']}, {m['s_dec']}, 0.5)) = 1"
    )
    assert "dataset-3" in _ids(_json(client, q))


# ── Temporal / spectral range predicates ────────────────────────────────────


def test_tap_temporal_range_overlap(client):
    m = _meta(client, "dataset-3")
    q = (
        "SELECT * FROM ivoa.ObsCore "
        f"WHERE t_min <= {m['t_max']} AND t_max >= {m['t_min']}"
    )
    assert "dataset-3" in _ids(_json(client, q))


def test_tap_spectral_range_overlap(client):
    m = _meta(client, "dataset-3")
    q = (
        "SELECT * FROM ivoa.ObsCore "
        f"WHERE em_min <= {m['em_max']} AND em_max >= {m['em_min']}"
    )
    assert "dataset-3" in _ids(_json(client, q))


def test_tap_range_excludes_everything(client):
    assert _json(client, "SELECT * FROM ivoa.ObsCore WHERE t_min > 1e12")["returned"] == 0


def test_tap_combined_geometry_range_and_equality(client):
    m = _meta(client, "dataset-3")
    q = (
        "SELECT * FROM ivoa.ObsCore WHERE "
        f"1 = CONTAINS(POINT('ICRS', s_ra, s_dec), CIRCLE('ICRS', {m['s_ra']}, {m['s_dec']}, 0.5)) "
        f"AND t_max >= {m['t_min']} AND obs_collection = '{m['obs_collection']}'"
    )
    assert "dataset-3" in _ids(_json(client, q))


# ── VOSI tables + capabilities ──────────────────────────────────────────────


def test_tap_tables_vosi(client):
    resp = client.get("/tap/tables")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    body = resp.text
    assert "<vosi:tableset" in body
    assert "ivoa.ObsCore" in body
    assert "<name>obs_id</name>" in body
    assert "<name>s_ra</name>" in body
    assert "pos.eq.ra" in body


def test_tap_capabilities_advertise_geometry_and_columns(client):
    caps = client.get("/tap/capabilities", headers={"Accept": "application/json"}).json()
    assert caps["tables_endpoint"] == "/tap/tables"
    assert any("CONTAINS" in g for g in caps["supported_geometry"])
    assert "s_ra" in caps["queryable_columns"]
    assert "t_min" in caps["queryable_columns"]
