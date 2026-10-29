# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
def test_datalink_valid_dataset(client):
    resp = client.get("/datalink/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dataset"]["obs_id"] == "dataset-3"


def test_datalink_multiple_replicas_and_best_node(client):
    resp = client.get("/datalink/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["routing"]["best_node"] == "B"
    assert len(data["routing"]["replicas"]) == 2


def test_datalink_links_present(client):
    resp = client.get("/datalink/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    rels = {item["rel"] for item in data["links"]}
    assert "self" in rels
    assert "direct-download" in rels


def test_datalink_service_descriptors_present(client):
    resp = client.get("/datalink/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    descriptor_types = {item["service_type"] for item in data["service_descriptors"]}
    assert "access-resolution" in descriptor_types
    assert "soda-sync" in descriptor_types


def test_datalink_soda_sync_descriptor_points_to_soda_sync(client):
    resp = client.get("/datalink/dataset-3")
    assert resp.status_code == 200
    data = resp.json()
    soda = next(item for item in data["service_descriptors"] if item["service_type"] == "soda-sync")
    assert soda["access_url"].endswith("/soda/sync")
    assert soda["enabled"] is True


def test_datalink_capability_flags_consistency(client):
    resp = client.get("/datalink/dataset-3")
    assert resp.status_code == 200
    caps = resp.json()["capabilities"]
    assert caps["supports_soda_sync"] is False
    assert caps["supports_soda_sync_endpoint"] is True
    assert caps["supports_soda_sync_execution"] is False


def test_datalink_not_found(client):
    resp = client.get("/datalink/missing")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "dataset_not_found"


def test_datalink_access_consistency_with_access_facade(client):
    datalink = client.get("/datalink/dataset-3")
    assert datalink.status_code == 200
    access = client.get("/access/dataset-3")
    assert access.status_code == 200

    datalink_payload = datalink.json()
    access_payload = access.json()
    assert datalink_payload["primary_access"]["access_url"] == access_payload["access_url"]


def test_links_endpoint_answers_several_ids_in_votable_by_default(client):
    # DataLink 1.1 {links}: ID repeated, VOTable without asking, a NotFoundFault
    # row for an unknown ID, every row carrying the ID it answers.
    from astropy.io.votable import parse_single_table
    import io
    r = client.get("/datalink", params=[("ID", "dataset-3"), ("ID", "nope"), ("ID", "dataset-1")])
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/x-votable+xml")
    table = parse_single_table(io.BytesIO(r.content)).to_table()
    ids = list(table["ID"])
    assert {"dataset-3", "dataset-1", "nope"} <= set(ids)
    errors = [row["error_message"] for row in table if row["ID"] == "nope"]
    assert len(errors) == 1 and str(errors[0]).startswith("NotFoundFault")
    assert all(not row["error_message"] for row in table if row["ID"] != "nope")
    # The same by POST.
    p = client.post("/datalink", data={"ID": ["dataset-3", "dataset-1"]})
    assert p.status_code == 200 and b"NotFoundFault" not in p.content


def test_links_endpoint_refuses_a_format_it_does_not_serve(client):
    r = client.get("/datalink", params={"ID": "dataset-3", "RESPONSEFORMAT": "application/json"})
    assert r.status_code == 400


def test_tap_rows_point_at_the_links_endpoint(client):
    query = "SELECT * FROM ivoa.obscore WHERE obs_id = 'dataset-3'"
    r = client.get("/tap/sync", params={"QUERY": query})
    assert "/datalink?ID=dataset-3" in r.text
    assert "content=datalink" in r.text


def test_links_rows_and_faults_follow_datalink_1_1(client):
    # Error rows carry #this; the results resource names the standard; a
    # dataset no node can serve is a fault of its own row only.
    from astropy.io.votable import parse
    import io
    from app.main import app
    from app.models.node import Node
    with app.state.testing_session_local() as db:
        for node in db.query(Node).all():
            node.is_available = False
        db.commit()
    r = client.get("/datalink", params=[("ID", "dataset-3"), ("ID", "nope")])
    assert r.status_code == 200, r.text
    assert b'name="standardID" value="ivo://ivoa.net/std/DataLink#links-1.1"' in r.content
    table = parse(io.BytesIO(r.content)).get_first_table().to_table()
    by_id = {row["ID"]: row for row in table}
    assert str(by_id["nope"]["semantics"]) == "#this"
    assert str(by_id["nope"]["error_message"]).startswith("NotFoundFault")
    assert str(by_id["dataset-3"]["error_message"]).startswith("TransientFault")


def test_links_endpoint_normative_cases(client):
    from astropy.io.votable import parse
    import io
    # No ID: a valid VOTable with an empty table.
    empty = client.get("/datalink")
    assert empty.status_code == 200
    assert len(parse(io.BytesIO(empty.content)).get_first_table().to_table()) == 0
    # The VOTable RESPONSEFORMAT spellings all give the standard document.
    for fmt in ("votable", "application/x-votable+xml", "application/x-votable+xml;content=datalink"):
        r = client.get("/datalink", params={"ID": "dataset-3", "RESPONSEFORMAT": fmt})
        assert r.status_code == 200 and b"#links-1.1" in r.content, fmt
    # Over the limit on IDs: OVERFLOW, and every answered ID complete.
    from app.routers import datalink as router
    ids = [("ID", "dataset-1")] * (router.MAX_LINKS_IDS + 5)
    big = client.get("/datalink", params=ids)
    assert big.status_code == 200 and b'name="QUERY_STATUS" value="OVERFLOW"' in big.content
    one = client.get("/datalink", params={"ID": "dataset-1"})
    table_one = parse(io.BytesIO(one.content)).get_first_table().to_table()
    table_big = parse(io.BytesIO(big.content)).get_first_table().to_table()
    assert len(table_big) == router.MAX_LINKS_IDS * len(table_one)
