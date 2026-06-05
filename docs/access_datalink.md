# Access Layer: DataLink-like JSON and VOTable

## Purpose

`GET /datalink/{obs_id}` provides the canonical production DataLink-like JSON envelope by default.
It also supports a minimal VOTable links table with `RESPONSEFORMAT=application/x-votable+xml` or `FORMAT=votable`.

`GET /access/{obs_id}` remains available as a compatibility facade over `/datalink/{obs_id}`.

This is not a full IVOA DataLink server yet. It is a practical precursor that keeps existing clients working and exposes structured links/service descriptors for future VO evolution.

## Response Structure

Top-level shape:

```json
{
  "dataset": {},
  "routing": {},
  "primary_access": {},
  "links": [],
  "service_descriptors": [],
  "capabilities": {}
}
```

Legacy compatibility fields are still present:
- `obs_id`
- `best_node`
- `access_url`
- `access_mode`
- `supported_operations`
- `supports_soda`
- `supports_datalink`

## DataLink Conceptual Mapping

- `dataset`: identity aligned with ObsCore fields (`obs_id`, `obs_collection`, `dataproduct_type`)
- `routing`: selected node and replica list used for operational access resolution
- `primary_access`: selected direct endpoint + format/size metadata
- `links`: DataLink-like related links (`self`, `direct-download`, `alternate-replica`, placeholders)
- `service_descriptors`: DataLink-style service descriptors for current and future services
- `capabilities`: explicit feature flags for current behavior

## Placeholders

Current placeholders are explicitly marked:
- `preview` link
- `metadata` link
- `soda-async` links/descriptors
- `cutout` descriptor

`soda-sync` is exposed as an operational stub endpoint (`/soda/sync`) for validation and routing orchestration.
Actual server-side subset execution remains not implemented.

## Curl Example

```bash
curl 'http://localhost:8000/datalink/dataset-3'
curl 'http://localhost:8000/datalink/dataset-3?FORMAT=votable'
curl 'http://localhost:8000/access/dataset-3'
```

## Example Response (abridged)

```json
{
  "obs_id": "dataset-3",
  "best_node": "B",
  "access_url": "http://localhost:8000/access/dataset-3",
  "dataset": {
    "obs_id": "dataset-3",
    "obs_collection": "skava-demo",
    "dataproduct_type": "image"
  },
  "routing": {
    "best_node": "B",
    "replicas": [{"code": "A"}, {"code": "B"}]
  },
  "primary_access": {
    "access_url": "https://node-b.example.org/datalink/dataset-3",
    "access_format": "image/fits",
    "access_estsize": 3072
  },
  "links": [
    {"rel": "self", "href": "http://localhost:8000/access/dataset-3"},
    {"rel": "direct-download", "href": "https://node-b.example.org/datalink/dataset-3"},
    {"rel": "alternate-replica", "href": "https://node-a.example.org/datalink/dataset-3"}
  ],
  "service_descriptors": [
    {"service_type": "access-resolution", "enabled": true},
    {"service_type": "soda-sync", "enabled": true}
  ],
  "capabilities": {
    "supports_datalink": true,
    "supports_soda_sync": false,
    "supports_soda_sync_endpoint": true,
    "supports_soda_sync_execution": false,
    "supports_soda_async": false,
    "supports_cutout": false,
    "supports_preview": false
  }
}
```
