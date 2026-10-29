# DataLink API

`GET /datalink/{obs_id}` — IVOA DataLink-aligned resolution of a
single dataset into access URLs and service descriptors.

## Endpoint

```
GET /datalink/{obs_id}
```

Public, no authentication required. Returns 404 when the obs_id is
unknown.

## Response envelope

```{list-table}
:header-rows: 1
:widths: 28 72

* - Field
  - Meaning
* - ``dataset``
  - Slim view of the dataset (obs_id, obs_collection,
    dataproduct_type). The full ObsCore is on the discovery endpoint.
* - ``routing.best_node``
  - Node code of the ranked-first replica.
* - ``routing.replicas[]``
  - All known replicas, with each one's host node properties.
* - ``primary_access``
  - The chosen replica: ``access_url``, ``access_format``,
    ``access_estsize``.
* - ``links[]``
  - IVOA-style link table: ``rel``, ``href``, ``content_type``,
    ``title``, ``description``, ``node_id``. Includes the canonical
    ``#this``, plus preview / metadata / soda-sync placeholders.
* - ``service_descriptors[]``
  - Per-service hints (see below).
* - ``capabilities``
  - Quick boolean flags useful for clients deciding which features
    to render.
```

## Worked example

```bash
OBS=power9-3a7f1b2c0e5d4986
curl -s "https://skava.inaf.it/datalink/$OBS" | jq
```

Selected fields:

```json
{
  "dataset": {
    "obs_id": "power9-3a7f1b2c0e5d4986",
    "obs_collection": "inaf-power9-ska",
    "dataproduct_type": "image"
  },
  "primary_access": {
    "access_url": "http://pleiadi-gpu.oact.inaf.it:8001/data/crab.fits",
    "access_format": "image/fits",
    "access_estsize": 4096
  },
  "service_descriptors": [
    {
      "service_type": "access-resolution",
      "access_url": "https://skava.inaf.it/datalink/power9-3a7f1b2c0e5d4986",
      "standard_id": "ivo://ivoa.net/std/DataLink#links-1.1",
      "enabled": true
    },
    {
      "service_type": "soda-sync",
      "access_url": "https://skava.inaf.it/soda/sync",
      "standard_id": "ivo://ivoa.net/std/SODA#sync-1.0",
      "supported_parameters": ["ID","POS","BAND","TIME","RESPONSEFORMAT"],
      "enabled": true
    },
    {
      "service_type": "visivo-backend",
      "endpoint": "http://pleiadi-gpu.oact.inaf.it:8000",
      "node_code": "POWER9",
      "requires_auth": true,
      "supports_kinds": ["image","cube","dynspec"],
      "enabled": true
    }
  ]
}
```

## Service descriptors

```{list-table}
:header-rows: 1
:widths: 24 18 58

* - ``service_type``
  - Standard
  - Purpose
* - ``access-resolution``
  - DataLink 1.1
  - The canonical "give me an access URL" service. Points back at
    this same endpoint.
* - ``soda-sync``
  - SODA sync 1.0
  - Validates parameters and routes (`/soda/sync`). Always enabled.
* - ``soda-async``
  - SODA async 1.0
  - Reserved (``enabled: false`` until async execution lands).
* - ``cutout``
  - SODA sync 1.0
  - Real cutout via `/soda/execute`. ``enabled: true`` **when the
    dataset has a node with a co-located VisIVO backend** (else false).
* - ``visivo-backend``
  - SKAVA-specific
  - VisIVO compute backend co-located with the best replica.
    Desktop clients route compute here instead of downloading.
```

## The visivo-backend descriptor

Emitted whenever the ranked-first replica's Node has a non-empty
``visivo_backend_url``. Fields:

