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

Parameter names follow the IVOA DAL convention (upper case) except for
`obs_id`, `limit` and `offset`. All filters are combined with AND.

```{list-table}
:header-rows: 1
:widths: 22 14 18 46

* - Parameter
  - Type
  - Default
  - Meaning
* - ``limit``
  - int
  - 100
  - Max records returned (range 1-1000).
* - ``offset``
  - int
  - 0
  - Pagination offset (at most 1 000 000).
* - ``POS``
  - ``CIRCLE <ra> <dec> <radius>``
  - —
  - Cone search, ICRS degrees. RA in [0, 360], Dec in [-90, 90],
    radius > 0. Only the ``CIRCLE`` form is accepted.
* - ``BAND``
  - ``<min> <max>`` (m)
  - —
  - Overlap with ``[em_min, em_max]``. ``min/max`` with a slash is
    also accepted; ``min`` must not exceed ``max``.
* - ``TIME``
  - ``<min> <max>`` (MJD)
  - —
  - Overlap with ``[t_min, t_max]``. Same syntax as ``BAND``.
* - ``COLLECTION``
  - str
  - —
  - Exact match on ``obs_collection``.
* - ``DPTYPE``
  - str
  - —
  - Exact match on ``dataproduct_type`` (``image``, ``cube``,
    ``dynspec``, …).
* - ``SPATIAL_CELL``
  - str
  - —
  - Exact match on ``spatial_index_cell``
    (e.g. ``order8:ra213:dec85``).
* - ``obs_id``
  - str
  - —
  - Exact match. Returns at most one record.
```

The cone filter keeps the datasets whose footprint intersects the query
circle, the footprint taken as a circle of radius `s_fov/2` around the
centre (`s_ra`, `s_dec`): the spherical distance between the two centres is
at most the sum of the radii, computed exactly on the sphere (haversine form;
the poles and RA 0/360 included). The circle is an approximation of the
footprint, not the region `s_region` would describe. TAP's ADQL `CONTAINS`
tests the centre only (see [TAP](tap.md)). `BAND` and `TIME` require both bounds of the
dataset to be set. Results are ordered by `obs_id`.

## Example

```bash
curl -s "https://skava.inaf.it/discovery/search?POS=CIRCLE%20150.0%20-30.0%200.5&DPTYPE=cube&limit=10" | jq
```

Response (truncated):

```json
{
  "results": [
    {
      "metadata": {
        "obs_id": "tb-cube-l",
        "obs_collection": "skava-testbed",
        "obs_title": null,
        "dataproduct_type": "cube",
        "calib_level": null,
        "target_name": "Synthetic HI field tb-cube-l",
        "s_ra": 149.9987,
        "s_dec": -29.9989,
        "s_fov": 1.1378,
        "em_min": 0.21414,
        "em_max": 0.21633,
        "spatial_index_order": 8,
        "spatial_index_cell": "order8:ra213:dec85",
        "license": "CC-BY-4.0"
      },
      "replicas": [
        {
          "code": "BIG",
          "name": "Testbed node big",
          "is_enabled": true,
          "is_available": true,
          "latency_score": 10.0,
          "load_score": 0.2,
          "capability_score": 1.0,
          "access_endpoint": "file:///data/cubes/tb-cube-l.fits",
          "rank_reason": "rtt 1.2 ms, cpu pressure 0%, 0.0 tasks/worker, needs 3.0 GB of 7.3 GB free",
          "score": 21.85,
          "telemetry_age_s": 9.4
        }
      ],
      "best_node": "BIG",
      "access_url": "https://skava.inaf.it/access/tb-cube-l",
      "datalink_descriptor": {
        "service": "https://skava.inaf.it/access/tb-cube-l",
        "standard_hint": "DataLink/SODA precursor",
        "operations": ["download", "cutout", "band_subset"]
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
  - The ObsCore-shaped columns of the dataset (``obs_id``,
    ``obs_collection``, ``obs_title``, ``dataproduct_type``,
    ``calib_level``, ``target_name``, ``facility_name``,
    ``instrument_name``, ``s_ra``, ``s_dec``, ``s_fov``, ``t_min``,
    ``t_max``, ``em_min``, ``em_max``, ``spatial_index_order``,
    ``spatial_index_cell``, ``access_estsize``, ``checksum``, ``doi``, ``pid``,
    ``citation``, ``license``).
* - ``replicas[]``
  - The eligible replicas of the dataset, with the host node's
    properties flattened in, already ranked by the configured policy
    (``SKAVA_RANKING_POLICY``): index 0 is the best. Replicas the
    policy set aside are not listed here (DataLink lists them under
    ``routing.excluded``).
* - ``replicas[].rank_reason``
  - Why the policy put the replica there (declared scores for the
    ``static`` policy; RTT, CPU pressure, tasks per worker and memory
    for ``resource_aware``).
* - ``replicas[].score``
  - The ``resource_aware`` cost (lower is better); ``null`` under the
    ``static`` policy and for replicas that could not be measured.
* - ``replicas[].telemetry_age_s``
  - Age in seconds of the node telemetry the decision used, or
    ``null``.
* - ``best_node``
  - Convenience copy of ``replicas[0].code``.
* - ``access_url``
  - ``{SKAVA_PUBLIC_BASE_URL}/access/{obs_id}``: the access resolver,
    which returns a JSON routing envelope (best node, replica URL,
    supported operations, DataLink-style links).
* - ``datalink_descriptor``
  - Quick hint: ``operations`` is ``["download"]``, plus ``cutout``
    and ``band_subset`` when some ranked replica is a ``file://`` copy
    on a node with a co-located VisIVO backend. Use
    ``/datalink/{obs_id}`` for the full envelope.
```

