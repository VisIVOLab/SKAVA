# Clients

SKAVA tells a client where a dataset is, which node should serve it and
why, and which services that node offers. It does not open files or run
computations for the client. This page describes what a client reads from
SKAVA's answer and how the main kinds of client use it. The fields are
specified in the [DataLink API](../api/datalink.md); the services behind
them in [Compute next to data](../architecture/compute-next-to-data.md).

```{contents}
:local:
:depth: 2
```

## What a client reads

A client finds a dataset with [discovery](../api/discovery.md) or
[TAP](../api/tap.md), then resolves it with `GET /datalink/{obs_id}` (JSON)
or the standard `{links}` endpoint `GET /datalink?ID=...` (VOTable). The
answer carries four things a client acts on.

### The ranked replicas

`routing.replicas[]` lists the copies of the dataset, best first, one per
node. Each has the node's `code`, the copy's `access_endpoint`, and the
ranking decision:

```{list-table}
:header-rows: 1
:widths: 24 76

* - Field
  - Meaning
* - ``rank_reason``
  - Why the policy put the replica where it is, as text a client can show
    to the user (under ``resource_aware``: the measured round trip, CPU
    pressure, tasks per worker and memory margin; under ``static``: the
    declared scores).
* - ``score``
  - The ``resource_aware`` cost, lower is better; ``null`` under
    ``static``.
* - ``telemetry_age_s``
  - Age in seconds of the node telemetry the decision used.
```

`routing.policy` names the policy and `routing.excluded[]` lists the
replicas set aside, each with its `reason`. `primary_access.access_url` is
the first replica's endpoint. A `file://` endpoint is a path on that node's
own storage: no client can read it from elsewhere, only a service running
on that node can (see below).

### The service descriptors

`service_descriptors[]` lists SKAVA's own services and those of the nodes.
The ones that point at a node:

```{list-table}
:header-rows: 1
:widths: 24 76

* - ``service_type``
  - What it is
* - ``visivo-backend``
  - The VisIVO Visual Analytics backend co-located with a node, one
    descriptor per ranked replica whose node has one, in ranking order.
    Carries ``endpoint`` (the backend's URL as registered on the node),
    ``node_code``, ``requires_auth`` and ``supports_kinds``
    (``image``, ``cube``, ``dynspec``). ``enabled`` is false when the node
    is disabled or unavailable.
* - ``node-soda-sync``
  - The node's SODA sync service (``ivo://ivoa.net/std/SODA#sync-1.0``),
    present when the first ranked ``file://`` replica sits on a node with a
    backend.
* - ``node-soda-async``
  - The same node's SODA async (UWS) service
    (``ivo://ivoa.net/std/SODA#async-1.0``).
* - ``visivo-moment``, ``visivo-pv``
  - Moment maps (``OPERATION=MOMENT``) and position-velocity diagrams
    (``OPERATION=PV``) as SODA async jobs on that node. Present for
    datasets whose ``dataproduct_type`` is ``cube`` only.
```

The node services carry `input_params`: the fixed values a client must
send, `ID` (the replica's own `file://` endpoint on that node) and, for the
operations, `OPERATION`. They also carry `node_code` and `requires_auth`.

### Authentication per service

`requires_auth: true` means the node's backend expects the backend's own
token, not SKAVA's. SKAVA's token (static or from the IAM) is for SKAVA's
endpoints; a node's token is for that node. A client must never send one in
place of the other.

### Matching keys

A client that keeps its own list of compute backends recognises a node by
two keys: the descriptor's `endpoint` (the URL) and its `node_code` (the
node's `code` in the catalogue, also `routing.replicas[].code` and
`links[].node_id`). A client that reaches a node at another address than
the one registered in SKAVA (a tunnel, a VPN) matches on `node_code`. The
copy to open on a node is that node's replica in `routing.replicas`, not
`primary_access`, which belongs to the first node only.

## Generic VO clients

pyvo, TOPCAT, Aladin and other VO tools use the standard interfaces only:
TAP on `ivoa.obscore` to find datasets, and the DataLink VOTable to reach
them. The DataLink VOTable carries the same decision as the JSON:

* one `#this` row per copy, best node first, with `node_id`, `rank_reason`
  and `score`; a copy on a node's own storage is served through that node's
  SODA sync service (the file as stored), and its `file://` location is in
  `local_access_url`;
* one `#auxiliary` row per co-located backend, pointing at its status
  document (`/v1/node/status`);
* `#cutout` rows (the node's SODA sync and async) and `#proc` rows
  (moment, PV), each bound to a service-descriptor `RESOURCE` with the
  standard SODA parameters typed and `ID` fixed to the node's replica;
* `link_auth` on each row says whether that link needs a token.

A client that follows a `#cutout` row calls the node's SODA directly. A
client that calls SKAVA's `/soda/sync` instead is redirected (303) to the
same node service. See the [SODA API](../api/soda.md).

## VisIVO Visual Analytics

The VisIVO Visual Analytics desktop searches SKAVA from its SKAVA tab,
shows the node SKAVA ranked first with its `rank_reason`, and opens the
dataset on that node's backend by matching the `visivo-backend`
descriptors against the backends the user registered; it runs cutouts,
moment maps, PV diagrams and source finders through the node services
above. How it picks the node, when it falls back, and how it handles
SKAVA's and the nodes' tokens is documented by VisIVO:
[SKAVA discovery](https://visivo.readthedocs.io/en/latest/user-guide/skava-discovery.html).

## See also

* [DataLink API](../api/datalink.md) for every field.
* [Compute next to data](../architecture/compute-next-to-data.md) for the
  pattern.
* [Registering a node SKAVA cannot reach](../operations/node-behind-firewall.md)
  for a node behind a firewall or a tunnel.
