# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Tests for SODA execution delegated to a node's co-located VisIVO backend.

These cover the compute-next-to-data path of /soda/execute:
* delegation to the backend when the best node has visivo_backend_url and a
  file:// replica → FITS streamed back;
* graceful fallback to the staging handoff when there is no backend;
* the DataLink capability flags flipping to reflect execution availability.
"""
import httpx

from app.main import app
from app.models.dataset import Dataset
from app.models.node import Node
from app.models.replica import DatasetReplica


def _enable_backend_on_best_node(file_url: str = "file:///data/dataset-3.fits") -> None:
    """Point dataset-3's replicas at a file:// URL and give their nodes a backend."""
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "dataset-3").one()
        replicas = db.query(DatasetReplica).filter(DatasetReplica.dataset_id == dataset.id).all()
        dataset.dataproduct_type = "cube"       # moments and PV are cube operations
        for replica in replicas:
            replica.access_endpoint = file_url
            replica.status = "available"
            replica.is_public = True
            replica.node.visivo_backend_url = "http://node-backend:8000"
            replica.node.visivo_backend_requires_auth = False
        db.commit()


def test_soda_execute_delegates_to_backend(client, monkeypatch):
    _enable_backend_on_best_node()

    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200,
            content=b"SIMPLE  =                    T / FITS cutout",
            headers={
                "content-type": "application/fits",
                "content-disposition": 'attachment; filename="dataset-3_cutout.fits"',
                "X-Soda-Applied": "pos",
            },
        )

    monkeypatch.setattr("app.services.soda_execution_service.httpx.post", fake_post)

    resp = client.post("/soda/execute", params={"ID": "dataset-3", "POS": "CIRCLE 103 -23 0.05"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/fits")
    assert resp.headers["X-Soda-Applied"] == "pos"
    assert resp.content.startswith(b"SIMPLE")
    # SKAVA delegated to the node backend's cutout endpoint with the file URL.
    assert captured["url"] == "http://node-backend:8000/v1/datasets/cutout"
    assert captured["json"]["access_url"] == "file:///data/dataset-3.fits"
    assert captured["json"]["pos"] == "CIRCLE 103.0 -23.0 0.05"


def test_soda_execute_backend_error_surfaces_502(client, monkeypatch):
    _enable_backend_on_best_node()

    def fake_post(url, json=None, headers=None, timeout=None):
        return httpx.Response(400, json={"detail": "POS does not overlap"})

    monkeypatch.setattr("app.services.soda_execution_service.httpx.post", fake_post)

    resp = client.post("/soda/execute", params={"ID": "dataset-3", "POS": "CIRCLE 10 80 0.01"})
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "backend_execution_failed"


def test_soda_execute_falls_back_to_staging_without_backend(client):
    # No backend configured on the seed nodes → metadata-cache handoff JSON.
    resp = client.post("/soda/execute", params={"ID": "dataset-3", "POS": "CIRCLE 103 -23 0.05"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["operation"]["type"] == "subset"


def test_datalink_capabilities_flip_when_backend_present(client):
    _enable_backend_on_best_node()
    caps = client.get("/datalink/dataset-3").json()["capabilities"]
    assert caps["supports_soda_sync_execution"] is True
    assert caps["supports_soda_sync"] is True
    assert caps["supports_cutout"] is True


def test_datalink_cutout_descriptor_enabled_with_backend(client):
    _enable_backend_on_best_node()
    descriptors = client.get("/datalink/dataset-3").json()["service_descriptors"]
    cutout = next(d for d in descriptors if d["service_type"] == "cutout")
    assert cutout["enabled"] is True
    assert cutout["access_url"].endswith("/soda/execute")


def test_access_and_votable_advertise_cutout_when_executable(client):
    """With a co-located backend on a file:// replica the cutout is real:
    /access lists it, and the DataLink VOTable carries the #cutout row, the
    SODA service RESOURCE and one #auxiliary row per VisIVO backend."""
    _enable_backend_on_best_node()
    access = client.get("/access/dataset-3").json()
    assert access["supports_soda"] is True
    assert access["supported_operations"] == ["download", "cutout", "band_subset"]

    from xml.etree import ElementTree as ET
    ns = {"v": "http://www.ivoa.net/xml/VOTable/v1.3"}
    vot = client.get("/datalink/dataset-3", params={"RESPONSEFORMAT": "votable"}).text
    root = ET.fromstring(vot)                      # well-formed
    names = [f.get("name") for f in root.findall(".//v:TABLE/v:FIELD", ns)]
    cells = [[td.text or "" for td in tr.findall("v:TD", ns)] for tr in root.findall(".//v:TR", ns)]
    assert cells and all(len(c) == len(names) for c in cells)   # before zip, which would drop extras
    rows = [dict(zip(names, c)) for c in cells]
    # The node's own SODA services: sync and async cutouts, and the moment/PV
    # operations, each a row pointing at its service descriptor.
    cutout = [r for r in rows if r["semantics"] == "#cutout"]
    proc = [r for r in rows if r["semantics"] == "#proc"]
    assert len(cutout) == 2 and len(proc) == 2
    standards = set()
    for row in cutout + proc:
        service = root.find(f".//v:RESOURCE[@ID='{row['service_def']}']", ns)
        assert service is not None and service.get("utype") == "adhoc:service"
        params = {p.get("name"): p.get("value") for p in service.findall("v:PARAM", ns)}
        assert params["accessURL"].startswith("http://node-backend:8000/soda/")
        inputs = {p.get("name"): p.get("value") for p in service.findall("v:GROUP/v:PARAM", ns)}
        assert inputs["ID"] == "file:///data/dataset-3.fits"      # the replica's ID on that node
        standards.add(params.get("standardID"))
    assert {"ivo://ivoa.net/std/SODA#sync-1.0", "ivo://ivoa.net/std/SODA#async-1.0"} <= standards
    assert not any(r["access_url"].endswith("/soda/execute") for r in rows)   # the proxy is not SODA
    backend = [r for r in rows if r["semantics"] == "#auxiliary"]
    assert backend and all(r["access_url"].endswith("/v1/node/status") and r["content_type"] == "application/json"
                           for r in backend)


def test_soda_execute_uses_first_executable_replica(client, monkeypatch):
    """Best node has no backend, a lower-ranked node does: the cutout runs
    there, on that node's own copy, and the response says so."""
    from app.models.node import Node
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "dataset-3").one()
        replicas = db.query(DatasetReplica).filter(DatasetReplica.dataset_id == dataset.id).all()
        assert len(replicas) >= 2, "seed must give dataset-3 two replicas"
        for replica in replicas:
            replica.status, replica.is_public = "available", True
            replica.node.visivo_backend_url = None
        best = db.query(Node).filter(Node.code == "B").one()
        other = next(r for r in replicas if r.node.code != "B")
        other.access_endpoint = "file:///other/dataset-3.fits"
        other.node.visivo_backend_url = "http://other-backend:8000"
        other_code = other.node.code
        db.commit()
        assert best.visivo_backend_url is None

    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"], captured["json"] = url, json
        return httpx.Response(200, content=b"SIMPLE  =                    T",
                              headers={"content-type": "application/fits"},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.soda_execution_service.httpx.post", fake_post)
    resp = client.post("/soda/execute", params={"ID": "dataset-3", "POS": "CIRCLE 103 -23 0.05"})
    assert resp.status_code == 200, resp.text
    assert captured["url"].startswith("http://other-backend:8000")
    assert captured["json"]["access_url"] == "file:///other/dataset-3.fits"
    assert resp.headers.get("X-Soda-Executed-On") == other_code


def test_soda_execute_prefers_the_higher_ranked_executable_replica(client, monkeypatch):
    """Two executable replicas: the one ranked first wins, whichever it is."""
    from app.models.node import Node
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "dataset-3").one()
        replicas = db.query(DatasetReplica).filter(DatasetReplica.dataset_id == dataset.id).all()
        for i, replica in enumerate(replicas):
            replica.status, replica.is_public = "available", True
            replica.access_endpoint = f"file:///copy-{replica.node.code}.fits"
            replica.node.visivo_backend_url = f"http://backend-{replica.node.code}:8000"
        db.commit()
    best = client.get("/datalink/dataset-3").json()["routing"]["best_node"]

    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"], captured["json"] = url, json
        return httpx.Response(200, content=b"SIMPLE  =                    T",
                              headers={"content-type": "application/fits"},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.soda_execution_service.httpx.post", fake_post)
    resp = client.post("/soda/execute", params={"ID": "dataset-3", "POS": "CIRCLE 103 -23 0.05"})
    assert resp.status_code == 200, resp.text
    assert captured["url"].startswith(f"http://backend-{best}:8000")
    assert captured["json"]["access_url"] == f"file:///copy-{best}.fits"
    assert resp.headers.get("X-Soda-Executed-On") == best


def _decisions() -> float:
    from app.metrics import RANKING_DECISIONS

    return sum(s.value for metric in RANKING_DECISIONS.collect()
               for s in metric.samples if s.name.endswith("_total"))


def test_soda_execute_counts_one_ranking_decision(client, monkeypatch):
    # One request is one decision, on the delegated path and on the staging one.
    _enable_backend_on_best_node()
    monkeypatch.setattr(
        "app.services.soda_execution_service.httpx.post",
        lambda *a, **kw: httpx.Response(200, content=b"SIMPLE", headers={"content-type": "application/fits"}),
    )
    before = _decisions()
    assert client.post("/soda/execute", params={"ID": "dataset-3"}).status_code == 200
    assert _decisions() - before == 1


def test_soda_execute_staging_counts_one_ranking_decision(client):
    before = _decisions()
    assert client.post("/soda/execute", params={"ID": "dataset-3"}).status_code == 200
    assert _decisions() - before == 1


def test_soda_sync_redirects_to_the_node_that_can_cut(client):
    from urllib.parse import parse_qs, urlparse

    _enable_backend_on_best_node()
    resp = client.get("/soda/sync", params={"ID": "dataset-3", "POS": "CIRCLE 103 -23 0.05"},
                      follow_redirects=False)
    assert resp.status_code == 303
    target = urlparse(resp.headers["location"])
    assert f"{target.scheme}://{target.netloc}{target.path}" == "http://node-backend:8000/soda/sync"
    query = parse_qs(target.query)
    assert query["ID"] == ["file:///data/dataset-3.fits"] and query["POS"] == ["CIRCLE 103 -23 0.05"]


def test_soda_sync_stays_a_routing_answer_without_a_node(client):
    resp = client.get("/soda/sync", params={"ID": "dataset-3"}, follow_redirects=False)
    assert resp.status_code == 200 and resp.json()["mode"] == "soda-sync-stub"


def _votable(client):
    from xml.etree import ElementTree as ET

    ns = {"v": "http://www.ivoa.net/xml/VOTable/v1.3"}
    root = ET.fromstring(client.get("/datalink/dataset-3", params={"RESPONSEFORMAT": "votable"}).text)
    names = [f.get("name") for f in root.findall(".//v:TABLE/v:FIELD", ns)]
    rows = [dict(zip(names, [td.text or "" for td in tr.findall("v:TD", ns)]))
            for tr in root.findall(".//v:TR", ns)]
    return root, rows, ns


def test_service_params_are_typed_and_description_comes_first(client):
    _enable_backend_on_best_node()
    root, rows, ns = _votable(client)
    sync = next(r for r in rows if r["semantics"] == "#cutout")
    service = root.find(f".//v:RESOURCE[@ID='{sync['service_def']}']", ns)
    assert service[0].tag == f"{{{ns['v']}}}DESCRIPTION"            # schema order
    params = {p.get("name"): p for p in service.findall("v:GROUP/v:PARAM", ns)}
    assert params["BAND"].get("datatype") == "double" and params["BAND"].get("xtype") == "interval"
    assert params["BAND"].get("arraysize") == "2" and params["BAND"].get("unit") == "m"
    assert params["CIRCLE"].get("xtype") == "circle" and params["POLYGON"].get("xtype") == "polygon"
    assert params["ID"].get("value") == "file:///data/dataset-3.fits"


def test_operations_declare_the_async_protocol_and_only_for_cubes(client):
    _enable_backend_on_best_node()
    root, rows, ns = _votable(client)
    procs = [r for r in rows if r["semantics"] == "#proc"]
    assert len(procs) == 2
    for row in procs:
        service = root.find(f".//v:RESOURCE[@ID='{row['service_def']}']", ns)
        params = {p.get("name"): p.get("value") for p in service.findall("v:PARAM", ns)}
        assert params["standardID"] == "ivo://ivoa.net/std/SODA#async-1.0"
        inputs = {p.get("name"): p.get("value") for p in service.findall("v:GROUP/v:PARAM", ns)}
        assert inputs["OPERATION"] in ("MOMENT", "PV")
    # A 2-D image has no spectral axis: no moment or PV operations.
    with app.state.testing_session_local() as db:
        db.query(Dataset).filter(Dataset.obs_id == "dataset-3").one().dataproduct_type = "image"
        db.commit()
    _, rows, _ = _votable(client)
    assert not [r for r in rows if r["semantics"] == "#proc"]
    assert len([r for r in rows if r["semantics"] == "#cutout"]) == 2
    json_types = [d["service_type"] for d in client.get("/datalink/dataset-3").json()["service_descriptors"]]
    assert "visivo-moment" not in json_types and "node-soda-sync" in json_types


def test_status_rows_say_a_token_is_in_play(client):
    _enable_backend_on_best_node()
    with app.state.testing_session_local() as db:
        for node in db.query(Node).all():
            node.visivo_backend_requires_auth = True
        db.commit()
    _, rows, _ = _votable(client)
    status = [r for r in rows if r["semantics"] == "#auxiliary"]
    assert status and all(r["link_auth"] == "optional" for r in status)


def test_soda_sync_forwards_circle_and_refuses_polygon_without_a_node(client):
    from urllib.parse import parse_qs, urlparse

    stub = client.get("/soda/sync", params={"ID": "dataset-3", "POLYGON": "1 2 3 4 5 6"}, follow_redirects=False)
    assert stub.status_code == 400
    as_circle = client.get("/soda/sync", params={"ID": "dataset-3", "CIRCLE": "103 -23 0.05"}, follow_redirects=False)
    assert as_circle.status_code == 200 and as_circle.json()["mode"] == "soda-sync-stub"
    both = client.get("/soda/sync", params={"ID": "dataset-3", "POS": "CIRCLE 1 2 3", "CIRCLE": "1 2 3"},
                      follow_redirects=False)
    assert both.status_code == 400

    _enable_backend_on_best_node()
    resp = client.get("/soda/sync", params={"ID": "dataset-3", "CIRCLE": "103 -23 0.05", "BAND": "0.2 0.22"},
                      follow_redirects=False)
    assert resp.status_code == 303
    query = parse_qs(urlparse(resp.headers["location"]).query)
    assert query["CIRCLE"] == ["103 -23 0.05"] and query["BAND"] == ["0.2 0.22"]


def test_service_inputs_parse_as_fillable_values(client):
    # A VO client fills the inputParams in from what astropy parsed: an empty
    # input must come back as an (empty) value, never as None.
    import io

    from astropy.io.votable import parse

    _enable_backend_on_best_node()
    raw = client.get("/datalink/dataset-3", params={"RESPONSEFORMAT": "votable"}).content
    votable = parse(io.BytesIO(raw))
    services = [r for r in votable.resources if r.type == "meta" and r.utype == "adhoc:service"]
    assert len(services) == 4
    for service in services:
        for group in service.groups:
            for param in group.entries:
                assert param.value is not None, (service.ID, param.name)


def test_soda_sync_by_post_redirects_with_every_parameter(client, db_session=None):
    # A 303 is followed with a GET and no body: the node's URL must carry
    # every subsetting parameter the client posted.
    from urllib.parse import parse_qs, urlparse
    from app.main import app
    from app.models.node import Node
    with app.state.testing_session_local() as db:
        node = db.query(Node).filter(Node.code == "A").one()
        node.visivo_backend_url = "http://node-a.example.org:8000"
        db.commit()
    from app.ingestion.services.ingest_service import IngestService
    with app.state.testing_session_local() as db:
        IngestService(db, source_type="manual").ingest_records([{
            "obs_id": "post-cube", "dataproduct_type": "cube", "node_id": "A",
            "access_url": "file:///data/post-cube.fits"}])
    form = {"ID": "post-cube", "POS": "CIRCLE 150 2 0.2", "BAND": "0.21 0.22",
            "TIME": "59000 59001", "RESPONSEFORMAT": "application/fits"}
    r = client.post("/soda/sync", data=form, follow_redirects=False)
    assert r.status_code == 303, r.text
    target = urlparse(r.headers["location"])
    query = {k: v[0] for k, v in parse_qs(target.query).items()}
    assert target.path.endswith("/soda/sync")
    assert query["POS"] == form["POS"] and query["BAND"] == form["BAND"]
    assert query["TIME"] == form["TIME"] and query["RESPONSEFORMAT"] == form["RESPONSEFORMAT"]
    assert query["ID"] != "post-cube"          # the replica's own identifier on the node
    # The same request by GET redirects to the same place.
    g = client.get("/soda/sync", params=form, follow_redirects=False)
    assert g.status_code == 303 and g.headers["location"] == r.headers["location"]
