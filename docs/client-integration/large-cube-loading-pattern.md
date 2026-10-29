# Large cube loading (Pattern B)

How SKAVA + VisIVO handle cubes that are *too large to auto-load into a
laptop client*. The pattern is named "Pattern B" in code reviews to
distinguish it from "Pattern A" (server-side rendering, see
{doc}`../architecture/compute-next-to-data`).

Pattern B is the production default for HI / SKA Phase 1 cubes (typical
size: 1–20 GB). Server-side rendering (Pattern A) is available where the
node's backend has an EGL context, and the client offers it when the
user asks for a full-resolution load of a large cube; on a node without
EGL, Pattern B is the only path to full resolution.

## The problem

A typical HI cube from the SKA Science Data Challenges is 10 GB float32
(643 × 643 × 6668 voxels). Auto-loading it to the client means:

* 10 GB of RAM on the laptop just for the volume array
* Plus 2–3× VTK overhead (octree, transfer-function LUT, gradient grids)
* Plus 10 GB+ VRAM for hardware volume rendering
* Plus a 10 GB transfer through the SSH tunnel (~3 min at 50 MB/s)

A MacBook with 32 GB / 16 GB unified GPU survives but thrashes. A laptop
with 16 GB simply OOMs. The user gets a multi-minute spinner followed by
a hung viewer.

## The fix in one sentence

