"""HDF5 extractor for LOFAR / generic beamformed dynamic-spectrum files.

LOFAR's beamformed format (ICD-3) is the canonical structure we target,
but the extractor falls back to reading root-level attributes for
generic HDF5 datasets so other instruments (CHIME, MeerKAT) can plug in
without a dedicated extractor.

The extracted shape is ObsCore: dynspec-like products have
``dataproduct_type=dynspec`` (not in the standard ObsCore vocab but
adopted by VisIVO + SKAVA for SKA-pathfinder workflows).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from skava_publisher.extractors.base import Extractor

logger = logging.getLogger("skava.publisher.hdf5")


def _attr(group, key: str) -> Any:
    """Best-effort read of an HDF5 attribute, decoding bytes to str."""
    try:
        v = group.attrs.get(key)
    except Exception:
        return None
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8", errors="replace").strip()
        except Exception:
            return None
    if hasattr(v, "tolist"):
        try:
            return v.tolist()
        except Exception:
            return None
    return v


class Hdf5Extractor(Extractor):
    name = "hdf5"

    _SUFFIXES = (".h5", ".hdf5")

    def supports(self, path: Path) -> bool:
        name = path.name.lower()
        return any(name.endswith(s) for s in self._SUFFIXES)

    def extract(self, path: Path) -> dict[str, Any]:
        import h5py
        out: dict[str, Any] = {
            "access_format": "application/x-hdf5",
            "dataproduct_type": "dynspec",
        }

        with h5py.File(path, "r") as f:
            root = f["/"]

            # LOFAR ICD-3 conventional attributes — try first, fall
            # back to common alternatives.
            obs_id = (
                _attr(root, "OBSERVATION_ID")
                or _attr(root, "obs_id")
                or _attr(root, "OBS_ID")
            )
            if obs_id:
                out["obs_id"] = str(obs_id)

            target = (
                _attr(root, "TARGET")
                or _attr(root, "OBJECT")
                or _attr(root, "target_name")
            )
            if target:
                out["target_name"] = str(target)

            telescop = (
                _attr(root, "TELESCOPE")
                or _attr(root, "FACILITY")
                or _attr(root, "facility_name")
            )
            if telescop:
                out["facility_name"] = str(telescop)

            instr = (
                _attr(root, "INSTRUMENT")
                or _attr(root, "instrument_name")
            )
            if instr:
                out["instrument_name"] = str(instr)

            # Spatial — LOFAR uses ANTENNA_RA / ANTENNA_DEC, others
            # use POINTING_RA / POINTING_DEC, plain RA / DEC, …
            for ra_key, dec_key in (
                ("POINTING_RA", "POINTING_DEC"),
                ("ANTENNA_RA", "ANTENNA_DEC"),
                ("RA", "DEC"),
                ("s_ra", "s_dec"),
            ):
                ra = _attr(root, ra_key)
                dec = _attr(root, dec_key)
                if isinstance(ra, (int, float)) and isinstance(dec, (int, float)):
                    out["s_ra"] = float(ra)
                    out["s_dec"] = float(dec)
                    break

            # Time bounds
            for tmin_key, tmax_key in (
                ("OBSERVATION_START_MJD", "OBSERVATION_END_MJD"),
                ("MJD_START", "MJD_END"),
                ("t_min", "t_max"),
            ):
                t_min = _attr(root, tmin_key)
                t_max = _attr(root, tmax_key)
                if isinstance(t_min, (int, float)):
                    out["t_min"] = float(t_min)
                if isinstance(t_max, (int, float)):
                    out["t_max"] = float(t_max)
                if "t_min" in out or "t_max" in out:
                    break

            # Spectral — most beamformed files store frequency in Hz
            # at root level.
            for fmin_key, fmax_key in (
                ("OBSERVATION_FREQUENCY_MIN", "OBSERVATION_FREQUENCY_MAX"),
                ("FREQ_MIN", "FREQ_MAX"),
            ):
                f_min = _attr(root, fmin_key)
                f_max = _attr(root, fmax_key)
                if isinstance(f_min, (int, float)) and isinstance(f_max, (int, float)):
                    if f_min > 0 and f_max > 0:
                        # Hz → wavelength m, swap order so em_min < em_max.
                        c = 299_792_458.0
                        out["em_min"] = c / float(f_max)
                        out["em_max"] = c / float(f_min)
                    break

        return out
