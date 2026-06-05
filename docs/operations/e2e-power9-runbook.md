# Power9 testbed — end-to-end runbook

Step-by-step validation of the full compute-next-to-data flow on the
INAF Power9 SRC testbed. Each step prints what success looks like;
the troubleshooting hints in the bottom section cover what to do when
a step disagrees.

```{note}
For the **general** pattern of integrating SKAVA with a SLURM cluster
+ shared filesystem (applicable to any SRC, not just INAF Power9),
see [SLURM-backed VisIVO backend](../client-integration/slurm-backed-backend).
This page is the worked example.
```

The runbook assumes:

* SKAVA is up at `http://localhost:8000` on your Mac
* The publisher CLI works on your Mac (already validated end-to-end
  against MAC-LOCAL)
* You have SSH access to the Power9 host (`pleiadi-gpu.oact.inaf.it`)
* The Apptainer image `backend-gpu.sif` is built on Power9

## 0. Pre-flight

```bash
# On your Mac
docker compose -f ~/Documents/GitHub/SKAVA/docker-compose.yml ps
# Both db and api should be Up (healthy)

curl -sf http://localhost:8000/system/health | jq
# {"status": "ok", "version": "0.1.0", ...}
```

```bash
# On Power9
ssh pleiadi-gpu.oact.inaf.it
ls -la ~/VisIVO-next/backend-gpu.sif
# -rw-r--r--  1 fvitello fvitello 1.5G  Jun  5 21:00 backend-gpu.sif
nvidia-smi
# Should show the GPU(s) and driver version >= 525
```

## 1. Bring the Power9 backend up

```bash
# On Power9
cd ~/VisIVO-next

# Background launch with GPU passthrough, path jail, sensible workers
APPTAINERENV_VISIVO_WORKERS=8 \
APPTAINERENV_VISIVO_DATA_ROOT=/data \
nohup apptainer run --nv \
    --bind /data:/data \
    backend-gpu.sif > /tmp/visivo-backend.log 2>&1 &

echo $!  > /tmp/visivo-backend.pid

# Wait + grab the token
sleep 3
grep "Backend token" /tmp/visivo-backend.log
# [VisIVO] Backend token: <THIS_IS_YOUR_TOKEN>
```

Save the token as `POWER9_TOKEN` in your terminal.

## 2. Confirm the backend is reachable

```bash
# From Power9 itself
curl -sf -H "Authorization: Bearer $POWER9_TOKEN" \
     http://localhost:8000/v1/health | jq
# {"status": "ok"}

# From your Mac (assumes pleiadi-gpu is reachable on the network)
curl -sf -H "Authorization: Bearer $POWER9_TOKEN" \
     http://pleiadi-gpu.oact.inaf.it:8000/v1/health | jq
# {"status": "ok"}
```

If the Mac→Power9 hop fails, the rest of the runbook won't work —
fix the network reachability (VPN, firewall, hostname resolution)
before continuing.

## 3. Register the POWER9 node in SKAVA

Either via the admin UI (`http://localhost:8000/admin/nodes/`):

```
Code:                POWER9
Name:                INAF Power9 (Catania)
Base URL:            http://pleiadi-gpu.oact.inaf.it:8000
VisIVO backend URL:  http://pleiadi-gpu.oact.inaf.it:8000
Requires bearer:     ✓
Latency score:       10
Load score:          0.05
Capability score:    1.0
Enabled / Available: ✓ / ✓
```

Or via the helper script:

```bash
cd ~/Documents/GitHub/SKAVA
./scripts/register_power9_testbed.sh \
    pleiadi-gpu.oact.inaf.it:8000 \
    power9-smoke-001 \
    file:///data/cubes/m87.fits      # adjust to a real FITS on Power9
```

Verify in the admin UI:

```bash
curl -s "http://localhost:8000/discovery/search?obs_collection=inaf-power9-ska" | jq '.total'
# >= 1
```

## 4. Configure the desktop client

In VisIVO desktop:

### Settings → SKAVA

```
SKAVA base URL: http://localhost:8000
Token:          (leave empty — discovery is open by default)
```

### Settings → Remote Backends → Add

