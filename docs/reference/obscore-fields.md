# ObsCore fields

SKAVA's ``datasets`` table mirrors the IVOA ObsCore data model with a
few SKAVA-specific extensions. This page is the canonical column
reference.

## Required ObsCore fields

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
  - Survey / collection grouping (e.g. ``inaf-power9-ska``).
* - ``dataproduct_type``
  - VARCHAR
  - 64
  - ObsCore vocabulary plus SKAVA extensions:
    ``image`` \| ``cube`` \| ``dynspec`` \| ``polarimetric`` \|
    ``catalog`` \| ``event``.
* - ``calib_level``
  - INT
  - 0–4
  - 0 raw, 1 calibrated, 2 derived, 3 advanced product, 4 user-
    contributed.
* - ``target_name``
  - VARCHAR
  - 128
  - Object the observation targets.
* - ``facility_name``
  - VARCHAR
  - 128
  - Telescope / observatory name.
* - ``instrument_name``
  - VARCHAR
  - 128
  - Instrument / camera / backend.
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
  - Right ascension of the field centre (J2000).
* - ``s_dec``
  - DOUBLE
  - deg
  - Declination of the field centre (J2000).
* - ``s_fov``
  - DOUBLE
  - deg
  - Diameter of the smallest enclosing circle of the field.
* - ``spatial_index_order``
  - INT
  - HEALPix order
  - Used by the spatial index for cone-search acceleration.
* - ``spatial_index_cell``
  - VARCHAR(64)
  - HEALPix cell id
  - Pre-computed; updated on insert/update.
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
  - Estimated payload size for client UI hints.
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
  - Where this row came from (``skava-publisher`` \| ``admin-ui``
    \| ``manual-csv``).
* - ``source_ref``
  - VARCHAR(256)
  - —
  - Free-form ref to the ingest event (``publisher@POWER9``,
    ``daily-cron``).
* - ``checksum``
  - VARCHAR(128)
  - —
  - File SHA256 (lowercase hex). Populated by the publisher for
    files under ``checksum_max_bytes``.
* - ``provenance_json``
  - JSONB
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
  - TIMESTAMPTZ
  - —
  - First time SKAVA saw this obs_id.
* - ``updated_at``
  - TIMESTAMPTZ
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
    root).
* - ``access_endpoint``
  - VARCHAR(512)
  - —
  - URL clients consume.
* - ``status``
  - VARCHAR(32)
  - default ``available``
  - ``available`` \| ``quarantined`` \| ``evicted``.
* - ``is_public``
  - BOOL
  - default true
  - Visibility flag.
```

Unique constraint: ``(dataset_id, node_id)``. One replica per
node per dataset.

## SKAVA extensions

Fields that go beyond classic ObsCore:

* ``provenance_json`` — JSONB free-form provenance
* ``obs_title`` — human title
* ``spatial_index_order`` / ``spatial_index_cell`` — HEALPix-based
  spatial index for cone searches
* ``checksum`` — SHA256 of the source file

Future extensions:

* MOC-based footprints (currently only s_fov scalar)
* Polarisation tag in a dedicated column
* `s_region` STC-S string for non-circular footprints

## Backwards compatibility

When new optional columns are added, existing rows get NULL until
they're re-ingested. Discovery responses serialise NULLs explicitly
so client code can detect "old row, this field unknown" from
"genuinely missing".
