# TAP API

`GET /tap/sync` — IVOA TAP-compatible synchronous query interface.
Async TAP is on the roadmap.

## Endpoint

```
GET /tap/sync?LANG=ADQL&QUERY=<ADQL>
```

Public, no auth required by default.

## Supported subset

```{list-table}
:header-rows: 1
:widths: 32 18 50

* - Feature
  - Status
  - Notes
* - ``LANG=ADQL``
  - ✓
  - Required parameter.
* - ``QUERY``
  - ✓
  - URL-encoded ADQL.
* - ``FORMAT=votable``
  - ✓ (default)
  - Returns ``application/x-votable+xml``.
* - ``FORMAT=json``
  - ✓
  - Convenience non-standard format for scripts.
* - ``FORMAT=csv``
  - planned
  - For TOPCAT compatibility.
* - ``MAXREC=N``
  - ✓
  - Cap on returned rows (default 1000, max 100 000).
* - ``REQUEST=doQuery``
  - ✓
  - Accepted; default behaviour.
* - Async (``/tap/async``)
  - ✗
  - Roadmap.
* - VOSI capabilities
  - ✓
  - At ``/vosi/capabilities``.
```

## ADQL subset (sync)

Supported today:

* `SELECT TOP N col1, col2, ...`
* `FROM ivoa.ObsCore` (alias for SKAVA's `datasets` table)
* `WHERE` with `=`, `!=`, `<`, `>`, `<=`, `>=`, `AND`, `OR`, `NOT`,
  `LIKE` (substring with `%`), `IS NULL`, `BETWEEN`
* `ORDER BY col [ASC|DESC]`
* Numeric and string literals

Not yet supported:

* Joins (only ObsCore is visible)
* Subqueries
* Aggregate functions (`COUNT`, `AVG`, `MIN`, `MAX`)
* Geometric functions (`CONTAINS`, `INTERSECTS`, `POINT`, `CIRCLE`)
* `GROUP BY` / `HAVING`

The supported subset is enough for the bulk of "give me records
matching X" workflows. Use `/discovery/search` for spatial cone
search until ADQL geometry lands.

## Example queries

### Top 10 most-recent imaging datasets

```adql
SELECT TOP 10 obs_id, target_name, t_min, t_max
FROM   ivoa.ObsCore
WHERE  dataproduct_type = 'image'
ORDER  BY t_min DESC
```

```bash
QUERY=$(python3 -c "from urllib.parse import quote; print(quote('''
SELECT TOP 10 obs_id, target_name, t_min, t_max
FROM   ivoa.ObsCore
WHERE  dataproduct_type = 'image'
ORDER  BY t_min DESC
'''))")
curl -s "https://skava.inaf.it/tap/sync?LANG=ADQL&QUERY=$QUERY" | head -40
```

### Datasets in a survey, JSON-formatted

```bash
QUERY="SELECT obs_id,s_ra,s_dec FROM ivoa.ObsCore WHERE obs_collection='inaf-power9-ska'"
curl -s "https://skava.inaf.it/tap/sync?LANG=ADQL&QUERY=$QUERY&FORMAT=json" | jq
```

### Datasets in a frequency band

```adql
SELECT obs_id, em_min, em_max
FROM   ivoa.ObsCore
WHERE  em_min BETWEEN 1.0e-3 AND 2.0e-3
   AND em_max BETWEEN 1.0e-3 AND 2.0e-3
```

## VOTable response shape

```xml
<?xml version="1.0" encoding="UTF-8"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">
  <RESOURCE type="results">
    <INFO name="QUERY_STATUS" value="OK"/>
    <TABLE>
      <FIELD name="obs_id" datatype="char" arraysize="*"/>
      <FIELD name="target_name" datatype="char" arraysize="*"/>
      <FIELD name="t_min" datatype="double"/>
      <FIELD name="t_max" datatype="double"/>
      <DATA>
        <TABLEDATA>
          <TR><TD>power9-3a7f...</TD><TD>Crab Pulsar</TD><TD>59010.0</TD><TD>59010.5</TD></TR>
        </TABLEDATA>
      </DATA>
    </TABLE>
  </RESOURCE>
</VOTABLE>
```

## Errors

```{list-table}
:header-rows: 1
:widths: 18 82

* - Status
  - When
* - 200
  - Always for parseable queries — even invalid syntax returns 200
    with ``<INFO name="QUERY_STATUS" value="ERROR"/>`` in the
    VOTable.
* - 400
  - Missing ``QUERY`` or ``LANG`` parameters.
* - 5xx
  - DB error / unexpected exception.
```

The "always 200" rule for ADQL errors is by IVOA convention — VO
tools (TOPCAT, Aladin) look at the embedded `QUERY_STATUS` rather
than HTTP status codes.

## VO discoverability

Add SKAVA to TOPCAT / Aladin via the registry once the endpoint is
publicly listed. Until then, point clients directly at:

```
https://skava.inaf.it/tap
```

Both TOPCAT and Aladin treat the base URL as a TAP service and
auto-detect the sync endpoint.

## Limits

* `MAXREC` defaults to 1000; can be raised to 100 000.
* No per-query timeout enforced today; the reverse proxy timeout
  applies.
* Connection pool exhaustion under high QPS — set `SKAVA_DB_POOL_SIZE`
  appropriately for your traffic.

## See also

* [VOSI capabilities](https://www.ivoa.net/documents/VOSI/) — SKAVA
  exposes them at ``/vosi/capabilities``.
* [Discovery API](discovery) — non-TAP path for the same data with
  proper cone search support.
