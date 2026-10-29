#!/usr/bin/env bash
# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
#
# What a real node is, recorded before an end-to-end run: the host (CPU,
# memory, GPU), the container runtime and image, the VisIVO commit the image
# was built from, and each dataset (size, SHA-256, FITS geometry). Prints a
# text report; run it on the node and keep the output with the run's results.
#
# Usage:
#   scripts/node_provenance.sh <image.sif> <visivo-checkout> <dataset> [dataset ...] > node_provenance.txt
#
# Example (INAF PLEIADI-GPU):
#   scripts/node_provenance.sh ~/visivo/backend-conda.sif ~/visivo/VisIVO-next \
#       /data/skava/cube.fits > node_provenance.txt

set -uo pipefail

SIF="${1:?usage: node_provenance.sh <image.sif> <visivo-checkout> <dataset> [dataset ...]}"
VISIVO="${2:?missing the VisIVO checkout the image was built from}"
shift 2
[ "$#" -ge 1 ] || { echo "no dataset given" >&2; exit 2; }

section() { printf '\n## %s\n' "$1"; }
run() { printf '$ %s\n' "$*"; "$@" 2>&1 || printf '(exit %s)\n' "$?"; }

printf '# Node provenance\n'
printf 'recorded: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'host: %s\n' "$(hostname -f 2>/dev/null || hostname)"

section "Operating system"
run uname -a
[ -r /etc/os-release ] && run grep -E '^(NAME|VERSION)=' /etc/os-release

section "CPU"
if command -v lscpu >/dev/null; then
    lscpu | grep -E '^(Architecture|Model name|Model|Socket\(s\)|Core\(s\) per socket|Thread\(s\) per core|CPU\(s\)):'
fi
run nproc

section "Memory"
run free -g

section "GPU"
if command -v nvidia-smi >/dev/null; then
    run nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv
else
    echo "nvidia-smi not found"
fi

section "Scheduler limits of this shell (if inside a job)"
env | grep -E '^SLURM_(JOB_ID|CPUS_ON_NODE|MEM_PER_NODE|JOB_GPUS|GPUS_ON_NODE)=' || echo "not in a SLURM job"

section "Container runtime and image"
run apptainer --version
run ls -l "$SIF"
run sha256sum "$SIF"
apptainer inspect --labels "$SIF" 2>/dev/null || true

section "VisIVO Visual Analytics checkout the image was built from"
run git -C "$VISIVO" rev-parse HEAD
run git -C "$VISIVO" describe --tags --always --dirty

section "Inside the image: Python and GPU libraries"
apptainer exec --nv "$SIF" python - <<'EOF' 2>&1
import importlib, platform
print("python", platform.python_version(), platform.machine())
for name in ("numpy", "astropy", "dask", "numba", "cupy", "vtk", "fastapi"):
    try:
        mod = importlib.import_module(name)
        print(name, getattr(mod, "__version__", "?"))
    except Exception as exc:  # noqa: BLE001
        print(name, "not available:", type(exc).__name__)
try:
    import cupy
    print("cupy devices", cupy.cuda.runtime.getDeviceCount())
except Exception as exc:  # noqa: BLE001
    print("cupy devices: none (", type(exc).__name__, ")")
EOF

for DATA in "$@"; do
    section "Dataset $DATA"
    run ls -l "$DATA"
    run sha256sum "$DATA"
    apptainer exec --bind "$(dirname "$DATA")" "$SIF" python - "$DATA" <<'EOF' 2>&1
import sys
from astropy.io import fits
with fits.open(sys.argv[1], memmap=True) as hdul:
    for i, hdu in enumerate(hdul):
        h = hdu.header
        if h.get("NAXIS", 0) == 0:
            continue
        axes = [h.get(f"NAXIS{k}") for k in range(1, h["NAXIS"] + 1)]
        types = [h.get(f"CTYPE{k}") for k in range(1, h["NAXIS"] + 1)]
        print(f"HDU {i}: NAXIS={axes} CTYPE={types} BITPIX={h.get('BITPIX')} BUNIT={h.get('BUNIT')} "
              f"OBJECT={h.get('OBJECT')} OBS_ID={h.get('OBS_ID')} TELESCOP={h.get('TELESCOP')}")
EOF
done
