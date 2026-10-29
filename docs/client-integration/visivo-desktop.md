# VisIVO desktop integration

The desktop application VisIVO Visual Analytics (Qt 6 + VTK 9,
[VisIVOLab/VisIVO-next](https://github.com/VisIVOLab/VisIVO-next))
consumes SKAVA via a dedicated **SKAVA** tab. This page documents how
the integration is wired and how to configure the client to talk to
your SKAVA instance.

## What the user sees

* A tab next to "Data Hub" labelled **SKAVA**.
* A **Discovery service** box: the protocol (*SKAVA JSON API* or
  *IVOA TAP + DataLink (SRCNet)*), the service URL, a bearer token,
  **Sign in…** / **IAM…** for an OpenID Connect sign-in, and, folded
  under **Advanced**, the TAP URL, DataLink URL and Computing Broker
  URL.
* A foldable **Filters** form: position (RA / Dec / radius), band
  (min / max with a MHz / GHz / Hz / m unit), time (MJD), collection,
  dataproduct type, obs_id, limit / offset.
* A results table (obs_id, Target, Type, Sky position, Band, Time,
  **Served by**, **Why**) and the provenance of the selected row
  (title, DOI, PID, licence, citation).
* **Served by** names the node SKAVA ranked first and how many other
  replicas exist; **Why** is SKAVA's reason for that ranking (with the
  resource-aware policy: measured round trip, CPU pressure, queue,
  memory margin; with the static policy: the declared scores).
  Hovering either shows every replica in ranking order with its cost,
  reason and telemetry age.
* **Open** (or a double-click), **Open via…** (pick the node among the
  replicas instead of SKAVA's first choice) and **Compute next to
  data…** (SODA cutout, moment map, PV diagram, source finder).

## Configuration

The SKAVA connection lives in the tab's **Discovery service** box and
is saved in the desktop's settings:

```
Service:   SKAVA JSON API   https://skava.inaf.it
Token:     <empty, pasted, or obtained with Sign in…>
```

* **Token**: leave empty when the server runs open (no
  `SKAVA_ACCESS_TOKENS`, no IAM). **Sign in…** runs an OpenID Connect
  authorization-code flow as a public client (`vlva://callback`
  redirect) against the IAM configured with **IAM…**; a service that
  answers `401` with an `ivoa_bearer` challenge names its IAM, and the
  tab configures the endpoints from it. The refresh token is kept in
  the system's secure store, so the next start signs in silently.
  Any `401` offers a sign-in and repeats the request.
* **Advanced: Broker URL**: a Computing Broker that places the source
  finder; empty means the finder runs as a task on the dataset's node.

Then, in **Settings → Backends → Remote Backends**, register every
node whose compute backend you want to route to:

```
Identifier:    src-power9
Display name:  INAF Power9 (Catania)
URL:           http://pleiadi-gpu.oact.inaf.it:8000
Token:         <backend token>
SRC code:      POWER9
```

The `URL` and `SRC code` are the two matching keys used by the
desktop's routing logic. Either is enough to match; see
[backend routing](backend-routing.md) for the algorithm. The built-in
**local** backend is configured on the same page and is always the
fallback.

## What happens when the user clicks Open

```{mermaid}
sequenceDiagram
    User->>Desktop: click Open on selected row
    Desktop->>SKAVA: GET /datalink/{obs_id}<br/>(or the DataLink VOTable)
    SKAVA-->>Desktop: { routing.replicas, primary_access, service_descriptors }
    Note over Desktop: routeSkavaCandidates:<br/>registered Remote Backends matching<br/>the visivo-backend descriptors,<br/>in SKAVA's ranking order
    loop each candidate until one opens
        Desktop->>Node_backend: POST /v1/datasets/open_skava<br/>{ obs_id, access_url = that node's replica }
        Node_backend-->>Desktop: dataset_id + geometry, or a refusal
    end
    alt A candidate opened it
        Note over Desktop: status badge → BLUE<br/>"Backend: <node name>",<br/>tooltip = SKAVA's reason
    else No candidate, http(s) primary access
        Desktop->>local_VisIVO_backend: POST /v1/datasets/open_url<br/>{ url=primary_access.access_url }
        local_VisIVO_backend-->>Desktop: dataset_id + geometry<br/>(after downloading the file)
        Note over Desktop: status badge → GREY<br/>"Backend: Local"
    else No candidate, file:// primary access
        Note over Desktop: explain why each descriptor<br/>was skipped; offer Register backend…<br/>or Enter backend token…, then retry
    end
    Desktop->>User: open viewer with the dataset
```

A refusal moves on to the next node in SKAVA's ranking, and the status
bar says which node was skipped and which one served the dataset. An
`http(s)` replica on a matched node is fetched by that node's own
backend (`/v1/datasets/open_url` there), still next to the data.

The status-bar **badge** is the primary affordance for "where did
this dataset come from":

* **grey "Backend: Local"**: fallback download path
* **blue "Backend: <node name>"**: compute next to data; the tooltip
  carries SKAVA's ranking reason

## Recent Datasets integration

Datasets opened via SKAVA appear in the Data Hub's Recent Datasets
panel with:

* the FITS filename as the visible label
* a small **SKAVA** badge next to the name
* a tooltip showing the original ``obs_id``, the catalogue it came
  from and the node that served it

Clicking the entry **re-queries the same catalogue** (with the
protocol and VO endpoints it was found with) for that obs_id and
routes the open again, so if the file has migrated to a different
node since the original open, the desktop transparently picks the new
location.

## Two open paths, one backend protocol

The desktop always uses the same VisIVO backend HTTP API, regardless
of whether routing matched or fell back. The difference is which
endpoint:

```{list-table}
:header-rows: 1
:widths: 30 18 52

* - Endpoint
  - Path
  - When
* - ``/v1/datasets/open_skava``
  - Compute-next-to-data
  - A registered backend matches a SKAVA visivo-backend descriptor and
    its node holds a ``file://`` replica. The desktop passes
    ``{ obs_id, access_url }``; the backend opens the file from its
    own filesystem (no download).
* - ``/v1/datasets/open_url``
  - Download
  - On the matched node's backend for an ``http(s)`` replica there;
    otherwise on the local backend, as the last resort, which
    downloads the file via HTTP, caches it, then opens.
* - ``/v1/datasets/open``
  - Local path
  - Files opened from a local disk path, and products a node wrote to
    its workspace (cutouts, moment maps, finder masks), opened there.
```

## Compute next to data

**Compute next to data…** runs on the node through the services
SKAVA's DataLink advertises for the dataset (`node-soda-sync`,
`node-soda-async`, `visivo-moment`, `visivo-pv`; in the VOTable, the
`#cutout` and `#proc` rows). The product stays in the node's workspace
and is opened there.

* **SODA cutout…**: POS (CIRCLE or POLYGON), BAND and/or TIME,
  submitted to the node's `/soda/async` as a UWS job, polled, then
  opened in place. Without an advertised SODA job service the routed
  backend's own `/v1/datasets/cutout` is used.
* **Moment map…**: `OPERATION=MOMENT` (order 0, 1, 2; optional
  channel range and threshold). Cubes only.
* **PV diagram…**: `OPERATION=PV` (path vertices, slice width).
  Cubes only.
* **Source finder…**: the finders the node offers (`GET /v1/finders`,
  e.g. SoFiA-2, photutils). With a Broker URL the job goes to the
  Computing Broker (`POST /v1/jobs`), which asks SKAVA where to run it
  and starts the finder on that node's backend; otherwise the desktop
  opens the dataset on the first-ranked node and starts
  `POST /v1/tasks/sourcefind` there. The mask and the catalogue open
  from the node.

A node service is always called at the address of the backend
registered for that node, with that backend's token.

## Configuring multiple SKAVA instances

The tab queries one discovery service at a time. To switch between
sibling SRCs, change the service URL in the tab. Recent Datasets
entries remember the catalogue they came from, so a reopen still asks
the right one.

## Token handling

* If SKAVA is open (no `SKAVA_ACCESS_TOKENS`, no IAM in front of it),
  leave the token field empty.
* If the server requires static tokens, paste the same value into
  every desktop that should be allowed to query; with an IAM, use
  **Sign in…**. The same SKAVA token goes to the Computing Broker and
  to a storage node on the download path.
* Per-node backend tokens are separate: each Remote Backend entry
  carries its own, sent only to that backend. The automatic token of
  the local backend (`VISIVO_TOKEN` or `~/.visivo_token`) is sent only
  to the local backend's address.

## Where the code lives in the desktop

For developers diving in:

* ``src/gui/SkavaSearchPanel.{h,cpp}``: the tab UI
* ``src/skava/SkavaClient.{h,cpp}``, ``src/skava/VoTable.{h,cpp}``:
  SKAVA JSON API and IVOA TAP + DataLink client
* ``src/skava/BackendRouting.{h,cpp}``: ``routeSkavaCandidates()``,
  the matching rule
* ``src/gui/MainWindow_Open.cpp``: ``doOpenSkavaDataset()`` /
  ``openSkavaOnCandidate()`` / ``openSkavaWithoutRoute()``, the open
  flow
* ``src/gui/MainWindow_SkavaOps.cpp``, ``src/skava/NodeSoda.{h,cpp}``,
  ``src/skava/BrokerClient.{h,cpp}``,
  ``src/gui/SkavaSourceFindDialog.{h,cpp}``: compute next to data
* ``src/app/BackendClient.{h,cpp}::openSkavaDataset()``: the
  ``/v1/datasets/open_skava`` call
* ``src/Settings.{h,cpp}``, ``src/gui/BackendsSettingsWidget.cpp``:
  registry of Remote Backends
* ``src/auth/OIDCAuthorizationCodeFlow.{h,cpp}``: the sign-in

The full architectural picture is in
[Compute next to data](../architecture/compute-next-to-data.md).

## Sample troubleshooting flow

```{list-table}
:header-rows: 1
:widths: 40 60

* - Symptom
  - Diagnosis
* - SKAVA tab shows zero results
  - Wrong URL or no datasets. Test
    ``curl https://skava.inaf.it/discovery/search?limit=3``.
* - "… requires a sign-in"
  - The service answered ``401``. Sign in, or paste a token.
* - Badge stays grey even though the node has a backend
  - The dataset was downloaded: no registered backend was usable (no
    entry with the descriptor's URL or SRC code, a token missing, the
    kind not served, or no replica on that node). Compare the Node's
    ``visivo_backend_url`` with the Remote Backend URL, or set the
    SRC code.
* - "… is stored on an SRC node and can only be opened by the VisIVO
    backend running there"
  - The access_url is ``file://`` and no registered backend can open
    it. Use the offered **Register backend…** / **Enter backend
    token…**, or fix the entry in Settings → Backends.
* - Backend 401 on open
  - Wrong token in the Remote Backend entry; the next node is tried.
    The backend prints its token at startup.
```

## See also

* [Backend routing](backend-routing.md) for the matching algorithm.
* [Architecture / compute next to data](../architecture/compute-next-to-data.md).
