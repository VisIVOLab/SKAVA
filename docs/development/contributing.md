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

# Migrate + seed
alembic upgrade head
python -m app.seed

# Run uvicorn with hot reload
SKAVA_DATABASE_URL=postgresql+psycopg://skava:skava@localhost:5432/skava \
    uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000/admin/> after bootstrapping an admin
with ``python -m app.admin.cli create-user --role admin --username
dev``.

For the publisher CLI:

```bash
cd tools/skava-publisher
pip install -e ".[dev]"
```

## Coding conventions

* **Python** 3.10+. Type hints throughout. ``from __future__ import
  annotations`` at the top of every new file.
* **FastAPI** routers stay thin. Business logic lives in
  ``app/services/``.
* **SQLAlchemy** 2.x mapped ORM with ``Mapped[...]`` annotations and
  ``mapped_column()``. No legacy ``Column(...)``.
* **Pydantic v2** for request/response schemas in ``app/schemas/``.
* **Docstrings** in Google style; the napoleon Sphinx extension
  renders them in the API docs.
* **Tests** in ``tests/``. We use pytest with the ``httpx`` async
  client and an ephemeral PostgreSQL.

Formatters / linters:

```bash
ruff check .
ruff format .
mypy app/
```

CI enforces all three.

## Branching and PRs

* Default branch: ``main``.
* Feature branches: ``feat/<topic>``, ``fix/<topic>``,
  ``docs/<topic>``, ``refactor/<topic>``.
* One concern per PR. Big work splits into a stack of small ones.
* PR titles should make sense as standalone changelog entries.

Each PR runs:

* lint + typecheck
* unit + integration tests
* docs build (links checked)
* container build smoke test

Merge when all green and one ``approve`` from a maintainer.

## Issue templates

Three flavours:

* **Bug** — minimal reproducer, expected vs actual, environment.
* **Feature request** — user story, alternatives considered.
* **Question** — for things that don't quite fit either of the
  above; we'll redirect to discussions if appropriate.

## Documentation contributions

Docs live in ``docs/`` as MyST Markdown. To preview locally:

```bash
pip install -r docs/requirements.txt
make -C docs livehtml
```

A browser opens to the live-reloading site. Edit; it refreshes.

Style guide:

* present tense, declarative voice
* one sentence per line in source (preserves git blame)
* code blocks always tagged with the language
* link to other pages with ``[label](relative/path)`` (MyST resolves
  the ``.md`` extension automatically)
* admonitions: ``{note}``, ``{warning}``, ``{tip}``, ``{seealso}``

## What we'd love help with

* OIDC backend in ``app/admin/auth/oidc.py``.
* SODA cutout execution worker.
* Federation fan-out implementation (``app/routers/federation.py``).
* A second extractor for CASA Measurement Sets.
* Performance work on the spatial-index lookup.
* Internationalisation (IT, EN, ES). Phase 4 of the admin UI.

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
See the [security page](../deployment/security#disclosure) for
details.
