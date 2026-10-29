# Glossary

Acronyms and project-specific terms used across the SKAVA stack.

```{glossary}

ADQL
    Astronomical Data Query Language. SQL-like dialect used by TAP.
    SKAVA's `/tap/sync` and `/tap/async` support a subset over
    ``ivoa.ObsCore``.

API key
    Static shared secret used to authenticate service-to-service
    calls into SKAVA's internal endpoints. Configured via
    ``INTERNAL_API_KEY``.

Apptainer
    Container runtime preferred on HPC and shared SRCs. Successor to
    Singularity. Runs in user space, no root daemon, supports
    ppc64le natively.

audit log
    Append-only table (`audit_log`) recording every mutating action
    in SKAVA with actor, target, IP, request id, and an optional
    before/after diff.

bearer token
    Access token sent as ``Authorization: Bearer <token>``. SKAVA's
    public endpoints accept a static token (``SKAVA_ACCESS_TOKENS``) or
    an OIDC access token from the configured IAM, and are open when
    neither is configured.

bcrypt
    Password-hashing scheme. SKAVA uses cost factor 12 by default
    (configurable via `ADMIN_BCRYPT_ROUNDS`).

cone search
    Spatial query selecting all datasets whose centre lies within a
    circle on the sky.

compute next to data
    Architecture pattern where compute moves to where data lives,
    rather than data moving to the compute. SKAVA implements this
    via the visivo-backend and node SODA service descriptors, the
    303 redirect of ``/soda/sync`` to the node, the desktop's routing
    logic and the Computing Broker's placement.

Computing Broker
    SRCNet service that places batch jobs (e.g. a source finder) on a
    node. It asks SKAVA's DataLink where the dataset is and takes the
    first ranked node whose backend has the software and the memory the
    job needs. The testbed ships a stand-in (``testbed/broker_mock``).

CSRF
    Cross-Site Request Forgery. Mitigated in the admin UI with a
    per-session HMAC token embedded in every form.

DataLink
    IVOA standard for resolving an observation id into one or more
    access URLs and service descriptors. SKAVA's `/datalink/{obs_id}`
    endpoint emits a DataLink-compatible JSON envelope, or a DataLink
    VOTable with ``RESPONSEFORMAT=votable``.

dataproduct_type
    ObsCore field categorising a dataset (``image``, ``cube``, …).
    SKAVA stores it as given; the publisher emits ``image``, ``cube``
    and ``dynspec``. Moment and PV descriptors are offered for
    ``cube`` only.

dynspec
    Dynamic spectrum — a 2D time × frequency intensity map, typically
    LOFAR ICD-3 HDF5 or PSRFITS.

extractor
    Format-specific Python class in the publisher that reads a file
    and returns ObsCore-shape metadata.

federation
    Multiple SKAVA instances at different SRCs searched together:
    ``/federation/search`` asks the local catalogue and every sibling
    in ``SKAVA_FEDERATED_SRC_URLS`` with the caller's token, and merges
    the answers on ``obs_id`` (``also_at`` lists the other sites).

HDF5
    Hierarchical Data Format v5. Used by LOFAR ICD-3 dynamic-spectrum
    products.

HEALPix
    Hierarchical Equal Area isoLatitude Pixelisation of the sphere.
    SKAVA's spatial index is a simpler equal-angle sky cell
    (``order8:raN:decM``) that can later be replaced by HEALPix / MOC
    identifiers without changing the API.

IAM
    Identity and Access Management: the SRCNet service (INDIGO IAM, or
    Keycloak in the testbed) that issues the OIDC tokens SKAVA
    validates. Configured with ``IAM_WELLKNOWN_ENDPOINT``.

ingester
    SKAVA admin UI role. Can create / edit / delete datasets, nodes
    and replicas, and trigger ingestion runs.

INAF
    Istituto Nazionale di Astrofisica — the Italian national
    institute for astrophysics, which leads SKAVA development.

IVOA
    International Virtual Observatory Alliance. Sets the standards
    SKAVA aligns with (ObsCore, TAP, DataLink, SODA, VOSI).

ivoa_bearer
    IVOA SSO challenge SKAVA adds to the ``WWW-Authenticate`` header of
    a 401, naming the IAM's discovery URL so a client knows where to
    obtain a token.

manifest
    JSON or CSV file the publisher uploads to SKAVA. One record per
    dataset, ObsCore-shaped.

MJD
    Modified Julian Date. SKAVA uses MJD UTC for ``t_min`` /
    ``t_max``.

MyST
    Markedly Structured Text — Markdown extension used in these
    docs. CommonMark plus directives.

Node
    A federation member in SKAVA's catalogue: a site / data centre
    that hosts one or more dataset replicas.

node SODA
    The IVOA SODA service of a node's VisIVO backend: ``/soda/sync``
    for cutouts and ``/soda/async`` for UWS jobs (``OPERATION=CUTOUT``,
    ``MOMENT``, ``PV``). SKAVA advertises it in DataLink and redirects
    ``/soda/sync`` to it.

ObsCore
    IVOA Observation Core Data Model. The metadata schema SKAVA's
    `datasets` table mirrors.

obs_id
    Stable unique identifier for a dataset. UPSERT key during
    ingestion, and the key federated results are merged on.

OIDC
    OpenID Connect. SKAVA validates OIDC access tokens against the
    IAM's key set, expiry, issuer and, optionally, audience.

prober
    SKAVA's background task that measures each node backend's
    ``/v1/ping`` round trip and reads its ``/v1/node/status`` every
    ``SKAVA_TELEMETRY_INTERVAL_SECONDS``, feeding the resource-aware
    ranking.

PSRFITS
    Pulsar FITS — extension to standard FITS used by pulsar /
    transient instruments.

publisher
    The `skava-publisher` CLI: runs on a node, extracts ObsCore
    metadata from local files, uploads JSON manifests to SKAVA.

rank_reason
    Per-replica explanation of its place in the ranking, published in
    discovery, DataLink and the DataLink VOTable, alongside ``score``.
    Replicas set aside appear in ``routing.excluded`` with their reason.

ranking
    SKAVA's policy that orders dataset replicas: ``static`` by the
    latency, load and capability scores declared per node, or
    ``resource_aware`` by the telemetry the nodes' backends report
    (round trip, CPU pressure, queue, free memory). The top-ranked
    replica is the primary access target.

ReadTheDocs
    The hosting service for this documentation site.

replica
    One physical copy of a dataset on a specific Node. A Dataset
    may have many Replicas.

SODA
    Server-side Operations on Data Access — IVOA standard for
    cutouts and subsetting. SKAVA's `/soda/sync` redirects (303) to the
    node SODA service when a node can process the dataset in place, and
    otherwise validates and routes; `/soda/execute` is a non-standard
    proxy that has the node's co-located VisIVO backend compute the
    cutout.

SKA
    Square Kilometre Array — the radio observatory the catalogue
    serves data for.

SRC
    SKA Regional Centre. Each SRC runs (at minimum) data storage;
    in SKAVA's model, each SRC may also run a VisIVO backend.

state.db
    SQLite file the publisher uses to track files already
    published (avoid re-processing on re-run).

TAP
    Table Access Protocol — IVOA endpoint for ADQL queries.
    SKAVA's `/tap/sync` and `/tap/async` expose a subset, with the
    VOSI ``/tap/tables`` and ``/tap/capabilities`` documents.

testbed
    ``testbed/``: a docker-compose federation on one machine (two
    catalogues, Keycloak, a broker stand-in, four VisIVO backend nodes
    with different resources) used to exercise routing, near-data
    operations and federation.

UWS
    Universal Worker Service — IVOA pattern for asynchronous jobs,
    followed by the node SODA service's ``/soda/async``.

VisIVO Visual Analytics
    INAF desktop client (Visualisation Interface for the Virtual
    Observatory) that consumes SKAVA discovery and routes compute to
    nearby backends.

VisIVO backend
    HTTP service co-located with a Node's storage. Implements
    ``/v1/datasets/open_skava``, ``/v1/ping``, ``/v1/node/status``,
    the node SODA service and friends, so VisIVO Visual Analytics and
    VO clients can work on files without downloading them.

visivo-backend descriptor
    Entry in SKAVA's DataLink ``service_descriptors[]`` array telling
    clients which backend URL to use for compute on this dataset; one
    per ranked node with a backend, best first.

viewer
    SKAVA admin UI role. Read-only access to all admin pages.

VO
    Virtual Observatory. Umbrella for the IVOA standards.

VOSI
    Virtual Observatory Service Interface. SKAVA exposes
    ``/availability`` and ``/capabilities`` for the service, and
    ``/tap/tables`` and ``/tap/capabilities`` for TAP.

VOTable
    XML format for tabular data, used by TAP and DataLink responses.

WAL
    Write-Ahead Logging — PostgreSQL durability mechanism, also the
    journal mode used by the publisher's SQLite state file.

X-Internal-Api-Key
    HTTP header SKAVA's internal-ingestion endpoints require.
```
