# ObsCore fields

SKAVA's ``datasets`` table mirrors the IVOA ObsCore data model with a
few SKAVA-specific extensions. This page is the canonical column
reference.

## Core ObsCore fields

Only ``obs_id`` is NOT NULL in the database; every other column is
nullable. The ingestion API additionally requires ``dataproduct_type``
(plus the replica's ``node_id`` and ``access_url``).

```{list-table}
:header-rows: 1
:widths: 22 12 16 50

* - Column
  - Type
  - Length / range
  - Meaning
* - ``obs_id``
  - VARCHAR
  - 128
  - Unique stable identifier. UPSERT key.
* - ``obs_collection``
  - VARCHAR
  - 128
  - Survey / collection grouping (e.g. ``skava-testbed``). Indexed.
* - ``dataproduct_type``
  - VARCHAR
  - 64
  - Free string, by convention the ObsCore vocabulary plus SKAVA
    extensions: ``image`` \| ``cube`` \| ``dynspec`` \|
    ``polarimetric`` \| ``catalog`` \| ``event``. Indexed. Only
    ``cube`` gets the node moment/PV descriptors in DataLink.
* - ``calib_level``
  - INT
  - 0–4
  - ObsCore calibration level: 0 raw instrumental, 1 instrumental in
    standard format, 2 calibrated science-ready, 3 enhanced data
    product, 4 analysis product. Not range-checked on ingestion.
* - ``target_name``
  - VARCHAR
  - 128
  - Object the observation targets.
* - ``facility_name``
  - VARCHAR
  - 128
  - Telescope / observatory name. Not read by the ingestion API
    (set by seeding or the admin UI).
* - ``instrument_name``
  - VARCHAR
  - 128
  - Instrument / camera / backend. Not read by the ingestion API.
```

## Spatial fields

```{list-table}
:header-rows: 1
:widths: 22 14 14 50

* - Column
  - Type
  - Unit
  - Meaning
* - ``s_ra``
  - DOUBLE
  - deg
  - Right ascension of the field centre (ICRS), in [0, 360].
* - ``s_dec``
  - DOUBLE
  - deg
  - Declination of the field centre (ICRS), in [-90, 90].
* - ``s_fov``
  - DOUBLE
  - deg
  - Diameter of the smallest enclosing circle of the field (> 0).
    Half of it widens the ``POS`` / ``CONTAINS`` cone match.
* - ``spatial_index_order``
  - INT
  - order
  - Order of the sky cell (8 for ingested rows).
* - ``spatial_index_cell``
  - VARCHAR(64)
  - cell key
  - ``order<N>:ra<i>:dec<j>``, an equal-angle sky bin
    (2·2^N bins in RA, 2^N in Dec) computed on ingestion from
    ``s_ra``/``s_dec``. Not HEALPix; a stable key that a HEALPix/MOC
    index can later replace. Queried by the ``SPATIAL_CELL`` discovery
    filter; the cone search itself uses ``s_ra``/``s_dec``/``s_fov``.
```

## Time fields

```{list-table}
:header-rows: 1
:widths: 22 14 14 50

* - Column
  - Type
  - Unit
  - Meaning
* - ``t_min``
  - DOUBLE
  - MJD (UTC)
  - Start of the observation.
* - ``t_max``
  - DOUBLE
  - MJD (UTC)
  - End of the observation. Equals ``t_min`` for snapshots.
```

## Spectral fields

```{list-table}
:header-rows: 1
:widths: 22 14 14 50

* - Column
  - Type
  - Unit
  - Meaning
* - ``em_min``
  - DOUBLE
  - m (wavelength)
  - Lower spectral bound.
* - ``em_max``
  - DOUBLE
  - m (wavelength)
  - Upper spectral bound.
```

Note: SKAVA stores **wavelength** (metres). The publisher's spectral
extractor converts from frequency (Hz) automatically when needed.

## Access fields

```{list-table}
:header-rows: 1
:widths: 22 14 14 50

* - Column
  - Type
  - Unit
  - Meaning
* - ``access_format``
  - VARCHAR(128)
  - —
  - MIME-like type: ``image/fits`` \| ``application/x-hdf5`` \|
    ``application/x-psrfits``.
* - ``access_estsize``
  - INT
  - KB
  - Estimated payload size. Shown in DataLink and used by the
    ``resource_aware`` ranking policy to estimate the memory a node
    needs (× ``SKAVA_RANKING_MEMORY_FACTOR``).
```

The actual access URL lives on the ``dataset_replicas`` table,
which can have multiple rows per dataset.

## Provenance fields

```{list-table}
:header-rows: 1
:widths: 22 14 14 50

* - Column
  - Type
  - —
  - Meaning
* - ``doi``
  - VARCHAR(256)
  - —
  - DataCite DOI when available.
* - ``pid``
  - VARCHAR(256)
  - —
  - Other persistent identifier (Handle, ARK, …).
* - ``citation``
  - TEXT
  - —
  - Free-form citation block.
* - ``license``
  - VARCHAR(128)
  - —
  - SPDX-like license tag (``CC-BY-4.0``, ``CC0``, …).
* - ``source_type``
  - VARCHAR(64)
  - —
  - Where this row came from: ``skava-publisher`` for the publisher
    CLI, otherwise the manifest format (``csv`` \| ``json``) unless the
    uploader or the record sets another value.
* - ``source_ref``
  - VARCHAR(256)
  - —
  - Free-form ref to the ingest event (``publisher@BIG``,
    ``daily-cron``).
* - ``checksum``
  - VARCHAR(128)
  - —
  - File SHA256 (lowercase hex). Populated by the publisher for
    files up to ``checksum_max_bytes`` (50 GB by default).
* - ``provenance_json``
  - JSON
  - —
  - Free-form extra. Publisher writes ``{ sha256, rel_path,
    publisher_label }`` here.
```

## Timestamps

```{list-table}
:header-rows: 1
:widths: 22 14 14 50

* - Column
  - Type
  - —
  - Meaning
* - ``ingested_at``
  - TIMESTAMP (UTC)
  - —
  - Time of the last ingestion that wrote this obs_id (reset on
    every UPSERT, not only the first).
* - ``updated_at``
  - TIMESTAMP (UTC)
  - —
  - Last UPSERT touched this row.
```

## Optional title

```{list-table}
:header-rows: 1
:widths: 22 14 14 50

* - Column
  - Type
  - —
  - Meaning
* - ``obs_title``
  - VARCHAR(256)
  - —
  - Optional human-friendly title (not in classic ObsCore).
```

## Replica table

The ``dataset_replicas`` table joins datasets to nodes. Fields:

```{list-table}
:header-rows: 1
:widths: 22 14 14 50

* - Column
  - Type
  - —
  - Meaning
* - ``dataset_id``
  - FK datasets.id
  - cascade DELETE
  - Parent dataset.
* - ``node_id``
  - FK nodes.id
  - cascade DELETE
  - Hosting node.
* - ``remote_path``
  - VARCHAR(512)
  - —
  - Path on the node's filesystem (or relative under its serving
    root). The ingestion API fills a placeholder
    (``/ingested/<obs_id>``); clients use ``access_endpoint``.
* - ``access_endpoint``
  - VARCHAR(512)
  - —
  - URL clients consume (any scheme). A ``file://`` endpoint on a
    node with a co-located VisIVO backend is what enables node-side
    SODA and the moment/PV services.
* - ``status``
  - VARCHAR(32)
  - default ``available``
  - Free string. Only ``available`` replicas are routed; any other
    value (e.g. ``quarantined``) takes the replica out of discovery,
    DataLink and SODA with the reason ``replica <status>``.
* - ``is_public``
  - BOOL
  - default true
  - Visibility flag. Non-public replicas are never routed.
```

Unique constraint: ``(dataset_id, node_id)``. One replica per
node per dataset.

## SKAVA extensions

Fields that go beyond classic ObsCore:

* ``provenance_json`` — JSONB free-form provenance
* ``obs_title`` — human title
* ``spatial_index_order`` / ``spatial_index_cell`` — equal-angle sky
  cell key (HEALPix/MOC-ready)
* ``checksum`` — SHA256 of the source file

Not stored: MOC footprints and ``s_region`` (the footprint is the
``s_fov`` scalar), and a dedicated polarisation column.

## Backwards compatibility

When new optional columns are added, existing rows get NULL until
they're re-ingested. Discovery responses serialise NULLs explicitly
so client code can detect "old row, this field unknown" from
"genuinely missing".
