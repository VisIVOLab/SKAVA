# Glossary

Acronyms and project-specific terms used across the SKAVA stack.

```{glossary}

ADQL
    Astronomical Data Query Language. SQL-like dialect used by TAP.
    SKAVA's `/tap/sync` supports a subset.

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

bcrypt
    Password-hashing scheme. SKAVA uses cost factor 12 by default
    (configurable via `ADMIN_BCRYPT_ROUNDS`).

cone search
    Spatial query selecting all datasets whose centre lies within a
    circle on the sky.

compute next to data
    Architecture pattern where compute moves to where data lives,
    rather than data moving to the compute. SKAVA implements this
    via the visivo-backend service descriptor and the desktop's
    routing logic.

CSRF
    Cross-Site Request Forgery. Mitigated in the admin UI with a
    per-session HMAC token embedded in every form.

DataLink
    IVOA standard for resolving an observation id into one or more
    access URLs and service descriptors. SKAVA's `/datalink/{obs_id}`
    endpoint emits a DataLink-compatible JSON envelope.

dataproduct_type
    ObsCore field categorising a dataset:
    ``image`` \| ``cube`` \| ``dynspec`` \| ``polarimetric`` \|
    ``catalog`` \| ``event``.

dynspec
    Dynamic spectrum — a 2D time × frequency intensity map, typically
    LOFAR ICD-3 HDF5 or PSRFITS.

extractor
    Format-specific Python class in the publisher that reads a file
    and returns ObsCore-shape metadata.

federation
    Multiple SKAVA instances at different SRCs that fan-out queries
    among each other. Roadmap feature.

HDF5
    Hierarchical Data Format v5. Used by LOFAR ICD-3 dynamic-spectrum
    products.

HEALPix
    Hierarchical Equal Area isoLatitude Pixelisation of the sphere.
    SKAVA's spatial index uses it for cone-search acceleration.

ingester
    SKAVA admin UI role. Can create / edit / delete datasets, nodes
    and replicas, and trigger ingestion runs.

INAF
    Istituto Nazionale di Astrofisica — the Italian national
    institute for astrophysics, which leads SKAVA development.

IVOA
    International Virtual Observatory Alliance. Sets the standards
    SKAVA aligns with (ObsCore, TAP, DataLink, SODA, VOSI).

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

ObsCore
    IVOA Observation Core Data Model. The metadata schema SKAVA's
    `datasets` table mirrors.

obs_id
    Stable unique identifier for a dataset. UPSERT key during
    ingestion.

PSRFITS
    Pulsar FITS — extension to standard FITS used by pulsar /
    transient instruments.

publisher
    The `skava-publisher` CLI: runs on a node, extracts ObsCore
    metadata from local files, uploads JSON manifests to SKAVA.

ranking
    SKAVA's policy that orders dataset replicas by node latency,
    load, and capability scores. The top-ranked replica is the
    primary access target.

ReadTheDocs
    The hosting service for this documentation site.

replica
    One physical copy of a dataset on a specific Node. A Dataset
    may have many Replicas.

SODA
    Server-side Operations on Data Access — IVOA standard for
    cutouts and subsetting. SKAVA's `/soda/sync` validates and
    routes; execution is on the roadmap.

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
    SKAVA's `/tap/sync` exposes a subset.

VisIVO
    Visualisation Interface for the Virtual Observatory — INAF
    desktop client that consumes SKAVA discovery and routes compute
    to nearby backends.

VisIVO backend
    HTTP service co-located with a Node's storage. Implements
    ``/v1/datasets/open_skava`` and friends so the VisIVO desktop
    can open files without downloading.

visivo-backend descriptor
    Entry in SKAVA's DataLink ``service_descriptors[]`` array telling
    clients which backend URL to use for compute on this dataset's
    best replica.

viewer
    SKAVA admin UI role. Read-only access to all admin pages.

VO
    Virtual Observatory. Umbrella for the IVOA standards.

VOSI
    Virtual Observatory Service Interface. SKAVA exposes the
    capabilities endpoint at ``/vosi/capabilities``.

VOTable
    XML format for tabular data, used by TAP and DataLink responses.

WAL
    Write-Ahead Logging — PostgreSQL durability mechanism, also the
    journal mode used by the publisher's SQLite state file.

X-Internal-Api-Key
    HTTP header SKAVA's internal-ingestion endpoints require.
```
