# Testing

SKAVA's test suite lives in `tests/`. This page documents how it's
organised, how to run it locally, what kind of test to write for
new code, and the testbed used for end-to-end runs.

## Running tests

```bash
# Full suite (209 tests in 23 modules)
pytest -q

# A single module
pytest tests/test_federation.py -v

# A single test
pytest -k "test_discovery_dataset_4_best_node_b"

# Collection only (what would run)
pytest -q --co | tail -3
```

`tests/conftest.py` sets `SKAVA_DATABASE_URL` to in-memory SQLite,
`SKAVA_ENV=dev` and a test `INTERNAL_API_KEY` before the app is
imported, and every test gets a fresh seeded database — no PostgreSQL
or other external setup is required. `pyproject.toml` sets
`testpaths = ["tests"]` and puts the repository root on `sys.path`,
so plain `pytest` and `python -m pytest` behave the same.

## Suite layout

```
tests/
├── conftest.py                          # client / admin fixtures
├── data/                                # ingest_valid.csv/.json, ingest_invalid.csv
├── test_smoke.py                        # core endpoints answer
├── test_api.py                          # availability, metrics, capabilities, discovery, ranking
├── test_integration.py                  # discovery → access flow
├── test_access_datalink.py              # /access + DataLink content
├── test_datalink_endpoint.py            # /datalink links, service descriptors, SODA descriptor
├── test_soda_sync.py                    # /soda/sync parameters (ID, POS, BAND, TIME) and validation
├── test_soda_execution.py               # /soda/execute delegation to node backends
├── test_tap_adql.py                     # /tap sync/async + ADQL subset
├── test_srcnet_alignment.py             # SRCNet/IVOA alignment (TAP, DataLink VOTable), OIDC tokens
├── test_federation.py                   # /federation/search fan-out and merge
├── test_ranking.py                      # static ranking policy
├── test_resource_ranking.py             # resource-aware policy
├── test_telemetry.py                    # node prober + /internal/telemetry
├── test_ingestion.py                    # CSV + JSON parsers, validators
├── test_internal_ingestion_api.py       # /internal/ingestion/* with auth
├── test_production_hardening.py         # pagination limits, private replicas, VOTable / TAP formats
├── test_production_readiness_phase2.py  # provenance/PID, staging jobs, TAP async, spatial cells
├── test_broker_mock.py                  # testbed/broker_mock (Computing Broker stand-in)
├── test_admin_auth.py                   # login, logout, CSRF
├── test_admin_dashboard.py              # dashboard counts, activity, per-node listing
├── test_admin_nodes.py                  # node CRUD
├── test_admin_history.py                # audit history viewer
└── test_admin_csv_export.py             # CSV exports
```

## Key fixtures

```{list-table}
:header-rows: 1
:widths: 25 75

* - Fixture
  - What it provides
* - ``client``
  - A FastAPI ``TestClient`` on a fresh in-memory SQLite database,
    created from the models and seeded with the demo fixtures
    (``app.services.seed.seed_data``). ``get_db`` is overridden; the
    session factory is on ``app.state.testing_session_local`` for
    tests that need direct DB access.
* - ``admin_user``
  - An ``admin``-role user in that database.
* - ``admin_client``
  - The ``client`` after a real ``GET``/``POST /admin/login``
    (CSRF token included), so its cookie jar holds a valid session.
```

Settings are changed per test with ``monkeypatch.setattr(settings,
…)``, and outbound HTTP (siblings, node backends, the IAM) is faked
with ``httpx.MockTransport`` — see ``test_federation.py`` and
``test_telemetry.py``.

## Writing tests for routes

```python
def test_discovery_search_filters_by_collection(client):
    r = client.get("/discovery/search", params={"COLLECTION": "skava-demo"})

    assert r.status_code == 200
    body = r.json()
    assert all(m["metadata"]["obs_collection"] == "skava-demo"
               for m in body["results"])
```

Patterns we follow:

* arrange / act / assert blocks separated by a blank line
* one assertion family per test (``status_code`` + ``total`` is fine;
  asserting 12 unrelated things is not)
* parametrize for table-driven tests

## Writing tests for the admin UI

Mutating admin routes need the CSRF token from the form:

