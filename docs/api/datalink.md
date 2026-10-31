# DataLink API

`GET /datalink/{obs_id}` — IVOA DataLink-aligned resolution of a
single dataset into access URLs and service descriptors.

## Endpoints

```
GET|POST /datalink?ID=<id>[&ID=<id>...]     the DataLink 1.1 {links} endpoint (VOTable)
GET      /datalink/{obs_id}[?RESPONSEFORMAT=votable]   SKAVA's resource for one dataset (JSON)
```

**`/datalink`** is the standard `{links}` endpoint: one or more `ID`
(repeated, by GET or as POST form fields, at most 100; beyond that the first
100 are answered and `QUERY_STATUS` is `OVERFLOW`; no `ID` gives an empty
table), a VOTable by default,
`RESPONSEFORMAT` accepted only for VOTable types (anything else is a 400).
Every row carries the `ID` it answers. An unknown ID gives one row with
`semantics` `#this` and `NotFoundFault: <id>` in `error_message`; a dataset no
node can serve now gives `TransientFault: ...`; the other IDs are answered
normally. The results resource declares
`standardID = ivo://ivoa.net/std/DataLink#links-1.1`. When several IDs share
a response, each dataset's service-descriptor `RESOURCE` IDs are prefixed
(`id1-`, `id2-`, ...) so they stay unique. The `access_url` of every TAP row
points here.

**`/datalink/{obs_id}`** is SKAVA's application resource for one dataset:

Both are open unless the deployment requires tokens (static
`SKAVA_ACCESS_TOKENS` or OIDC; see [Authentication](auth.md)). The resource
returns 404 when the obs_id is unknown. JSON is the default; `RESPONSEFORMAT`
(or `FORMAT`) set to `votable`, `application/x-votable+xml`,
`application/xml` or `xml` returns the VOTable described below.

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
  - Node code of the selected replica (the first ranked replica whose
    access endpoint is usable; otherwise the next one in ranking order).
* - ``routing.policy``
  - The ranking policy that decided: ``static`` or ``resource_aware``
    (``SKAVA_RANKING_POLICY``).
* - ``routing.replicas[]``
  - The eligible replicas, best first, each with its host node's
    properties and the decision: ``rank_reason``, ``score`` (the
    ``resource_aware`` cost, lower is better; ``null`` under ``static``)
    and ``telemetry_age_s``.
* - ``routing.excluded[]``
  - The replicas the policy set aside, as ``{code, reason}`` (node
    disabled or unavailable, replica not public, backend unreachable at
    the last probe, not enough free memory, …).
