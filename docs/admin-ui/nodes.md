# Nodes

A **Node** is a federation member — a data centre / SRC site / mirror
archive that hosts one or more Dataset Replicas. The admin UI's
`/admin/nodes/` page is the CRUD surface; this page documents the
fields, when each matters, and the operational implications.

## Fields

```{list-table}
:header-rows: 1
:widths: 22 12 16 50

* - Field
  - Required?
  - Default
  - Meaning
* - **Code**
  - yes
  - —
  - Stable short identifier (max 32 chars; letters, digits,
    ``_`` and ``-``, no spaces). Must be unique. Used as ObsCore
    ``node_id`` on every replica and as the node_code in
    DataLink service descriptors. Stored upper-case. Examples:
    ``INAF-CT``, ``POWER9``, ``SARAO-CT``.
* - **Name**
  - yes
  - —
  - Human-readable label shown in the admin UI and in some
    DataLink fields.
* - **Base URL**
  - yes
  - —
  - Where the site exposes its data-access service. Used as a
    descriptive endpoint; the per-file URLs live on the Replicas
    instead. Schemes ``http(s)://``, ``file://``, ``ftp://``,
    ``sftp://``, ``s3://`` are all accepted — SKAVA is
    scheme-agnostic.
* - **VisIVO backend URL**
  - no
  - empty
  - Must start with ``http://`` or ``https://``. When set, the
    DataLink response emits a ``visivo-backend`` service descriptor
    pointing here, and, when this node holds a ``file://`` replica,
    the node SODA descriptors (``node-soda-sync``,
    ``node-soda-async``, plus ``visivo-moment`` / ``visivo-pv`` for
    cubes). Desktop clients then route compute to this URL instead
    of downloading the file (see
    [compute next to data](../architecture/compute-next-to-data.md)).
    It is also the address SKAVA's telemetry prober measures. Leave
    empty for archive-only nodes.
* - **Requires bearer-token authentication**
  - no
  - false
  - Stored as ``visivo_backend_requires_auth``. Surfaces as the
    ``requires_auth`` field of this node's ``visivo-backend`` and
    node SODA descriptors; desktops use it to decide whether to send
    the token they have for this node. The prober also sends
    ``SKAVA_VISIVO_BACKEND_TOKEN`` (as ``X-Visivo-Token``) when it
    reads such a node's status.
* - **Latency / load / capability scores**
  - no
  - empty
  - Declared scores. Under ``resource_aware`` (the default policy)
    the measured telemetry ranks the nodes and these scores only
    order the nodes that cannot be measured. Under ``static``
    (``SKAVA_RANKING_POLICY=static``) they are the whole ranking:
    latency ascending, then load ascending, then capability
    descending; an empty score sorts last.
* - **Enabled**
  - yes
  - true
  - Operator off-switch. A disabled node's replicas are excluded
    from DataLink routing (reason "node disabled by the operator")
    and the prober skips it. Its datasets stay discoverable.
* - **Available**
  - yes
  - true
  - Manual "is it serving right now?" flag. When unticked, the
    node's replicas are excluded from routing ("node marked
    unavailable by the operator") and its descriptors are emitted
    with ``enabled: false``. It is never changed automatically: the
    prober records its own result separately (see below).
```

## Measured state (telemetry)

Besides the fields above, each node row holds what SKAVA last measured
on, or was told by, its co-located backend: ``probe_ok`` (did it answer),
``probe_rtt_ms`` (median round trip of ``/v1/ping``),
``probe_error``, ``telemetry_json`` (its ``/v1/node/status``
document: CPU, memory, tasks, workers, capabilities) and
``telemetry_at``. Only enabled nodes with a VisIVO backend URL are
probed. A node SKAVA cannot reach (behind a firewall or an SSH tunnel)
can instead push the same document itself with a per-node token
(node reports, see [Telemetry](../api/telemetry.md)); the prober then
skips that node while its reports are fresh.

These columns are not shown or editable in the admin UI, and saving
the node form leaves them untouched. Read them with
``GET /internal/telemetry`` and force a new probe with
``POST /internal/telemetry/probe`` (both require the
``X-Internal-Api-Key``). The prober runs every
``SKAVA_TELEMETRY_INTERVAL_SECONDS`` (10 s by default; 0 disables the
background loop); the ``resource_aware`` policy ignores telemetry
older than ``SKAVA_TELEMETRY_TTL_SECONDS`` and does not route to a
node whose last probe failed.

## Adding a node — worked example

For a new INAF Power9 SRC node hosting both data and a VisIVO compute
backend:

```
Code:                POWER9
Name:                INAF Power9 (Catania)
Base URL:            http://pleiadi-gpu.oact.inaf.it:8000
VisIVO backend URL:  http://pleiadi-gpu.oact.inaf.it:8000
Requires bearer:     ✓
Latency score:       10
Load score:          0.05
Capability score:    1.0
Enabled / Available: ✓ / ✓
```

Click **Create node**. The page redirects to the edit form for the
new row with a green "Created node POWER9" flash.

## Editing a node

The same form is reused. The Code field is editable — if you rename a
node, every Replica that points at it keeps working because
references are by FK id, not by code.

Audit row produced: ``node.update`` with a before/after diff of every
changed column.

## Deleting a node

Two safety nets:

1. The form refuses to delete a node that still has Replicas pointing
   at it ("Cannot delete: N dataset replicas reference it. Remove
   those datasets first."). This prevents the cascade from silently
   wiping ingested data.
2. A browser confirmation dialog precedes the actual ``POST``.

The "remove the replicas first" step can be:

* Remove the node's replicas from each dataset's detail page
  (Replicas section), after publishing a copy on another node if the
  data must stay reachable.
* Delete the datasets that only live on this node.
* Bulk DELETE in PostgreSQL (audit-trail leaving — only do this on
  staging).

## How nodes feed the DataLink response

For each dataset's DataLink response:

1. SKAVA fetches all replicas of the dataset.
2. Replicas that are not available or not public, or whose node is
   disabled or marked unavailable, are excluded; the ranking policy
   (``static`` or ``resource_aware``) orders the rest.
3. The top-ranked replica with a usable access endpoint provides
   ``best_node``.
4. For every ranked replica's node with a non-empty
   ``visivo_backend_url``, SKAVA emits a ``visivo-backend`` service
   descriptor with that URL, best-ranked first.
5. The first ranked ``file://`` replica on a node with a VisIVO
   backend also yields that node's SODA descriptors.

Clients use the ``visivo-backend`` descriptor to run compute next to
the data; see [Clients](../clients/overview.md).

## Replica count column

The Nodes list shows a "Replicas" column with the count of dataset
replicas pointing at each node. Use it as a quick sanity check:

* zero ⇒ no datasets reference this node yet (publish via the CLI,
  or fix the node_code mismatch in your manifest)
* unexpected jump ⇒ a publisher might be over-publishing; check the
  ingestion history

## Status badges

* **active** (green): ``is_enabled=true and is_available=true``
* **disabled** (grey): ``is_enabled=false``
* **unavailable** (amber): ``is_enabled=true and is_available=false``
  (manual flag; the prober never changes it)

## API equivalence

Every action available in the UI can also be done as a direct DB
write, but the canonical path is the admin UI for operator changes
and the publisher CLI for ingestion. There is intentionally no REST
CRUD for nodes — the data is operational, not federated. Every
create, update and delete writes a ``node.create`` / ``node.update``
/ ``node.delete`` audit row.
