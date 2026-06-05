# SLURM-backed VisIVO backend

How to integrate SKAVA with a VisIVO compute backend that runs on a
SLURM cluster instead of a static host. This is the right pattern for
sites where:

* the SRC cluster has a **shared filesystem** mounted on every compute
  node (BeeGFS, GPFS, Lustre, NFS, …), **and**
* the login (frontend) node should NOT host long-running services, but
  compute nodes are ephemeral and can't accept direct connections from
  outside the cluster, **and**
* a desktop client outside the cluster still needs to drive compute on
  the SRC's data.

The pattern uses an **SSH tunnel** from the laptop, through the
frontend, into whichever compute node SLURM happens to schedule the
backend on. From SKAVA's perspective and from the desktop's
perspective, the backend lives at a stable URL — even though the
underlying compute node changes between sessions.

## Why this works — three stable layers

```{mermaid}
flowchart LR
    subgraph laptop["Laptop"]
        Client[VisIVO desktop]
    end
    subgraph cluster["SRC cluster"]
        Frontend[(Frontend / login node)]
        Compute[Compute node N<br/>SLURM-assigned]
        FS[(Shared FS)]
    end

    Client -- "ssh -L 8000:N:8000 user@frontend" --> Frontend
    Frontend -.tunnel.-> Compute
    Compute -- "fits.open" --> FS

    style Compute stroke-dasharray: 5 5
    style FS stroke-width: 3px
```

| Layer | What's stable | Why |
|---|---|---|
| **Shared filesystem path** | `file:///data/cubes/m87.fits` | All compute nodes see the same mount under the same path |
| **Backend URL from the laptop** | `http://localhost:8000` | SSH tunnel always exits to a fixed local port |
| **SKAVA Node identifier** | `node_code = SRC-NAME` | Stays the same across SLURM allocations |

So even though SLURM may schedule the backend on `node-gpu-03` today
and `node-gpu-15` tomorrow, neither SKAVA nor the desktop client ever
sees those names.

## Prerequisites

* Cluster with SLURM ≥ 20 and a shared filesystem mounted at the same
  path on every compute node.
* Apptainer (or Singularity) available on compute nodes.
* SSH access from the laptop to the cluster frontend.
* A built VisIVO backend Apptainer image stored on the cluster
  (path on the shared filesystem so every compute node sees it).

## One-time setup

### 1. Create the Node in SKAVA

From the admin UI (`/admin/nodes/`):

```
Code:                <SRC-NAME>         e.g. POWER9, AUSSRC, ZAGRID
Name:                <human-friendly>   e.g. INAF Power9 SRC (SLURM)
Base URL:            http://localhost:8000
VisIVO backend URL:  http://localhost:8000
Requires bearer:     ✓
```

`http://localhost:8000` is **not** a placeholder — it's the URL the
SSH tunnel exits to on every consuming laptop. SKAVA emits it as the
visivo-backend descriptor's `endpoint`; the desktop matches it
against its registered Remote Backends.

### 2. Publish the catalogue once

Run the publisher on the frontend (or any compute node — the shared
filesystem makes it equivalent):

```yaml
# /etc/skava-publisher.yaml
skava:
  api_url: https://skava.your-domain.org
  internal_api_key: ${SKAVA_INTERNAL_API_KEY}
node:
  code: <SRC-NAME>
  # {relpath} is relative to the scan root; combined with the file://
  # prefix it becomes a path that's valid on every compute node thanks
  # to the shared mount.
  file_serve_url_pattern: "file:///data/{relpath}"
scan:
  roots:
    - /data
defaults:
  obs_collection: your-collection
state:
  db_path: /var/lib/skava-publisher/state.db
```

```bash
skava-publisher --config /etc/skava-publisher.yaml publish -y
```

Records land in SKAVA with `access_url=file:///data/<rel>.fits`. Those
URLs stay valid forever — they describe a path in the cluster's
namespace, not on any specific node.

### 3. Register the Remote Backend on each laptop

In VisIVO desktop:

```
Settings → Remote Backends → Add:
  ID:        src-<src-name>
  URL:       http://localhost:8000        ← the local end of the tunnel
  Token:     <stable token, see below>
  SRC code:  <SRC-NAME>                   ← matches the Node's code
```