* - ``primary_access``
  - The selected replica: ``access_url``, ``access_format``,
    ``access_estsize`` (ObsCore's estimate, KB) and ``content_length``
    (bytes: the exact size the publisher measured, or the estimate × 1024
    when no exact size agrees with it).
* - ``links[]``
  - Link table: ``rel``, ``href``, ``content_type``, ``title``,
    ``description``, ``node_id`` (see below).
* - ``service_descriptors[]``
  - Per-service descriptors (see below).
* - ``capabilities``
  - Boolean flags for clients deciding which features to render:
    ``supports_datalink``, ``supports_soda_sync``,
    ``supports_soda_async``, ``supports_cutout``, ``supports_preview``
    (always false), ``supports_soda_sync_endpoint`` (always true),
    ``supports_soda_sync_execution``, ``supports_soda_async_endpoint``,
    ``supports_soda_async_execution``. The sync/cutout flags are true
    when a ranked replica is a ``file://`` copy on a node with a
    co-located VisIVO backend; the async flags when such a node can
    run the node SODA service for the dataset.
```

## Worked example

```bash
curl -s "https://skava.inaf.it/datalink/tb-cube-l" | jq
```

Selected fields (testbed, `resource_aware` policy):

```json
{
  "dataset": {
    "obs_id": "tb-cube-l",
    "obs_collection": "skava-testbed",
    "dataproduct_type": "cube"
  },
  "routing": {
    "best_node": "BIG",
    "policy": "resource_aware",
    "replicas": [
      {
        "code": "BIG",
        "access_endpoint": "file:///data/cubes/tb-cube-l.fits",
        "rank_reason": "rtt 1.7 ms, cpu pressure 0%, 0.0 tasks/worker, needs 3.0 GB of 7.3 GB free",
        "score": 22.35,
        "telemetry_age_s": 10.7
      }
    ],
    "excluded": [
      {
        "code": "SMALL",
        "reason": "not enough memory: rtt 1.7 ms, cpu pressure 0%, 0.0 tasks/worker, needs 3.0 GB of 1.8 GB free"
      }
    ]
  },
  "primary_access": {
    "access_url": "file:///data/cubes/tb-cube-l.fits",
    "access_format": "image/fits",
    "access_estsize": 3145733,
    "content_length": 3221230592
  },
  "service_descriptors": [
    {
      "service_type": "soda-sync",
      "service_id": "skava-soda-sync",
      "access_url": "https://skava.inaf.it/soda/sync",
      "standard_id": "ivo://ivoa.net/std/SODA#sync-1.0",
      "supported_parameters": ["ID", "POS", "BAND", "TIME", "RESPONSEFORMAT"],
      "enabled": true
    },
    {
      "service_type": "node-soda-sync",
      "service_id": "soda-sync-big",
      "access_url": "http://node-big:8000/soda/sync",
      "standard_id": "ivo://ivoa.net/std/SODA#sync-1.0",
      "supported_parameters": ["ID", "POS", "CIRCLE", "POLYGON", "BAND", "TIME", "RESPONSEFORMAT"],
      "node_code": "BIG",
      "requires_auth": false,
      "input_params": {"ID": "file:///data/cubes/tb-cube-l.fits"},
      "enabled": true
    },
    {
      "service_type": "visivo-backend",
      "service_id": "visivo-backend-big",
      "access_url": "http://node-big:8000",
      "endpoint": "http://node-big:8000",
      "node_code": "BIG",
      "requires_auth": false,
      "supports_kinds": ["image", "cube", "dynspec"],
      "enabled": true
    }
  ]
}
```

## Service descriptors

Every descriptor has `service_type`, `service_id`, `access_url`,
`standard_id`, `supported_parameters`, `enabled` and `description`;
node descriptors add `node_code`, `requires_auth` and, where a value is
fixed for this dataset, `input_params`.

```{list-table}
:header-rows: 1
:widths: 24 18 58

* - ``service_type``
  - Standard
  - Purpose
* - ``access-resolution``
  - DataLink 1.1
  - Points back at this endpoint. Always enabled.
* - ``soda-sync``
  - SODA sync 1.0
  - SKAVA's ``/soda/sync``. Always enabled: it answers 303 to the
    node's SODA service when a node can process the dataset in place,
    otherwise it validates the request and returns its routing.
* - ``soda-async``
  - SODA async 1.0
  - Always ``enabled: false``: SKAVA runs no jobs itself; asynchronous
    SODA is the node's service (``node-soda-async``).
* - ``cutout``
  - none
  - SKAVA's ``POST /soda/execute`` proxy (non-standard). Enabled when
    a ranked replica is a ``file://`` copy on a node with a co-located
    VisIVO backend.
* - ``node-soda-sync``
  - SODA sync 1.0
  - ``{backend}/soda/sync`` on the node holding the selected
    in-place replica (``ID``, ``POS``, ``CIRCLE``, ``POLYGON``,
    ``BAND``, ``TIME``, ``RESPONSEFORMAT``); ``input_params.ID`` is the
    replica's identifier on that node.
* - ``node-soda-async``
  - SODA async 1.0
  - ``{backend}/soda/async`` on the same node: the cutout as a UWS job.
* - ``visivo-moment``
  - SODA async 1.0
  - Moment map as a node UWS job (``OPERATION=MOMENT``; ``MOMENT``,
    ``CHANNELS``, ``THRESHOLD``). Cubes only.
* - ``visivo-pv``
  - SODA async 1.0
  - Position-velocity diagram as a node UWS job (``OPERATION=PV``;
    ``PVPATH``, ``PVWIDTH``). Cubes only.
* - ``visivo-backend``
  - SKAVA-specific
  - One per ranked node with a ``visivo_backend_url``, best first.
    Desktop clients route compute here instead of downloading.
```

The four node descriptors are emitted only when a node can process the
dataset in place: the first ranked replica that is a `file://` copy on
a node with a co-located VisIVO backend. They are enabled when that node
is enabled and available.

## The visivo-backend descriptor

Emitted for every ranked replica whose Node has a non-empty
``visivo_backend_url``, in ranking order. Fields:

```{list-table}
:header-rows: 1
:widths: 28 72

* - Field
  - Meaning
* - ``service_type``
  - Constant: ``visivo-backend``
* - ``service_id``
  - ``visivo-backend-<node_code>`` (lower-case)
* - ``access_url`` / ``endpoint``
  - The backend URL the Node operator configured.
* - ``node_code``
  - Which Node this descriptor belongs to (used by clients for
    matching against a local registry).
* - ``requires_auth``
  - True when the backend expects a bearer token.
* - ``supports_kinds``
  - Data product kinds the backend can handle (currently always
    ``image``, ``cube``, ``dynspec``).
* - ``enabled``
  - The node is enabled and available.
* - ``description``
  - Human-readable text.
```

A client that keeps its own list of compute backends recognises a node by
the descriptor's ``endpoint`` or its ``node_code``; see
[Clients](../clients/overview.md#matching-keys).

## Links table

```{list-table}
:header-rows: 1
:widths: 22 78

* - ``rel``
  - Meaning
* - ``self``
  - This DataLink document (JSON).
* - ``direct-download``
  - The selected replica's ``access_endpoint``, with ``node_id``.
* - ``alternate-replica``
  - One per other eligible replica, with ``node_id``.
* - ``preview`` / ``metadata``
  - Placeholders with ``href: null`` (no preview or separate metadata
    service is offered).
* - ``datalink``
  - Same URL as ``self``.
* - ``soda-sync``
  - SKAVA's ``/soda/sync``.
```

Generic VO clients (Aladin, TOPCAT) should request the VOTable, which
maps these onto the IVOA semantics vocabulary.

## VOTable output

JSON is the default. Request `RESPONSEFORMAT=application/x-votable+xml`
(or `FORMAT=votable`) to get a **conformant IVOA DataLink VOTable**:

- the standard `{links}` table columns
  (`ID, access_url, service_def, error_message, semantics, description,
  content_type, content_length, link_auth, link_authorized`) with the spec
  UCDs, plus the SKAVA extensions `node_id` (the node a row belongs to),
  `rank_reason` and `score` (the routing decision on the `#this` rows: why
  the policy ranked that replica where it is, and its cost, lower is
  better, as `routing.replicas[]` has them in the JSON) and
  `local_access_url` (see below);
- `content_length` in bytes, the file's exact size (ObsCore's
  `access_estsize` is in kilobytes);
- IVOA semantics vocabulary terms (`#this`, `#preview`, `#auxiliary`,
  `#cutout`, `#proc`);
- the `#this` rows are the replicas, best node first, and each is a link a
  client can follow to the dataset itself:
  - a copy at an `http(s)://` or `ftp://` URL is linked directly;
  - a `file://` copy on a node with a VisIVO backend is linked through the
    node's SODA, `<backend>/soda/sync?ID=<the file:// URL>`: with no `POS`,
    `BAND` or `TIME` the node returns the file as stored (every HDU, byte
    for byte), under the node's own token (`link_auth`). The `file://`
    location itself, which the node's backend opens in place, is in
    `local_access_url`, never in `access_url`;
  - a copy no client and no node service can reach (`file://` on a node
    without a backend, `sftp://`, ...) gets no row; a dataset left without
    a `#this` row gets one `NotFoundFault` row;
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
  - Success.
* - 401
  - Tokens are required and the request has none or an invalid one.
* - 404
  - ``dataset_not_found``: obs_id unknown.
* - 503
  - ``no_available_nodes``: the catalogue knows the dataset but no
    replica is eligible, or none of the eligible ones has a usable
    access endpoint.
* - 5xx
  - DB unavailable / unexpected exception.
```

## See also

* [Discovery API](discovery.md) for the parent search endpoint.
* [SODA API](soda.md) for the sync execution surface that this DataLink
  links to.
* [Compute next to data](../architecture/compute-next-to-data.md) for
  how clients use the visivo-backend descriptor.
