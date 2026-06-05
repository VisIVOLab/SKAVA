# VisIVO desktop integration

The VisIVO desktop app (Qt 6 + VTK 9) consumes SKAVA via a
dedicated **SKAVA Discovery** tab. This page documents how the
integration is wired and how to configure the client to talk to your
SKAVA instance.

## What the user sees

* A tab next to "Data Hub" labelled **SKAVA Discovery**.
* Connection bar: SKAVA URL + optional bearer token.
* Filter form: position (RA / Dec / radius), wavelength range, time
  range, collection, dataproduct type.
* Paginated results table with provenance details.
* **Open in VisIVO** button that routes the open via the SKAVA
  discovery flow.

## Configuration

In **Settings → SKAVA**:

```
SKAVA base URL:  https://skava.inaf.it
SKAVA token:     <leave empty unless your site enabled SKAVA_ACCESS_TOKENS>
```

Plus, in **Settings → Remote Backends**, register every node whose
compute backend you want to route to:

```
ID:        src-power9
Name:      INAF Power9 (Catania)
URL:       http://pleiadi-gpu.oact.inaf.it:8000
Token:     <backend token>
SRC code:  POWER9
```

The `URL` and `SRC code` are the two matching keys used by the
desktop's routing logic. Either is enough to match — see
[backend routing](backend-routing) for the algorithm.

## What happens when the user clicks "Open in VisIVO"

```{mermaid}
sequenceDiagram
    User->>Desktop: click Open on selected row
    Desktop->>SKAVA: GET /datalink/{obs_id}
    SKAVA-->>Desktop: { primary_access, service_descriptors }
    Note over Desktop: pickBackendForSkavaDataset:<br/>match descriptor against<br/>registered Remote Backends
    alt Backend matched
        Desktop->>VisIVO_backend: POST /v1/datasets/open_skava<br/>{ obs_id, access_url }
        VisIVO_backend-->>Desktop: dataset_id + geometry
        Note over Desktop: status badge → BLUE<br/>"Backend: <node name>"
    else No backend matched
        Desktop->>local_VisIVO_backend: POST /v1/datasets/open_url<br/>{ url=primary_access.access_url }
        local_VisIVO_backend-->>Desktop: dataset_id + geometry<br/>(after downloading the file)
        Note over Desktop: status badge → GREY<br/>"Backend: Local"
    end
    Desktop->>User: open viewer with the dataset
```

The status-bar **badge** is the primary affordance for "where did
this dataset come from":

* **grey "Backend: Local"** — fallback download path
* **blue "Backend: <node name>"** — compute next to data

## Recent Datasets integration

Datasets opened via SKAVA appear in the Data Hub's Recent Datasets
panel with:

* the FITS filename as the visible label
* a small **SKAVA** blue badge next to the name
* a tooltip showing the original ``obs_id``

Clicking the entry **re-queries SKAVA** for that obs_id and routes
the open again — so if the file has migrated to a different node
since the original open, the desktop transparently picks the new
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
  - Backend matches a SKAVA visivo-backend descriptor. The desktop
    passes ``{ obs_id, access_url }``; the backend opens the file
    from its own filesystem (no download).
* - ``/v1/datasets/open_url``
  - Download fallback
  - No matching backend. The local backend downloads the file via
    HTTP, caches it, then opens.
* - ``/v1/datasets/open``
  - Local path
  - Files dragged from a local disk path; never used by the SKAVA
    flow.
```

## Configuring multiple SKAVA instances

The desktop today supports one SKAVA URL at a time. To switch
between sibling SRCs, change the URL in Settings → SKAVA. A future
release will add a SKAVA-instances list mirroring Remote Backends.

## Token handling

* If SKAVA is open (no `SKAVA_ACCESS_TOKENS` set on the server),
  leave the SKAVA token field empty.
* If the server requires tokens, the same value goes in every
  desktop instance that should be allowed to query.
* Per-Node backend tokens are separate and stored encrypted in the
  desktop's settings DB.

## Where the code lives in the desktop

For developers diving in:

* ``src/gui/SkavaSearchPanel.{h,cpp}`` — the tab UI
* ``src/skava/SkavaClient.{h,cpp}`` — HTTP client to SKAVA
* ``src/gui/MainWindow.cpp::doOpenSkavaDataset()`` — the routing
  entry point
* ``src/app/BackendClient.{h,cpp}::openSkavaDataset()`` — the
  ``/v1/datasets/open_skava`` call
* ``src/Settings.{h,cpp}`` — registry of Remote Backends

The full architectural picture is in
[Compute next to data](../architecture/compute-next-to-data).

## Sample troubleshooting flow

```{list-table}
:header-rows: 1
:widths: 40 60

* - Symptom
  - Diagnosis
* - SKAVA tab shows zero results
  - Wrong URL or no datasets. Test
    ``curl https://skava.inaf.it/discovery/search?limit=3``.
* - Badge stays grey even though the node has a backend
  - The visivo_backend_url on the Node row doesn't match any
    registered Remote Backend. Compare URLs side-by-side; mind
    trailing slashes.
* - Open returns ``open_url requires http://``
  - Routing fell back to download. Same cause as above — and the
    access_url is ``file://`` so the local backend can't fetch it.
* - Backend 401 on open
  - Wrong token in Settings → Remote Backends. The backend prints
    its token at startup.
```

## See also

* [Backend routing](backend-routing) for the matching algorithm.
* [Architecture / compute next to data](../architecture/compute-next-to-data).
