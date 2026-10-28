"""Generate the testbed's science data: synthetic HI-like cubes, mirrored on nodes.

Each cube is written once and copied into every node directory that holds a
replica of it, so the nodes serve byte-identical copies. They are real copies
(separate inodes): hard links would share one page cache between the nodes, and
reading a replica on one node would warm it on the others. ``--link`` hard-links
instead, to save space where that does not matter (CI, smoke runs). The FITS
header carries an ``OBS_ID``, which the publisher uses as the logical identity:
the copies on different nodes therefore become replicas of one dataset rather
than unrelated datasets.

Usage::

    .venv/bin/python testbed/make_data.py --profile ci      # a few MB, for CI/smoke
    .venv/bin/python testbed/make_data.py --profile paper   # up to several GB

The layout is ``testbed/data/<node>/cubes/<name>.fits``; ``testbed/data`` is
git-ignored. Re-running skips cubes that already exist with the right size.
"""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

import numpy as np
from astropy.io import fits

HERE = Path(__file__).resolve().parent

# name -> (nx, ny, nz) per profile; sizes are float32, so bytes = 4*nx*ny*nz.
PROFILES = {
    "ci": {
        "tb-cube-s": (64, 64, 64),        # 1 MB
        "tb-cube-m": (128, 128, 128),     # 8 MB
        "tb-cube-l": (256, 256, 128),     # 32 MB
    },
    "paper": {
        "tb-cube-s": (256, 256, 256),     # 64 MB
        "tb-cube-m": (512, 512, 512),     # 512 MB
        "tb-cube-l": (1024, 1024, 768),   # 3 GB: larger than the small node's memory
    },
}

# Which node holds a replica of which cube. Every cube has at least two
# replicas, and the large one sits on the small node too, so the policy has to
# notice that the small node cannot serve it.
REPLICAS = {
    "tb-cube-s": ["big", "small", "far"],
    "tb-cube-m": ["big", "busy", "far"],
    "tb-cube-l": ["small", "big", "busy"],
}

NODES = ["big", "small", "far", "busy"]


def header_for(name: str, shape: tuple[int, int, int]) -> fits.Header:
    nx, ny, nz = shape
    h = fits.Header()
    h["SIMPLE"] = True
    h["BITPIX"] = -32
    h["NAXIS"] = 3
    h["NAXIS1"], h["NAXIS2"], h["NAXIS3"] = nx, ny, nz
    h["OBS_ID"] = name
    h["OBJECT"] = f"Synthetic HI field {name}"
    h["TELESCOP"] = "SKA-MID (synthetic)"
    h["BUNIT"] = "Jy/beam"
    h["CTYPE1"], h["CRVAL1"], h["CDELT1"], h["CRPIX1"], h["CUNIT1"] = "RA---SIN", 150.0, -4.0 / 3600, nx / 2, "deg"
    h["CTYPE2"], h["CRVAL2"], h["CDELT2"], h["CRPIX2"], h["CUNIT2"] = "DEC--SIN", -30.0, 4.0 / 3600, ny / 2, "deg"
    h["CTYPE3"], h["CRVAL3"], h["CDELT3"], h["CRPIX3"], h["CUNIT3"] = "FREQ", 1.40e9, -18.5e3, 1, "Hz"
    h["RESTFRQ"] = 1.420405752e9
    h["SPECSYS"] = "BARYCENT"
    h["BMAJ"] = h["BMIN"] = 12.0 / 3600
    h["BPA"] = 0.0
    return h


def fits_size(header: fits.Header, shape: tuple[int, int, int]) -> int:
    """Header plus data, each padded to whole 2880-byte FITS blocks."""
    data = 4 * shape[0] * shape[1] * shape[2]
    return len(header.tostring()) + -(-data // 2880) * 2880


def write_cube(path: Path, name: str, shape: tuple[int, int, int], seed: int) -> None:
    """Noise plus a few Gaussian sources with velocity gradients, one plane at a time."""
    nx, ny, nz = shape
    header = header_for(name, shape)
    tmp = path.with_suffix(".partial")
    # Write the header, then grow the file to its full size and fill plane by
    # plane through a memory map: memory use stays one plane whatever the size.
    header.tofile(tmp, overwrite=True)
    with tmp.open("rb+") as fh:
        fh.seek(fits_size(header, shape) - 1)
        fh.write(b"\0")
    with fits.open(tmp, mode="update", memmap=True) as hdul:
        data = hdul[0].data
        rng = np.random.default_rng(seed)
        yy, xx = np.mgrid[0:ny, 0:nx].astype(np.float32)
        sources = [
            (rng.uniform(0.2, 0.8) * nx, rng.uniform(0.2, 0.8) * ny,
             rng.uniform(0.25, 0.75) * nz, rng.uniform(3, 8), rng.uniform(0.02, 0.06) * nz,
             rng.uniform(0.005, 0.02), rng.uniform(-0.3, 0.3) * nz / nx)
            for _ in range(5)
        ]
        for z in range(nz):
            plane = rng.normal(0.0, 1.0e-3, size=(ny, nx)).astype(np.float32)
            for x0, y0, zc, r, dz, peak, grad in sources:
                # A rotating disc in miniature: the centre shifts with x.
                zc_x = zc + grad * (xx - x0)
                spec = np.exp(-0.5 * ((z - zc_x) / dz) ** 2)
                plane += (peak * spec * np.exp(-0.5 * ((xx - x0) ** 2 + (yy - y0) ** 2) / r ** 2)).astype(np.float32)
            data[z] = plane
        hdul.flush()
    os.replace(tmp, path)


def place(src: Path, dst: Path, link: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    same = dst.exists() and os.path.samefile(src, dst)
    if dst.exists() and (link == same) and dst.stat().st_size == src.stat().st_size:
        return
    if dst.exists():
        dst.unlink()
    if link:
        os.link(src, dst)
    else:
        shutil.copyfile(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="ci")
    parser.add_argument("--out", type=Path, default=HERE / "data")
    parser.add_argument("--link", action="store_true",
                        help="hard-link the replicas instead of copying them (shared page cache)")
    args = parser.parse_args()

    store = args.out / "_store"
    store.mkdir(parents=True, exist_ok=True)
    for i, (name, shape) in enumerate(PROFILES[args.profile].items()):
        expected = fits_size(header_for(name, shape), shape)
        src = store / f"{name}.fits"
        if not (src.exists() and src.stat().st_size == expected):
            print(f"writing {name} {shape} ({expected / 2**20:.0f} MiB)")
            write_cube(src, name, shape, seed=1000 + i)
        for node in NODES:
            dst = args.out / node / "cubes" / f"{name}.fits"
            if node in REPLICAS[name]:
                place(src, dst, args.link)
            elif dst.exists():
                dst.unlink()
    for node in NODES:
        (args.out / node / "cubes").mkdir(parents=True, exist_ok=True)
        held = sorted(p.name for p in (args.out / node / "cubes").glob("*.fits"))
        print(f"{node:6s} {held}")


if __name__ == "__main__":
    main()
