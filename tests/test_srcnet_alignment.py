"""SKAVA speaking the interfaces of the SRCNet architecture (v0.2/v0.3).

* TAP accepts the query shape SRCNet documents for its global TAP service:
  ``SELECT * FROM obscore WHERE CONTAINS(obscore.s_pos, CIRCLE('ICRS',…))=1``.
* The DataLink VOTable carries the DataLink 1.1 ``link_auth`` /
  ``link_authorized`` columns the SRCNet DataLink exposes.
* Access tokens issued by an OIDC IAM are accepted (signature against the
  issuer's JWKS, expiry, issuer, audience), and a 401 carries the
  ``ivoa_bearer`` challenge pointing at the IAM.
"""
from __future__ import annotations

import time
from xml.etree import ElementTree as ET

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.config import settings
from app.security.oidc import validator

NS = {"v": "http://www.ivoa.net/xml/VOTable/v1.4"}


# ── TAP ─────────────────────────────────────────────────────────────────────


def _tap(client, query):
    return client.get("/tap/sync", params={"REQUEST": "doQuery", "LANG": "ADQL",
                                           "QUERY": query, "FORMAT": "json"})


def test_tap_accepts_the_srcnet_example_query(client):
    ds = client.get("/discovery/dataset/dataset-3").json()["metadata"]
    ra, dec = ds["s_ra"], ds["s_dec"]
    srcnet = _tap(client, f"SELECT * FROM obscore WHERE CONTAINS(obscore.s_pos, CIRCLE('ICRS',{ra},{dec},0.5))=1")
    obstap = _tap(client, f"SELECT * FROM ivoa.ObsCore WHERE 1 = CONTAINS(POINT('ICRS', s_ra, s_dec), "
                          f"CIRCLE('ICRS', {ra}, {dec}, 0.5))")
    assert srcnet.status_code == 200, srcnet.text
    ids = lambda r: sorted(x["metadata"]["obs_id"] for x in r.json()["results"])
    assert "dataset-3" in ids(srcnet)
    assert ids(srcnet) == ids(obstap)


def test_tap_strips_table_qualifiers_and_aliases(client):
    r = _tap(client, "SELECT o.obs_id FROM ivoa.obscore AS o WHERE o.obs_id = 'dataset-3' AND ivoa.obscore.calib_level >= 0")
    assert r.status_code == 200, r.text
    assert [x["metadata"]["obs_id"] for x in r.json()["results"]] == ["dataset-3"]


def test_tap_numbers_are_not_mistaken_for_qualifiers(client):
    r = _tap(client, "SELECT * FROM obscore WHERE obscore.em_min <= 1.4e2 AND em_max >= 1.0e-9")
    assert r.status_code == 200, r.text


def test_tap_unknown_qualified_column_still_fails(client):
    r = _tap(client, "SELECT * FROM obscore WHERE obscore.not_a_column = 1")
    assert r.status_code == 400


# ── DataLink 1.1 auth columns ───────────────────────────────────────────────


def _rows(client, headers=None):
    vot = client.get("/datalink/dataset-3", params={"RESPONSEFORMAT": "votable"}, headers=headers or {})
    assert vot.status_code == 200, vot.text
    root = ET.fromstring(vot.text)
    names = [f.get("name") for f in root.findall(".//v:TABLE/v:FIELD", NS)]
    cells = [[td.text or "" for td in tr.findall("v:TD", NS)] for tr in root.findall(".//v:TR", NS)]
    assert all(len(c) == len(names) for c in cells)
    return names, [dict(zip(names, c)) for c in cells]


def test_datalink_votable_has_link_auth_columns(client):
    names, rows = _rows(client)
    assert names.index("link_auth") < names.index("link_authorized") < names.index("node_id")
    base = settings.public_base_url.rstrip("/")
    for r in rows:
        if r["access_url"].startswith(base):            # SKAVA's own links: open deployment
            assert r["link_auth"] == "false" and r["link_authorized"] == "true"
        else:                                           # a node's storage: unknown here
            assert r["link_auth"] == "" and r["link_authorized"] == ""


def test_node_service_rows_carry_the_nodes_own_auth(client, monkeypatch):
    # The SODA rows point at the node's services: their link_auth is the node's
    # rule (its backend's token), whatever SKAVA itself requires.
    from app.models.node import Node
    from app.main import app
    from tests.test_soda_execution import _enable_backend_on_best_node
    _enable_backend_on_best_node()
    monkeypatch.setattr(settings, "access_tokens", "secret-token")
    _, rows = _rows(client, {"Authorization": "Bearer secret-token"})
    services = [r for r in rows if r["semantics"] in ("#cutout", "#proc")]
    assert services and all(r["link_auth"] == "false" for r in services)
    with app.state.testing_session_local() as db:
        for node in db.query(Node).all():
            node.visivo_backend_requires_auth = True
        db.commit()
    _, rows = _rows(client, {"Authorization": "Bearer secret-token"})
    services = [r for r in rows if r["semantics"] in ("#cutout", "#proc")]
    assert services and all(r["link_auth"] == "true" for r in services)


