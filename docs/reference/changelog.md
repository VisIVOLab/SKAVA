# Changelog

All notable changes to SKAVA. The repository follows
[semantic versioning](https://semver.org).

## Unreleased

### Added

* **End-to-end run on a real node, recorded** — a runbook for INAF
  PLEIADI-GPU from an empty account to the evidence bundle (data copied,
  image built, backend on a GPU compute node, holdings published in place,
  node registered, the chain run from a laptop), with
  ``scripts/node_provenance.sh`` (host, GPU, image, data), a generic
  ``scripts/register_node.sh`` and ``testbed/experiments/e7_real_node.py``,
  a scripted client that times and records every step against one node.

### Fixed

* **Publisher: FITS metadata of real survey products** — a degenerate
  Stokes axis (length 1) no longer makes a cube ``polarimetric`` (ASKAP,
  MeerKAT and WSRT cubes were catalogued so, and their cube operations not
  advertised); descriptive keywords (``TELESCOP``, ``INSTRUME``, ``OBJECT``,
  dates) are read from the primary HDU when the data sit in an extension (ESO
  archive products); the spectral range is computed through WCSLIB at the
  pixel grid's corners, so velocity axes (``VRAD``, ``VOPT``, legacy
  ``VELO-xxx`` and ``FELO``), ``CD``/``PC`` matrices and air wavelengths give
  the right vacuum wavelengths, and a header whose unit contradicts its
  values gives no band rather than a wrong one.

### Removed

* The Power9 runbook and ``scripts/register_power9_testbed.sh``, which
  registered a hand-written record instead of publishing the node's files.

## 0.1.2 — 2026-10-29

### Added

* **Publisher: ``obs_id`` collisions on one node** — two files that give
  one ``obs_id`` from different paths, or a file whose ``obs_id`` the node
  already published from another file that still exists, are withheld and
  reported (``failed``, ``obs_id collision``) until resolved; a file that
  takes the place of one that is gone is published as its replacement
  (the old entry becomes ``replaced``). The state records each file's
  published ``access_url`` (a column added to existing state databases).

### Changed

* **Testbed conformance** uses two HTTP sessions: the catalogue's carries
  no credential, the nodes' sends their token only to the nodes' own
  addresses (redirects included); a check verifies that no request to the
  catalogue carried it.

## 0.1.1 — 2026-10-29

### Fixed

* **Replica identity on updates** — a node holding a dataset beside others
  whose record states no checksum, while the catalogue has one, is refused
  (``replica_unverified``) and its replica quarantined until a record shows
  the same checksum. The only holder republishing without a checksum
  withdraws the stored one, so no copy can join on it later. The first
  checksum of a dataset several nodes hold quarantines the others until
  they show the same.
