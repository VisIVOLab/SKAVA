# Testing

SKAVA's test suite lives in `tests/`. This page documents how it's
organised, how to run it locally, and what kind of test to write for
new code.

## Running tests

```bash
# Full suite
pytest -q

# A single module
pytest tests/test_discovery.py -v

# A single test
pytest -k "test_datalink_visivo_backend_descriptor"

# With coverage
pytest --cov=app --cov-report=term-missing
```

The suite uses an ephemeral PostgreSQL spun up by the test
fixtures — no external setup required.

## Suite layout

```
tests/
├── conftest.py                       # global fixtures
├── data/                             # sample CSV / JSON / FITS for ingestion tests
├── test_api.py                       # high-level API smoke
├── test_discovery_*.py               # /discovery/* endpoints
├── test_datalink.py                  # /datalink/* + visivo-backend descriptor
├── test_ingestion.py                 # CSV + JSON parsers, validators
├── test_internal_ingestion_api.py    # /internal/ingestion/* with auth
├── test_production_readiness*.py     # ranking, replicas, edge cases
├── test_production_hardening.py      # request id, error envelope, log format
├── test_seed.py                      # idempotent seed behaviour
└── admin/
    ├── test_auth.py                  # login, logout, CSRF
    ├── test_rbac.py                  # require_role guards
    ├── test_audit.py                 # @audited decorator behaviour
    └── test_nodes_datasets.py        # CRUD routes
```

## Key fixtures

```{list-table}
:header-rows: 1
:widths: 25 75

* - Fixture
  - What it provides
* - ``db_session``
  - A SQLAlchemy session bound to a transaction that rolls back at
    teardown. Use for unit tests.
* - ``client``
  - An ``httpx.AsyncClient`` pointed at the SKAVA app. Default
    headers include ``X-Request-Id`` for log correlation in test
    output.
* - ``test_internal_key``
  - A pre-configured internal API key valid for the test app.
* - ``test_admin_user`` / ``test_ingester_user`` / ``test_viewer_user``
  - Pre-seeded admin UI users for RBAC tests.
* - ``logged_in_client``
  - A ``client`` with a valid session cookie for ``test_admin_user``.
* - ``sample_dataset_factory``
  - Build a dataset with sensible defaults; override fields per test.
```

## Writing tests for routes

```python
def test_discovery_search_filters_by_collection(client, sample_dataset_factory):
    sample_dataset_factory(obs_collection="foo")
    sample_dataset_factory(obs_collection="bar")
    sample_dataset_factory(obs_collection="bar")

    r = client.get("/discovery/search?obs_collection=bar")

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert all(m["metadata"]["obs_collection"] == "bar"
               for m in body["results"])
```

Patterns we follow:

* arrange / act / assert blocks separated by a blank line
* one assertion family per test (``status_code`` + ``total`` is fine;
  asserting 12 unrelated things is not)
* parametrize for table-driven tests

## Writing tests for services

```python
def test_datalink_emits_visivo_backend_descriptor(
        db_session, sample_dataset_factory):
    ds = sample_dataset_factory(
        replicas=[{"node": "POWER9",
                    "node.visivo_backend_url": "http://power9:8000"}],
    )
    svc = DataLinkService(db_session)
    response = svc.resolve(ds.obs_id)
    descriptors = [d for d in response.service_descriptors
                   if d.service_type == "visivo-backend"]
    assert len(descriptors) == 1
    assert descriptors[0].endpoint == "http://power9:8000"
    assert descriptors[0].node_code == "POWER9"
```

## Writing tests for the admin UI

```python
def test_create_node_requires_ingester(logged_in_client, test_viewer_user):
    # viewer can't add nodes
    logged_in_client.cookies.set("...", test_viewer_user.session_cookie)
    r = logged_in_client.post("/admin/nodes/new", data={...})
    assert r.status_code == 403
```

CSRF token handling in tests:

```python
def csrf_token(client):
    r = client.get("/admin/nodes/new")
    soup = BeautifulSoup(r.text, "html.parser")
    return soup.find("input", {"name": "csrf_token"})["value"]
```

## Integration tests with the publisher

The publisher has its own pytest suite under
``tools/skava-publisher/tests/``. An end-to-end test brings up an
ephemeral SKAVA and calls the publisher CLI against it:

```python
def test_publisher_round_trip(skava_app, tmp_path):
    # ... arrange a manifest ...
    result = subprocess.run(
        ["skava-publisher", "--config", str(cfg),
         "publish", "-m", str(manifest), "-y"],
        env={**os.environ, "SKAVA_INTERNAL_API_KEY": skava_app.internal_key},
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    # ... assert SKAVA's catalogue contains the records ...
```

## Test data

Put sample files under ``tests/data/`` and reference them via
``Path(__file__).parent / "data" / "...``. Keep them small
(< 1 MB).

For FITS / HDF5 fixtures, generate on the fly with astropy / h5py
rather than committing binary blobs. The
``conftest.py::sample_fits_factory`` fixture helps.

## What we don't test (today)

* Performance under load — done ad-hoc with ``locust``; CI doesn't
  enforce SLOs.
* Cross-browser compatibility of the admin UI — covered by manual
  smoke tests pre-release.
* Apptainer image bring-up — the recipe's ``%test`` section is the
  smoke; full integration is manual.

## Continuous integration

GitHub Actions runs on every push:

* ``ruff check`` + ``ruff format --check`` (5 s)
* ``mypy app/`` (45 s)
* ``pytest -q`` (~2 min including ephemeral Postgres setup)
* ``sphinx-build`` of the docs (~30 s)
* ``docker build`` of the api image (~5 min)

A PR is mergeable when all jobs are green.

## Tips

* Use ``pytest -x`` (stop on first failure) when iterating.
* Use ``pytest --pdb`` to drop into a debugger on failure.
* Tests that hit the network or external APIs should be marked
  ``@pytest.mark.external`` and skipped by default in CI.