`SRC code` is the safety net: even if a colleague's tunnel uses a
different local port, the desktop falls back to matching by
`node_code` and the routing still works.

## Token strategy

Each SLURM submission can generate a fresh random token (the default
behaviour of `launch_backend_slurm.sh`), or you can reuse a stable
one:

```{list-table}
:header-rows: 1
:widths: 22 39 39

* - Strategy
  - Setup
  - Trade-off
* - Stable token
  - Generate once with ``openssl rand -hex 32``, store in
    ``~/.visivo/<src-name>_token``, pass to the launcher
    via ``--token "$(cat ...)"``.
  - Set Remote Backends token once and never touch it again. Best
    operator experience.
* - Per-session token
  - Let the launcher generate one; copy from the printed output into
    Settings → Remote Backends.
  - Stronger forward secrecy; fresh credentials per session.
* - Per-session via file
  - Launcher writes the token to ``~/.visivo_token``; future desktop
    versions can auto-load. Not implemented in Phase 1.
  - Best balance once the desktop supports it.
```

For SKA testbeds, the stable-token strategy is recommended — fewer
moving parts, easier to demo.

## Per-session workflow

Every time the operator wants to use the backend:

```bash
# On the laptop
bash scripts/visivo_slurm_tunnel.sh \
    --frontend       <cluster-frontend.example.org> \
    --user           <login> \
    --partition      gpu \
    --gres           gpu:1 \
    --data-root      /data \
    --sif            /path/to/backend.sif \
    --token          "$(cat ~/.visivo/<src-name>_token)"
```

The script:

1. SSHes to the frontend.
2. Runs `launch_backend_slurm.sh` to submit a SLURM job.
3. Waits for the job to start.
4. Polls the compute node's `/v1/health` endpoint until it returns
   200.
5. Opens an SSH tunnel `localhost:8000 → <compute-node>:8000` through
   the frontend.
