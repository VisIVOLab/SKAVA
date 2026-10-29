# SKAVA testbed

A reproducible federation on one machine: two SKAVA catalogues, an IAM and
four simulated SRC nodes, each a VisIVO Visual Analytics backend with its own
data, resource limits and network link. It is where the routing policy, the
near-data operations, the federation and the paper's experiments are run.

| Node | Memory | CPUs | Link | Holds |
|---|---|---|---|---|
| `node-big` | 8 GB | 4 | local | S, M, L |
| `node-small` | 2 GB | 1 | local | S, L |
| `node-far` | 4 GB | 2 | +80 ms, 100 Mbit/s | S, M |
| `node-busy` | 4 GB | 2, saturated by 4 busy processes | local | M, L |

Every cube has replicas on several nodes, and in the `paper` profile the large
cube (3 GB) is also on the small node, whose memory limit is smaller than the
cube. The backend reads cubes through memory maps, so the small node can still
open and slice it; what it cannot do well is an operation that needs the whole
cube in memory, which is what the routing experiments measure.

Replicas are separate copies (`make data` copies; `make_data.py --link`
hard-links to save space, at the cost of a page cache shared between nodes).

| Service | Port | What it is |
|---|---|---|
| `skava` | 18000 | the first site's catalogue: all four nodes, open (no token), federated with the second |
| `skava-2` | 18001 | the second site's catalogue: the far and busy nodes, the IAM's tokens required, federated with the first |
| `keycloak` | 18300 | the IAM (realm `srcnet`, public client `visivo`, user `astronomer` / `testbed`) |
| `broker` | 18200 | the Computing Broker stand-in |
| `node-*` | 18101–18104 | the nodes' backends (token `testbed-backend-token`) |

## Requirements

- Docker with Compose v2. The memory figures are cgroup limits, not
  reservations: the `ci` profile runs in a few GB, the `paper` profile needs
  the large node's 8 GB to be really available to Docker (lower the limits
  with `BIG_MEM`, `SMALL_MEM`, `FAR_MEM`, `BUSY_MEM`).
- This repository's `.venv` (for the data generator) and the VisIVO Visual
  Analytics repository next to this one (`VISIVO_REPO` to point elsewhere),
  from which the node image is built.

## Run

```bash
cd testbed
make data            # PROFILE=paper for the large cubes (several GB)
make up              # build and start: catalogues on :18000 and :18001, IAM on :18300, broker on :18200, nodes on :18101-18104
make seed            # register the nodes, then publish each node's files in place (far and busy to both sites)
make admin           # an account for the catalogues' web admin, http://localhost:18000/admin/ (and :18001)
make status
make down            # stop and remove everything (make clean: also the data)
```

`make seed` runs `skava-publisher` next to each node's data: it reads the
headers in place and sends only metadata. Mirrored files carry the same
`OBS_ID`, so they become replicas of one logical dataset.

Each node serves only what is under its roots (`VISIVO_DATA_ROOTS`): the
data it holds, read-only, and its workspace (`VISIVO_EXPORTS_DIR`,
`/workspace`), where the products it makes go, so that a cutout, a moment
map or a finder's mask opens in place on the node that made it. A
deployment that keeps the workspace outside the roots cannot open its own
products through the path routes.

## Two sites, one IAM

`skava-2` is a second SRC site: its own database (`skava2`, on the same
PostgreSQL), its own registrations (the far and busy nodes, published to it
by `make seed` as well), and the IAM's tokens required on its public
endpoints, as an SRCNet site would. Each catalogue lists the other in
`SKAVA_FEDERATED_SRC_URLS`, so `GET /federation/search` on either answers
from both, merged on `obs_id` (the cubes the two sites share are listed
once, the other site under `also_at`), asked with the caller's token. The
first site stays open, as the experiments E1–E5 and the broker expect; a
request to the second site without a token gets the `ivoa_bearer` challenge
that names the IAM.

The IAM is Keycloak with the realm in `keycloak/realm.json`: a public client
`visivo` (the desktop's authorization-code flow with its `vlva://callback`
redirect, and the password grant the scripts use) and a user `astronomer`
with password `testbed`. Tokens carry the issuer `http://localhost:18300/realms/srcnet`,
the address the host reaches the IAM at; the catalogue reaches it as
`keycloak:8080` inside the network (`IAM_WELLKNOWN_ENDPOINT`) and is told
the public issuer and discovery URL (`SKAVA_OIDC_ISSUER`,
`SKAVA_OIDC_PUBLIC_WELLKNOWN`). A token for a script:

