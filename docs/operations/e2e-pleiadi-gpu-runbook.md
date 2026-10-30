# End-to-end run on INAF PLEIADI-GPU

A complete, recorded run of the compute-next-to-data chain on one real
node: a cube copied to the cluster, the VisIVO Visual Analytics backend
started next to it on a GPU compute node, the node's holdings published in
place and the node registered in a SKAVA catalogue, then the dataset found,
resolved, opened and analysed from a laptop, with nothing downloaded. Every
step leaves evidence: at the end you have a bundle that says what ran, where,
on which versions, on which data, and what it did.

```{note}
This page is the worked example. The general pattern for a SLURM cluster
with a shared filesystem, for any SRC, is
[SLURM-backed VisIVO backend](../client-integration/slurm-backed-backend.md).
The VisIVO side (image, launcher, backend settings) is documented by VisIVO
Visual Analytics itself.
```

## What runs where

| Where | What |
|---|---|
| your laptop | the SKAVA catalogue (the testbed's, `http://localhost:18000`), the VisIVO Visual Analytics desktop, the scripted client, two SSH tunnels |
| `pleiadi-gpu.oact.inaf.it` (frontend) | the clones, the image build, the publisher; no long-lived service |
| a GPU compute node (SLURM job) | the VisIVO backend in Apptainer, with one GPU, next to the data |

The node is registered in the catalogue as `PLEIADI-GPU-OACT`. Two tunnels
join the laptop and the cluster:

* laptop `localhost:18900` → compute node `:18900` (the backend), opened by
  the VisIVO launcher helper; the catalogue's container reaches it as
  `host.docker.internal:18900`;
* frontend `localhost:18080` → laptop `localhost:18000` (the catalogue), a
  reverse tunnel, so the publisher on the frontend can send its metadata.

Throughout, set these once in each shell:

```bash
# on the laptop
export PLEIADI=pleiadi-gpu.oact.inaf.it   # the frontend
export PUSER=<your user on PLEIADI>
export NODE=PLEIADI-GPU-OACT
export SKAVA_REPO=~/Documents/GitHub/SKAVA
export VISIVO_REPO=~/Documents/GitHub/VisIVO-next
export EVIDENCE=$SKAVA_REPO/testbed/results/pleiadi   # the bundle
mkdir -p "$EVIDENCE"
```

```bash
# on the frontend
export WORK=/scratch/$USER/skava-e2e   # writable, and seen by the compute nodes
export DATA=$WORK/data                 # the node's holdings (the data root)
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

The conda variant has the full stack on ppc64le and SoFiA-2;
`APPTAINERENV_ENABLE_CUPY=1` adds the GPU kernels (Apptainer passes only
`APPTAINERENV_`-prefixed variables into the build, so a plain `ENABLE_CUPY=1`
is ignored). The build runs from the repository root and takes from a few
minutes to half an hour.

```bash
cd $WORK/visivo
APPTAINERENV_ENABLE_CUPY=1 apptainer build --fakeroot $WORK/backend-conda.sif apptainer/backend-conda.def
```

If `--fakeroot` is not allowed on the frontend, build in a short interactive
GPU job (`srun -p gpu --gres=gpu:1 --pty bash`) or ask the system
administrators for the build path they support.

## 3. Load the data

Copy the cube from the laptop to the data root (any FITS cube works; the
reference run uses the Apertif DR1 HI cube of field 200426041, 661 × 661 ×
1218 channels, float32, 2.0 GB):

```bash
# on the laptop
rsync -avP ~/Downloads/DemoData/3D_Ape-DR1_200426041_AP_B021_HI_image_cube0.fits \
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
to see the compute node's hardware:

```bash
cd $WORK
srun -p gpu --gres=gpu:1 --time=00:10:00 --chdir=$WORK \
    bash skava/scripts/node_provenance.sh $WORK/backend-conda.sif $WORK/visivo $DATA/*.fits \
    > $WORK/node_provenance.txt
less $WORK/node_provenance.txt
```

## 5. Start the backend on a compute node

From the laptop, the VisIVO helper submits the job, waits for the backend,
and opens the tunnel `localhost:18900` → compute node:

```bash
# on the laptop
cd $VISIVO_REPO
RWORK=/scratch/$PUSER/skava-e2e                            # $WORK on the cluster
VCOMMIT=$(ssh $PUSER@$PLEIADI "git -C $RWORK/visivo rev-parse --short HEAD")
bash scripts/visivo_slurm_tunnel.sh \
    --frontend $PLEIADI --user $PUSER --repo-dir $RWORK/visivo \
    --partition gpu --gres gpu:1 --cpus 8 --mem 64G --time 04:00:00 \
    --port 18900 \
    --data-root $RWORK/data \
    --workspace $RWORK/backend \
    --sif $RWORK/backend-conda.sif \
    --node-code $NODE --version "$VCOMMIT"
```

`--workspace` holds what the backend writes (products, which it also
serves as a data root, caches), the job's log and the token file.

`--data-root` must be the same absolute path the publisher writes into the
`file://` URLs (step 7 uses `$DATA`, the same directory). The helper prints
the compute node, the job id and the backend token; keep the token:

```bash
export NODE_TOKEN=<the printed token>
curl -s http://localhost:18900/v1/ping                     # {"ok": true}
curl -s http://localhost:18900/v1/node/status | python3 -m json.tool | head -40
```

The status document must show `"node_code": "PLEIADI-GPU-OACT"`, the
commit as `version`, the GPU declared, and the memory and CPUs of the job
(not of the whole node).

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
apptainer exec --env PYTHONUSERBASE=$PYTHONUSERBASE backend-conda.sif \
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

apptainer exec --env PYTHONUSERBASE=$PYTHONUSERBASE --bind $WORK backend-conda.sif \
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
curl -s http://localhost:18000/datalink/$OBS_ID > $EVIDENCE/datalink.json
python3 -m json.tool $EVIDENCE/datalink.json | grep -E '"best_node"|"policy"|"rank_reason"|"content_length"'
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
TESTBED_SKAVA_URL=http://localhost:18000 TESTBED_BACKEND_TOKEN=$NODE_TOKEN \
    ../.venv/bin/python -m experiments.e7_real_node \
        --node $NODE --backend http://localhost:18900 \
        --collection inaf-pleiadi --name e7_pleiadi
```

It ends with `all steps ok` and writes `results/e7_pleiadi.json` and `.csv`.
Run it two or three times if you want a spread; each run overwrites the file,
so rename it in between (`--name e7_pleiadi_2`).

## 10. The desktop run (the picture)

In VisIVO Visual Analytics:

1. Settings ▸ Remote Backends ▸ Add: URL `http://localhost:18900`, the node
   token, SRC code `PLEIADI-GPU-OACT`.
2. SKAVA tab: service `http://localhost:18000`, Search, the collection
   `inaf-pleiadi`. The row shows *Served by* `PLEIADI-GPU-OACT` and the reason.
3. *Open*: the cube opens from the node (status bar: the node's backend).
4. *Compute next to data* ▸ *Moment map*: moment 0, Compute; the map opens
   from the node's workspace.
5. Capture the window at each step (`screencapture -o -l<window id>`, or the
   app's own export) into `$EVIDENCE/`.

## 11. Collect the evidence

```bash
# on the laptop
RWORK=/scratch/$PUSER/skava-e2e
scp $PUSER@$PLEIADI:$RWORK/node_provenance.txt $PUSER@$PLEIADI:$RWORK/publish.log $EVIDENCE/
ssh $PUSER@$PLEIADI "ls -t $RWORK/backend/logs/visivo_backend_*.log | head -1 | xargs grep -E 'open_skava|soda|moment|Started|Uvicorn'" \
    > $EVIDENCE/backend_log_excerpt.txt
curl -s -H "X-Internal-Api-Key: testbed-internal-api-key" http://localhost:18000/internal/telemetry \
    > $EVIDENCE/telemetry.json
cp $SKAVA_REPO/testbed/results/e7_pleiadi.* $EVIDENCE/
git -C $SKAVA_REPO rev-parse --short HEAD > $EVIDENCE/skava_commit.txt
ls -l $EVIDENCE
```

The bundle, `testbed/results/pleiadi/`, answers the questions a reader asks
of a real-node validation:

| Question | Where |
|---|---|
| Which hardware (CPU, memory, GPU) | `node_provenance.txt`, and `e7_pleiadi.json` (`node_status_before`: what the job was granted) |
| Which data (format, size, geometry, checksum) | `node_provenance.txt`, `datalink.json` (`content_length`) |
| Which software (VisIVO commit, image hash, Apptainer, SKAVA commit) | `node_provenance.txt`, `skava_commit.txt`, the node status `version` |
| What the catalogue decided, and why | `datalink.json`, `telemetry.json` |
| What was done on the node, how long it took | `e7_pleiadi.json` / `.csv`, `backend_log_excerpt.txt`, the screenshots |
| That nothing was downloaded | `e7_pleiadi.json` (the product path is on the node), `backend_log_excerpt.txt` |

## 12. Tear down

```bash
# on the laptop
bash $VISIVO_REPO/scripts/visivo_slurm_tunnel.sh --stop   # closes the tunnel, cancels the job
pkill -f "ssh -N -f -R 18080:localhost:18000"            # the reverse tunnel
```

The node stays registered in the testbed catalogue; disable it in the
admin UI (`http://localhost:18000/admin/nodes/`) if you want it out of the
rankings.

## Troubleshooting

```{list-table}
:header-rows: 1
:widths: 36 64

* - Symptom
  - What to check
* - The helper cannot parse the launcher's output
  - The job did not start (partition, GPU quota, time limit). Its log is in
    ``$WORK/backend/logs/`` on the frontend; ``squeue -u $USER`` shows why it waits.
* - ``Read-only file system`` anywhere
  - Something still writes under ``$HOME``: check that ``APPTAINER_CACHEDIR``,
    ``APPTAINER_TMPDIR`` and ``PYTHONUSERBASE`` are exported in that shell,
    and that the backend was started with ``--workspace``.
* - ``/v1/node/status`` shows no node code or GPU
  - The launcher on the frontend predates ``--node-code``: update the
    VisIVO clone there.
* - Telemetry says the probe failed
  - The catalogue's container cannot reach ``host.docker.internal:18900``.
    Check ``docker exec testbed-skava-1 python -c "import urllib.request;
    print(urllib.request.urlopen('http://host.docker.internal:18900/v1/ping').read())"``.
    If it fails, open the tunnel on all interfaces (``ssh -g -L``) or let the
    node report itself (node reports, see the configuration page).
* - ``publish.log`` shows ``replica_unverified`` or ``replica_conflict``
  - The obs_id is already catalogued from another node with another
    checksum: it is another product under the same identifier. Give the
    cube its own ``OBS_ID`` (the collection does not change the identity).
* - ``Withheld: obs_id ... is given by ... too``
  - Two files under the data root share an ``OBS_ID``; keep one product per
    ``OBS_ID`` (the publisher refuses to merge them).
* - Open refused: outside the data roots
  - ``--data-root`` must be the cluster path of ``$DATA`` exactly as the
    publisher's ``file://`` URLs name it.
* - The moment map is slow
  - Check ``cupy devices`` in ``node_provenance.txt``; zero means the image
    was built without ``APPTAINERENV_ENABLE_CUPY=1`` or the job has no GPU.
```
