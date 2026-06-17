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
  - Stable short identifier (max 32 chars). Used as ObsCore
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
  - When set, the DataLink response emits a ``visivo-backend``
    service descriptor pointing here. Desktop clients then route
    compute to this URL instead of downloading the file (see
    [compute next to data](../architecture/compute-next-to-data)).
* - **Requires bearer**
  - no
  - false
  - Toggle that surfaces in the service descriptor's
    ``requires_auth`` field. Desktops use it to decide whether to
    send the token they have for this node.
* - **Latency / load / capability scores**
  - no
  - empty
  - Used by the replica-ranking algorithm to choose the best replica
    when a dataset has more than one. Lower latency wins; higher
    capability wins; load is inverse. Empty = neutral.
* - **Enabled**
  - yes
  - true
  - Operator off-switch. A disabled node is invisible to discovery
    until re-enabled.
* - **Available**
  - yes
  - true
  - "Is it healthy right now?" toggle. Future enhancement: derived
    automatically from a healthcheck against
    ``visivo_backend_url``.
```

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
2. A confirmation modal precedes the actual ``POST``.

The "remove the replicas first" step can be:

* Re-ingest the affected datasets pointing at a different node (the
  ingestion pipeline updates existing replicas in place).
* Delete the datasets that only live on this node.
* Bulk DELETE in PostgreSQL (audit-trail leaving — only do this on
  staging).

## How nodes feed the DataLink response

For each dataset's DataLink response:

1. SKAVA fetches all replicas of the dataset.
2. The ranking policy orders them by
   ``latency × load × capability``.
3. The top-ranked replica's node provides ``best_node``.
4. For every node with a non-empty ``visivo_backend_url``, SKAVA
   emits a ``visivo-backend`` service descriptor with that URL.
5. Other descriptors (access-resolution, soda-sync, etc.) are
   generated independently of node properties.

The desktop client uses the ``visivo-backend`` descriptor to drive
compute-next-to-data routing — see
[Client integration / backend routing](../client-integration/backend-routing).

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
  (manual flag; not yet auto-derived)

## API equivalence

Every action available in the UI also exists as a direct DB write or
an Alembic migration in a script, but the canonical path is the
admin UI for operator changes and the publisher CLI for ingestion.
There is intentionally no public REST CRUD for nodes — the data is
operational, not federated.
