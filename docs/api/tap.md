# TAP API

`GET|POST /tap/sync` — IVOA TAP-compatible synchronous query interface
over `ivoa.ObsCore`, with the VOSI `/tap/capabilities` and
`/tap/tables` documents and a simple (non-UWS) async job endpoint.

## Endpoints

```{list-table}
:header-rows: 1
:widths: 32 68

* - Endpoint
  - Purpose
* - ``GET /tap/sync``
  - ADQL query, parameters in the query string.
* - ``POST /tap/sync``
  - Same, parameters form-encoded (as pyvo and TOPCAT send them).
* - ``GET /tap/capabilities``
  - VOSI capabilities (XML, ``application/xml``). ``FORMAT=json`` or an
    ``Accept`` header preferring ``application/json`` returns the
    service's JSON summary (queryable columns, operators, limits).
* - ``GET /tap/tables``
  - VOSI tableset describing ``ivoa.ObsCore`` (columns, datatypes,
    UCDs, units).
* - ``POST /tap/async``
  - Submits a query as a job (form-encoded ``QUERY``, ``LANG``,
    ``REQUEST``, ``MAXREC``, ``FORMAT``). The job runs at submission and
    the response is its final state.
* - ``GET /tap/async/{job_id}``
  - The stored job: ``job_id``, ``created_at``, ``completed_at``,
    ``status`` (``completed`` \| ``failed``), ``query``, ``maxrec``,
    ``format``, ``result`` (the JSON search response),
    ``error_message``, ``submitted_by``.
```

`/tap/sync` and `/tap/async` follow the deployment's token rule (open
unless static tokens or OIDC are configured, see
[Authentication](auth.md)); `/tap/capabilities` and `/tap/tables` are
always open. `submitted_by` is a non-reversible reference to the
caller's token (`token:<sha256 prefix>`), never the token itself.

`/tap/async` is not a UWS job list: there is no `PHASE`, no
`/results` sub-resource and no job listing. Long-running asynchronous
work belongs to the nodes' SODA services (see [SODA](soda.md)).

## Parameters

```{list-table}
:header-rows: 1
:widths: 32 18 50

* - Parameter
  - Default
  - Notes
* - ``QUERY``
  - —
  - Required. ADQL (URL- or form-encoded).
* - ``LANG``
  - ``ADQL``
  - Anything else is refused (400).
* - ``REQUEST``
  - ``doQuery``
  - Anything else is refused (400).
* - ``RESPONSEFORMAT`` / ``FORMAT``
  - ``votable``
  - ``votable``, ``votable/td``, ``application/x-votable+xml`` (with
    or without parameters), ``text/xml``, ``application/xml``, ``xml``
    return a TABLEDATA VOTable; ``json`` / ``application/json`` the
    JSON search response. Other values (e.g. ``csv``) are refused.
    ``RESPONSEFORMAT`` wins when both are given.
* - ``MAXREC``
  - 100
  - Row cap, 1-1000 (a value above 1000 is refused). ``SELECT TOP N``
    takes precedence and is clamped to 1000.
```

## ADQL subset

Supported:

* `SELECT ... FROM ivoa.ObsCore` (or `ObsCore`). The select list is
  not evaluated: every row carries the fixed column set below.
* `TOP N`.
* `WHERE` with predicates joined by `AND` only. Each predicate is
  `column OP value` with `=`, `!=`, `<>`, `<`, `<=`, `>`, `>=`; string
  columns take single-quoted literals, numeric columns numbers. Table
  qualifiers (`obscore.s_ra`, `ivoa.obscore.t_min`) are stripped.
* The cone predicate
  `1 = CONTAINS(POINT('ICRS', s_ra, s_dec), CIRCLE('ICRS', ra, dec, radius))`,
  or the SRCNet form `CONTAINS(s_pos, CIRCLE('ICRS', ra, dec, radius)) = 1`
  (same centre-based approximation as the discovery `POS` filter).

Queryable columns: `obs_id`, `obs_collection`, `obs_title`,
`dataproduct_type`, `target_name`, `facility_name`, `instrument_name`,
`source_type`, `source_ref`, `access_format`, `spatial_index_cell`,
`doi`, `pid`, `license` (strings); `calib_level`, `s_ra`, `s_dec`,
`s_fov`, `t_min`, `t_max`, `em_min`, `em_max`, `access_estsize`,
`spatial_index_order` (numbers).