```python
import re

def _csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m, "no csrf_token in page"
    return m.group(1)


def test_node_create_round_trip(admin_client):
    csrf = _csrf(admin_client.get("/admin/nodes/new").text)

    r = admin_client.post("/admin/nodes/new",
                          data={"code": "TESTNODE", ..., "csrf_token": csrf},
                          follow_redirects=False)

    assert r.status_code in (302, 303)
```

## Test data

Put sample files under ``tests/data/`` and reference them via
``Path(__file__).parent / "data" / "..."``. Keep them small
(< 1 MB). For FITS / HDF5 fixtures, generate on the fly with astropy /
h5py rather than committing binary blobs.

## The testbed

`testbed/` is a reproducible federation on one machine, for the
end-to-end runs the unit suite cannot do: two SKAVA catalogues
(`:18000` open, `:18001` requiring the IAM's tokens, federated with
each other), a Keycloak IAM (`:18300`, realm `srcnet`), a Computing
Broker stand-in (`:18200`) and four simulated SRC nodes — VisIVO
Visual Analytics backends with different memory, CPU and network
links (`:18101`–`18104`). The catalogues run the `resource_aware`
policy with the prober on. `testbed/README.md` has the details and
the credentials (development-only).

It needs Docker with Compose v2, this repository's `.venv`, and the
VisIVO Visual Analytics repository next to this one (`VISIVO_REPO` to
point elsewhere), from which the node image is built.

```{list-table}
:header-rows: 1
:widths: 30 70

* - `make` target (in `testbed/`)
  - What it does
* - `data`
  - Generate the science data (`PROFILE=ci` default, `paper` for the
    large cubes).
* - `node-base`
  - Build the VisIVO backend base image the nodes are built on.
* - `up`
  - Build and start catalogues, IAM, broker and nodes.
* - `seed`
  - Register the nodes and publish each node's holdings in place with
    `skava-publisher`.
* - `admin`
  - Create a web-admin account on both catalogues.
* - `status`
  - What the catalogues (`/availability?include_nodes=true`) and the
    broker know.
* - `conformance`
  - Read TAP, DataLink, a node's SODA and UWS job list with pyvo from
    inside the testbed network.
* - `experiments`, `experiment-e1`, `experiment-e6`
  - The scripted evaluation (placement, failure, bytes moved, source
    finding, federation; E1 is the routing benchmark on PostgreSQL),
    writing `results/`.
* - `figures`, `tables`
  - Figures and LaTeX tables from `results/`.
* - `down`, `clean`
  - Stop and remove everything (`clean` also removes the data).
```

```bash
cd testbed
make data up seed admin
make status
make down
```

`test_broker_mock.py` covers the broker stand-in's placement logic
without the testbed running.

## The publisher's tests

`tools/skava-publisher/tests/` checks the publisher on its own: the
extractor order (PSRFITS before plain FITS), the state each file is left
in after a publish (published only when SKAVA took the record, failed
otherwise, the extraction-time fingerprint kept), `publish -m` with its
file fingerprints, and `watch.enabled`. It needs the publisher
installed, and is not part of the CI workflow:

```bash
cd tools/skava-publisher
pip install -e . pytest
pytest
```

## What we don't test (today)

* Performance under load — the routing and discovery benchmarks
  (`scripts/benchmark_routing.py`, `scripts/benchmark_discovery.py`)
  are run by hand; CI doesn't enforce SLOs.
* PostgreSQL-specific behaviour — the suite runs on SQLite; the
  testbed runs on PostgreSQL.
* Cross-browser compatibility of the admin UI — covered by manual
  smoke tests pre-release.
* Apptainer image bring-up — the publisher recipe's ``%test`` section
  is the smoke; full integration is manual.

## Continuous integration

The `tests` workflow (`.github/workflows/tests.yml`) runs on every
push to and pull request against `main`:

* Python 3.11 and 3.12 (matrix), pip cache keyed on `pyproject.toml`
* `pip install -e ".[dev]"`
* `pytest -v --tb=short` with `SKAVA_DATABASE_URL` set to in-memory
  SQLite

A PR is mergeable when both jobs are green. A second workflow mirrors
`docs/` to the documentation site on pushes to `main`; there is no lint,
type-check, docs-build or image-build job.

## Tips

* Use ``pytest -x`` (stop on first failure) when iterating.
* Use ``pytest --pdb`` to drop into a debugger on failure.
* Never let a test reach the network: fake outbound calls with
  ``httpx.MockTransport``.
