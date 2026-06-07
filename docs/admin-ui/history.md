# History (audit log viewer)

The History page (`/admin/history/`) is a read-only browser over the
`audit_log` table — the same append-only ledger that every mutating
admin action writes to. It exists to answer questions like:

* *"Who changed the production node `POWER9`'s base URL last week?"*
* *"How many dataset deletions happened since the migration?"*
* *"What did the bulk upload run actually do?"* — full diff per row

The page is added in Phase 3; before Phase 3 the same data was only
visible as the "Recent activity" widget on the Dashboard (last 10 rows).

## Layout

```text
┌────────────────────────────────────────────────────────────────────┐
│ Audit history                                       1,287 entries  │
├────────────────────────────────────────────────────────────────────┤
│ ┌ Filter ──────────────────────────────────────────────────┐       │
│ │ Search action/target id  Section  Target type  Actor     │       │
│ │ From (UTC)  To (UTC)                                     │       │
│ │ [ Apply filter ] [ Reset ]              ⬇ Export CSV     │       │
│ └──────────────────────────────────────────────────────────┘       │
│                                                                    │
│ When (UTC)        Who           Action            Target           │
│ 2026-06-06 14:01  alice         node.update       node/POWER9   ▸  │
│ 2026-06-06 14:00  alice         dataset.create    dataset/ds_… ▸  │
│ …                                                                  │
└────────────────────────────────────────────────────────────────────┘
```

Clicking the **▸** (Details) opens a single-row view with the full
`changes_json` payload pretty-printed and the rest of the metadata
(user agent, request id, IP) visible.

## Filters

All filters compose with AND semantics; an empty filter is ignored.

| Field | Behaviour | Underlying column |
|---|---|---|
| Search | case-insensitive substring on `action` OR `target_id` | `action`, `target_id` |
| Section | exact prefix match (e.g. `node`, `dataset`, `auth`) | `action` (LIKE `prefix.%`) |
| Target type | exact match | `target_type` |
| Actor | case-insensitive substring on the snapshot label | `actor_label` |
| From / To | UTC-midnight inclusive boundary | `occurred_at` |

The Section dropdown is populated by stripping each `action` at its
first dot and de-duplicating — operators see whatever categories the
codebase has actually written, never a stale hardcoded list.

The To date is treated as the **end** of the chosen day (i.e. strictly
< the next day's midnight) so a "today only" filter does not exclude
events from the current day's afternoon.

## CSV export

The **Export CSV** link mirrors the current filter set — same query
parameters, same semantics — so the operator's mental model is
*"what I see is what I download"*.

* Path: `GET /admin/history/export.csv?<same params as list>`
* Body: streamed CSV (`text/csv; charset=utf-8`), one header row +
  one row per record
* Columns: `occurred_at, actor, action, target_type, target_id,
  ip_address, request_id, changes_json`
* Soft cap: `100,000` rows per export (override with `?limit=N`,
  capped server-side to the same maximum)
* Datetimes emit as RFC 3339 (`2026-06-06T12:30:00+00:00`)
* `changes_json` is rendered as compact JSON (one line per cell);
  downstream tools can `json.loads` the column directly

The export is generated as a Python generator — memory stays flat
regardless of result-set size.

## Permissions

Same as the rest of the admin UI:

* `viewer` → read History (list + detail + export)
* `ingester` → also read History (cannot mutate it; the table is
  append-only at the application layer)
* `admin` → same as `ingester` for History

`audit_log` is never updated or deleted from application code.
Retention is an external concern handled by ops scripts (e.g. cron
`pg_dump` to cold storage + `DELETE WHERE occurred_at < now() - …`).
See {doc}`../operations/admin-ui-runbook` for the recommended schedule.

## Implementation pointers

```{list-table}
:header-rows: 1
:widths: 30 70

* - Concern
  - File
* - Router
  - `app/admin/routers/history.py`
* - Templates
  - `app/admin/templates/history/list.html`, `…/detail.html`
* - CSV streaming helper
  - `app/admin/csv_export.py:stream_csv`
* - Audit model
  - `app/models/audit_log.py`
* - Audit write hook (used by all mutating routes)
  - `app/admin/audit/service.py:log_action`
```

## Examples — typical operator queries

**1. "Show every change to the POWER9 node in June 2026":**

```
/admin/history/?target_type=node&q=POWER9&since=2026-06-01&until=2026-06-30
```

Export → CSV with one row per change + before/after diff in
`changes_json`.

**2. "All failed login attempts":**

```
/admin/history/?action_prefix=auth&q=login_failed
```

The `auth.login_failed` rows include the attempted username in
`target_id`; combine with `ip_address` column for brute-force
detection.

**3. "Bulk export of last 30 days for compliance review":**

```
/admin/history/export.csv?since=2026-05-06
```

Returns ≤ 100,000 rows. For larger windows split by date or query
the database directly.
