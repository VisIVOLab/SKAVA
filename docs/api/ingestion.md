# Internal ingestion API

`/internal/ingestion/*` — authenticated endpoints used by the
publisher CLI and the (planned) admin UI bulk upload. NOT a public
API — gated by `X-Internal-Api-Key`.

## Endpoints

```{list-table}
:header-rows: 1
:widths: 35 18 47

* - Endpoint
  - Method
  - Purpose
* - ``/internal/ingestion/dry-run``
  - POST
  - Validate + simulate without writing rows.
* - ``/internal/ingestion/run``
  - POST
  - Validate + write. The canonical ingestion call.
* - ``/internal/ingestion/history``
  - GET
  - List recent ingestion jobs.
* - ``/internal/ingestion/history/{job_id}``
  - GET
  - Single job detail including per-record errors.
```

## Authentication

Every call requires the `X-Internal-Api-Key` header. The value must
match `INTERNAL_API_KEY` (or `SKAVA_INTERNAL_API_KEY`) in the
api container's environment.

```bash
curl -fsS -X POST "$SKAVA/internal/ingestion/dry-run" \
    -H "X-Internal-Api-Key: $INTERNAL_KEY" \
    -F "file=@/tmp/manifest.csv" \
    -F "format=csv" \
    -F "source_ref=daily-cron"
```

Missing or wrong key → 401 with:

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Invalid or missing internal API key"
  },
  "request_id": "..."
}
```

## Request shape

`multipart/form-data` with three form fields:

```{list-table}
:header-rows: 1
:widths: 22 14 12 52

* - Field
  - Type
  - Required?
  - Meaning
* - ``file``
  - file upload
  - **yes**
  - CSV or JSON manifest body. Max ~64 MB (configurable in reverse
    proxy).
* - ``format``
  - str
  - no
  - ``csv`` \| ``json``. Auto-detected from the filename suffix if
    omitted.
* - ``source_ref``
  - str
  - no
  - Free-text identifier captured in the audit row. Common values:
    ``publisher@<node>``, ``mac-dev``, ``cron-daily``.
* - ``source_type``
  - str
  - no
  - Defaults to the format. Use to override (e.g.
    ``skava-publisher`` so the audit history filters cleanly).
```

## CSV format

UTF-8, comma-separated, one header row, one record per line. Columns:

```
obs_id, obs_collection, dataproduct_type, calib_level,
target_name, s_ra, s_dec, t_min, t_max,
em_min, em_max, access_format, access_estsize,
node_id, access_url, is_public
```

Optional columns (ignored if missing):

```
facility_name, instrument_name, s_fov, doi, pid,
citation, license, source_ref
```

Example:

```csv
obs_id,obs_collection,dataproduct_type,calib_level,target_name,s_ra,s_dec,t_min,t_max,em_min,em_max,access_format,access_estsize,node_id,access_url,is_public
power9-test-001,inaf-power9,cube,2,M87,187.7059,12.3911,59600.0,59600.5,2.1e-3,2.1e-3,image/fits,4096,POWER9,file:///data/cubes/m87.fits,true
```

## JSON format

Either:

```json
[
  { "obs_id": "power9-test-001", ... },
  { "obs_id": "power9-test-002", ... }
]
```

or wrapped in a `records` envelope:

```json
{
  "records": [
    { "obs_id": "...", ... }
  ],
  "source_ref": "publisher@power9"
}
```

The publisher CLI uses the wrapped form so the manifest file can
carry its own provenance.

## Per-record fields

```{list-table}
:header-rows: 1
:widths: 22 12 66

* - Field
  - Required?
  - Notes
* - ``obs_id``
  - yes
  - Unique key. SKAVA performs an UPSERT — same obs_id updates the
    existing row.
* - ``dataproduct_type``
  - yes
  - ``image`` \| ``cube`` \| ``dynspec`` \| ``polarimetric`` \|
    ``catalog`` \| ``event`` \| arbitrary string.
* - ``node_id``
  - yes
  - Code of an existing Node. Unknown → record skipped with error
    ``unknown node X``.
* - ``access_url``
  - yes
  - URL with a scheme. SKAVA is scheme-agnostic.
* - ``calib_level``
  - no
  - 0–4.
* - ``s_ra`` / ``s_dec``
  - no
  - Degrees, J2000. Validation: 0 ≤ ra ≤ 360, -90 ≤ dec ≤ 90.
* - ``s_fov``
  - no
  - Degrees. Must be > 0 when present.
* - ``t_min`` / ``t_max``
  - no
  - MJD. Validation: t_min ≤ t_max when both present.
* - ``em_min`` / ``em_max``
  - no
  - Metres. Same range check.
* - ``access_estsize``
  - no
  - KB. Used for hints in DataLink responses.
* - ``is_public``
  - no
  - Defaults true. Replica visibility flag.
* - ``provenance_json``
  - no
  - Free-form JSON object. The publisher CLI fills SHA256 + rel_path.
* - ``doi`` / ``pid`` / ``citation`` / ``license``
  - no
  - Plain strings.
```

## Response

```json
{
    "job": {
        "job_id": 17,
        "started_at": "2026-06-05T16:45:43.768107",
        "completed_at": "2026-06-05T16:45:43.773072",
        "status": "succeeded",
        "source_type": "skava-publisher",
        "source_ref": "publisher@POWER9",
        "filename": "manifest.csv",
        "dry_run": false,
        "record_count": 1003,
        "summary": {
            "total_records": 1003,
            "inserted_datasets": 950,
            "updated_datasets": 53,
            "inserted_replicas": 1003,
            "updated_replicas": 0,
            "skipped_records": 0,
            "validation_errors": []
        }
    },
    "summary": { ... same shape ... }
}
```

`status` is one of:

* `succeeded` — every record applied
* `partial` — some records skipped due to validation errors
* `failed` — DB-level error; no record applied

Per-record errors are listed under `summary.validation_errors[]`
with `{index, code, message}`.

## Common validation errors

```{list-table}
:header-rows: 1
:widths: 32 68

* - Error
  - Cause
* - ``Missing required field: <name>``
  - Schema check failed.
* - ``unknown node <code>``
  - The publisher's config references a node not registered in
    SKAVA's ``nodes`` table.
* - ``s_ra must be in [0, 360]``
  - Number out of range.
* - ``t_min must be <= t_max``
  - Range inverted.
* - ``access_url must include a scheme``
  - URL had no ``://``.
```

## History

```bash
curl -s -H "X-Internal-Api-Key: $INTERNAL_KEY" \
    "$SKAVA/internal/ingestion/history?limit=20" | jq
```

Returns the last N jobs ordered by `started_at DESC`. Combine with
`/internal/ingestion/history/{job_id}` for per-record errors.

## Retention

Job rows are never deleted by SKAVA. Production sites should:

```sql
DELETE FROM ingestion_jobs
WHERE  completed_at < now() - interval '365 days';
```

Adjust to your audit policy.

## See also

* [Publisher / overview](../publisher/overview) — the canonical
  consumer of this API.
* [Admin UI / audit](../admin-ui/audit) for the cross-cutting audit
  log that also captures ingestion-triggered changes.