```bash
curl -s -d grant_type=password -d client_id=visivo -d username=astronomer -d password=testbed -d scope=openid \
    http://localhost:18300/realms/srcnet/protocol/openid-connect/token | jq -r .access_token
```

Each catalogue also has the web admin SKAVA ships (`/admin/`: dashboard,
datasets with their replicas, nodes, uploads, audit log), a local account
separate from the IAM; `make admin` creates it on both sites.

`make conformance` reads the catalogue's TAP and DataLink, a node's SODA
services and its UWS job list with pyvo, from a container on the testbed's
network (`conformance/check_pyvo.py`), the way a generic VO client would.

## Running a finder next to the data

The `broker` service (port 18200) stands in for the SRCNet Computing Broker:
it takes a job, asks SKAVA where the dataset is, picks the first ranked node
whose backend has the requested finder and the memory the job needs, and
runs the finder as a task on that node. The job's placement reports every
candidate and why it was taken or left.

The memory need is the request's own figure (`"memory": "8G"`) or, when the
request has none, what the node states for the finder in its status
(`capabilities.finder_memory`: a factor of the dataset's size plus a floor)
applied to the dataset's size in the catalogue; a node with less free is
skipped with the figures in the reason. The check is only as good as its
inputs: a node that reports no available-memory figure, or states nothing
for the finder, is not held back, and the placement report says what was
known. The desktop client leaves the figure out, so the node's own statement
decides.

```bash
curl -s -X POST localhost:18200/v1/jobs -H 'content-type: application/json' -d '{
  "image": "inaf:visivo-finders:1.0", "cmd": ["sourcefind"],
  "rucio_did": "tb-cube-m", "requires_capability": ["finder:sofia2"],
  "cpu": 2,
  "parameters": {"params": {"scfind.threshold": 4.0}}}'
curl -s localhost:18200/v1/jobs/<id>            # status, placement, result
curl -s localhost:18200/v1/jobs/<id>/events     # server-sent events until it ends
curl -s localhost:18200/v1/jobs/<id>/logs
curl -s -X POST localhost:18200/v1/jobs/<id>/cancel
```

The node image (`node/Dockerfile`) adds SoFiA-2, compiled from its source
repository at build time, to the VisIVO backend image; `make node-base`
builds that base from the VisIVO repository next to this one (`VISIVO_REPO`
to point elsewhere), and `make up` builds the rest.

## Experiments

`experiments/` holds the scripted sessions the paper's evaluation is made
of (placement quality, a node dying mid-session, bytes moved, source finding
through the broker, the routing benchmark on PostgreSQL); see
[experiments/README.md](experiments/README.md). `make experiments` runs them
against the running testbed and `make figures` draws the figures. On a
laptop, keep the host awake while they run (`caffeinate -i -s make
experiments` on macOS): a sleeping host stops its own clocks but not the
containers', and a job clock that spans the sleep is wrong; every result
file records the host's clock skew so such a run is recognised.

## Knobs

| Variable | Default | Meaning |
|---|---|---|
| `FAR_DELAY`, `FAR_RATE` | `80ms`, `100mbit` | the far node's link (netem on its egress) |
| `BUSY_WORKERS` | `4` | CPU-bound processes on the busy node |
| `*_MEM`, `*_CPUS` | see the table | cgroup limits of each node |
| `TESTBED_BACKEND_TOKEN` | `testbed-backend-token` | token of the node backends |
| `TESTBED_INTERNAL_API_KEY` | `testbed-internal-api-key` | the catalogues' ingestion key |
| `TESTBED_FEDERATION_TIMEOUT` | `2` | seconds a catalogue waits for a sibling |
| `TESTBED_KEYCLOAK_ADMIN_PASSWORD` | `testbed-admin` | the IAM's admin console (`http://localhost:18300`, user `admin`) |
| `TESTBED_ADMIN_USER`, `TESTBED_ADMIN_PASSWORD` | `admin`, `TestbedAdmin1` | the catalogues' web admin (`make admin`; `/admin/` on either site) |

These are development credentials for a local testbed; never reuse them.

## Connecting the desktop client

Point VisIVO Visual Analytics' SKAVA panel at `http://localhost:18000` and
register the four node backends (`http://localhost:18101` … `18104`, token as
above) with node codes `BIG`, `SMALL`, `FAR` and `BUSY`; the client matches
SKAVA's backend descriptors to them by node code.

Pointed at the second site (`http://localhost:18001`) instead, the panel
gets the `ivoa_bearer` challenge, offers to sign in, opens the IAM's page
(user `astronomer`, password `testbed`) and retries with the token; its
"IAM…" setup is filled from the discovery URL the challenge names.
