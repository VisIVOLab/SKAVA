# Internal ingestion API

`/internal/ingestion/*` — authenticated endpoints used by the
publisher CLI and operator scripts. NOT a public API — gated by
`X-Internal-Api-Key`.

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
  - List recent ingestion jobs (``limit`` 1-500, default 50).
* - ``/internal/ingestion/history/{job_id}``
  - GET
  - Single job detail including per-record errors (404
    ``ingestion_job_not_found`` when unknown).
```

## Authentication

Every call requires the `X-Internal-Api-Key` header. The value must
match `INTERNAL_API_KEY` (or `SKAVA_INTERNAL_API_KEY`) in the
api container's environment. When no key is configured at all, every
call is refused with 401 (`Internal API key is not configured`).

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

`multipart/form-data` with these form fields:

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
  - CSV or JSON manifest body (UTF-8). An empty file is refused
    (400). The size limit is the reverse proxy's.
* - ``format``
  - str
  - no
  - ``csv`` \| ``json``. Detected from the ``.csv`` / ``.json``
    filename suffix if omitted; 400 when neither gives a format.
* - ``source_ref``
  - str
  - no
  - Free-text identifier stored on the job and, unless a record
    carries its own ``source_ref``, on each dataset. Common values:
    ``publisher@<node>``, ``cron-daily``.
* - ``source_type``
  - str
  - no
  - Defaults to the format. Use to override (e.g.
    ``skava-publisher`` so the job history filters cleanly); a record's
    own ``source_type`` wins for that dataset.
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
s_fov, checksum, doi, pid, citation, license,
source_type, source_ref
```

`node_code` is accepted as an alias of `node_id`, `access_endpoint` of
`access_url`. `obs_title`, `facility_name` and `instrument_name` are
stored when present; a later record without them keeps the stored
values. A text value longer than its column (for example 128
characters for `target_name`, 512 for `access_url`) skips the record
with a `validation_error`, instead of failing the whole run.

Example:

```text
obs_id,obs_collection,dataproduct_type,calib_level,target_name,s_ra,s_dec,t_min,t_max,em_min,em_max,access_format,access_estsize,node_id,access_url,is_public
tb-cube-x,skava-testbed,cube,2,M87,187.7059,12.3911,59600.0,59600.5,0.2114,0.2142,image/fits,4096,BIG,file:///data/cubes/m87.fits,true
```

## JSON format

Either:

```text
[
  { "obs_id": "power9-test-001", ... },
  { "obs_id": "power9-test-002", ... }
]
```

or wrapped in a `records` envelope:

```text
{
  "records": [
    { "obs_id": "...", ... }
  ]
}
```

Only the `records` list of the envelope is read; any other top-level
key is ignored (pass `source_ref` as a form field or per record).

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
    existing row (only the fields given a non-empty value overwrite).
* - ``dataproduct_type``
  - yes
  - ``image`` \| ``cube`` \| ``dynspec`` \| ``polarimetric`` \|
    ``catalog`` \| ``event`` \| arbitrary string.
* - ``node_id``
  - yes
  - Code (or numeric id) of an existing Node. Unknown → record skipped
    with code ``node_not_found``. Alias: ``node_code``.
* - ``access_url``
  - yes
  - URL with a scheme. SKAVA is scheme-agnostic. Alias:
    ``access_endpoint``.
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
  - KB. Shown in DataLink ``primary_access`` and used by the
    ``resource_aware`` ranking policy to estimate memory need.
* - ``is_public``
  - no
  - Defaults true. Replica visibility flag (``true/false``,
    ``1/0``, ``yes/no``, ``y/n``, ``t/f``); a non-public replica is
    never handed out by discovery.
* - ``provenance`` / ``provenance_json``
  - no
  - Free-form JSON object (a scalar is wrapped as ``{"value": …}``).
    The publisher CLI fills SHA256 + rel_path.
