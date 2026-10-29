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

NS = {"v": "http://www.ivoa.net/xml/VOTable/v1.3"}


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


def test_datalink_votable_this_rows_carry_the_routing_decision(client):
    # The replicas come best node first, each with the policy's reason, as
    # the JSON envelope's routing.replicas have them.
    names, rows = _rows(client)
    assert names.index("node_id") < names.index("rank_reason") < names.index("score")
    json_replicas = client.get("/datalink/dataset-3").json()["routing"]["replicas"]
    this_rows = [r for r in rows if r["semantics"] == "#this"]
    assert [r["node_id"] for r in this_rows] == [rep["code"] for rep in json_replicas]
    for row, rep in zip(this_rows, json_replicas):
        assert rep["rank_reason"] and row["rank_reason"] == rep["rank_reason"]
        assert row["score"] == ("" if rep["score"] is None else str(rep["score"]))


def test_datalink_votable_scores_are_doubles_and_other_rows_say_nothing(client):
    # With costs set (the resource-aware policy's), a VO reader gets them as
    # float64 on the replica rows, masked on every other row; the FIELDs are
    # typed as the DataLink VOTable needs them.
    import io
    from astropy.io.votable import parse_single_table
    from app.schemas.datalink import DataLinkResponse
    from app.vo.votable import datalink_to_votable
    from tests.test_soda_execution import _enable_backend_on_best_node

    _enable_backend_on_best_node()        # adds #auxiliary, #cutout and #proc rows
    envelope = DataLinkResponse.model_validate(client.get("/datalink/dataset-3").json())
    for i, rep in enumerate(envelope.routing.replicas):
        rep.score = 1.25 + i
        rep.rank_reason = f"{rep.code}: rtt {i + 1} ms & <measured>"
    xml = datalink_to_votable(envelope)
    root = ET.fromstring(xml)
    fields = {f.get("name"): f for f in root.findall(".//v:TABLE/v:FIELD", NS)}
    assert fields["score"].get("datatype") == "double" and fields["score"].get("arraysize") is None
    assert fields["score"].get("ucd") is None          # a cost, not an ordinal rank
    assert fields["rank_reason"].get("datatype") == "char" and fields["rank_reason"].get("arraysize") == "*"
    table = parse_single_table(io.BytesIO(xml.encode()), verify="exception").array
    semantics = [str(s) for s in table["semantics"]]
    assert "#auxiliary" in semantics and "#cutout" in semantics
    scores = table["score"]
    assert scores.dtype.kind == "f"
    expected = {rep.code: (rep.score, rep.rank_reason) for rep in envelope.routing.replicas}
    seen = set()
    for row, sem, masked in zip(table, semantics, scores.mask):
        if sem == "#this":
            score, reason = expected[str(row["node_id"])]
            assert not masked and float(row["score"]) == score and str(row["rank_reason"]) == reason
            seen.add(str(row["node_id"]))
        else:
            assert masked and str(row["rank_reason"]) == ""
    assert seen == set(expected)


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


def test_the_expected_issuer_and_the_public_discovery_url_can_be_set(client, iam, monkeypatch):
    """An IAM the service reaches on a private name: the tokens carry the
    public issuer, which SKAVA_OIDC_ISSUER names; the challenge tells the
    clients the public discovery URL, not the one the service fetches."""
    monkeypatch.setattr(settings, "oidc_wellknown", "http://keycloak:8080/realms/srcnet/.well-known/openid-configuration")
    monkeypatch.setattr(settings, "oidc_public_wellknown", "http://localhost:18300/realms/srcnet/.well-known/openid-configuration")
    monkeypatch.setattr(settings, "oidc_issuer", "http://localhost:18300/realms/srcnet")
    monkeypatch.setattr("httpx.get", lambda url, timeout: type("R", (), {"json": lambda self: {
        "issuer": "http://keycloak:8080/realms/srcnet", "jwks_uri": "http://keycloak:8080/jwk"}})())
    validator.reset()
    assert _search(client, _token(iam, iss="http://localhost:18300/realms/srcnet")).status_code == 200
    refused = _search(client, _token(iam, iss="http://keycloak:8080/realms/srcnet"))
    assert refused.status_code == 401
    assert "localhost:18300/realms/srcnet/.well-known" in refused.headers["WWW-Authenticate"]
    assert "keycloak:8080" not in refused.headers["WWW-Authenticate"]


