# Backend routing

How the VisIVO desktop client decides which compute backend to send a
SKAVA-opened dataset to. This is the algorithm at the heart of
compute-next-to-data.

## Inputs

1. **SKAVA DataLink response** for the dataset, in particular the
   ``service_descriptors[]`` array. The relevant entries have
   ``service_type == "visivo-backend"``:

   ```json
   {
     "service_type": "visivo-backend",
     "endpoint": "http://pleiadi-gpu.oact.inaf.it:8000",
     "node_code": "POWER9",
     "requires_auth": true,
     "supports_kinds": ["image","cube","dynspec"]
   }
   ```

2. **Desktop's registered Remote Backends** from
   ``Settings → Remote Backends``:

   ```
   id:        src-power9
   url:       http://pleiadi-gpu.oact.inaf.it:8000
   srcCode:   POWER9
   token:     <bearer>
   ```

## The algorithm

```{mermaid}
flowchart TD
    A[For each visivo-backend descriptor in DataLink]
    A --> B{Find registered backend with<br/>URL == descriptor.endpoint?}
    B -- yes --> M1[Pick that backend]
    B -- no --> C{Find registered backend with<br/>srcCode == descriptor.node_code?}
    C -- yes --> M2[Pick that backend]
    C -- no --> A
    M1 --> S[Use openSkavaDataset on chosen backend]
    M2 --> S
    A -- exhausted --> F[Fallback to download via local backend]
```

* Stop as soon as a match is found.
* Match by URL has higher priority than match by ``srcCode`` —
  letting an operator override the node-level routing for a single
  client without changing SKAVA.
* When several descriptors match different backends, the **first
  descriptor** that matches wins (DataLink order = SKAVA's ranking
  policy order).

## Why two matching keys

```{list-table}
:header-rows: 1
:widths: 25 75

* - Match key
  - When it's the right one
* - URL exact match
  - The Node operator and the desktop user agree on the backend's
    URL. Most common case.
* - srcCode match (``node_code``)
  - The Node's backend URL is something the desktop can't easily
    write down (e.g. behind a VPN with a private hostname). The
    desktop registers a backend with the same ``srcCode`` pointing
    at an alternative reachable URL. Useful for VPN-bridged setups.
```

## Trim before compare

URL match trims one trailing ``/``:

```
http://pleiadi-gpu/        ==  http://pleiadi-gpu
```

But is otherwise byte-for-byte. Mismatches in port number, case, or
trailing path segments → no match.

`srcCode` match is case-sensitive and exact.

## What happens after the match

```cpp
BackendClient client(chosen.url, chosen.token);
const auto opened = client.openSkavaDataset(obsId, datalink.primaryAccessUrl);
```

The desktop sends both:

* ``obs_id`` — for the backend's session bookkeeping and audit logging
* ``access_url`` — the file URL the desktop already retrieved from
  SKAVA, so the backend doesn't need to re-query SKAVA itself

The backend resolves the access_url to a local path
(``access_url_to_local_path``), checks the ``VISIVO_DATA_ROOT`` jail,
and opens the file.

## Fallback path

When no descriptor matches a registered backend:

```cpp
client.openDatasetFromUrl(datalink.primaryAccessUrl, obsId);
```

This calls ``/v1/datasets/open_url`` on the local backend, which:

1. Downloads the file via HTTP into a local cache directory.
2. Opens it with the same metadata pipeline used by ``open``.

Only HTTP / HTTPS access URLs are honoured by this path; ``file://``
URLs result in an error. The desktop status bar shows the grey
"Backend: Local" badge.

## Why the desktop, not SKAVA, makes the routing decision

The user knows their network reachability better than SKAVA does.
Concretely:

* SKAVA can't tell whether the desktop is on the SRC's VPN or not.
* SKAVA can't tell which of multiple backends the user trusts.
* SKAVA shouldn't be a single point of failure for compute routing.

So SKAVA's job is to **list the options** (the descriptors); the
desktop **picks one** from its registered set. The same model lets
non-VisIVO clients consume the DataLink envelope and choose their
own resolution.

## Recent Datasets reopen

When a SKAVA-opened dataset appears in Recent Datasets and the user
clicks reopen, the desktop:

1. Reads the stored ``obs_id``.
2. Calls ``GET /datalink/{obs_id}`` on SKAVA — gets the *current*
   descriptors and access_url (possibly different from the original
   open).
3. Re-runs ``pickBackendForSkavaDataset`` with the fresh data.
4. Routes the open.

This makes Recent Datasets resilient to:

* File migration between nodes
* Backend URL changes
* Replica rebalancing
* Discovery descriptor evolution

## Edge cases

```{list-table}
:header-rows: 1
:widths: 38 62

* - Case
  - Behaviour
* - Multiple descriptors, multiple matches
  - Earliest descriptor wins.
* - One descriptor, but ``requires_auth=true`` and the registered
    backend has empty token
  - The desktop tries the call anyway. Backend returns 401; the
    desktop falls back to download.
* - Descriptor's ``supports_kinds`` doesn't include the dataset's
    ``dataproduct_type``
  - Currently ignored by the matcher. Roadmap: pre-filter
    descriptors against the dataset's kind.
* - The matched backend is offline
  - Open call fails; desktop shows the error message in a dialog
    and badge stays whichever was set before the click.
* - Local backend not running
  - Fallback path's health check fails; desktop shows
    "Backend unavailable" without attempting the download.
```

## Tracing routing decisions

The desktop logs the routing choice at INFO level:

```
[skava] obs_id=power9-3a7f1b2c… → matched backend src-power9 by URL
[skava] obs_id=mac-local-… → no descriptor matched → fallback download
```

Pair these with the backend's `[open_skava]` log lines to follow a
single open across all three processes (desktop → backend → file
system).