* - ``checksum``
  - no
  - ``sha256:<lowercase hex>``, the form the publisher writes. Shown by
    ``/provenance/{obs_id}``. SKAVA does not normalise it: the ingestion
    and the federated merge compare checksums as exact strings (after
    trimming spaces), so a record with another prefix or upper-case hex
    never matches a copy published by the publisher.
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
        "source_ref": "publisher@BIG",
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
            "validation_errors": [],
            "started_at": "2026-06-05T16:45:43.768500",
            "finished_at": "2026-06-05T16:45:43.772900"
        },
        "error_message": null,
        "triggered_by": "internal-api"
    },
    "summary": {
        "processed": 1003,
        "inserted_datasets": 950,
        "updated_datasets": 53,
        "inserted_replicas": 1003,
        "updated_replicas": 0,
        "skipped": 0,
        "validation_errors": []
    }
}
```

The top-level `summary` is a compact view of `job.summary`
(`processed` = `total_records`, `skipped` = `skipped_records`).

`status` is one of:

* `succeeded` — the run finished; records that failed validation are
  skipped and listed, the rest applied
* `dry_run` — a dry run finished; nothing was written
* `failed` — an unexpected error; nothing applied, the call answers
  500 `ingestion_failed` and the job keeps the `error_message`
* `running` — while in progress. Only one job runs at a time: a second
  call answers 409 `ingestion_running`.

Per-record errors are listed under `summary.validation_errors[]`
with `{index, code, message}`; `code` is `validation_error`,
`normalization_error` (e.g. a non-numeric `s_ra` or an invalid boolean)
or `node_not_found`.

## Common validation errors

```{list-table}
:header-rows: 1
:widths: 32 68

* - Error
  - Cause
* - ``Missing required field: <name>``
  - Schema check failed.
* - ``Node not found: <code>``
  - The publisher's config references a node not registered in
    SKAVA's ``nodes`` table.
* - ``s_ra must be in [0, 360]``
  - Number out of range (likewise ``s_dec``, ``s_fov must be > 0``).
* - ``t_min must be <= t_max``
  - Range inverted (likewise ``em_min``/``em_max``).
* - ``access_url must include a scheme``
  - URL had no ``scheme://``.
* - ``replica_unverified``: ``obs_id X is held by other nodes and ... states
    no checksum``
  - A node that does not yet hold the dataset sent a record, and this record
    or the catalogue states no checksum. With ``SKAVA_REPLICA_IDENTITY=checksum``
    (the default) a replica is accepted only on equal checksums; publish them
    (``scan.compute_checksum``), raise ``scan.checksum_max_bytes`` for large
    files, or declare the replica in the admin UI. A node that already holds
    the dataset beside others gets the same answer when its record states no
    checksum while the catalogue has one: nothing shows its file is still the
    same copy, and its replica is quarantined until a record proves it.
* - ``<field> is longer than <n> characters``
  - A text value longer than its column (128 for ``target_name``, 512
    for ``access_url``, ...).
* - ``replica_conflict``: ``obs_id X is already catalogued as a different
    product on other nodes``
  - Another node holds a product under this ``obs_id`` whose
    ``checksum``, ``access_estsize`` or ``dataproduct_type`` differs from
    this record's (where both state it). Records sharing an ``obs_id`` are
    replicas of one product; a different product needs its own
    ``obs_id``. The only node holding a dataset may replace its file: the
    identity fields its new record does not restate are then cleared. When
    the refused record comes from a node that already holds the dataset
    beside others (its file changed), that node's replica is also
    quarantined: it leaves the ranking until a record of the node proves
    its copy again, with a checksum equal to the catalogue's. Two copies
    that disagree are never served under one dataset. The only holder
    republishing without a checksum withdraws the stored one (it described
    the old file); a holder bringing the first checksum of a dataset others
    hold too quarantines their replicas until their records show the same
    checksum. These are guarantees on the catalogue after each ingestion: a
    file changed in place is seen only at the publisher's next scan, so
    sites must keep replicas immutable or replace them through the
    publisher.
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

* [Publisher / overview](../publisher/overview.md) — the canonical
  consumer of this API.
* [Admin UI / audit](../admin-ui/audit.md) for the cross-cutting audit
  log that also captures ingestion-triggered changes.