```{list-table}
:header-rows: 1
:widths: 28 72

* - Field
  - Meaning
* - ``service_type``
  - Constant: ``visivo-backend``
* - ``service_id``
  - ``visivo-backend-<node_code>`` (lower-case)
* - ``endpoint``
  - The backend URL the Node operator configured.
* - ``node_code``
  - Which Node this descriptor belongs to (used by clients for
    matching against a local registry).
* - ``requires_auth``
  - True when the backend expects a bearer token.
* - ``supports_kinds``
  - Optional list of data product kinds (``image``, ``cube``,
    ``dynspec``, ``polarimetric``) the backend can handle.
* - ``description``
  - Human-readable text.
```

VisIVO desktop's routing logic walks the descriptors and tries to
match each against its registered backends, first by URL then by
node code. See
[Client integration / backend routing](../client-integration/backend-routing).

## Links table

DataLink-style; for each link:

```{list-table}
:header-rows: 1
:widths: 18 22 60

* - ``rel``
  - ``#this`` \| ``preview`` \| ``metadata`` \| ``datalink`` \|
    ``soda-sync`` \| ``direct-download``
  - IVOA semantics. ``#this`` is the canonical self-link.
```

Generic VO clients (Aladin, TOPCAT) will render these as a tabular
list when the user clicks "follow DataLink" on a search result.

## VOTable output

JSON is the default. Request `RESPONSEFORMAT=application/x-votable+xml`
(or `FORMAT=votable`) to get a **conformant IVOA DataLink VOTable**:

- the standard `{links}` table columns
  (`ID, access_url, service_def, error_message, semantics, description,
  content_type, content_length, link_auth, link_authorized`) with the spec
  UCDs, plus the SKAVA extensions `node_id` (the node a row belongs to),
  `rank_reason` and `score` (the routing decision on the `#this` rows: why
  the policy ranked that replica where it is, and its cost, lower is
  better, as `routing.replicas[]` has them in the JSON);
- IVOA semantics vocabulary terms (`#this`, `#preview`, `#auxiliary`,
  `#cutout`, `#proc`);
- the `#this` rows are the replicas, best node first;
- one `#auxiliary` row per **VisIVO backend** co-located with a replica,
  best node first, so VO clients see where the dataset can be analysed in
  place: `access_url` is the backend's status document
  (`<backend>/v1/node/status`, `application/json`; `link_auth` is
  `optional` when the backend's API takes a token), `node_id` the node code;
- **only when the node can process the dataset in place** (a `file://`
  replica on a node with a VisIVO backend): `#cutout` rows for the node's
  own SODA (`standardID = SODA#sync-1.0` and `SODA#async-1.0`) and, for a
  cube, `#proc` rows for the moment-map and PV operations
  (`SODA#async-1.0` with a fixed `OPERATION`), each with a service-descriptor
  `RESOURCE` (`utype="adhoc:service"`) whose `inputParams` `GROUP` carries
  the typed SODA parameters and fixes `ID` to the replica's identifier on
  that node.

The `soda-sync` link (SKAVA's redirecting endpoint) and the `/soda/execute`
proxy appear in the JSON envelope only: in a VOTable a `#cutout` row means
"this returns the cutout", which only the node's service does.

This is what Aladin / TOPCAT consume as a DataLink document; the JSON
descriptor is what the VisIVO desktop reads via `service_descriptors`.

## Error responses

```{list-table}
:header-rows: 1
:widths: 18 82

* - Status
  - Meaning
* - 200
  - Success — even when the dataset has zero healthy replicas (the
    response includes the empty ``primary_access``).
* - 404
  - obs_id unknown.
* - 5xx
  - DB unavailable / unexpected exception.
```

A response with valid 200 and zero replicas is a useful signal that
"the catalogue knows this dataset but no node currently hosts a
copy" — typically a stuck staging job.

## See also

* [Discovery API](discovery) for the parent search endpoint.
* [SODA API](soda) for the sync execution surface that this DataLink
  links to.
* [Compute next to data](../architecture/compute-next-to-data) for
  how clients use the visivo-backend descriptor.
