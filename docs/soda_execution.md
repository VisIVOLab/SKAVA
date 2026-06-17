# SODA execution — compute-next-to-data

How SKAVA turns a SODA subset request into a real FITS cutout **without moving the
file**. The byte-level work runs on the SRC node that already holds the data; only the
(small) cutout transits the network.

## Two services, one boundary

```
SODA / VO client
      │  POST /soda/execute?ID=…&POS=…&BAND=…
      ▼
   SKAVA  ── resolves best node + file:// replica ──┐
      │                                             │ delegates (httpx)
      │                                             ▼
      │                        VisIVO backend @ node  POST /v1/datasets/cutout
      │                                             │  fits.open(file:///data/…)
      │                                             │  astropy Cutout2D + spectral slice
      │  ◀── application/fits (streamed) ───────────┘
      ▼
   client receives the cutout
```

* **SKAVA never reads the science file.** It has no filesystem access to SRC storage;
  it only orchestrates and proxies the result.
* **The VisIVO backend never re-queries SKAVA.** SKAVA passes the `file://` access_url it
  already resolved; the backend opens it in place (same trust model as `open_skava`).

## SKAVA side — `POST /soda/execute`

Delegation conditions (all required):

1. the dataset's best ranked node has `Node.visivo_backend_url` set;
2. the selected replica's `access_endpoint` is a `file://` URL.

When met, SKAVA POSTs to `{visivo_backend_url}/v1/datasets/cutout` with the SODA
parameters and streams back `application/fits`. Otherwise it falls back to the
metadata-cache staging handoff (legacy behaviour), so catalogue entries without a
co-located backend still get a routed access URL.

Configuration (`app/config.py`):

| Setting | Env var | Default | Purpose |
|---|---|---|---|
| `visivo_backend_token` | `SKAVA_VISIVO_BACKEND_TOKEN` | `None` | Forwarded as `X-Visivo-Token` when the node backend requires auth. |
| `soda_backend_timeout_seconds` | `SKAVA_SODA_BACKEND_TIMEOUT_SECONDS` | `120` | Bounds the synchronous wait on the node backend. |

Errors:
- `502 backend_execution_failed` — node backend reachable but returned an error / timed out.
- `404 dataset_not_found`, `503 no_available_nodes` — as for the other access endpoints.

Implementation: `app/services/soda_execution_service.py`, wired in `app/routers/soda.py`.

## VisIVO backend side — `POST /v1/datasets/cutout`

Part of the VisIVO backend (`backend/app/routers/datasets.py`, logic in
`backend/app/soda_cutout.py`). Request body:

```json
{
  "obs_id": "dataset-3",
  "access_url": "file:///data/dataset-3.fits",
  "pos": "CIRCLE 103 -23 0.05",
  "band": "1.3e-6 1.4e-6",
  "responseformat": "application/fits"
}
```

Behaviour:
- resolves `file://` → local path, enforcing the `VISIVO_DATA_ROOT` jail (shared with
  `open_skava`);
- opens the FITS with astropy, applies a spatial cutout (`POS = CIRCLE | RANGE | POLYGON`,
  via `Cutout2D` on the celestial WCS — works for 2D images and N-D cubes) and a spectral
  cutout (`BAND` in metres, converted to the dataset's spectral axis unit);
- fixes `CRPIX` for the trimmed axes and streams the subset back as `application/fits`,
  with `X-Soda-Applied` listing which subsets took effect.

Parameters the WCS cannot support (e.g. `BAND` on an image with no spectral axis) and
non-overlapping regions return `400`.

## What is and isn't wired to the VisIVO desktop

- The desktop's **compute-next-to-data open** (`/v1/datasets/open_skava` + moments /
  region / channel) is unchanged and already wired.
- `/v1/datasets/cutout` is consumed by **SKAVA `/soda/execute`** (VO/SODA clients) **and**
  by the VisIVO desktop's **"SODA subset"** action in the SKAVA Discovery tab. The desktop
  calls it with `save_to_workspace=true` so the cutout is written to the node backend's
  Workspace Exports and opened **in place** (never downloaded to the client). The desktop
  also keeps its separate VLKB cutout path (`/v1/vlkb/fetch_cutout`).