* **DataLink ``#this`` rows** through a node's SODA state the media type the
  node sends (``application/fits`` for FITS, by the file's name otherwise).

### Added

* **Testbed conformance** — ``make conformance`` follows every ``#this``
  link of a dataset from outside the nodes and compares status, media
  type, size and SHA-256 with what the catalogue declares.

### Changed

* The VisIVO backend's own settings are documented by VisIVO Visual
  Analytics; these pages name only what must agree with the catalogue and
  link there.

## 0.1.0 — 2026-10-29 (first public release)

Everything below, to the next heading of this level, is in 0.1.0.

### Added (October 2026)

* **DataLink 1.1 ``{links}`` endpoint** — ``GET|POST /datalink?ID=...``: one
  or more IDs, VOTable by default, fault rows for unknown or unavailable
  datasets; the TAP rows' ``access_url`` points to it.
* **License** — SKAVA is released under the Apache License 2.0, with a
  NOTICE file; ``CITATION.cff`` gives the citation metadata.
* **Resource-aware routing** — a background prober reads each node
  backend's ``/v1/ping`` and ``/v1/node/status`` (migration 0009) and the
  ``resource_aware`` policy (``SKAVA_RANKING_POLICY``) ranks replicas on
  reachability, round-trip time, CPU pressure, queue depth and free memory
  against the dataset's size. Every replica carries a ``score``, a
  ``rank_reason`` and the age of its telemetry; the DataLink names the
  policy and lists the excluded replicas with their reasons. Probe metrics
  and ``/internal/telemetry`` endpoints. ``resource_aware`` is the default
  policy and the prober runs every 10 s; nodes it cannot measure keep the
  declared order.
* **Node reports** — a node the prober cannot reach posts its own status to
  ``POST /internal/telemetry/report``, authenticated with a per-node token
  (``python -m app.security.node_token CODE``); the prober skips it while the
  report is fresh, and the newer of a probe and a report is kept.
* **SODA on the node** — ``/soda/sync`` redirects (303) to the SODA service
  of the first ranked node that can cut the dataset in place, with
  ``CIRCLE``, ``POLYGON``, ``BAND`` and ``TIME``; the DataLink advertises the
  node's SODA sync and async services and, for cubes, its moment-map and
  position–velocity operations, in JSON and as VOTable service resources.
* **OIDC** — bearer tokens from an IAM are validated (signature, expiry,
  issuer, audience) and a 401 carries the IVOA ``ivoa_bearer`` challenge;
  ``SKAVA_OIDC_ISSUER`` and ``SKAVA_OIDC_PUBLIC_WELLKNOWN`` for an IAM
  reached on a private name.
* **Federated search** — ``/federation/search`` asks the local catalogue and
  the sibling catalogues concurrently with the caller's token and merges
  the answers on ``obs_id`` (the other sites under ``also_at``); each
  source's status is reported.
* **TAP** — ``CONTAINS(s_pos, CIRCLE(...))``, TAP 1.1 ``RESPONSEFORMAT``, an
  ObsCore-like VOTable whose ``access_url`` is the DataLink document, and a
  VOSI XML ``/tap/capabilities`` with the real row limits (default 100,
  maximum 1000).
* **Testbed** (``testbed/``) — two catalogues, a Keycloak IAM, a Computing
  Broker stand-in and four simulated nodes, with pyvo conformance checks and
  the evaluation experiments; see [the testbed](../development/testbed.md).

### Fixed (October 2026)

* **Fail-closed replica identity** — with ``SKAVA_REPLICA_IDENTITY=checksum``
  (the default) a node joins a dataset's replicas only with a checksum equal
  to the catalogue's (``replica_unverified`` otherwise), and the federated
  search merges only listings with equal checksums. The publisher now sends
  the SHA-256 as the record's ``checksum``: after upgrading, run
  ``publish --force`` once on every node.
* **Product identity** — a record is refused as ``replica_conflict`` when
  its ``obs_id`` is already held by other nodes as a different product
  (another checksum, size or product type); records within one batch and
  dry runs are checked alike. A node holding the dataset beside others
  whose new record contradicts the catalogue (its file changed) is refused
  and its replica quarantined, out of the ranking, until a record proves the
  copy again with an equal checksum. The federated search no longer merges two
  different products listed under one ``obs_id``: they are returned apart,
  flagged ``identity_conflict``.
* **DataLink ``content_length``** is in bytes, as DataLink defines it: the
  exact size the publisher now records (``provenance_json.size_bytes``), not
  ObsCore's ``access_estsize``, which is in kilobytes.
* **DataLink ``#this`` rows** lead a client to the dataset: a ``file://``
  copy is linked through its node's SODA (which, unconstrained, returns the
  file as stored) and its location moves to the ``local_access_url``
  column; a copy nothing can reach gets no row.
* **TAP ``CONTAINS``** tests the dataset's centre, as ADQL defines it; the
  discovery API's ``POS`` keeps the footprint overlap.
* **SODA by POST** — ``POST /soda/sync`` (form parameters) redirects with
  every parameter in the node's URL.
* **Cone search** — ``POS=CIRCLE`` (and TAP ``CONTAINS``) now uses the exact
  spherical overlap with each dataset's footprint (haversine form); the RA
  difference used to be taken without ``cos(Dec)``, which missed datasets
  inside the circle away from the equator.
* **Publisher** — PSRFITS files named ``*.fits`` reach the PSRFITS
  extractor (extractors are ordered by priority, then name; ``*.sf`` is
  in the default ``scan.include``); a file is marked ``published`` only
  when SKAVA took its record, ``failed`` with SKAVA's reason otherwise,
  and a failed upload is recorded; ``publish -m`` records outcomes for
  the unchanged files its manifest describes; the state keeps each
  file's extraction-time fingerprint; ``watch.enabled: false`` disables
  ``watch``.
* **Ingestion** stores ``obs_title``, ``facility_name`` and
  ``instrument_name``, and a value longer than its column skips its
  record instead of failing the run on PostgreSQL.
* **Admin** — ``ADMIN_LOGIN_RATE_LIMIT_PER_MINUTE`` is enforced: failed
  sign-ins per client address per minute, then 429 with ``Retry-After``.

### Changed (October 2026)

* Discovery returns replicas in ranking order; one ranking decision is
  counted per ``/soda/execute`` request, which runs on the first replica
  that can cut in place, so what is advertised is what runs.
* Job records (staging, TAP async, SODA staging) store a hashed
  ``token_reference`` of the requester, never the token itself.
* ``/capabilities`` and the DataLink link descriptions describe the service
  as it is; the legacy flat documentation pages were folded into the
  sections of this site.
