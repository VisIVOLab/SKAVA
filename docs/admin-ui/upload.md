# Bulk upload

`/admin/upload` is the browser-facing front-end for SKAVA's ingestion
pipeline. Drag a CSV or JSON manifest onto the form, pick dry-run or
run, and the same record-by-record validation + UPSERT that the
publisher CLI triggers happens server-side.

## When to use this vs the publisher CLI

```{list-table}
:header-rows: 1
:widths: 28 36 36

* - Aspect
  - Admin UI Upload
  - skava-publisher CLI
* - Where it runs
  - Operator's browser
  - On the data node
* - Max file size
  - 32 MB (hard cap)
  - Unlimited (streams record-by-record)
* - Idempotency
  - UPSERT on ``obs_id``
  - UPSERT + per-file state.db skip
* - Auth
  - admin session + CSRF
  - ``X-Internal-Api-Key`` shared secret
* - Audit
  - admin audit row + ingestion job row
  - ingestion job row only
* - Best for
  - one-off analyst manifests, small re-imports, spot-checks
  - production publishing of a node's data tree
```

The two paths share the same `IngestionJobService`, so the result of
either is byte-equivalent in the catalogue.

## Permissions

Visible to all logged-in users; only `ingester` and `admin` can
actually submit. `viewer` sees a message explaining how to request
the role.

## Form fields

```{list-table}
:header-rows: 1
:widths: 26 14 12 48

* - Field
  - Type
  - Required?
  - Notes
* - **Manifest file**
  - file
  - yes
  - CSV or JSON, ≤ 32 MB.
* - **Format**
  - select
  - no
  - ``Auto-detect`` (from the filename suffix) \| ``CSV`` \| ``JSON``.
* - **Source reference**
  - text
  - no
  - Captured on the audit row. Defaults to
    ``admin-ui:<your-username>``.
* - **Run mode**
  - radio
  - yes
  - ``Dry run`` (default) — validate without writing.
    ``Run`` — UPSERT into the catalogue.
```

## Workflow

1. Pick a manifest from disk (or drag it onto the input field).
2. Leave **Dry run** selected for the first attempt.
3. Click **Upload**.
4. Inspect the summary card that appears below the form:
   * inserted / updated counts
   * skipped count (records that failed schema validation)
   * a collapsible table of per-record errors with the row index
     and the code+message
5. If the dry-run is clean, switch to **Run** and re-submit.
6. Refresh `/admin/datasets/` to see the new records.

## Summary card

After a submit, the page renders the form and a "summary" panel side
by side. Fields:

* **Inserted datasets** — rows created.
* **Updated datasets** — rows that already existed and got UPSERTed.
* **Inserted replicas** — replica rows created.
* **Updated replicas** — replica rows updated.
* **Skipped** — records that failed validation; these are listed by
  row index in the collapsible "validation errors" table.

Job number (``job #N``) is the primary key in `ingestion_jobs` —
useful for the future History page filter.

## Errors and limits

```{list-table}
:header-rows: 1
:widths: 35 65

* - Error
  - Meaning
* - ``File exceeds 32 MB``
  - HTTP 413. Use the publisher CLI for larger manifests.
* - ``Uploaded file is empty``
  - HTTP 400.
* - ``Parse error: ...``
  - Malformed CSV header or JSON document. Open the file in a text
    editor; the error message identifies the offending construct.
* - ``Ingestion refused: An ingestion job is already running``
  - SKAVA only allows one ingestion job at a time. Wait or check
    the dashboard for the current job.
* - One or more rows in the validation table
  - Per-record schema failures. Fix the source file or accept the
    skip (skipped records are not written).
```

## Audit trail

Two audit artefacts are produced for every upload:

1. An ``ingestion_jobs`` row with totals, dry-run flag, source ref,
   filename, ``triggered_by="admin-ui:<username>"``, and the full
   ``summary_json`` blob (including the per-record errors).
2. An ``audit_log`` row with
   ``action="ingestion.upload"`` (or ``ingestion.upload.dry_run``),
   ``target_type="ingestion_job"``, ``target_id=<job_id>``, and a
   compact ``changes_json`` summary.

The cross-cutting admin audit page (Phase 3) will filter on both.

## Format reminders

### CSV

UTF-8, comma-separated, one header row, one record per row. See
[ObsCore fields reference](../reference/obscore-fields) for the
column list. The publisher CLI's documentation includes a
[worked example](../api/ingestion#csv-format).

### JSON

Either a top-level array of records or an object with a
``records`` array. Same per-record schema as CSV.

## Security

* Bound to the admin session, so the internal API key is never
  exposed in the browser.
* CSRF token validated on every POST.
* File size capped at 32 MB to prevent worker memory exhaustion.
* RBAC enforced: viewer cannot reach the POST handler even by
  forging a request.

## What this page deliberately doesn't do

* **Stream records back to the browser one at a time.** That would
  give per-record progress for huge files; we don't need it because
  the cap is small enough that the whole job finishes in seconds.
* **Allow CSV editing in-place.** Out of scope; use a spreadsheet
  app or the publisher CLI's manifest generation.
* **Approve-then-publish multi-step workflow.** Dry-run + run is the
  simplest version of approval; a richer two-step
  "ingester drafts, admin approves" flow is Phase 5 scope.
