# SKAVA testbed

A reproducible federation on one machine: the SKAVA catalogue and four
simulated SRC nodes, each a VisIVO Visual Analytics backend with its own data,
resource limits and network link. It is where the routing policy, the
near-data operations and the paper's experiments are run.

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
make up              # build and start: catalogue on :18000, nodes on :18101-18104
make seed            # register the nodes, then publish each node's files in place
make status
make down            # stop and remove everything (make clean: also the data)
```

`make seed` runs `skava-publisher` next to each node's data: it reads the
headers in place and sends only metadata. Mirrored files carry the same
`OBS_ID`, so they become replicas of one logical dataset.

## Knobs

| Variable | Default | Meaning |
|---|---|---|
| `FAR_DELAY`, `FAR_RATE` | `80ms`, `100mbit` | the far node's link (netem on its egress) |
| `BUSY_WORKERS` | `4` | CPU-bound processes on the busy node |
| `*_MEM`, `*_CPUS` | see the table | cgroup limits of each node |
| `TESTBED_BACKEND_TOKEN` | `testbed-backend-token` | token of the node backends |
| `TESTBED_INTERNAL_API_KEY` | `testbed-internal-api-key` | SKAVA's ingestion key |

These are development credentials for a local testbed; never reuse them.

## Connecting the desktop client

Point VisIVO Visual Analytics' SKAVA panel at `http://localhost:18000` and
register the four node backends (`http://localhost:18101` … `18104`, token as
above) with node codes `BIG`, `SMALL`, `FAR` and `BUSY`; the client matches
SKAVA's backend descriptors to them by node code.