```
ID:        src-power9
Name:      INAF Power9 (Catania)
URL:       http://pleiadi-gpu.oact.inaf.it:8000
Token:     <POWER9_TOKEN from step 1>
SRC code:  POWER9
```

Save. The badge stays grey ("Backend: Local") until the first SKAVA
open.

## 5. End-to-end smoke

In the desktop:

1. Open **SKAVA Discovery** tab.
2. Type any filter that matches a Power9-published dataset (e.g.
   `obs_collection: inaf-power9-ska`).
3. Click **Search**. The table should populate.
4. Pick a row → **Open in VisIVO**.

What success looks like:

* Status bar badge turns **blue**: ``Backend: INAF Power9 (Catania)``
* Viewer opens with the cube / image
* No download progress bar — open happens in < 1 s for any size

Watch the backend log on Power9:

```bash
tail -f /tmp/visivo-backend.log | grep "open_skava\|moments\|region"
```

Expected line on open:

```
[open_skava] session=xxx dataset_id=ds_xxx kind=cube
            obs_id=power9-... path=/data/cubes/m87.fits
```

## 6. Compute-next-to-data benchmark

Once the dataset is open, exercise heavy compute:

* **Moment map** (Cube menu → Moment maps): for a 5 GB cube the wall
  time should be 1-2 s with `numba` + the GPU.
* **Region stats**: instant.
* **Channel map mosaic**: O(N) seconds where N = number of channels.

For each, the relevant timing line appears in the backend log:

```
[moment] dataset_id=ds_xxx order=0 elapsed_ms=842
```

Compare with the same dataset opened via the local backend on your
Mac (drag-drop a downloaded copy):

```
[moment] dataset_id=ds_yyy order=0 elapsed_ms=18450
```

The 20× speed-up demonstrates the value of compute-next-to-data:
no file transfer + GPU acceleration on the SRC.

## 7. Tear-down

```bash
# On Power9
kill "$(cat /tmp/visivo-backend.pid)"
rm /tmp/visivo-backend.pid /tmp/visivo-backend.log
```

The state inside the container is ephemeral; no cleanup needed.

## Troubleshooting

```{list-table}
:header-rows: 1
:widths: 36 64

* - Symptom
  - Diagnosis
* - Backend on Power9 listens but Mac curl times out
  - Firewall. Test ``nc -vz pleiadi-gpu.oact.inaf.it 8000`` from the
    Mac. Open the port or VPN in.
* - Status badge stays grey on Open
  - Routing didn't match. Check that ``/datalink/<obs_id>`` on SKAVA
    contains a ``visivo-backend`` descriptor with
    ``endpoint=http://pleiadi-gpu.oact.inaf.it:8000``, AND that the
    desktop's Remote Backend URL matches byte-for-byte.
* - Open returns 401 from Power9
  - Token mismatch between desktop Settings and the backend's
    startup log.
* - Open returns "outside VISIVO_DATA_ROOT"
  - The published ``access_url`` points outside ``/data``. Either
    move the file under ``/data`` or change
    ``APPTAINERENV_VISIVO_DATA_ROOT`` to its parent.
* - Open returns "Unsupported file type"
  - The path resolved to something that isn't FITS / HDF5. Verify
    with ``file <path>`` on Power9.
* - Moment map is slow even on Power9
  - Confirm CuPy is loaded: ``apptainer exec --nv backend-gpu.sif
    python -c "import cupy; print(cupy.cuda.runtime.getDeviceCount())"``.
    If 0 / ImportError, the build was CPU-only.
```

## Success criteria checklist

Tick each one before declaring the testbed validated:

- [ ] Pre-flight (step 0) — both SKAVA and the Power9 backend respond
      to `/system/health` and `/v1/health` respectively.
- [ ] Discovery (step 3) — at least one dataset visible in the admin
      UI tagged ``node=POWER9``.
- [ ] Routing (step 5) — desktop badge turns blue on Open, backend
      log shows the ``[open_skava]`` line.
- [ ] Performance (step 6) — moment / channel / region operations
      complete in < 5 s on a multi-GB dataset.
- [ ] Tear-down (step 7) — clean stop, no lingering processes.

If every box ticks, the testbed proves the architecture
end-to-end. Document the result and announce on the WP team
mailing list.