* The repository moved to <https://github.com/VisIVOLab/SKAVA>.

### Added

* **TAP ObsTAP profile upgrade** — the ``/tap/sync`` ADQL surface now supports
  range/equality predicates on whitelisted ObsCore columns (temporal/spectral
  filtering) and the ObsTAP cone-search geometry
  ``1 = CONTAINS(POINT('ICRS', s_ra, s_dec), CIRCLE('ICRS', ra, dec, radius))``,
  reusing the discovery filtering. New VOSI ``GET /tap/tables`` tableset
  (TAP_SCHEMA equivalent) so TOPCAT/pyvo can introspect columns/UCDs.
* **SODA execution (compute-next-to-data)** — ``POST /soda/execute`` performs a
  real byte-level FITS cutout by delegating to the dataset node's co-located
  VisIVO backend (``/v1/datasets/cutout``) when it serves a ``file://`` replica,
  streaming ``application/fits`` back; falls back to the staging handoff
  otherwise. New settings ``SKAVA_VISIVO_BACKEND_TOKEN`` /
  ``SKAVA_SODA_BACKEND_TIMEOUT_SECONDS``.
* **Conformant IVOA DataLink VOTable** — ``/datalink/{obs_id}`` with
  ``RESPONSEFORMAT=application/x-votable+xml`` now emits the standard ``{links}``
  columns (spec UCDs), IVOA semantics terms, and a SODA cutout service descriptor.
* DataLink capability flags (``supports_soda_sync_execution`` / ``supports_cutout``)
  and the ``cutout`` service descriptor now reflect per-dataset execution
  availability (enabled when a ranked node has a co-located VisIVO backend).
* Admin UI Phase 3 — audit history viewer with filters + CSV export.
* Federation fan-out implementation behind ``SKAVA_FEDERATED_SRC_URLS``.
* **Production deploy hardening** — compose overrides (standalone-TLS / behind
  existing reverse proxy), container hardening (``no-new-privileges``,
  ``cap_drop``, ``read_only`` + tmpfs, resource limits), nginx ``/metrics``
  block + ``/admin`` rate limit, and ``SKAVA_RUN_SEED`` to skip demo seeding
  in production.

### Fixed

* **PostgreSQL migrations** — shortened revision id ``0005_..._support``
  (33 → 29 chars); the old id overflowed ``alembic_version.version_num``
  (VARCHAR(32)) and broke ``alembic upgrade`` on real Postgres (SQLite
  silently allowed it, hiding it in CI).
* **Admin audit log on SQLite** — ``audit_log.id`` is now
  ``BigInteger().with_variant(Integer, "sqlite")`` so the PK auto-increments
  under SQLite (BIGINT PRIMARY KEY is not the rowid alias); previously every
  admin action that wrote an audit row failed the test/CI suite.
* **Admin “Add dataset” route** — ``GET /admin/datasets/{dataset_id:int}`` so
  the dynamic route no longer shadows ``/admin/datasets/new`` (which tried to
  parse ``"new"`` as an int).
* **CI test collection** — ``pythonpath = ["."]`` in pytest config so
  ``from tests.conftest import …`` resolves under plain ``pytest`` (not only
  ``python -m pytest``).

### Done

* **Admin UI Phase 2c** — bulk CSV / JSON drag-drop upload form.
  Session-authenticated, dry-run by default, server-side wraps
  ``IngestionJobService`` directly (no internal API key needed in
  the browser). 32 MB cap; per-record error table; audit row
  ``ingestion.upload`` written alongside the ingestion job.
* **Power9 testbed runbook** — step-by-step end-to-end validation
  procedure with troubleshooting matrix.
* **SLURM-backed VisIVO backend pattern** — generic integration
  recipe for any SRC running SLURM + shared filesystem (BeeGFS,
  GPFS, Lustre, NFS). Three-stable-layers approach: filesystem path,
  ``localhost`` tunnel URL, node code. Token rotation strategies.

### Changed

* (none yet)

### Fixed

* (none yet)

## Before 0.1.0: the initial feature set

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

1. Set the version in ``pyproject.toml``, ``tools/skava-publisher/pyproject.toml``,
   ``tools/skava-publisher/skava_publisher/__init__.py``, ``CITATION.cff``
   and ``docs/conf.py``.
2. Date the version's heading in this changelog.
3. Commit, then create the GitHub release with the tag ``vX.Y.Z`` and the
   changelog section as its notes. With the repository enabled on Zenodo,
   the release is archived and receives a DOI.
4. Read the Docs rebuilds the documentation from ``main``.

No container image or Apptainer SIF is built by CI: the images are built
from ``Dockerfile`` and ``tools/skava-publisher/apptainer/publisher.def``
where they are deployed.
