# Backend routing

How the VisIVO Visual Analytics desktop client decides which compute backend to send a
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

   Over the IVOA protocol (TAP + DataLink VOTable) the same information
   comes from the `#auxiliary` row pointing at the backend's
   `/v1/node/status`, with `node_id` naming the node. Descriptors with
   `enabled: false` are ignored. SKAVA emits one per ranked replica's
   node that has a `visivo_backend_url`, in ranking order, and lists
   each replica's `access_endpoint` under `routing.replicas`.

2. **Desktop's registered backends** from
   ``Settings → Backends → Remote Backends`` (the built-in local
   backend is part of the same registry):

   ```
   id:        src-power9
   url:       http://pleiadi-gpu.oact.inaf.it:8000
   srcCode:   POWER9
   token:     <bearer>
   ```

## The algorithm

```{mermaid}
flowchart TD
    A[For each visivo-backend descriptor in DataLink, in ranking order]
    A --> B{Registered backend with<br/>URL == descriptor.endpoint<br/>or srcCode == node_code?}
    B -- no --> A
    B -- yes --> K{Backend serves this<br/>dataproduct_type?<br/>supports_kinds}
    K -- no --> A
    K -- yes --> T{requires_auth and no token<br/>for that backend?}
    T -- yes --> A
    T -- no --> R{SKAVA lists a replica<br/>on that node?}
    R -- no --> A
    R -- yes --> S[Add to the candidates]
    S --> A
    A -- exhausted --> O[Try the candidates in order;<br/>a refusal moves to the next]
    O -- all refused or none --> F{Primary access<br/>http or file?}
    F -- http --> D[Download via the local backend]
    F -- file --> P[Explain, offer to register the<br/>advertised backend or enter<br/>its token, retry]
```

* Every usable descriptor becomes a **candidate**, in DataLink order
  (SKAVA's ranking). The first is tried; if its backend refuses the
  open (offline, 401, file missing, outside its data roots), the next
  one is tried, and the status bar says so. The download is the last
  resort.
* **Open via…** in the SKAVA tab moves the node the user picked to the
  front of the candidates; the others keep SKAVA's order.
* A token counts when the registered entry has one. The automatic
  token (`VISIVO_TOKEN` or `~/.visivo_token`) counts only when the
  entry's URL is the desktop's own local backend (loopback host, same
  port): it is never sent to another backend, not even one on the same
  machine at another port.
* **The access URL travels with the node.** The desktop opens
  `routing.replicas[node_code].access_endpoint` on the chosen backend — the
  `primary_access.access_url` belongs to the best node only, and another
  node's copy of the file lives at another path.
* A `file://` replica is opened in place (`/v1/datasets/open_skava`); an
  http(s) replica is fetched by that node's own backend
  (`/v1/datasets/open_url`), next to the data.
* For a descriptor, a match by URL against any registered entry has
  higher priority than a match by ``srcCode``, letting an operator
  override the node-level routing for a single client without
  changing SKAVA.

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

URL match trims trailing ``/`` and treats the names of the machine's own
loopback as one host:

```
http://pleiadi-gpu/                ==  http://pleiadi-gpu
http://host.docker.internal:8001   ==  http://127.0.0.1:8001  ==  http://localhost:8001  ==  http://[::1]:8001
```

The second line is what makes the Docker demo work out of the box: SKAVA in
a container reaches the desktop's backend as `host.docker.internal`, the
desktop registers it as `127.0.0.1`. Anything else — port, path, another
host — must match exactly.

`srcCode` match is case-sensitive and exact.

## What happens after the match

```cpp
const SkavaRouting routing = routeSkavaCandidates(settings, datalink, preferredNode);
// openSkavaOnCandidate(), for routing.candidates[i] (node + that node's replica):
BackendClient client(route.node.url, route.node.token);
const auto opened = !pathFromFileUrl(route.accessUrl).isEmpty()
        ? client.openSkavaDataset(obsId, route.accessUrl)                 // open in place
        : client.openDatasetFromUrl(route.accessUrl, obsId, skavaToken);  // node fetches it
// not valid → candidates[i + 1]; none left → openSkavaWithoutRoute()
```

The open runs off the UI thread behind a cancellable progress dialog.
The status-bar badge names the chosen node; its tooltip gives SKAVA's
ranking reason.

The desktop sends both:

* ``obs_id`` — for the backend's session bookkeeping and audit logging
* ``access_url`` — the file URL the desktop already retrieved from
  SKAVA, so the backend doesn't need to re-query SKAVA itself

The backend resolves the access_url to a local path
(``access_url_to_local_path``: ``file://`` only, local host only),
checks the ``VISIVO_DATA_ROOT`` / ``VISIVO_DATA_ROOTS`` jail, and
opens the file. A refusal comes back as ``valid: false`` with the
reason, which sends the desktop to the next candidate.

## Fallback path

When no candidate exists or every one refused:

* an **http(s)** primary access URL is downloaded by the local backend,
  forwarding the SKAVA token to the storage node
  (`openDatasetFromUrl(url, obsId, skavaToken)`);
* a **file://** one exists only on its node's disk, so nothing local can read
  it. The desktop says why each descriptor was passed over and, when SKAVA
  advertises a backend for a node that has no registered counterpart, offers
  **Register backend…** (asking for a token if `requires_auth`), then retries
  through it.

The download calls ``/v1/datasets/open_url`` on the local backend
(after a health check), which:

1. Downloads the file via HTTP into a local cache directory.
2. Opens it with the same metadata pipeline used by ``open``.

A ``file://`` primary access never reaches this path. The desktop
status bar shows the grey "Backend: Local" badge.

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

1. Reads the stored ``obs_id`` and the catalogue, protocol and VO
   endpoints the entry was found with.
2. Calls ``GET /datalink/{obs_id}`` on that catalogue (or its DataLink
   VOTable): gets the *current* descriptors and replicas (possibly
   different from the original open).
3. Re-runs ``routeSkavaCandidates`` with the fresh data.
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
  - The earliest is tried first; the others follow, in order, if it
    refuses.
* - ``requires_auth=true`` and the registered backend has an empty
    token (and is not the local backend with its automatic token)
  - The descriptor is skipped, with the reason shown to the user, who
    is offered **Enter backend token…**.
* - Descriptor's ``supports_kinds`` doesn't include the dataset's
    ``dataproduct_type``
  - The descriptor is skipped (a `timeseries` / dynamic spectrum counts
    as `dynspec`).
* - The matched node lists no replica of the dataset
  - The descriptor is skipped: the desktop never hands one node's path
    to another node's backend.
* - The matched backend is offline or refuses the open
  - The next candidate is tried; with none left, the fallback path
    runs and the badge returns to Local.
* - Local backend not running
  - Fallback path's health check fails; desktop shows
    "Backend unavailable" without attempting the download.
```

## Tracing routing decisions

The desktop shows the routing choice in the status bar (the badge,
with SKAVA's reason as tooltip, and a message when a fallback node
served the open) and logs each refusal as a warning:

```
[skava] backend src-power9 refused open: <the backend's error>
```

When nothing could serve a ``file://`` dataset, the dialog lists every
skipped descriptor and why. Pair these with the backend's
`[open_skava]` log lines to follow a single open across all three
processes (desktop → backend → file system).
