# End-to-end run on INAF PLEIADI-GPU (2026-10-30)

One real SRC node, recorded with `testbed/experiments/e7_real_node.py`
following `docs/operations/e2e-pleiadi-gpu-runbook.md`.

## Setup

| | |
|---|---|
| Catalogue | SKAVA 0.1.2 (the container's `app/` is file-for-file the tag e5ea3c6; later commits change only tooling), testbed compose on a laptop, `resource_aware` policy, prober every 10 s |
| Node | `PLEIADI-GPU-OACT`, SLURM job 940 on `r33c1s01` (8 CPUs, 64 GB, 1 × Tesla V100-SXM2-16GB) |
| Backend | VisIVO Visual Analytics in Apptainer (`backend-conda-gpu.sif`, built from c198ac5, SoFiA-2 2.7.1, CuPy 13.1.0); `backend/app` overlaid from d9ccbd7 with `--backend-src` (the only file that differs is `backend/app/node_status.py`, the cgroup v1 and SLURM memory grant reading) |
| Link | laptop to compute node through an SSH tunnel via the frontend; probe RTT 77-84 ms |
| Data | 10 FITS files (about 12 GB) in `/scratch/fvitello/skava-e2e/data`, published in place by `skava-publisher` from the frontend (10 datasets, 10 replicas, no skips); only metadata left the cluster |

`node_provenance.txt` records the host, the GPU, the job's limits, the image's
SHA-256 and each dataset's size, SHA-256 and FITS geometry. Its "checkout"
section shows d9ccbd7, the clone the overlay came from.

## Results

Three runs per dataset; each cell is first run / median of runs 2-3, in
seconds, as the scripted client saw them through the tunnel. The ADQL query
(5-6 ms) and the DataLink resolution (3-6 ms) are omitted. The first Apertif
run was cold (page cache and JIT): its slice and moment times are the cold
figures.

| Dataset | Shape | Open in place | First slice | Moment-0 (client) | Product opened | Moment-0 job (node) |
|---|---|---|---|---|---|---|
| Apertif DR1 HI cube | 661×661×1218 | 0.27 / 0.27 | 4.70 / 0.69 | 2.69 / 1.61 | 0.78 / 0.81 | 2.34 / 1.32 |
| HCG 44 HI cube | 700×700×158 | 0.32 / 0.28 | 0.85 / 0.79 | 0.64 / 0.72 | 0.81 / 0.87 | 0.41 / 0.37 |
| WALLABY Hydra TR2 cube | 196×280×109 | 0.16 / 0.16 | 0.21 / 0.22 | 0.48 / 0.45 | 0.35 / 0.36 | 0.04 / 0.04 |

Every run routed to `PLEIADI-GPU-OACT` under `resource_aware`. Every step
succeeded, and no byte of the cubes was downloaded. The DataLink
`content_length` equals the file size in bytes (`datalink_*.json`, taken with
the node idle).

## Known limits of this node

* The cluster runs cgroup v1 without pressure stall information, so the
  ranking reason reads "cpu pressure unknown" and CPU utilisation is not
  reported.
* SLURM does not enforce the memory limit with a cgroup on this cluster. The
  node reports the job's grant (`SLURM_MEM_PER_NODE`) as its limit.

## Files

`node_provenance.txt`, `publish.log`, `datalink_<id>.json` (Apertif
f9d87580137323b7, HCG 44 eae0ae4d9b7fdbf0, WALLABY 5cccbc587841e345),
`telemetry.json`, `backend_log_excerpt.txt`, `e7_<dataset>_<run>.{json,csv}`.