A dataset with no eligible replica is left out of the search results
(it still counts in `total`, so `returned` can be lower than the page
size); `/discovery/dataset/{obs_id}` answers 503 `no_available_nodes`
for it.

## Performance

* Indexed columns: `obs_id` (unique), `obs_collection`,
  `dataproduct_type`, `spatial_index_cell`, `spatial_index_order`.
* The `POS` filter is evaluated on `s_ra`/`s_dec`/`s_fov`; for very
  large catalogues, narrow with `COLLECTION`, `DPTYPE` or
  `SPATIAL_CELL` as well.
* The default limit of 100 keeps responses small; raise it up to 1000
  for bulk pulls.

## Pagination

`limit` + `offset`, ordered by `obs_id`. Offsets beyond 1 000 000 are
refused (400); use narrower filters for deeper scans.

```bash
total=$(curl -s "https://skava.inaf.it/discovery/search?COLLECTION=...&limit=1" | jq .total)
echo "Total: $total"
for offset in $(seq 0 1000 $total); do
    curl -s "https://skava.inaf.it/discovery/search?COLLECTION=...&limit=1000&offset=$offset" \
        | jq -c '.results[].metadata.obs_id'
done
```

## Errors

Errors use the JSON envelope
`{"error": {"code", "message", "details"}, "request_id"}`.

```{list-table}
:header-rows: 1
:widths: 25 75

* - Status
  - When
* - 200
  - Always for a valid query, even when ``returned=0``.
* - 400
  - ``invalid_query``: malformed ``POS``/``BAND``/``TIME``, ``limit``
    out of range, ``offset`` above 1 000 000. ``error.details`` lists
    the failing fields for validation errors.
* - 401
  - Only when static tokens (``SKAVA_ACCESS_TOKENS``) or OIDC
    (``IAM_WELLKNOWN_ENDPOINT``) are configured and the request lacks
    a valid token (see [Authentication](auth.md)). Otherwise discovery
    is open.
* - 404
  - ``dataset_not_found`` on ``/discovery/dataset/{obs_id}``.
* - 503
  - ``no_available_nodes`` on ``/discovery/dataset/{obs_id}`` when no
    replica is eligible.
* - 5xx
  - DB unavailable / unexpected exception. ``request_id`` in the
    response correlates with the structured logs.
```

## See also

* [DataLink API](datalink.md) — resolve a single obs_id with full
  service descriptors and links.
* [TAP API](tap.md) — same data via ADQL for VO tools.
* [Federation API](federation.md) — the same filters across sibling SKAVA instances.
