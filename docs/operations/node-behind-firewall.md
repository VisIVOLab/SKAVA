# Registering a node SKAVA cannot reach

Some nodes run their VisIVO Visual Analytics backend where the catalogue
cannot open a connection to it: a compute node of a SLURM cluster reached
through an SSH tunnel, a host behind a firewall or a NAT. The clients reach
the backend (through their tunnel or VPN); SKAVA does not. This page covers
SKAVA's side of such a node: how to register it, how to publish its files,
how the ranking policy learns its state, and what must agree between the
catalogue and the node.

How to start the backend on a cluster (the launcher, the SSH tunnel, the
token, the container image and the GPUs) is documented by VisIVO:
[Running the backend on a SLURM cluster](https://visivo.readthedocs.io/en/latest/deployment/hpc-slurm.html).

```{contents}
:local:
:depth: 2
```

## When this applies

* The node's files sit on a filesystem the backend reads directly (for a
  cluster, a shared filesystem mounted at the same path on every compute
  node).
* The backend's address changes, or is private: SLURM places the job on a
  different compute node each time, or only a tunnel leads to it.
* SKAVA's resource-aware prober cannot call the backend's `/v1/ping` and
  `/v1/node/status` from the catalogue's host.

## 1. Register the node

In the admin UI (`/admin/nodes/`), or with
[`scripts/register_node.sh`](https://github.com/VisIVOLab/SKAVA/blob/main/scripts/register_node.sh)
on a Docker Compose deployment:

```
Code:                <SRC-NAME>          e.g. PLEIADI-GPU-OACT
Name:                <human-friendly>
Base URL:            <the site's data-access URL, descriptive>
VisIVO backend URL:  <the backend's URL as the clients reach it>
Requires bearer:     yes, when the backend requires its token
```

SKAVA hands the **VisIVO backend URL** to every client unchanged, as the
`endpoint` of the node's `visivo-backend` descriptor, and builds the node's
SODA URLs from it. Give it the address the clients use. When every client
reaches the backend through a tunnel that exits on its own machine, that
address is a loopback URL such as `http://localhost:8000`: it is not a
placeholder, each client resolves it to its own end of the tunnel.

The **code** must be the node code the backend declares in its status
document; a node report whose status names another code is refused (see
[Telemetry API](../api/telemetry.md#errors)).

## 2. Publish the files in place

Run [`skava-publisher`](../publisher/overview.md) where the files are (the
cluster frontend, or any host that mounts the same filesystem), with
`file://` access URLs that name the path the backend will read:

```yaml
skava:
  api_url: https://skava.example.org
  internal_api_key: ${SKAVA_INTERNAL_API_KEY}
node:
  code: <SRC-NAME>
  file_serve_url_pattern: "file:///data/{relpath}"
scan:
  roots:
    - /data
  compute_checksum: true
defaults:
  obs_collection: your-collection
state:
  db_path: /var/lib/skava-publisher/state.db
```

```bash
skava-publisher --config /etc/skava-publisher.yaml publish -y
```

The records carry `access_url=file:///data/<relpath>`. On a shared
filesystem that path is valid on every compute node, so it stays valid
across SLURM allocations: a new job on another compute node needs no
republishing. Only metadata reaches SKAVA; the files do not move. If the
publisher cannot reach the catalogue from the cluster, open a reverse SSH
tunnel to it, as in the
[PLEIADI-GPU run](e2e-pleiadi-gpu-runbook.md#7-publish-the-nodes-holdings-in-place).

## 3. Let the node report its state

Under the default `resource_aware` policy, SKAVA probes `/v1/ping` and
`/v1/node/status` at the VisIVO backend URL, from the catalogue's host. A
loopback or private URL there does not reach the node, the probe fails, and
the node's replicas go to `routing.excluded` as "backend unreachable at the
last probe". Choose one of:

```{list-table}
:header-rows: 1
:widths: 28 72

* - Option
  - What it takes
* - Node reports (recommended)
  - The backend posts its status document to
    ``POST /internal/telemetry/report`` with the node's own token, and the
    prober leaves the node alone while the reports are fresh. Print the
    token on the catalogue's host with
    ``python -m app.security.node_token <SRC-NAME>`` and give it to the
    node's operator with the catalogue's URL and the node code. See
    [Telemetry API](../api/telemetry.md).
* - A URL SKAVA can reach
  - Register a stable address the catalogue can probe (a reverse proxy
    in front of the current compute node). Clients that reach the backend
    another way match the node on its ``node_code`` instead of the URL.
* - The static policy
  - ``SKAVA_RANKING_POLICY=static`` ranks on the declared scores only and
    probes nothing. The ranking then no longer reflects the nodes' load.
```

## What must agree

```{list-table}
:header-rows: 1
:widths: 30 70

* - In SKAVA
  - On the node's backend
* - The node's ``code``
  - The node code the backend declares and reports with.
* - The publisher's ``file://`` paths (``file_serve_url_pattern``)
  - The backend's data root: the published paths must lie inside it, as
    absolute paths on the node.
* - ``SKAVA_VISIVO_BACKEND_TOKEN`` (when the prober reads a status
    document that requires a token)
  - The backend's token.
* - The node token from ``app.security.node_token`` (node reports)
  - The token the backend sends as ``X-Skava-Node-Token``.
* - The VisIVO backend URL
  - The address the clients use for that backend.
```

The backend's own settings for each of these are listed by VisIVO:
[Running the backend as an SRC node](https://visivo.readthedocs.io/en/latest/deployment/src-node.html).

## How clients match the endpoint

SKAVA does not rewrite the endpoint per client. A client compares the
descriptor's `endpoint` with the backends it knows; when two users' tunnels
exit at different local ports, the URL matches for one of them only, and
the other matches the node by `node_code`. Every client that reaches the
backend by a loopback URL therefore needs the node code of the entry it
registered to equal the node's `code` in SKAVA. See
[Clients](../clients/overview.md#matching-keys).

## Verify from SKAVA's side

```bash
# The node's state as the policy sees it: "source": "push" for a node that reports
curl -s -H "X-Internal-Api-Key: $INTERNAL_API_KEY" \
    https://skava.example.org/internal/telemetry | jq '.nodes[] | select(.code == "<SRC-NAME>")'

# What clients receive for a published dataset
curl -s "https://skava.example.org/datalink/<obs-id>" \
    | jq '.routing.best_node, .routing.replicas[0].rank_reason,
          (.service_descriptors[] | select(.service_type == "visivo-backend"))'
```

The descriptor's `endpoint` is the URL registered on the node, its
`node_code` the node's code, and `routing.best_node` names the node when it
is the best ranked holder of the dataset.

## See also

* [End-to-end run on INAF PLEIADI-GPU](e2e-pleiadi-gpu-runbook.md), a
  recorded run of this setup.
* [Telemetry API](../api/telemetry.md) for node reports.
* [Nodes](../admin-ui/nodes.md) for every node field.
