# Changelog

All notable changes to SKAVA. The repository follows
[semantic versioning](https://semver.org).

## Unreleased

### Added

* Admin UI Phase 2c — bulk CSV / JSON drag-drop upload form wrapping
  ``/internal/ingestion/run``.
* Admin UI Phase 3 — audit history viewer with filters + CSV export.
* x86_64 + NVIDIA RTX PRO 6000 Blackwell VisIVO backend Apptainer
  recipe.
* Federation fan-out implementation behind ``SKAVA_FEDERATED_SRC_URLS``.

### Changed

* (none yet)

### Fixed

* (none yet)

## 0.1.0 — first public release (date TBD)

Initial public version of the SKAVA stack as the basis for the INAF
SRC testbed.

### Added

#### Discovery / DataLink / SODA / TAP

* Discovery endpoint with ObsCore filters, cone search, pagination.
* DataLink endpoint emitting access URLs and service descriptors,
  including the **visivo-backend** descriptor.
* SODA sync stub: validation + routing decision.
* TAP sync subset (SELECT / WHERE / ORDER BY).
* VOSI capabilities.

#### Internal ingestion

* CSV + JSON manifest parsers.
* Per-record validation with structured error output.
* IngestionJob history table.
* ``X-Internal-Api-Key`` authentication.
* Idempotent UPSERT on ``obs_id``.

#### Admin UI Phase 1

* Local username + bcrypt password authentication.
* Three roles: admin, ingester, viewer.
* CSRF token in every form.
* Dashboard with counts and recent activity.
* Append-only audit log writing on every mutation.
* CLI for user management
  (``python -m app.admin.cli create-user / reset-password / set-role
  / list-users / deactivate``).

#### Admin UI Phase 2

* Nodes CRUD with delete safety (refuses if Replicas exist).
* Datasets CRUD with replica inline management.
* Datasets search + filters + pagination.
* "Pre-fill from FITS" form helper using astropy.

#### skava-publisher CLI

* ``scan`` / ``validate`` / ``publish`` / ``watch`` / ``status``
  subcommands.
* Three built-in extractors: ``fits``, ``hdf5``, ``psrfits``.
* Entry-point-based plugin system for third-party extractors.
* Local SQLite ``state.db`` to skip already-published files.
* Apptainer recipe for ppc64le / x86_64 / aarch64.
* SHA256 checksum captured per file in provenance.

#### Compute next to data

* Backend ``/v1/datasets/open_skava`` accepting ``{ obs_id,
  access_url }``.
* Path jail via ``VISIVO_DATA_ROOT``.
* Scheme jail (file://) + extension whitelist.
* Desktop ``MainWindow::doOpenSkavaDataset`` routing logic with
  URL / srcCode matching.
* Status bar "served by" badge.
* SKAVA-tagged Recent Datasets entries with smart reopen via SKAVA
  re-query.

#### Documentation

* Sphinx + MyST docs hosted on ReadTheDocs.
* This changelog.

### Known limitations

* SODA execution not implemented (validates and routes only).
* TAP async + full ADQL geometry functions not implemented.
* Federation router stubs only.
* OIDC for admin UI not implemented (local password only).
* No built-in rate limiting (use a reverse proxy).
* No bundled Grafana dashboards / Prometheus rules (community welcome
  to contribute).

## Versioning policy

* **major** bump on incompatible API or schema changes.
* **minor** bump on backwards-compatible new features.
* **patch** bump on backwards-compatible bug fixes / docs / security
  patches.

The publisher CLI has its own semver track — the SKAVA core and
publisher are versioned independently but the internal-ingestion
API is kept backwards-compatible for at least two minor versions on
each side.

## Release process (maintainers)

1. Bump version in ``app/__init__.py`` and ``tools/skava-publisher/
   skava_publisher/__init__.py`` as needed.
2. Update this changelog under the new version heading.
3. Tag: ``git tag -s v0.1.0 -m "v0.1.0"``.
4. Push: ``git push origin v0.1.0``.
5. GitHub Actions builds the api image + publisher SIF and pushes to
   the registry.
6. ReadTheDocs auto-rebuilds the docs.
7. Announce on the mailing list.