6. Prints the local URL + token (ready to paste if your Remote
   Backend hasn't been pre-registered).

Tear down with:

```bash
bash scripts/visivo_slurm_tunnel.sh --stop
# → closes the tunnel and scancels the SLURM job
```

## What happens when the operator clicks Open in the desktop

```{mermaid}
sequenceDiagram
    participant L as Laptop (VisIVO desktop)
    participant S as SKAVA
    participant T as SSH tunnel
    participant B as Backend (on compute node)
    participant F as Shared filesystem

    L->>S: GET /datalink/{obs_id}
    S-->>L: { service_descriptors: [{<br/>  type: "visivo-backend",<br/>  endpoint: "http://localhost:8000",<br/>  node_code: "SRC-NAME"<br/>}], primary_access.access_url: "file:///data/..." }
    Note over L: pickBackendForSkavaDataset:<br/>URL match on http://localhost:8000<br/>→ src-<src-name> Remote Backend
    L->>T: POST /v1/datasets/open_skava<br/>{ obs_id, access_url=file:///data/... }
    T->>B: forwarded
    B->>F: fits.open("/data/...")
    F-->>B: header + memmapped arrays
    B-->>T: { dataset_id, kind, geometry }
    T-->>L: same
    Note over L: viewer opens; subsequent moment/<br/>cutout requests follow the same tunnel
```

The shared filesystem is the only data path; nothing transits the
tunnel except control-plane messages and compute results.

## Edge cases

```{list-table}
:header-rows: 1
:widths: 30 70

* - Case
  - Behaviour
* - Two colleagues run the same workflow simultaneously
  - Each opens their own SSH tunnel to a different compute node.
    Both tunnels exit to the same ``localhost:8000`` because the
    laptops are isolated. SKAVA sees one descriptor with
    ``http://localhost:8000`` — that's actually correct, because each
    laptop interprets it locally.
* - Port 8000 already taken on the laptop
  - Pass ``--port 8765`` to the tunnel helper. Either update the
    Remote Backend URL to match, or rely on the ``srcCode`` match
    fallback.
* - SLURM preempts the job mid-session
  - The tunnel breaks. Re-run the helper — the publisher's data and
    SKAVA's Node URL are unchanged, so a new tunnel restores the
    flow.
* - Backend image is updated
  - Rebuild the ``.sif`` on the cluster. No SKAVA / desktop change
    needed; next SLURM launch picks up the new image.
* - Data file moves to a new path on the shared filesystem
  - Re-run the publisher. SKAVA's ingestion is idempotent on
    ``obs_id`` — existing rows update in place to the new
    ``access_url``.
* - The SSH frontend is behind a bastion / requires MFA
  - SSH's ``ProxyJump`` and ``ProxyCommand`` work transparently with
    the helper script's underlying ``ssh -L``. Configure them in
    ``~/.ssh/config`` once.
```

## Why not run the backend on the frontend

The frontend (login node) is shared with other users and has limited
resources. Running a long-lived VisIVO backend there:

* contends with interactive shell sessions
* breaks the "no compute on login node" policy most clusters enforce
* doesn't give access to the cluster's GPUs (which live on compute
  nodes)
* may be killed by the cluster's session limits

The SLURM-backed pattern solves all four.

## Why not give the backend a public hostname

A reverse proxy on a stable URL (e.g. `visivo.src-name.org`) is the
alternative pattern. It works, but:

* requires an always-on proxy host with TLS termination
* needs the proxy to track the current compute-node hostname and
  re-route on every SLURM allocation (or use service discovery)
* adds an admin surface and a point of failure
* doesn't beat the SSH-tunnel pattern for ergonomics — the operator
  already has SSH access for many other reasons

For sites that DO have a stable public hostname (e.g. behind a
Kubernetes ingress), simply set SKAVA's `visivo_backend_url` to that
hostname and the SLURM-tunnel pattern becomes optional.

## Verifying end-to-end

```bash
# Health check through the tunnel
curl -sf -H "Authorization: Bearer $VISIVO_TOKEN" \
     http://localhost:8000/v1/health
# {"ok": true, "version": "..."}

# What SKAVA hands clients for a published dataset
curl -s "https://skava.example.org/datalink/<obs-id>" \
    | jq '.service_descriptors[] | select(.service_type == "visivo-backend")'
# {
#   "service_type": "visivo-backend",
#   "endpoint": "http://localhost:8000",
#   "node_code": "<SRC-NAME>",
#   "requires_auth": true,
#   "supports_kinds": ["image","cube","dynspec"]
# }

# Manually drive open_skava end-to-end
curl -s -X POST \
    -H "Authorization: Bearer $VISIVO_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"obs_id":"<obs-id>","access_url":"file:///data/cubes/foo.fits"}' \
    http://localhost:8000/v1/datasets/open_skava | jq
# { "valid": true, "dataset_id": "ds_...", "kind": "cube", "geometry": {...} }
```

All three steps succeeding means the laptop ↔ SKAVA ↔ SLURM ↔
backend ↔ filesystem chain is wired correctly.

## Variants

```{list-table}
:header-rows: 1
:widths: 32 68

* - Variant
  - When it fits
* - Single stable URL via reverse proxy
  - You can dedicate one always-on host with TLS to front the
    backend. SKAVA's URL points at the proxy; the proxy points at the
    current compute node. No SSH tunnel needed on each laptop.
* - SLURM-tunnel (this page)
  - Cluster with shared FS + frontend SSH access. Most common SRC
    setup.
* - Job-array per-user
  - Each operator's job has a deterministic compute-node selection
    (e.g. via ``--nodelist``). Predictable, but reduces SLURM's
    scheduling flexibility.
* - srun --pty interactive
  - Useful for one-off debug sessions; not appropriate for shared
    operator use.
```

The SLURM-tunnel pattern is the default we ship the helper script
for; the other variants reuse the same SKAVA + Remote Backend
configuration with a different network layer.

## See also

* [Compute next to data](../architecture/compute-next-to-data) — the
  architectural pattern this page operationalises.
* [Backend routing](backend-routing) — how the desktop client
  matches descriptors against Remote Backends.
* [Power9 testbed runbook](../operations/e2e-power9-runbook) — a
  worked example of this pattern on the INAF Power9 SRC.
