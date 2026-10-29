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
| `make experiment-e1` | the cost of the routing decision against catalogue size and replica count, on PostgreSQL |
| `make experiments` | E2 placement quality (static against resource-aware policy), E3 a node killed mid-session, E4 bytes moved (kernel counters), E5 source finding through the broker, E6 the federation |
| `make conformance` | pyvo reads the catalogue's TAP and DataLink, a node's SODA services and its UWS jobs from inside the network; every `#this` link of a dataset is followed from outside the nodes and compared with the catalogued file (status, media type, size, SHA-256); the catalogue is called without credentials and the nodes' token goes only to the nodes, which a last check confirms |
| `make figures`, `make tables` | the figures and LaTeX tables from the results |

E2 and E3 restart the catalogue and kill node containers, and E6 stops the
second catalogue: run the experiments alone, not while the testbed is in
use. On a laptop keep the host awake (`caffeinate -i -s make experiments`
on macOS); every result records the host's clock skew.

## Connecting the desktop client

In VisIVO Visual Analytics, register the four node backends under
Settings ▸ Remote Backends (`http://localhost:18101` … `18104`, token
`testbed-backend-token`, SRC codes `BIG`, `SMALL`, `FAR`, `BUSY`), then
point the SKAVA tab at `http://localhost:18000`. Pointed at
`http://localhost:18001`, the tab receives the `ivoa_bearer` challenge and
signs in at the IAM. See [the desktop client](../client-integration/visivo-desktop.md).