def test_datalink_votable_has_no_self_rows(client):
    # SKAVA's own DataLink endpoint must not appear as a "#this" row. (The base
    # seed's fake replica URLs also end in /datalink/<id>, on the NODE's host.)
    own = settings.public_base_url.rstrip("/") + "/datalink/"
    _, rows = _rows(client)
    assert not any(r["access_url"].startswith(own) for r in rows)


def test_tap_votable_is_obscore_with_datalink_access(client):
    r = client.get("/tap/sync", params={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "votable",
                                        "QUERY": "SELECT * FROM obscore WHERE obs_id = 'dataset-3'"})
    root = ET.fromstring(r.text)
    names = [f.get("name") for f in root.findall(".//v:TABLE/v:FIELD", NS)]
    for col in ("obs_id", "obs_title", "target_name", "s_fov", "calib_level", "access_url", "access_format"):
        assert col in names
    row = dict(zip(names, [td.text or "" for td in root.find(".//v:TR", NS).findall("v:TD", NS)]))
    assert row["access_format"] == "application/x-votable+xml;content=datalink"
    assert row["access_url"].endswith("/datalink/dataset-3?RESPONSEFORMAT=votable")


# ── OIDC ────────────────────────────────────────────────────────────────────

ISSUER = "https://iam.example.org/"


@pytest.fixture()
def iam(monkeypatch):
    """An IAM with one RSA key, served through PyJWT's JWKS client."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True) | {"kid": "k1", "use": "sig", "alg": "RS256"}
    monkeypatch.setattr(settings, "oidc_jwks_uri", "https://iam.example.org/jwk")
    monkeypatch.setattr(settings, "oidc_wellknown", None)
    monkeypatch.setattr(settings, "oidc_audience", "skava")
    monkeypatch.setattr("jwt.PyJWKClient.fetch_data", lambda self: {"keys": [jwk]})
    validator.reset()
    yield key
    validator.reset()


def _token(key, **claims):
    now = int(time.time())
    body = {"sub": "astronomer", "iss": ISSUER, "aud": "skava", "iat": now, "exp": now + 600} | claims
    return jwt.encode(body, key, algorithm="RS256", headers={"kid": "k1"})


def _search(client, token):
    return client.get("/discovery/search", params={"limit": 1}, headers={"Authorization": f"Bearer {token}"})


def test_valid_iam_token_is_accepted(client, iam):
    assert _search(client, _token(iam)).status_code == 200


def test_expired_wrong_audience_and_foreign_key_are_refused(client, iam):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for bad in (_token(iam, exp=int(time.time()) - 3600),
                _token(iam, aud="someone-else"),
                _token(other)):
        r = _search(client, bad)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"


def test_symmetric_algorithms_are_never_accepted(client, iam):
    forged = jwt.encode({"sub": "x", "aud": "skava", "iat": int(time.time()), "exp": int(time.time()) + 60},
                        "any-shared-secret", algorithm="HS256", headers={"kid": "k1"})
    assert _search(client, forged).status_code == 401


def test_missing_token_gets_the_ivoa_bearer_challenge(client, iam, monkeypatch):
    monkeypatch.setattr(settings, "oidc_wellknown", "https://iam.example.org/.well-known/openid-configuration")
    validator.reset()
    r = client.get("/discovery/search", params={"limit": 1})
    assert r.status_code == 401
    challenge = r.headers["WWW-Authenticate"]
    assert challenge.startswith('Bearer realm="SKAVA"')
    assert 'ivoa_bearer standard_id="ivo://ivoa.net/sso#BearerToken"' in challenge
    assert "iam.example.org/.well-known/openid-configuration" in challenge


def test_static_tokens_keep_working_next_to_oidc(client, iam, monkeypatch):
    monkeypatch.setattr(settings, "access_tokens", "legacy-token")
    assert _search(client, "legacy-token").status_code == 200
    assert _search(client, _token(iam)).status_code == 200


@pytest.mark.parametrize("fmt", ["votable", "votable/td", "application/x-votable+xml;serialization=tabledata"])
def test_tap_responseformat_tap11(client, fmt):
    r = client.get("/tap/sync", params={"REQUEST": "doQuery", "LANG": "ADQL", "RESPONSEFORMAT": fmt,
                                        "QUERY": "SELECT * FROM obscore WHERE obs_id = 'dataset-3'"})
    assert r.status_code == 200, r.text
    assert "<TABLEDATA>" in r.text
