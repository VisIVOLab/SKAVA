# Datasets

The Datasets section of the admin UI is the primary interactive
surface on a populated SKAVA catalogue. It supports browse, search,
filter, single-record edit, replica management, and a small-file
FITS pre-fill helper.

## List view (`/admin/datasets/`)

Paginated (50 records / page) table with:

* Free-text search across ``obs_id``, ``obs_title``, ``target_name``
* Filter dropdowns: ``obs_collection``, ``dataproduct_type``
  (auto-populated from the distinct values in the DB)
* Total + page counter
* "+ Add dataset" button for `ingester` / `admin`
* Per-row replica count, edit + delete actions for editors
* **Export CSV** link for the current filter

Search box semantics: `ILIKE '%<query>%'` (case-insensitive
substring). For exact-match or richer queries, use the TAP endpoint.

## CSV export (`/admin/datasets/export.csv`)

Takes the same `q`, `collection` and `dptype` parameters as the list,
so what you see is what you download. Columns: `obs_id`,
`obs_collection`, `dataproduct_type`, `obs_title`, `target_name`,
`s_ra`, `s_dec`, `s_fov`, `t_min`, `t_max`, `em_min`, `em_max`,
`replica_count`. Streamed, capped at 100,000 rows.

## Detail view (`/admin/datasets/{id}`)

Three sections:

1. **ObsCore** — every ObsCore-aligned column with a friendly label
2. **Provenance** — DOI / PID / license / citation / source type /
   source ref / checksum / ingested-at / updated-at
3. **Replicas** — table of every physical copy with an inline
   "Add replica" form when the user has edit rights

Top-right buttons: **Edit** (jumps to the edit form), **Delete**
(with a confirmation dialog that shows the replica count to be
cascade-deleted).

## Create / edit form

The form is the same template for `new` and `edit`. Fieldsets:

* Identity (`obs_id`, title, collection, dptype, calib level,
  target / facility / instrument)
* Spatial / time / spectral (RA / Dec / FoV / t_min / t_max /
  em_min / em_max)
* Access (format, estimated size)
* Provenance (DOI, PID, license, source ref, citation)

Validation is server-side; client-side is intentionally minimal so
JS errors can't bypass the rules.

Range sanity: `t_min ≤ t_max`, `em_min ≤ em_max`. Both checked on
submit; if either fails, the operator gets an inline error and the
form re-renders with the already-typed values preserved.

## FITS pre-fill helper

At the top of the create/edit form there's a "Pre-fill from FITS
file" panel:

```
[📁 Choose file]    [Extract metadata]
```

Workflow:

1. The operator picks a FITS file (≤ 5 MB; larger uploads get
   HTTP 413).
2. The browser uploads it to `POST /admin/datasets/extract-from-fits`.
3. SKAVA parses, with astropy, the header of the first HDU whose
   `NAXIS` is non-zero (the primary HDU in a simple file, the first
   data extension in a MEF), extracts what it can, returns a JSON
   dict of `field_name → value`, and writes a
   `dataset.extract_from_fits` audit row.
4. A small in-page JS script iterates the dict and fills **only the
   empty form fields**, leaving any value the operator already
   typed in untouched.

What gets extracted, best-effort:

* `obs_id` ← `OBS_ID` or `OBSID`, when present
* `target_name` ← `OBJECT`
* `facility_name` ← `TELESCOP`
* `instrument_name` ← `INSTRUME`
* `s_ra`, `s_dec` ← WCS centre of the image (falling back to the
  `RA` / `DEC` keywords)
* `s_fov` ← largest of (NAXISx × pixel scale)
* `t_min`, `t_max` ← `MJD-OBS` plus `MJD-END` or `EXPTIME`;
  `DATE-OBS` when `MJD-OBS` is missing
* `em_min`, `em_max` (metres) ← spectral axis bounds (`FREQ`,
  `WAVE`, `VOPT`, `VRAD`), or `RESTFREQ` → λ
* `dataproduct_type` ← heuristic from NAXIS + presence of STOKES
  (`image`, `cube` or `polarimetric`)
* `access_format` ← `image/fits` default

Limits:

* obs_id is rarely in FITS headers — usually the operator types it
* calib_level can't be inferred portably — left empty

## Replicas

Inside the dataset detail page, the Replicas section shows every
physical copy and lets editors add or remove them.

Add-replica form fields:

* **Node** — dropdown of every enabled Node
* **Remote path** — path on the node's filesystem (or a relative
  path under the node's serving root)
* **Access endpoint** — fully-qualified URL the consumer should hit
* **Public** — visibility flag (defaults true)

All but **Public** are required. New replicas get status
``available``. Audit row: ``replica.create``.

Uniqueness: one Replica per (dataset, node) pair. Attempting to add
a duplicate gets a flash error.

Remove triggers a confirmation dialog. Audit row:
``replica.delete`` with a snapshot of the removed fields.

## RBAC summary

| Action | viewer | ingester | admin |
|---|---|---|---|
| List + search | ✓ | ✓ | ✓ |
| CSV export | ✓ | ✓ | ✓ |
| View detail | ✓ | ✓ | ✓ |
| Add new dataset | ✗ | ✓ | ✓ |
| Edit | ✗ | ✓ | ✓ |
| Delete | ✗ | ✓ | ✓ |
| Add / remove replica | ✗ | ✓ | ✓ |
| FITS pre-fill | ✗ | ✓ | ✓ |

## When NOT to use the UI

The single-record form is for hand-edits and one-off additions.
For **bulk** ingestion (more than a handful of records) use the
[publisher CLI](../publisher/overview.md) on the node where the data
lives. The publisher:

* doesn't require moving the file to your laptop
* tracks already-published files in a local SQLite, skipping
  unchanged ones on re-run
* records each batch as an ingestion job
* handles HDF5 / PSRFITS natively, not just FITS

The admin UI is a peer of the publisher, not a competitor.

For a small CSV / JSON manifest prepared by hand, use the
[Upload](upload.md) page, which runs the same ingestion pipeline under
your admin session.
