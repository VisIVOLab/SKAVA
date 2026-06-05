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

Search box semantics: `LIKE '%<query>%'` (case-insensitive). For
substring or exact-match alternatives, use the TAP endpoint.

## Detail view (`/admin/datasets/{id}`)

Three sections:

1. **ObsCore** — every ObsCore-aligned column with a friendly label
2. **Provenance** — DOI / PID / license / citation / source ref /
   checksum / ingested-at / updated-at
3. **Replicas** — table of every physical copy with an inline
   "Add replica" form when the user has edit rights

Top-right buttons: **Edit** (jumps to the edit form), **Delete**
(with confirmation modal that shows the replica count to be
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

1. The operator picks a FITS file (≤ 5 MB).
2. The browser uploads it to `POST /admin/datasets/extract-from-fits`.
3. SKAVA parses the primary HDU header with astropy (or the first
   non-empty HDU in a MEF file), extracts what it can, returns a
   JSON dict of `field_name → value`.
4. A small in-page JS script iterates the dict and fills **only the
   empty form fields**, leaving any value the operator already
   typed in untouched.

What gets extracted, best-effort:

* `target_name` ← `OBJECT`
* `facility_name` ← `TELESCOP`
* `instrument_name` ← `INSTRUME`
* `s_ra`, `s_dec` ← WCS centre of the primary HDU
* `s_fov` ← largest of (NAXISx × CDELTx)
* `t_min`, `t_max` ← `MJD-OBS` + `EXPTIME` (or `MJD-END`)
* `em_min`, `em_max` ← `RESTFREQ` → λ, or spectral axis bounds
* `dataproduct_type` ← heuristic from NAXIS + presence of STOKES
* `access_format` ← `image/fits` default

Limits:

* obs_id is rarely in FITS headers — the operator types it manually
* calib_level can't be inferred portably — left empty
* Multi-extension files are handled (skip empty primary, descend to
  first NAXIS > 0 HDU)

## Replicas

Inside the dataset detail page, the Replicas section shows every
physical copy and lets editors add or remove them.

Add-replica form fields:

* **Node** — dropdown of every enabled Node
* **Remote path** — path on the node's filesystem (or a relative
  path under the node's serving root)
* **Access endpoint** — fully-qualified URL the consumer should hit
* **Public** — visibility flag (defaults true)

Uniqueness: one Replica per (dataset, node) pair. Attempting to add
a duplicate gets a flash error.

Remove triggers a confirmation modal. Audit row:
``replica.delete`` with a snapshot of the removed fields.

## RBAC summary

| Action | viewer | ingester | admin |
|---|---|---|---|
| List + search | ✓ | ✓ | ✓ |
| View detail | ✓ | ✓ | ✓ |
| Add new dataset | ✗ | ✓ | ✓ |
| Edit | ✗ | ✓ | ✓ |
| Delete | ✗ | ✓ | ✓ |
| Add / remove replica | ✗ | ✓ | ✓ |
| FITS pre-fill | ✗ | ✓ | ✓ |

## When NOT to use the UI

The single-record form is for hand-edits and one-off additions.
For **bulk** ingestion (more than a handful of records) use the
[publisher CLI](../publisher/overview) on the node where the data
lives. The publisher:

* doesn't require moving the file to your laptop
* tracks already-published files in a local SQLite, skipping
  unchanged ones on re-run
* writes a structured audit row per record
* handles HDF5 / PSRFITS natively, not just FITS

The admin UI is a peer of the publisher, not a competitor.

## Phase 2c: drag-drop CSV / JSON

Planned: the Upload page accepts a CSV / JSON manifest from a
browser drag-drop and feeds it into the existing
``/internal/ingestion/run`` endpoint with a session-auth wrapper.
This will be useful for analysts producing a small manifest
locally and uploading without having to deal with the API key.

Until that lands, use the publisher CLI or
``/internal/ingestion/run`` directly via curl.