Not supported (400 `invalid_query`): `OR`, `NOT`, `LIKE`, `BETWEEN`,
`IS NULL`, joins, subqueries, aggregates, `GROUP BY`, and any geometry
other than the cone above (`INTERSECTS`, `POLYGON`, `BOX`, …).
`ORDER BY` is accepted but ignored: rows always come in `obs_id` order.

## Example queries

### Cubes in a band

```text
SELECT TOP 10 * FROM ivoa.ObsCore
WHERE  dataproduct_type = 'cube'
  AND  em_min <= 0.2150 AND em_max >= 0.2142
```

```bash
curl -s https://skava.inaf.it/tap/sync \
    --data-urlencode "LANG=ADQL" \
    --data-urlencode "QUERY=SELECT TOP 10 * FROM ivoa.ObsCore WHERE dataproduct_type = 'cube' AND em_min <= 0.2150 AND em_max >= 0.2142"
```

### Cone search, JSON-formatted

```bash
curl -s -G https://skava.inaf.it/tap/sync \
    --data-urlencode "LANG=ADQL" \
    --data-urlencode "FORMAT=json" \
    --data-urlencode "QUERY=SELECT * FROM ivoa.ObsCore WHERE 1 = CONTAINS(POINT('ICRS', s_ra, s_dec), CIRCLE('ICRS', 150.0, -30.0, 0.5))" | jq
```

### Time overlap

```text
SELECT * FROM ivoa.ObsCore
WHERE  t_min <= 60000 AND t_max >= 59000
```

## VOTable response shape

The columns are always `obs_id`, `obs_collection`, `obs_title`,
`dataproduct_type`, `calib_level`, `target_name`, `facility_name`,
`instrument_name`, `s_ra`, `s_dec`, `s_fov`, `t_min`, `t_max`,
`em_min`, `em_max`, `access_url`, `access_format`. `access_url` is the
dataset's DataLink document
(`{base}/datalink/{obs_id}?RESPONSEFORMAT=votable`) and
`access_format` is `application/x-votable+xml;content=datalink`, the
ObsCore convention for datasets whose access needs a resolution step.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">
  <RESOURCE type="results">
    <INFO name="QUERY_STATUS" value="OK"/>
    <TABLE name="ivoa.ObsCore">
      <FIELD name="obs_id" datatype="char" arraysize="*"/>
      ...
      <FIELD name="access_url" datatype="char" arraysize="*"/>
      <FIELD name="access_format" datatype="char" arraysize="*"/>
      <DATA>
        <TABLEDATA>
          <TR><TD>tb-cube-l</TD>...<TD>https://skava.inaf.it/datalink/tb-cube-l?RESPONSEFORMAT=votable</TD><TD>application/x-votable+xml;content=datalink</TD></TR>
        </TABLEDATA>
      </DATA>
    </TABLE>
  </RESOURCE>
</VOTABLE>
```

Datasets with no eligible replica are left out of the results.

## Errors

```{list-table}
:header-rows: 1
:widths: 18 82

* - Status
  - When
* - 200
  - Query executed (possibly zero rows).
* - 400
  - ``invalid_query``: missing ``QUERY``, wrong ``LANG`` or
    ``REQUEST``, ``MAXREC`` out of range, unsupported
    ``RESPONSEFORMAT``, a query not on ``ivoa.ObsCore``, or an ADQL
    construct outside the subset. Also an unknown async ``job_id``.
* - 401
  - Tokens are required and the request has none or an invalid one.
* - 5xx
  - DB error / unexpected exception.
```

Errors are returned as SKAVA's JSON error envelope
(`{"error": {"code", "message", "details"}, "request_id"}`), not as a
VOTable with `QUERY_STATUS=ERROR`. On `/tap/async` a query error does
not fail the request: the job is stored with `status: "failed"` and
the message in `error_message`.

## VO discoverability

Point clients directly at the base URL:

```
https://skava.inaf.it/tap
```

TOPCAT and pyvo treat it as a TAP service, read `/tap/capabilities`
and `/tap/tables`, and send queries to `/tap/sync`.

## Limits

* `MAXREC` defaults to 100 and cannot exceed 1000 (the capabilities
  document declares both as `outputLimit` default and hard).
* No per-query timeout is enforced; the reverse proxy timeout applies.
* Connection pool exhaustion under high QPS — set `SKAVA_DB_POOL_SIZE`
  appropriately for your traffic.

## See also

* [VOSI](https://www.ivoa.net/documents/VOSI/) — SKAVA exposes the
  capabilities at ``/tap/capabilities`` and the tableset at
  ``/tap/tables``.
* [Discovery API](discovery.md) — non-TAP path for the same data.
