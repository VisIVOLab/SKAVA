# SKAVA — Data Discovery and Access Service

**SKAVA** is the data-discovery and access service of the INAF
contribution to the SKA Regional Centre (SRC) Network. It exposes an
IVOA-aligned HTTP API that lets clients **discover** astronomical
datasets across federated nodes, **resolve** how to access each
dataset, and **route** compute requests to a backend co-located with
the data ("compute next to data").

```{rubric} What SKAVA is
```

* A **catalogue of metadata**, not a file storage. Files live on the
  node that produced them; SKAVA stores ObsCore-shaped records that
  point at them.
* A **federation hub**: each node is a row in the database with its
  own access endpoint, ranking score, and optional co-located VisIVO
  compute backend.
* A **discovery + DataLink + SODA endpoint** that astronomical clients
  can query without knowing the internal topology of the federation.

```{rubric} What SKAVA is not
```

* Not a download server. Bytes never flow through SKAVA — clients hit
  the access URL the catalogue hands them.
* Not a compute service. VisIVO backends do the compute; SKAVA only
  tells clients which backend serves a given dataset.

## At a glance

```{mermaid}
flowchart LR
    Client -- "1. discovery" --> SKAVA
    SKAVA  -- "2. visivo-backend descriptor + access URL" --> Client
    Client -- "3. open(obs_id, access_url)" --> VisIVO_Backend
    VisIVO_Backend -- "4. fits.open(local path)" --> Storage[(node storage)]
    VisIVO_Backend -- "5. compute results" --> Client
```

Three round-trips, no file transfer. The full architecture is in
[Compute next to data](architecture/compute-next-to-data).

## Documentation map

```{toctree}
:caption: Getting started
:maxdepth: 2

getting-started/installation
getting-started/quickstart
getting-started/concepts
```

```{toctree}
:caption: Architecture
:maxdepth: 2

architecture/overview
architecture/compute-next-to-data
architecture/data-flow
architecture/components
```

```{toctree}
:caption: Deployment
:maxdepth: 2

deployment/docker
deployment/configuration
deployment/security
deployment/production
```

```{toctree}
:caption: Admin UI
:maxdepth: 2

admin-ui/overview
admin-ui/users-roles
admin-ui/nodes
admin-ui/datasets
admin-ui/audit
```

```{toctree}
:caption: skava-publisher
:maxdepth: 2

publisher/overview
publisher/installation
publisher/configuration
publisher/workflows
publisher/extractors
publisher/apptainer
```

```{toctree}
:caption: HTTP API
:maxdepth: 2

api/discovery
api/datalink
api/soda
api/tap
api/ingestion
api/auth
```

```{toctree}
:caption: Client integration
:maxdepth: 2

client-integration/visivo-desktop
client-integration/backend-routing
```

```{toctree}
:caption: Operations
:maxdepth: 2

operations/monitoring
operations/backup
operations/upgrades
operations/troubleshooting
```

```{toctree}
:caption: Development
:maxdepth: 2

development/contributing
development/testing
development/extending-extractors
```

```{toctree}
:caption: Reference
:maxdepth: 1

reference/obscore-fields
reference/env-vars
reference/glossary
reference/changelog
```

## Quick links

::::{grid} 1 2 2 3
:class-container: padding-3

:::{grid-item-card} {fas}`rocket` First-time install
:link: getting-started/installation
:link-type: doc

Bring up SKAVA with Docker Compose in under five minutes.
:::

:::{grid-item-card} {fas}`book` REST API reference
:link: api/discovery
:link-type: doc

Discovery, DataLink, SODA, TAP and internal ingestion endpoints.
:::

:::{grid-item-card} {fas}`upload` Publish your data
:link: publisher/overview
:link-type: doc

Use the publisher CLI to ingest a node's metadata without moving files.
:::

:::{grid-item-card} {fas}`user-shield` Admin UI
:link: admin-ui/overview
:link-type: doc

Web admin for managing nodes, datasets, users and audit history.
:::

:::{grid-item-card} {fas}`bug` Troubleshooting
:link: operations/troubleshooting
:link-type: doc

Common errors and how to fix them.
:::

:::{grid-item-card} {fas}`code-branch` Contributing
:link: development/contributing
:link-type: doc

Coding conventions, tests, and how to add a new extractor.
:::

::::

## License

SKAVA is released under the MIT license. See the
[LICENSE](https://github.com/VisIVOLab/SKAVA/blob/main/LICENSE) file in
the repository root.
