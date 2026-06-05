# Discovery API

`GET /discovery/search` and `GET /discovery/dataset/{obs_id}` —
public, paginated, ObsCore-aligned.

## Endpoints

```{list-table}
:header-rows: 1
:widths: 35 65

* - Endpoint
  - Purpose
* - ``GET /discovery/search``
  - Paginated list with optional filters. The primary entry point
    for "show me datasets matching X".
* - ``GET /discovery/dataset/{obs_id}``
  - Single dataset detail in the same envelope as a search hit.
    Use when you already know the obs_id.
```

## Query parameters

```{list-table}
:header-rows: 1
:widths: 22 14 18 46

* - Parameter
  - Type
  - Default
  - Meaning
* - ``limit``
  - int
  - 50
  - Max records returned (range 1–500).
* - ``offset``
  - int
  - 0
  - Pagination cursor.
* - ``ra`` / ``dec`` / ``radius``
  - float (deg)
  - —
  - Cone search. All three required if any is supplied.
* - ``dataproduct_type``
  - str
  - —
  - Exact match: ``image`` \| ``cube`` \| ``dynspec`` \|
    ``polarimetric`` \| ``catalog`` \| ``event`` \| …
* - ``obs_collection``
  - str
  - —
  - Exact match against the survey / collection label.
* - ``calib_level``
  - int (0-4)
  - —
  - Exact match.
* - ``target_name``
  - str
  - —
  - Case-insensitive substring match.
* - ``em_min_min`` / ``em_min_max`` / ``em_max_min`` / ``em_max_max``
  - float (m)
  - —
  - Range filters on the spectral bounds.
* - ``t_min_min`` / ``t_min_max`` / ``t_max_min`` / ``t_max_max``
  - float (MJD)
  - —
  - Range filters on the time bounds.
* - ``obs_id``
  - str
  - —
  - Exact match. Returns at most one record.
```

Cone search uses the spatial index (`spatial_index_order` +
`spatial_index_cell`) for sub-millisecond lookups; brute-force
fallback if no index entry exists for the dataset.

## Example

```bash
curl -s "https://skava.inaf.it/discovery/search?ra=83.6&dec=22.0&radius=0.5&dataproduct_type=image&limit=10" | jq
```

Response (truncated):

```json
{
  "results": [
    {
      "metadata": {
        "obs_id": "power9-3a7f1b2c0e5d4986",
        "obs_collection": "inaf-power9-ska",
        "dataproduct_type": "image",
        "calib_level": 2,
        "target_name": "Crab Pulsar",
        "facility_name": "ASKAP",
        "instrument_name": "PAF",
        "s_ra": 83.6331,
        "s_dec": 22.0145,
        "s_fov": 0.1,
        "t_min": 59010.0,
        "t_max": 59010.5,
        "em_min": 2.1e-3,
        "em_max": 2.1e-3,
        "doi": null,
        "pid": null,
        "license": "CC-BY-4.0"
      },
      "replicas": [
        {
          "code": "POWER9",
          "name": "INAF Power9 (Catania)",
          "is_enabled": true,
          "is_available": true,
          "latency_score": 10.0,
          "load_score": 0.05,
          "capability_score": 1.0,
          "access_endpoint": "http://pleiadi-gpu.oact.inaf.it:8001/data/crab.fits"
        }
      ],
      "best_node": "POWER9",
      "access_url": "https://skava.inaf.it/access/power9-3a7f1b2c0e5d4986",
      "datalink_descriptor": {
        "service": "https://skava.inaf.it/access/power9-3a7f1b2c0e5d4986",
        "standard_hint": "DataLink/SODA precursor",
        "operations": ["download", "cutout:TBD", "band_subset:TBD", "time_subset:TBD"]
      }
    }
  ],
  "total": 1,
  "limit": 10,
  "offset": 0,
  "returned": 1
}
```

## Result envelope

```{list-table}
:header-rows: 1
:widths: 22 78

* - Field
  - Meaning
* - ``metadata``
  - Every ObsCore-shaped column of the dataset.
* - ``replicas[]``
  - Every Replica of the dataset, with the host Node's properties
    flattened in. Already ranked — index 0 is the best.
* - ``best_node``
  - Convenience copy of ``replicas[0].code``.
* - ``access_url``
  - SKAVA-side short link redirector that 303-redirects to the
    chosen replica's ``access_endpoint``.
* - ``datalink_descriptor``
  - Quick DataLink hint. Use the dedicated ``/datalink/{obs_id}``
    endpoint for the full envelope.
```

## Performance

* Indexed columns: `obs_id` (unique), `obs_collection`,
  `dataproduct_type`, `spatial_index_cell`, `spatial_index_order`.
* `target_name` is **not** indexed (substring match means LIKE
  '%...%' which can't use a B-tree). Avoid it as the only filter on
  large catalogues.
* Default limit 50 keeps response under a few KB; bump to 500 for
  bulk pulls.

## Pagination

`limit` + `offset`. Cursor-based pagination is on the roadmap (Phase
4) for stable iteration over millions of rows.

For now:

```bash
total=$(curl -s "https://skava.inaf.it/discovery/search?obs_collection=...&limit=1" | jq .total)
echo "Total: $total"
for offset in $(seq 0 500 $total); do
    curl -s "https://skava.inaf.it/discovery/search?obs_collection=...&limit=500&offset=$offset" \
        | jq -c '.results[].metadata.obs_id'
done
```

## Errors

```{list-table}
:header-rows: 1
:widths: 25 75

* - Status
  - When
* - 200
  - Always for valid query, even when ``returned=0``.
* - 400
  - Malformed parameter (string in ``ra``, ``radius`` without
    ``ra``+``dec``, etc.). The JSON ``error.details`` lists which
    fields failed and why.
* - 401
  - Only if ``SKAVA_ACCESS_TOKENS`` is configured and the request
    lacks a valid bearer token. Otherwise discovery is open.
* - 5xx
  - DB unavailable / unexpected exception. ``request_id`` in the
    response correlates with the structured logs.
```

## See also

* [DataLink API](datalink) — resolve a single obs_id with full
  service descriptors and links.
* [TAP API](tap) — same data via ADQL for VO tools.
