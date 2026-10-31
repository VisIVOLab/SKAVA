# The testbed

`testbed/` is a federation on one machine, built from one compose file:
two SKAVA catalogues, an IAM, a Computing Broker and four simulated SRC
nodes, each a VisIVO Visual Analytics backend with its own data, resource
limits and network link. It is where the routing policy, the operations
next to the data, the federation and the evaluation experiments run, and
it is reproducible as a whole.

## What runs

| Service | Port | What it is |
|---|---|---|
| `skava` | 18000 | the first site's catalogue: all four nodes, open (no token), federated with the second |
| `skava-2` | 18001 | the second site's catalogue: the far and busy nodes only, the IAM's tokens required, federated with the first |
| `keycloak` | 18300 | the IAM: realm `srcnet`, public client `visivo`, user `astronomer` / `testbed` |
| `broker` | 18200 | a stand-in for the SRCNet Computing Broker (job API, placement through SKAVA) |
| `node-big`, `node-small`, `node-far`, `node-busy` | 18101–18104 | the nodes' VisIVO backends, with SoFiA-2 and photutils |
| `db` | 15432 | PostgreSQL, one database per catalogue |

| Node | Memory | CPUs | Link |
|---|---|---|---|
| `node-big` | 8 GB | 4 | local |
| `node-small` | 2 GB | 1 | local |
| `node-far` | 4 GB | 2 | +80 ms, 100 Mbit/s (`tc netem`) |
| `node-busy` | 4 GB | 2, saturated by four CPU-bound processes | local |

The data are three synthetic HI cubes (`tb-cube-s`, `-m`, `-l`), each with
injected sources and replicated on three of the four nodes. Each node
publishes its holdings in place with
[`skava-publisher`](../publisher/overview.md): only metadata travels, and
mirrored files with the same `OBS_ID` become replicas of one logical
dataset. Each catalogue probes its nodes every 10 s and ranks replicas with
the resource-aware policy.

## Running it

```bash
cd testbed
make data            # the cubes; PROFILE=paper for the large ones (several GB)
make up              # build and start everything
make seed            # register the nodes and publish their holdings
make admin           # an account for the web admin of both catalogues
make status
make down            # stop and remove (make clean: also the data)
```

The node image is built from the VisIVO Visual Analytics repository
checked out next to this one (`VISIVO_REPO` to point elsewhere); SoFiA-2 is
compiled into it. The memory figures are cgroup limits: the `paper`
profile needs the big node's 8 GB to be really available to the container
engine. The credentials in the compose file are for a local testbed only.

The [testbed README](https://github.com/VisIVOLab/SKAVA/blob/main/testbed/README.md)
has the knobs (link shaping, limits, tokens, federation timeout), the IAM's
setup and how the broker places a job.

## Experiments

`testbed/experiments/` holds scripted sessions that speak the same APIs as
the desktop client; each writes `results/<name>.json` and `.csv`.

| Target | Experiment |
|---|---|
| `make experiment-e1` | the cost of the routing decision against catalogue size and replica count, on PostgreSQL (`scripts/benchmark_routing.py`, in process: `results/routing_n.*`, `results/routing_k.*`), then `experiments.e1_prober`: the same resolution through the running SKAVA container, and from SKAVA's metrics what probing the four nodes costs (`results/e1_prober.*`) |
| `make experiments` | E2 placement quality (static against resource-aware policy), E3 a node killed mid-session, E4 bytes moved (kernel counters), E5 source finding through the broker, E6 the federation |
| `make conformance` | pyvo reads the catalogue's TAP and DataLink, a node's SODA services and its UWS jobs from inside the network; every `#this` link of a dataset is followed from outside the nodes and compared with the catalogued file (status, media type, size, SHA-256); the catalogue is called without credentials and the nodes' token goes only to the nodes, which a last check confirms; the run is logged to `results/conformance.log` with the commits of SKAVA and VisIVO it ran on |
| `make figures`, `make tables` | the figures and LaTeX tables from the results |

`results/routing_v012.json` and `.csv` are the in-process benchmark
(`scripts/benchmark_routing.py`) repeated on PostgreSQL 16 for release
0.1.2, at 10⁴ and 10⁶ datasets with three replicas each.

E2 and E3 restart the catalogue and kill node containers, and E6 stops the
second catalogue: run the experiments alone, not while the testbed is in
use. On a laptop keep the host awake (`caffeinate -i -s make experiments`
on macOS); every result records the host's clock skew.

## E7: a real node

`testbed/experiments/e7_real_node.py` records the full chain against a SKAVA
catalogue and one real node outside the testbed: the ADQL query that finds
the dataset, the DataLink resolution (the node chosen, the policy and its
reason), the open in place on the node, the first channel slice, a moment-0
map as a SODA job on the node, and the product opened where it was made,
each step timed, with the node's status document before and after. Nothing
is downloaded.

```bash
cd testbed
TESTBED_SKAVA_URL=http://localhost:18000 TESTBED_BACKEND_TOKEN=<node token> \
    ../.venv/bin/python -m experiments.e7_real_node --node <CODE> \
        --backend http://localhost:18900 --obs-id <obs_id> --name <name>
```

`--backend` is the node's backend as the client reaches it (a tunnel is
fine). Two scripts prepare the node:
[`scripts/register_node.sh`](https://github.com/VisIVOLab/SKAVA/blob/main/scripts/register_node.sh)
registers it in a Docker Compose catalogue (idempotent), and
[`scripts/node_provenance.sh`](https://github.com/VisIVOLab/SKAVA/blob/main/scripts/node_provenance.sh)
records the host, GPU, container image, VisIVO commit and each dataset's
size, SHA-256 and FITS geometry. The recorded run on INAF PLEIADI-GPU is in
`testbed/results/pleiadi/`, with its own README; the steps are in
[End-to-end run on INAF PLEIADI-GPU](../operations/e2e-pleiadi-gpu-runbook.md).

## Connecting the desktop client

The VisIVO Visual Analytics desktop can drive the testbed. Its node
backends are at `http://localhost:18101` to `18104`, with the token
`testbed-backend-token` and the node codes `BIG`, `SMALL`, `FAR` and
`BUSY`; the catalogues are `http://localhost:18000` (open) and
`http://localhost:18001` (which answers with the `ivoa_bearer` challenge and
signs in at the IAM). How to register backends and point the desktop at a
catalogue is documented by VisIVO:
[SKAVA discovery](https://visivo.readthedocs.io/en/latest/user-guide/skava-discovery.html).
See also [Clients](../clients/overview.md).
