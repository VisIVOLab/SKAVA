"""FITS extractor — reads the primary HDU header (or first non-empty HDU).

Mirrors the logic of ``app/admin/services/fits_extract.py`` on the
SKAVA side but adapted to operate on a filesystem path directly (no
file upload). Heuristics for spatial / time / spectral fields handle
the standard surveys (JWST, HST, ALMA, ASKAP, VLA, SARAO) without
per-survey special-casing.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from skava_publisher.extractors.base import Extractor

logger = logging.getLogger("skava.publisher.fits")

_C_M_S = 299_792_458.0


def _opt_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return f
    return None


def _opt_str(value: Any) -> str | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    s = str(value).strip()
    return s or None


def _select_primary_header(hdul):
    """Pick the first HDU whose NAXIS > 0 (skips the empty primary in MEFs)."""
    for hdu in hdul:
        if hdu.header.get("NAXIS", 0):
            return hdu.header
    return hdul[0].header


def _dataproduct_type(header) -> str | None:
    naxis = header.get("NAXIS", 0)
    if not isinstance(naxis, int):
        return None
    for ax in range(1, naxis + 1):
        ctype = str(header.get(f"CTYPE{ax}", "")).upper()
        if "STOKES" in ctype:
            return "polarimetric"
    if naxis == 2:
        return "image"
    if naxis == 3:
        return "cube"
    if naxis == 4:
        return "polarimetric"
    return None


def _spatial(header) -> dict[str, float]:
    out: dict[str, float] = {}
    try:
        import warnings
        from astropy.wcs import FITSFixedWarning, WCS
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FITSFixedWarning)
            wcs = WCS(header)
        if wcs.has_celestial:
            nx = int(header.get("NAXIS1", 1) or 1)
            ny = int(header.get("NAXIS2", 1) or 1)
            sky = wcs.celestial.pixel_to_world(nx / 2.0, ny / 2.0)
            out["s_ra"] = float(sky.ra.deg)
            out["s_dec"] = float(sky.dec.deg)
            try:
                scales = wcs.celestial.proj_plane_pixel_scales()
                fov_x = nx * float(scales[0].to_value("deg"))
                fov_y = ny * float(scales[1].to_value("deg"))
                out["s_fov"] = max(fov_x, fov_y)
            except Exception:
                pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("WCS extraction failed: %s", exc)
    if "s_ra" not in out:
        ra = _opt_float(header.get("RA"))
        if ra is not None:
            out["s_ra"] = ra
    if "s_dec" not in out:
        dec = _opt_float(header.get("DEC"))
        if dec is not None:
            out["s_dec"] = dec
    return out


def _time(header) -> dict[str, float]:
    out: dict[str, float] = {}
    mjd_obs = _opt_float(header.get("MJD-OBS"))
    mjd_end = _opt_float(header.get("MJD-END"))
    exptime = _opt_float(header.get("EXPTIME"))
    if mjd_obs is not None:
        out["t_min"] = mjd_obs
        out["t_max"] = (
            mjd_end if mjd_end is not None
            else (mjd_obs + exptime / 86400.0 if exptime is not None else mjd_obs)
        )
        return out
    date_obs = _opt_str(header.get("DATE-OBS"))
    if date_obs:
        try:
            from astropy.time import Time
            t = Time(date_obs, format="isot", scale="utc")
            out["t_min"] = float(t.mjd)
            out["t_max"] = (
                float(t.mjd) + exptime / 86400.0
                if exptime is not None else float(t.mjd)
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("DATE-OBS parse failed: %s", exc)
    return out


def _spectral(header) -> dict[str, float]:
    out: dict[str, float] = {}
    restfreq = _opt_float(header.get("RESTFREQ") or header.get("RESTFRQ"))
    if restfreq is not None and restfreq > 0:
        wave = _C_M_S / restfreq
        out["em_min"] = wave
        out["em_max"] = wave
    naxis = header.get("NAXIS", 0) or 0
    for ax in range(1, int(naxis) + 1):
        ctype = str(header.get(f"CTYPE{ax}", "")).upper()
        if ctype.startswith(("FREQ", "WAVE", "VOPT", "VRAD")):
            n = _opt_float(header.get(f"NAXIS{ax}"))
            crval = _opt_float(header.get(f"CRVAL{ax}"))
            cdelt = _opt_float(header.get(f"CDELT{ax}"))
            crpix = _opt_float(header.get(f"CRPIX{ax}"))
            if None in (n, crval, cdelt, crpix):
                continue
            v_lo = crval + (1 - crpix) * cdelt
            v_hi = crval + (n - crpix) * cdelt
            if v_lo > v_hi:
                v_lo, v_hi = v_hi, v_lo
            cunit = str(header.get(f"CUNIT{ax}", "")).strip()
            try:
                from astropy import units as u
                q_lo = v_lo * u.Unit(cunit or "Hz")
                q_hi = v_hi * u.Unit(cunit or "Hz")
                if ctype.startswith("FREQ"):
                    lo_m = _C_M_S / q_hi.to_value("Hz")
                    hi_m = _C_M_S / q_lo.to_value("Hz")
                else:
                    lo_m = q_lo.to_value("m")
                    hi_m = q_hi.to_value("m")
                out["em_min"] = float(min(lo_m, hi_m))
                out["em_max"] = float(max(lo_m, hi_m))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Spectral axis conversion failed: %s", exc)
            break
    return out


class FitsExtractor(Extractor):
    name = "fits"

    _SUFFIXES = (".fits", ".fit", ".fts", ".fits.gz", ".fits.fz")

    def supports(self, path: Path) -> bool:
        name = path.name.lower()
        return any(name.endswith(s) for s in self._SUFFIXES)

    def extract(self, path: Path) -> dict[str, Any]:
        from astropy.io import fits
        out: dict[str, Any] = {}
        with fits.open(path, memmap=True) as hdul:
            header = _select_primary_header(hdul)

            obs_id = _opt_str(header.get("OBS_ID") or header.get("OBSID"))
            if obs_id:
                out["obs_id"] = obs_id

            obj = _opt_str(header.get("OBJECT"))
            if obj:
                out["target_name"] = obj

            telescop = _opt_str(header.get("TELESCOP"))
            if telescop:
                out["facility_name"] = telescop

            instrume = _opt_str(header.get("INSTRUME"))
            if instrume:
                out["instrument_name"] = instrume

            dptype = _dataproduct_type(header)
            if dptype:
                out["dataproduct_type"] = dptype

            out.update(_spatial(header))
            out.update(_time(header))
            out.update(_spectral(header))
            out.setdefault("access_format", "image/fits")
        return out
