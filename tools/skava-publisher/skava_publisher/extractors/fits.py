# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
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


class _WithPrimary:
    """The data HDU's header, falling back to the primary header for a
    keyword the data HDU does not carry: a multi-extension product (an ESO
    archive cube, say) keeps TELESCOP, INSTRUME, OBJECT, the observation
    dates in the primary HDU and the data with its WCS in an extension.
    Only for descriptive keywords: the WCS is read from the data HDU alone."""

    def __init__(self, data, primary):
        self.data, self.primary = data, primary

    def get(self, key, default=None):
        if key in self.data:
            return self.data.get(key, default)
        if self.primary is not None and key in self.primary:
            return self.primary.get(key, default)
        return default


def _dataproduct_type(header) -> str | None:
    """image, cube or polarimetric, from the axes that have more than one
    pixel: a degenerate Stokes or frequency axis (length 1, common in radio
    images and cubes) does not make a product polarimetric or a cube."""
    naxis = header.get("NAXIS", 0)
    if not isinstance(naxis, int) or naxis < 1:
        return None
    significant = 0
    for ax in range(1, naxis + 1):
        try:
            length = int(header.get(f"NAXIS{ax}", 1) or 1)
        except (TypeError, ValueError):
            length = 1
        if length <= 1:
            continue
        if "STOKES" in str(header.get(f"CTYPE{ax}", "")).upper():
            return "polarimetric"
        significant += 1
    if significant == 2:
        return "image"
    if significant == 3:
        return "cube"
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


def _rest_frequency(header, wcsprm=None) -> float | None:
    """The rest frequency in Hz: RESTFRQ/RESTFREQ, or from RESTWAV/RESTWAVE."""
    if wcsprm is not None:
        if wcsprm.restfrq and wcsprm.restfrq > 0:
            return float(wcsprm.restfrq)
        if wcsprm.restwav and wcsprm.restwav > 0:
            return _C_M_S / float(wcsprm.restwav)
    f = _opt_float(header.get("RESTFRQ") or header.get("RESTFREQ"))
    if f is not None and f > 0:
        return f
    w = _opt_float(header.get("RESTWAV") or header.get("RESTWAVE"))
    return _C_M_S / w if w is not None and w > 0 else None


def _spectral(header) -> dict[str, float]:
    """The ObsCore em_min/em_max (metres) the spectral axis spans.

    WCSLIB, through astropy, interprets the header: CD or PC with CDELT,
    cross terms, and the legacy AIPS conventions (VELO-xxx with VELREF,
    FELO) that it translates to the standard types. The spectral world
    coordinate is evaluated at every corner of the pixel grid and turned
    into wavelengths with the Doppler convention of its type (radio for
    VRAD, optical for VOPT, relativistic for VELO), through the rest
    frequency. Without a spectral axis that can be converted, the rest
    wavelength alone, when the header gives one.
    """
    out: dict[str, float] = {}
    restfreq = _rest_frequency(header)
    if restfreq is not None:
        out["em_min"] = out["em_max"] = _C_M_S / restfreq
    try:
        import itertools
        import warnings

        import numpy as np
        from astropy import units as u
        from astropy.io import fits
        from astropy.wcs import WCS

        hdr = header if isinstance(header, fits.Header) else fits.Header(dict(header))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wcs = WCS(hdr)
        if not wcs.has_spectral:
            return out
        axis = wcs.wcs.spec
        if str(wcs.wcs.ctype[axis]).upper().startswith("AWAV"):
            # ObsCore wants vacuum wavelengths: WCSLIB converts air to vacuum.
            wcs.wcs.sptr("WAVE-???")
        ctype = str(wcs.wcs.ctype[axis]).upper()
        unit = u.Unit(wcs.wcs.cunit[axis] or "")
        restfreq = _rest_frequency(header, wcs.wcs) or restfreq
        # Only the pixel axes the spectral coordinate depends on (the
        # correlation matrix: cross terms included), and only those longer
        # than one pixel, vary between their two ends; the rest stay at 1.
        shape = [max(1, int(hdr.get(f"NAXIS{k + 1}", 1) or 1)) for k in range(wcs.pixel_n_dim)]
        depends = wcs.axis_correlation_matrix[axis]
        ends = [(1.0, float(n)) if depends[k] and n > 1 else (1.0,) for k, n in enumerate(shape)]
        if sum(len(e) > 1 for e in ends) > 8:
            return out              # not a product layout this extractor knows
        corners = np.array(list(itertools.product(*ends)))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            world = wcs.all_pix2world(corners, 1)[:, axis]
        values = world * unit
        kind = ctype[:4]
        if kind in ("FREQ",):
            metres = values.to(u.m, equivalencies=u.spectral())
        elif kind == "WAVE":
            metres = values.to(u.m)
        elif kind in ("VRAD", "VOPT", "VELO", "ZOPT"):
            if restfreq is None:
                return out
            rest = restfreq * u.Hz
            if kind == "ZOPT":
                metres = (_C_M_S / restfreq) * (1 + values.to_value(u.dimensionless_unscaled)) * u.m
            else:
                convention = {"VRAD": u.doppler_radio, "VOPT": u.doppler_optical,
                              "VELO": u.doppler_relativistic}[kind]
                with np.errstate(all="ignore"):
                    metres = values.to(u.m, equivalencies=convention(rest))
        else:
            return out
        metres = np.asarray(metres.to_value(u.m), dtype=float)
        if not np.all(np.isfinite(metres)) or np.any(metres <= 0):
            # Not a wavelength range under the axis's own convention: the
            # header's unit does not match its values (km/s declared, m/s
            # written, say). No band is better than a wrong one.
            logger.warning("spectral axis %s (%s) gives no valid wavelength range; CUNIT is probably "
                           "wrong for its values", ctype, unit)
            return out
        out["em_min"] = float(metres.min())
        out["em_max"] = float(metres.max())
    except Exception as exc:  # noqa: BLE001 - a header WCSLIB cannot read gives no band
        logger.debug("Spectral axis conversion failed: %s", exc)
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
            # Descriptive keywords may live in the primary HDU of a
            # multi-extension file; the WCS-derived fields use ``header``.
            described = _WithPrimary(header, hdul[0].header if header is not hdul[0].header else None)

            obs_id = _opt_str(described.get("OBS_ID") or described.get("OBSID"))
            if obs_id:
                out["obs_id"] = obs_id

            obj = _opt_str(described.get("OBJECT"))
            if obj:
                out["target_name"] = obj

            telescop = _opt_str(described.get("TELESCOP"))
            if telescop:
                out["facility_name"] = telescop

            instrume = _opt_str(described.get("INSTRUME"))
            if instrume:
                out["instrument_name"] = instrume

            dptype = _dataproduct_type(header)
            if dptype:
                out["dataproduct_type"] = dptype

            out.update(_spatial(header))
            out.update(_time(described))
            out.update(_spectral(header))
            out.setdefault("access_format", "image/fits")
        return out