The backend tells the client the cube's size and its own threshold
(4 GiB, or a quarter of the backend's memory when that is less); the
client chooses auto-load vs preview-only from it, and exposes explicit
"Load Full Resolution" and "Crop Full Resolution…" actions in the View
menu.

## Backend side

Every open response (`/v1/datasets/open`, `/v1/datasets/open_url`,
`/v1/datasets/open_skava`) carries three fields:

```json
{
  "file_size_bytes": 11027525760,
  "full_res_threshold_bytes": 4294967296,
  "recommended_load_mode": "preview_only"
}
```

`recommended_load_mode` is computed from `file_size_bytes ≥
full_res_threshold_bytes`:

* `"auto_full"` — client should auto-fetch the full cube after preview
  (legacy behaviour, exact bytes-on-disk under the threshold)
* `"preview_only"` — client should stop at preview and surface explicit
  user actions for full-res or crop

When `VISIVO_FULL_RES_THRESHOLD_BYTES` is set, it is the threshold,
outright. Otherwise the threshold is the smaller of:

* 4 GiB, empirically the size above which a 16 GB-RAM laptop with
  integrated/low-end discrete GPU starts thrashing on VTK volume
  rendering of an HI cube;
* a quarter of the memory the backend can have (the tightest cgroup
  limit in a container, such as a SLURM job's `--mem`, else the
  host's RAM). A full-resolution load streams the cube in concurrent
  slabs, so about twice the cube sits in the backend's memory at once:
  a node with 8 GB gets a 2 GiB threshold instead of being killed
  serving a 3 GB cube.

Implementation pointer: `backend/app/fits_dataset.py`,
`geometry_metadata()` and `_full_res_threshold_bytes()` (memory limit
from `backend/app/node_status.py`). Schema: `backend/app/schemas.py`,
`OpenDatasetResponse`.

## Client side

`BackendOpenDatasetResult` parses the three fields with safe defaults
(legacy backend → fields absent → `recommended_load_mode = "auto_full"`,
preserving the old behaviour).

`vtkWindowCube` consumes them in its constructor:

* `recommendedLoadMode == "auto_full"` → preview lands → automatically
  call `requestHighResCube()` (same code path as before)
* `recommendedLoadMode == "preview_only"` → preview lands → status bar
  shows ``Preview-only mode: cube is 10.0 GB (threshold 4.0 GB). Use
  View → Load Full Resolution or Crop Region for full-res data.``

The View menu has two actions (always visible, useful even on small
cubes for manual reload):

```text
View → Load Full Resolution        ← fetches the whole cube at full resolution
View → Crop Full Resolution…       ← opens the sub-cube ROI dialog
```

**Load Full Resolution** first checks the cube
against the client's own local-load threshold (setting
`Cube/local_full_threshold_mb`, default 256 MB). Above it, a warning
explains the memory and transfer cost and offers **Use Remote
Rendering** when the backend can render server-side, or a crop
otherwise; the user can still load it anyway.

Implementation pointers: `src/app/BackendClient.{h,cpp}`,
`src/gui/vtkWindowCube.{h,cpp}`, `src/gui/vtkWindowCube_Setup.cpp`.

## Crop full resolution

Reuses the existing `/v1/cube/subvolume` (or its faster sibling
`/v1/cube/subvolume_bin`, see below) plus the in-built sub-cube ROI
dialog. The operator picks X / Y / Z ranges, the backend returns only
those voxels at full resolution, the client renders the cropped cube
in-place. The cropped FITS is also persisted under the workspace
exports for re-opening later.

For a 10 GB cube + a ROI cropping to 30% on each axis (typical
"interesting region"), the cropped fetch is ≈ 270 MB — well under the
4 GiB threshold and ~10 s through the tunnel.

## Binary streaming endpoint

For full-resolution payloads (full cube or large crop), the backend
exposes `/v1/cube/subvolume_bin` returning **raw little-endian float32**
in the HTTP body with metadata in `X-Visivo-*` headers. The client
prefers it over the legacy JSON endpoint and falls back automatically
on 404 (older backend).

Why: empirical on an SDC2 1.6 GB subcube:

| Path | Encoding | Wall-time |
|---|---|---|
| Legacy JSON + base64 + zlib | 2.1 GB on the wire | 80–120 s (often timeout) |
| Legacy JSON + base64 (zlib off) | 2.0 GB on the wire | 50–60 s |
| Binary endpoint | 1.6 GB raw, 4 parallel slabs | 8–12 s |

The client splits the Z range into 4 concurrent slab requests
(configurable via `VISIVO_SUBVOLUME_PARALLEL` on the client, 1–16); each slab is its own
TCP stream over the same SSH tunnel, so per-stream TCP fairness
multiplies effective bandwidth ~3–4×.

The backend route bypasses the per-session task-slot rate limit for the
binary endpoint — the slabs are atomic pieces of one user request and
must run in parallel; counting each against the quota would 429 the
4th slab and silently fall back to the slow JSON path.

## Slice scrubbing during full-res load

Slice fetches (`/v1/cube/slice`) are routed through `_run_interactive`
on the backend, which **bypasses Dask** and the rate limit. Dask
dispatch overhead (~100–500 ms per task) is fine for the moment-map
fan-out but ruinous for a 100 ms interactive slice fetch.

On the client, slice changes are debounced at 300 ms across **every**
input path (slider drag, spinbox arrows, mouse wheel on the slider, the
floating ChannelOverlay scrubber). Idle ±1 prefetch is scheduled
500 ms after the last user action and cancelled on the next one, so a
rapid scroll produces zero prefetch and the tunnel stays clear for the
slice the user is actively looking at.

## Threshold tuning per deployment

The threshold is a backend setting: it applies to every client of that
backend, and the memory cap above still lowers the default on a small
node. An explicit value overrides both.

```{list-table}
:header-rows: 1
:widths: 25 25 50

* - Client class
  - Recommended threshold
  - Rationale
* - MacBook Air, 16 GB RAM
  - 2 GiB
  - 6× margin on the cube → workable VTK overhead
* - MacBook Pro, 32 GB RAM
  - 4 GiB (default)
  - 8× margin → comfortable for SDC2-class cubes
* - Workstation, 64+ GB RAM, discrete GPU
  - 8 GiB
  - Allow auto-load up to small SKA-Phase-1 cubes
* - Tablet / iPad client
  - 256 MiB
  - Always preview-only; never auto-load full res
```

Set via `APPTAINERENV_VISIVO_FULL_RES_THRESHOLD_BYTES=<bytes>` exported
in the environment `launch_backend_slurm.sh` runs in (the batch job
inherits it and Apptainer passes it into the container), or via
`VISIVO_FULL_RES_THRESHOLD_BYTES` on a bare-metal backend.

## See also

* {doc}`slurm-backed-backend` — the SLURM + SSH tunnel deployment
  pattern this builds on top of
* {doc}`../operations/e2e-pleiadi-gpu-runbook` — worked example on the INAF
  PLEIADI-GPU system
* {doc}`../architecture/compute-next-to-data` — why Pattern B is
  preferred over per-laptop data transfer for SKA-scale cubes
