# End-to-end run on INAF PLEIADI-GPU

A complete, recorded run of the compute-next-to-data chain on one real
node: a cube copied to the cluster, the VisIVO Visual Analytics backend
started next to it on a GPU compute node, the node's holdings published in
place and the node registered in a SKAVA catalogue, then the dataset found,
resolved, opened and analysed from a laptop, with nothing downloaded. Every
step leaves evidence: at the end you have a bundle that says what ran, where,
on which versions, on which data, and what it did.

```{note}
This page is the worked example. SKAVA's side of the general pattern, a
node the catalogue cannot reach, is
[Registering a node SKAVA cannot reach](node-behind-firewall.md). The
VisIVO side (image, launcher, tunnel, backend settings) is documented by
VisIVO: [Running the backend on a SLURM cluster](https://visivo.readthedocs.io/en/latest/deployment/hpc-slurm.html).
The steps marked "On the VisIVO side" below give only the values SKAVA
needs from it.
```

## What runs where

| Where | What |
|---|---|
| your laptop | the SKAVA catalogue (the testbed's, `http://localhost:18000`), the VisIVO Visual Analytics desktop, the scripted client, two SSH tunnels |
| `pleiadi-gpu.oact.inaf.it` (frontend) | the clones, the image build, the publisher; no long-lived service |
| a GPU compute node (SLURM job) | the VisIVO backend in Apptainer, with one GPU, next to the data |

The node is registered in the catalogue as `PLEIADI-GPU-OACT`. Two tunnels
join the laptop and the cluster:

* laptop `localhost:18900` → compute node `:18900` (the backend), opened
  on the VisIVO side with the backend; the catalogue's container reaches it
  as `host.docker.internal:18900`;
* frontend `localhost:18080` → laptop `localhost:18000` (the catalogue), a
  reverse tunnel, so the publisher on the frontend can send its metadata.

Throughout, set these once in each shell:

```bash
# on the laptop
export PLEIADI=pleiadi-gpu.oact.inaf.it   # the frontend
export PUSER=<your user on PLEIADI>
export NODE=PLEIADI-GPU-OACT
export SKAVA_REPO=<path of your SKAVA checkout>
export EVIDENCE=$SKAVA_REPO/testbed/results/pleiadi   # the bundle
mkdir -p "$EVIDENCE"
```

```bash
# on the frontend
export WORK=/scratch/$USER/skava-e2e   # writable, and seen by the compute nodes
export DATA=$WORK/data                 # the node's holdings (the data root)
export SIF=$WORK/backend-conda-gpu.sif # the backend image (step 2)
export NODE=PLEIADI-GPU-OACT
export APPTAINER_CACHEDIR=$WORK/apptainer-cache APPTAINER_TMPDIR=$WORK/apptainer-tmp
export PYTHONUSERBASE=$WORK/pyuser     # where pip --user installs the publisher
mkdir -p "$WORK" "$DATA" "$APPTAINER_CACHEDIR" "$APPTAINER_TMPDIR" "$PYTHONUSERBASE"
```

On PLEIADI the home directory is read-only, so everything this run writes
goes under `/scratch/$USER`: the clones, the image and its build cache, the
data, the publisher's installation and state, and the backend's products,
caches, logs and token (the launcher's `--workspace`).

## 0. Prerequisites

* SSH access to the frontend, with a key (the helpers run `ssh` non-interactively).
* A SLURM account with access to a GPU partition (default `gpu`, one GPU).
* Outbound internet on the frontend (git clone, conda packages, pip).
* On the laptop: the SKAVA testbed catalogue up (`cd testbed && make up`),
  the VisIVO Visual Analytics desktop, Python 3.11 (the SKAVA virtualenv).
* `$WORK` on a filesystem shared with the compute nodes and writable
  (`/scratch/$USER`; check with `df -h $WORK`; avoid node-local `/tmp`).

## 1. Clones and versions on the frontend

```bash
ssh $PUSER@$PLEIADI
cd $WORK
git clone https://github.com/VisIVOLab/VisIVOVisualAnalytics.git visivo
git clone https://github.com/VisIVOLab/SKAVA.git skava
git -C skava rev-parse --short HEAD      # note it: the SKAVA tools of this run
git -C visivo rev-parse --short HEAD     # note it: the backend version of this run
```

The SKAVA clone needs the tools of this page (`scripts/node_provenance.sh`,
the publisher's collision checks): `main`, or a release after 0.1.2. Use the
VisIVO commit you want to report; to pin a release, `git -C visivo checkout
<tag>`. The laptop's SKAVA checkout should be the same commit.

## 2. Build the backend image (once)

```{admonition} On the VisIVO side
:class: tip

Build the VisIVO backend's conda image with the GPU kernels, on the
frontend, as `$WORK/backend-conda-gpu.sif` (`$SIF`), and link
`backend-conda.sif` to it (`ln -sf backend-conda-gpu.sif backend-conda.sif`
in `$WORK`): `backend-conda.sif` is the name VisIVO's EGL image for
server-side 3D rendering, `backend-egl.sif`, is built on. The recorded
run used `backend-conda-gpu.sif`; `backend-egl.sif` is needed only to
render cubes on the node's GPU from the desktop. How to build both:
[Running the backend on a SLURM cluster](https://visivo.readthedocs.io/en/latest/deployment/hpc-slurm.html).

SKAVA needs nothing from the image itself. Steps 4 and 7 use it only as a
Python with astropy, to record the node and to run the publisher.
```

## 3. Load the data

Copy the cube from the laptop to the data root (any FITS cube works; the
reference run uses the Apertif DR1 HI cube of field 200426041, 661 × 661 ×
1218 channels, float32, 2.0 GB):

```bash
# on the laptop
rsync -avP <path of the cube>/3D_Ape-DR1_200426041_AP_B021_HI_image_cube0.fits \
    $PUSER@$PLEIADI:/scratch/$PUSER/skava-e2e/data/
```

Then, on the frontend, check it arrived whole:

```bash
ls -l $DATA
sha256sum $DATA/*.fits      # compare with `shasum -a 256` of the laptop copy
```

## 4. Record what the node is

The provenance report: host, CPU, memory, GPU, Apptainer, the image's hash,
the VisIVO commit, the Python and GPU libraries inside the image, and each
dataset (size, SHA-256, FITS geometry). Run it inside the GPU job allocation
to see the compute node's hardware. Once the backend is up (step 5), running
it as a step of the backend's own job records that job's node and limits:
`srun --jobid=<backend job> --overlap bash skava/scripts/node_provenance.sh ...`.

```bash
cd $WORK
srun -p gpu --gres=gpu:1 --time=00:10:00 --chdir=$WORK \
    bash skava/scripts/node_provenance.sh $SIF $WORK/visivo $DATA/*.fits \
    > $WORK/node_provenance.txt
less $WORK/node_provenance.txt
```

## 5. Start the backend on a compute node

```{admonition} On the VisIVO side
:class: tip

Start the backend in a SLURM job on a GPU compute node, from the image of
step 2, with an SSH tunnel from the laptop's `localhost:18900` to it:
[Running the backend on a SLURM cluster](https://visivo.readthedocs.io/en/latest/deployment/hpc-slurm.html).
The values SKAVA needs:

* **data root**: `$DATA` (`/scratch/$PUSER/skava-e2e/data`), the same
  absolute path the publisher writes into the `file://` URLs in step 7;
* **node code**: `$NODE` (`PLEIADI-GPU-OACT`), the code the node is
  registered with in step 6;
* **version**: the VisIVO commit noted in step 1, so the node's status
  document names what ran;
* **token**: the backend's token, which the scripted client sends to the
  node in step 9. Keep it as `NODE_TOKEN`.

The reference run asked for 8 CPUs, 64 GB and one GPU for 4 hours.
```

Check the backend through the tunnel:

```bash
# on the laptop
export NODE_TOKEN=<the token of the backend>
curl -s http://localhost:18900/v1/ping                     # {"ok": true}
curl -s http://localhost:18900/v1/node/status | python3 -m json.tool | head -40
```

The status document must show `"node_code": "PLEIADI-GPU-OACT"`, the
commit as `version`, the GPU declared, and the memory and CPUs of the job
(not of the whole node): this is what the catalogue will rank the node on.
PLEIADI's SLURM does not enforce `--mem` with a control-group limit, so the
backend has to read the job's grant; a backend that reports the whole
node's memory (about 334 GB) is too old for this run (see the VisIVO page).

## 6. Register the node in the catalogue

The catalogue (in Docker on the laptop) reaches the tunnel through
`host.docker.internal`:

```bash
# on the laptop
cd $SKAVA_REPO
SKAVA_COMPOSE_FILE=testbed/docker-compose.yml \
    scripts/register_node.sh $NODE "INAF PLEIADI-GPU (Catania)" http://host.docker.internal:18900 true
```

Within one probe interval (10 s) the catalogue measures the node:

```bash
curl -s -H "X-Internal-Api-Key: testbed-internal-api-key" \
    http://localhost:18000/internal/telemetry | python3 -m json.tool | grep -A12 "$NODE"
# "probe_ok": true, "probe_rtt_ms": ..., the node's CPU pressure and free memory
```

If the catalogue cannot reach the tunnel, see Troubleshooting.

## 7. Publish the node's holdings in place

The publisher runs on the frontend, inside the backend image (which has
astropy), reads the headers where the files lie, and sends only metadata
to the catalogue through a reverse tunnel.

```bash
# on the laptop: the reverse tunnel, frontend:18080 → laptop:18000
ssh -N -f -R 18080:localhost:18000 $PUSER@$PLEIADI
```

```bash
# on the frontend: install the publisher for the image's Python (once)
cd $WORK
apptainer exec --env PYTHONUSERBASE=$PYTHONUSERBASE $SIF \
    python -m pip install --user --no-cache-dir ./skava/tools/skava-publisher

cat > $WORK/publisher.yaml <<EOF
skava:
  api_url: http://localhost:18080
  internal_api_key: testbed-internal-api-key
node:
  code: $NODE
  file_serve_url_pattern: "file://$DATA/{relpath}"
scan:
  roots: [$DATA]
  compute_checksum: true
defaults:
  obs_collection: inaf-pleiadi
  license: CC-BY-4.0
  publisher_label: skava-publisher@pleiadi-gpu
state:
  db_path: $WORK/publisher-state.db
EOF

apptainer exec --env PYTHONUSERBASE=$PYTHONUSERBASE --bind $WORK $SIF \
    python -m skava_publisher -c $WORK/publisher.yaml publish --yes 2>&1 | tee $WORK/publish.log
```

`publish.log` ends with SKAVA's answer: one record processed, none skipped.
The dataset's identifier is its `OBS_ID` header or, without one, a stable
one derived from the node code and the file's path.

## 8. Check the decision

```bash
# on the laptop
curl -s "http://localhost:18000/tap/sync?LANG=ADQL&REQUEST=doQuery&RESPONSEFORMAT=json&QUERY=SELECT%20obs_id,%20access_url%20FROM%20ivoa.obscore%20WHERE%20obs_collection%20=%20'inaf-pleiadi'" \
    | python3 -m json.tool | head -20
export OBS_ID=<the obs_id above>
curl -s http://localhost:18000/datalink/$OBS_ID | python3 -m json.tool > $EVIDENCE/datalink_$OBS_ID.json
grep -E '"best_node"|"policy"|"rank_reason"|"content_length"' $EVIDENCE/datalink_$OBS_ID.json
```

Expected: `best_node` is `PLEIADI-GPU-OACT`, `policy` is `resource_aware`,
the reason quotes the measured round trip, CPU pressure and free memory,
and `content_length` is the file's size in bytes.

## 9. The scripted run (the record)

The scripted client speaks the same APIs as the desktop and times every
step: ADQL query, DataLink resolution, open in place on the node, first
channel slice, a moment-0 map as a SODA job on the node, the product opened
where it was made, the node's status before and after.

```bash
# on the laptop
cd $SKAVA_REPO/testbed
export TESTBED_SKAVA_URL=http://localhost:18000 TESTBED_BACKEND_TOKEN=$NODE_TOKEN
for rep in 1 2 3; do
    ../.venv/bin/python -m experiments.e7_real_node \
        --node $NODE --backend http://localhost:18900 \
        --obs-id $OBS_ID --name pleiadi/e7_apertif_$rep
done
```

Each run ends with `all steps ok` and writes `results/pleiadi/<name>.json`
and `.csv`, straight into the bundle. The first run of a dataset is cold
(page cache, compiled kernels): three runs give the cold figure and a warm
spread. Repeat with each dataset you published, one `--obs-id` and one name
each (the reference run used Apertif, HCG 44 and WALLABY).

## 10. The desktop run

The same chain can be driven from the VisIVO Visual Analytics desktop: point
its SKAVA tab at `http://localhost:18000`, search the collection
`inaf-pleiadi`, and open the dataset on the node registered as
`PLEIADI-GPU-OACT` (backend `http://localhost:18900`, the node token). How
is documented by VisIVO:
[SKAVA discovery](https://visivo.readthedocs.io/en/latest/user-guide/skava-discovery.html).
The record of this run is the scripted one of step 9.

## 11. Collect the evidence

```bash
# on the laptop
RWORK=/scratch/$PUSER/skava-e2e
scp $PUSER@$PLEIADI:$RWORK/node_provenance.txt $PUSER@$PLEIADI:$RWORK/publish.log $EVIDENCE/
ssh $PUSER@$PLEIADI "ls -t $RWORK/backend/logs/visivo_backend_*.log | head -1 | xargs grep -E 'open_skava|soda|moment|Started|Uvicorn|ERROR|Traceback'" \
    > $EVIDENCE/backend_log_excerpt.txt
curl -s -H "X-Internal-Api-Key: testbed-internal-api-key" http://localhost:18000/internal/telemetry \
    > $EVIDENCE/telemetry.json
ls -l $EVIDENCE
```

The bundle, `testbed/results/pleiadi/`, answers the questions a reader asks
of a real-node validation:

| Question | Where |
|---|---|
| Which hardware (CPU, memory, GPU) | `node_provenance.txt`, and the `e7_*.json` files (`node_status_before`: what the job was granted) |
| Which data (format, size, geometry, checksum) | `node_provenance.txt`, `datalink_*.json` (`content_length`) |
| Which software (VisIVO commit, image hash, Apptainer, SKAVA commit) | `node_provenance.txt`, the `e7_*.json` metadata (`skava_commit`, `visivo_commit`), the node status `version` |
| What the catalogue decided, and why | `datalink_*.json`, `telemetry.json` |
| What was done on the node, how long it took | `e7_*.json` / `.csv`, `backend_log_excerpt.txt` |
| That nothing was downloaded | `e7_*.json` (the product path is on the node), `backend_log_excerpt.txt` |

Add a `README.md` stating the setup (job, image and overlay commits, link,
data) and summarising the runs; the reference run's is in the repository.

## 12. Tear down

```bash
# on the laptop
pkill -f "ssh -N -f -R 18080:localhost:18000"            # the reverse tunnel
```

On the VisIVO side, close the backend's tunnel and cancel its SLURM job
([Running the backend on a SLURM cluster](https://visivo.readthedocs.io/en/latest/deployment/hpc-slurm.html)).

The node stays registered in the testbed catalogue; disable it in the
admin UI (`http://localhost:18000/admin/nodes/`) if you want it out of the
rankings.

## Troubleshooting

```{list-table}
:header-rows: 1
:widths: 36 64

* - Symptom
  - What to check
* - The backend job does not start, or its status document lacks the node
    code, the GPU or the job's memory
  - On the VisIVO side: see its troubleshooting in
    [Running the backend on a SLURM cluster](https://visivo.readthedocs.io/en/latest/deployment/hpc-slurm.html).
* - ``Read-only file system`` anywhere
  - Something still writes under ``$HOME``: check that ``APPTAINER_CACHEDIR``,
    ``APPTAINER_TMPDIR`` and ``PYTHONUSERBASE`` are exported in that shell,
    and that the backend writes its workspace under ``$WORK``.
* - Telemetry says the probe failed
  - The catalogue's container cannot reach ``host.docker.internal:18900``.
    Check ``docker exec testbed-skava-1 python -c "import urllib.request;
    print(urllib.request.urlopen('http://host.docker.internal:18900/v1/ping').read())"``.
    If it fails, open the tunnel on all interfaces (``ssh -g -L``) or let the
    node report itself ([Telemetry API](../api/telemetry.md#node-reports)).
* - ``publish.log`` shows ``replica_unverified`` or ``replica_conflict``
  - The obs_id is already catalogued from another node with another
    checksum: it is another product under the same identifier. Give the
    cube its own ``OBS_ID`` (the collection does not change the identity).
* - ``Withheld: obs_id ... is given by ... too``
  - Two files under the data root share an ``OBS_ID``; keep one product per
    ``OBS_ID`` (the publisher refuses to merge them).
* - Open refused: outside the data roots
  - The backend's data root must be the cluster path of ``$DATA`` exactly
    as the publisher's ``file://`` URLs name it.
* - ``content_length`` is a multiple of 1024, not the file's size
  - The publisher is an old installation: SKAVA clones before ``a7a909e``
    tracked a stale ``tools/skava-publisher/build/``, which pip installed
    in place of the source. Delete it, reinstall with ``--force-reinstall``,
    and publish again (the records are updated, not duplicated).
* - The moment map is slow
  - Check ``cupy devices`` in ``node_provenance.txt``; zero means the image
    has no GPU kernels or the job has no GPU (VisIVO side).
```
