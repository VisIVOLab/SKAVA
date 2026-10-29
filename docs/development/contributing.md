# Contributing

How to set up a dev environment, file good issues, and submit
patches. SKAVA is open-source MIT — INAF-internal SRC needs drive
the roadmap but external contributions are welcome.

## Dev environment

```bash
git clone https://github.com/VisIVOLab/SKAVA.git
cd SKAVA

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Bring up Postgres
docker compose -f docker-compose.yml up -d db

# Migrate + seed (SKAVA_ENV=dev defaults the database URL to
# postgresql+psycopg://skava:skava@localhost:5432/skava)
alembic upgrade head
python -m app.seed

# Run uvicorn with hot reload
uvicorn app.main:app --reload --port 8000
```

The tests need no database at all (they run on in-memory SQLite, see
[testing](testing.md)).

Open <http://localhost:8000/admin/> after bootstrapping an admin
with ``python -m app.admin.cli create-user --role admin --username
dev``.

For the publisher CLI:

```bash
cd tools/skava-publisher
pip install -e ".[dev]"
```

## Coding conventions

* **Python** 3.11+ for the service (CI runs 3.11 and 3.12); the
  publisher supports 3.10+. Type hints throughout.
* **FastAPI** routers stay thin. Business logic lives in
  ``app/services/``.
* **SQLAlchemy** 2.x mapped ORM with ``Mapped[...]`` annotations and
  ``mapped_column()``. No legacy ``Column(...)``.
* **Pydantic v2** for request/response schemas in ``app/schemas/``.
* **Docstrings** in Google style; the napoleon Sphinx extension
  renders them in the API docs.
* **Tests** in ``tests/``. We use pytest with FastAPI's
  ``TestClient`` on an in-memory SQLite database.

Formatters / linters (not enforced by CI; run them before a PR):

```bash
ruff check .
ruff format .
```

## Branching and PRs

* Default branch: ``main``.
* Feature branches: ``feat/<topic>``, ``fix/<topic>``,
  ``docs/<topic>``, ``refactor/<topic>``.
* One concern per PR. Big work splits into a stack of small ones.
* PR titles should make sense as standalone changelog entries.

Each PR to ``main`` runs the ``tests`` workflow
(``.github/workflows/tests.yml``): ``pytest`` on Python 3.11 and
3.12. Build the docs locally (``make -C docs html``, warnings are
errors) when you touch ``docs/``.

Merge when all green and one ``approve`` from a maintainer.

## Issues

The repository has no issue templates; please shape an issue as one
of:

* **Bug** — minimal reproducer, expected vs actual, environment.
* **Feature request** — user story, alternatives considered.
* **Question** — for things that don't quite fit either of the
  above; we'll redirect to discussions if appropriate.

## Documentation contributions

Docs live in ``docs/`` as MyST Markdown. To preview locally:

```bash
pip install -r docs/requirements.txt sphinx-autobuild
make -C docs livehtml
```

A browser opens to the live-reloading site. Edit; it refreshes.
``make -C docs linkcheck`` checks the external links. Read the Docs
builds the public site (<https://skava.readthedocs.io>) from this
repository on every push to ``main``, with ``.readthedocs.yaml``.

Style guide:

* present tense, declarative voice
* one sentence per line in source (preserves git blame)
* code blocks always tagged with the language
* link to other pages with ``[label](relative/path)`` (MyST resolves
  the ``.md`` extension automatically)
* admonitions: ``{note}``, ``{warning}``, ``{tip}``, ``{seealso}``

## What we'd love help with

* OIDC sign-in for the admin UI (the public API already accepts
  OIDC tokens; the admin UI has local accounts only).
* An asynchronous SODA execution path (``/soda/execute`` is
  synchronous today).
* A second extractor for CASA Measurement Sets (see
  [extending the publisher](extending-extractors.md)).
* Performance work on the spatial-index lookup.
* Internationalisation of the admin UI (IT, EN, ES).

## What we'd rather you not PR

* Reformatting changes without a substantive code change.
* New optional dependencies without a clear use case.
* Breaking changes to the public API surface without an RFC
  conversation first.

## Code of conduct

We follow the
[Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
Be kind, be specific, default to writing.

## Security disclosures

Email ``security@skava.inaf.it`` rather than filing a public issue.
See the [security page](../deployment/security.md#disclosure) for
details.
