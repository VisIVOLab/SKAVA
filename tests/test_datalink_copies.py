# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""What the DataLink {links} rows promise about a dataset's copies: a "#this"
row leads a client to the dataset, and content_length is in bytes."""
from xml.etree import ElementTree as ET

import pytest

from app.main import app
from app.models.dataset import Dataset
from app.models.replica import DatasetReplica

NS = {"v": "http://www.ivoa.net/xml/VOTable/v1.3"}


def _rows(client, obs_id="dataset-3"):
    root = ET.fromstring(client.get(f"/datalink/{obs_id}", params={"RESPONSEFORMAT": "votable"}).text)
    names = [f.get("name") for f in root.findall(".//v:TABLE/v:FIELD", NS)]
    cells = [[td.text or "" for td in tr.findall("v:TD", NS)] for tr in root.findall(".//v:TR", NS)]
    assert all(len(c) == len(names) for c in cells)
    return [dict(zip(names, c)) for c in cells]


def _set(size_bytes=None, estsize=1, endpoint=None, backend=None, requires_auth=False):
    with app.state.testing_session_local() as db:
        dataset = db.query(Dataset).filter(Dataset.obs_id == "dataset-3").one()
        dataset.access_estsize = estsize
        dataset.provenance_json = {"size_bytes": size_bytes} if size_bytes is not None else {}
        for replica in db.query(DatasetReplica).filter(DatasetReplica.dataset_id == dataset.id):
            if endpoint is not None:
                replica.access_endpoint = endpoint.format(node=replica.node.code)
            replica.node.visivo_backend_url = backend
            replica.node.visivo_backend_requires_auth = requires_auth
        db.commit()


def _copies(rows):
    return [r for r in rows if r["semantics"] == "#this" and not r["error_message"]]


def test_content_length_is_the_files_size_in_bytes(client):
    # The publisher's exact size wins; the ObsCore estimate is kilobytes.
    _set(size_bytes=3_221_234_567, estsize=3_145_736,
         endpoint="https://{node}.example.org/cube.fits")
    copies = _copies(_rows(client))
    assert copies and {r["content_length"] for r in copies} == {"3221234567"}
    assert client.get("/datalink/dataset-3").json()["primary_access"]["content_length"] == 3_221_234_567


def test_without_the_exact_size_the_estimate_is_scaled_to_bytes(client):
    _set(estsize=2048, endpoint="https://{node}.example.org/cube.fits")
    assert {r["content_length"] for r in _copies(_rows(client))} == {str(2048 * 1024)}


def test_a_node_local_copy_is_reached_through_the_nodes_soda(client):
    _set(size_bytes=1000, endpoint="file:///data/{node}/cube.fits", backend="http://backend:8000",
         requires_auth=True)
    rows = _rows(client)
    copies = _copies(rows)
    assert copies
    for row in copies:
        # Every #this access_url is something a client can retrieve.
        assert row["access_url"].startswith("http://backend:8000/soda/sync?ID=file%3A%2F%2F%2Fdata%2F")
        assert row["local_access_url"] == f"file:///data/{row['node_id']}/cube.fits"
        assert row["link_auth"] == "true"
        assert row["content_type"] == "application/fits"     # what the node's SODA sends
        # Unconstrained, the node's SODA returns the file as stored.
        assert row["content_length"] == "1000"
    assert not any(r["access_url"].startswith("file:") for r in rows)


def test_a_local_copy_without_a_node_service_is_not_offered_as_a_link(client):
    _set(endpoint="file:///data/{node}/cube.fits", backend=None)
    rows = _rows(client)
    assert _copies(rows) == []
    faults = [r for r in rows if r["error_message"]]
    assert len(faults) == 1 and faults[0]["error_message"].startswith("NotFoundFault")
    assert faults[0]["semantics"] == "#this"


def test_pyvo_reads_the_copies(client):
    from astropy.io.votable import parse
    from io import BytesIO

    _set(size_bytes=1000, endpoint="file:///data/{node}/cube.fits", backend="http://backend:8000")
    body = client.get("/datalink/dataset-3", params={"RESPONSEFORMAT": "votable"}).content
    table = parse(BytesIO(body)).get_first_table().to_table()
    this = table[table["semantics"] == "#this"]
    assert len(this) == 2 and all(str(u).startswith("http://backend:8000/soda/sync?") for u in this["access_url"])


def test_a_copy_neither_a_client_nor_the_node_reads_gets_no_link(client):
    _set(size_bytes=1000, endpoint="sftp://{node}.example.org/cube.fits", backend="http://backend:8000")
    rows = _rows(client)
    assert _copies(rows) == [] and rows[0]["error_message"].startswith("NotFoundFault")


def test_a_stale_exact_size_gives_way_to_the_estimate(client):
    # The file was replaced (new estimate) by a record without provenance.
    _set(size_bytes=102_400, estsize=200, endpoint="https://{node}.example.org/cube.fits")
    assert {r["content_length"] for r in _copies(_rows(client))} == {str(200 * 1024)}


def test_an_exact_size_without_an_estimate_is_not_trusted(client):
    # A replacement that stated no size cleared the estimate; the old exact
    # size describes the old file.
    _set(size_bytes=102_400, estsize=None, endpoint="https://{node}.example.org/cube.fits")
    assert {r["content_length"] for r in _copies(_rows(client))} == {""}


@pytest.mark.parametrize("name, media", [("cube.fits", "application/fits"), ("cube%2Efits", "application/fits"),
                                         ("cube.fits.gz", "application/gzip"),
                                         ("search.sf", "application/octet-stream"),
                                         ("beam.h5", "application/x-hdf5")])
def test_a_node_local_row_states_the_type_the_node_will_send(client, name, media):
    _set(size_bytes=1000, endpoint="file:///data/{node}/" + name, backend="http://backend:8000")
    assert {r["content_type"] for r in _copies(_rows(client))} == {media}