def test_the_presented_token_is_separate_from_the_verified_one(client, monkeypatch):
    """An open instance verifies nothing and its endpoints see no token
    (None); what forwards a token on the caller's behalf reads it as
    presented, and what records who asked keeps a reference, not the token."""
    import asyncio

    from app.security.internal_api_key import presented_token, require_access_token, token_reference
    assert asyncio.run(require_access_token(authorization="Bearer abc", x_skava_access_token=None)) is None
    assert asyncio.run(presented_token(authorization="Bearer abc", x_skava_access_token=None)) == "abc"
    assert asyncio.run(presented_token(authorization=None, x_skava_access_token="xyz")) == "xyz"
    assert asyncio.run(presented_token(authorization=None, x_skava_access_token=None)) is None
    assert token_reference(None) is None
    assert token_reference("abc").startswith("token:") and "abc" not in token_reference("abc")
    assert token_reference("abc") == token_reference("abc") != token_reference("abd")
    # A job records a reference to its requester, never the credential (an
    # instance that verifies tokens; an open one records nothing).
    secret = "a-bearer-credential"
    monkeypatch.setattr(settings, "access_tokens", secret)
    auth = {"Authorization": f"Bearer {secret}"}
    job = client.post("/staging/jobs", params={"ID": "dataset-3"}, headers=auth).json()
    shown = client.get(f"/staging/jobs/{job['job_id']}", headers=auth).json()
    assert shown["requested_by"] == token_reference(secret) and secret not in str(shown)
    job = client.post("/tap/async", data={"QUERY": "SELECT * FROM ivoa.ObsCore"}, headers=auth).json()
    shown = client.get(f"/tap/async/{job['job_id']}", headers=auth).json()
    assert shown["submitted_by"] == token_reference(secret) and secret not in str(shown)
    # The SODA proxy's staging fallback records the same reference.
    job = client.post("/soda/execute", params={"ID": "dataset-3"}, headers=auth).json()
    assert job.get("requested_by") in (None, token_reference(secret)) and secret not in str(job)
    if job.get("job_id"):
        shown = client.get(f"/staging/jobs/{job['job_id']}", headers=auth).json()
        assert shown["requested_by"] == token_reference(secret) and secret not in str(shown)
    monkeypatch.setattr(settings, "access_tokens", None)
    job = client.post("/staging/jobs", params={"ID": "dataset-3"}, headers=auth).json()
    assert client.get(f"/staging/jobs/{job['job_id']}").json()["requested_by"] is None


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


def test_tap_capabilities_is_a_vosi_document_that_pyvo_reads(client):
    """A VO client reads /tap/capabilities as VOSI XML; the JSON summary
    stays available on request."""
    import io

    from pyvo.io.vosi import parse_capabilities

    r = client.get("/tap/capabilities")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    caps = parse_capabilities(io.BytesIO(r.content))
    ids = [str(c.standardid) for c in caps]
    assert "ivo://ivoa.net/std/TAP" in ids and "ivo://ivoa.net/std/VOSI#tables" in ids
    tap = next(c for c in caps if str(c.standardid) == "ivo://ivoa.net/std/TAP")
    assert tap.interfaces[0].accessurls[0].content == "http://testserver/tap"
    assert [lang.name for lang in tap.languages] == ["ADQL"]
    assert client.get("/tap/capabilities", params={"FORMAT": "json"}).json()["standard_id"] == "ivo://ivoa.net/std/TAP"
    assert client.get("/tap/capabilities", headers={"Accept": "application/json"}).json()["languages"]


def test_tap_capabilities_negotiation_and_limits(client, monkeypatch):
    from xml.etree.ElementTree import fromstring

    from app.config import settings
    from app.vo.tap_schema import TAP_DEFAULT_ROWS, TAP_MAX_ROWS, tap_capabilities_xml

    xml = {"Accept": "application/xml, application/json;q=0"}
    assert client.get("/tap/capabilities", headers=xml).headers["content-type"].startswith("application/xml")
    assert client.get("/tap/capabilities", headers={"Accept": "*/*"}).headers["content-type"].startswith("application/xml")
    assert client.get("/tap/capabilities", headers={"Accept": "text/html"}).headers["content-type"].startswith("application/xml")
    json_first = {"Accept": "application/json, */*;q=0.1"}
    assert client.get("/tap/capabilities", headers=json_first).headers["content-type"].startswith("application/json")
    from app.routers.tap import _prefers_json
    assert _prefers_json("application/xml;q=0, application/*;q=0.5"), "the specific refusal wins over the wildcard"
    assert not _prefers_json("application/json;q=0.9, application/xml")
    assert _prefers_json("APPLICATION/JSON;Q=0.9, APPLICATION/XML;Q=0.1")
    assert not _prefers_json("application/json;q=2, application/xml"), "a malformed quality value is ignored"
    assert not _prefers_json("application/json;q=inf, application/xml")
    assert not _prefers_json("") and not _prefers_json("garbage") and not _prefers_json("text/*")
    assert _prefers_json("application/json")
    # Only what the route serves counts: text/xml is not an offer, so JSON wins here.
    assert _prefers_json("application/json;q=0.9, text/*;q=1")
    # A quoted parameter may hold the separators.
    assert not _prefers_json('application/json;profile="a,b";q=0, application/xml;q=0.5')
    assert _prefers_json('application/xml;note="x;y";q=0.1, application/json')
    assert not _prefers_json("application/json;q=0.\u0669, application/xml;q=0.5"), "ASCII digits only"
    assert _prefers_json(" application/json ; Q=0.900 , application/xml ; q=0.100 ")
    # The advertised limits are the implemented ones, and a base URL with an
    # ampersand still gives well-formed XML.
    root = fromstring(client.get("/tap/capabilities").content)
    ns = {"v": "http://www.ivoa.net/xml/VOSICapabilities/v1.0"}
    assert root.find("capability/outputLimit/default", ns).text == str(TAP_DEFAULT_ROWS)
    assert root.find("capability/outputLimit/hard", ns).text == str(TAP_MAX_ROWS)
    assert client.get("/tap/sync", params={"QUERY": "SELECT * FROM ivoa.ObsCore", "MAXREC": TAP_MAX_ROWS}).status_code == 200
    assert client.get("/tap/sync", params={"QUERY": "SELECT * FROM ivoa.ObsCore", "MAXREC": TAP_MAX_ROWS + 1}).status_code in (400, 422)
    fromstring(tap_capabilities_xml("https://example.org/skava&archive"))
