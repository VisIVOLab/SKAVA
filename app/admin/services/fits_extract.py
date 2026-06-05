"""Extract ObsCore-shaped metadata from a FITS file's headers.

The admin UI's "Pre-fill from FITS" button uploads a file, this module
parses the primary HDU's header (and the first non-empty image HDU as
a fallback for MEFs that put the science array in HDU 1+) and returns a
``dict[str, value]`` keyed by the form field names that the Datasets
edit form already uses.

Every extraction is best-effort: missing or malformed headers cause
the corresponding field to be omitted from the result rather than
raise. Callers should treat the result as a SUGGESTION and the
operator is expected to review/correct before saving.

Tested patterns:
* SDO/HMI, JWST, HST: standard CRVAL1/CRVAL2 + CDELT
* ALMA / VLA / SARAO cubes: spectral axis as 3rd dimension
* SKA dynamic-spectrum PSRFITS: time on axis 1, freq on axis 2
"""
from __future__ import annotations

import logging
from typing import Any, BinaryIO

logger = logging.getLogger("skava.admin.fits")


# Speed of light in m/s — used to convert RESTFREQ to wavelength.
_C_M_S = 299_792_458.0


def _opt_float(value: Any) -> float | None:
    """Coerce a header value to float if it makes sense, else None.

    FITS headers carry ints, floats, strings, booleans, and BLANK
    sentinels. We accept only numeric scalars; anything else returns
    None so the form field stays empty rather than getting "<UNDEF>".
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        # NaN / inf from corrupt headers — skip silently.
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return f
    return None


def _opt_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    s = str(value).strip()
    return s or None


def _detect_dataproduct_type(header) -> str | None:
    """Heuristic: image (2D) vs cube (3D w/ spectral) vs polarimetric (3-4D w/ STOKES)."""
    naxis = header.get("NAXIS", 0)
    if not isinstance(naxis, int):
        return None
    if naxis == 2:
        return "image"
    # Look for STOKES on any axis — typically axis 3 or 4.
    for ax in range(1, naxis + 1):
        ctype = str(header.get(f"CTYPE{ax}", "")).upper()
        if "STOKES" in ctype:
            return "polarimetric"
    if naxis == 3:
        return "cube"
    if naxis == 4:
        # 4D usually means [pol, freq, y, x] — treat as polarimetric cube.
        return "polarimetric"
    return None


def _extract_spatial(header) -> dict[str, float]:
    """Compute spatial centre + FoV from WCS, falling back to RA/DEC keywords."""
    out: dict[str, float] = {}
    try:
        # WCS parsing is the heavy lift; import lazily so the rest of
        # the SKAVA service (which doesn't need astropy at startup) is
        # not slowed down by it.
        import astropy.units as u  # noqa: F401
        from astropy.wcs import FITSFixedWarning, WCS
        import warnings

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
                scales = wcs.celestial.proj_plane_pixel_scales()  # list of Quantity[deg]
                fov_x = nx * float(scales[0].to_value("deg"))
                fov_y = ny * float(scales[1].to_value("deg"))
                out["s_fov"] = max(fov_x, fov_y)
            except Exception:
                pass
    except Exception as exc:  # noqa: BLE001 — astropy raises a lot of things
        logger.debug("WCS extraction failed, falling back to RA/DEC keywords: %s", exc)

    # Header fallback (some FITS lack a full WCS but carry RA/DEC).
    if "s_ra" not in out:
        ra = _opt_float(header.get("RA"))
        if ra is not None:
            out["s_ra"] = ra
    if "s_dec" not in out:
        dec = _opt_float(header.get("DEC"))
        if dec is not None:
            out["s_dec"] = dec
    return out


def _extract_time(header) -> dict[str, float]:
    """Extract t_min/t_max from MJD-OBS, MJD-END, EXPTIME or DATE-OBS."""
    out: dict[str, float] = {}
    mjd_obs = _opt_float(header.get("MJD-OBS"))
    mjd_end = _opt_float(header.get("MJD-END"))
    exptime = _opt_float(header.get("EXPTIME"))  # seconds

    if mjd_obs is not None:
        out["t_min"] = mjd_obs
        if mjd_end is not None:
            out["t_max"] = mjd_end
        elif exptime is not None:
            out["t_max"] = mjd_obs + exptime / 86400.0
        else:
            out["t_max"] = mjd_obs
        return out

    # DATE-OBS fallback — convert to MJD via astropy.time.
    date_obs = _opt_str(header.get("DATE-OBS"))
    if date_obs:
        try:
            from astropy.time import Time
            t = Time(date_obs, format="isot", scale="utc")
            out["t_min"] = float(t.mjd)
            if exptime is not None:
                out["t_max"] = float(t.mjd) + exptime / 86400.0
            else:
                out["t_max"] = float(t.mjd)
        except Exception as exc:  # noqa: BLE001
            logger.debug("DATE-OBS parse failed: %s", exc)
    return out


def _extract_spectral(header) -> dict[str, float]:
    """em_min / em_max in metres. Reads RESTFREQ + spectral axis bounds."""
    out: dict[str, float] = {}

    # Single-frequency line obs.
    restfreq = _opt_float(header.get("RESTFREQ") or header.get("RESTFRQ"))
    if restfreq is not None and restfreq > 0:
        out["em_min"] = _C_M_S / restfreq
        out["em_max"] = _C_M_S / restfreq

    # Spectral axis bounds: find the FREQ / WAVE axis, compute range.
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
                # If the axis is FREQ → convert to wavelength via c/f.
                if ctype.startswith("FREQ"):
                    lo_m = (_C_M_S / q_hi.to_value("Hz"))
                    hi_m = (_C_M_S / q_lo.to_value("Hz"))
                else:
                    lo_m = q_lo.to_value("m")
                    hi_m = q_hi.to_value("m")
                out["em_min"] = float(min(lo_m, hi_m))
                out["em_max"] = float(max(lo_m, hi_m))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Spectral axis unit conversion failed: %s", exc)
            break  # first match wins
    return out


def _select_primary_header(hdul):
    """Pick the most informative HDU header.

    Primary HDU often has only metadata (NAXIS=0); the actual science
    image lives in ``hdul[1]`` for many MEF files (e.g. JWST, ALMA).
    Walk until we find a header with a non-zero NAXIS, or fall back to
    primary if none.
    """
    for hdu in hdul:
        if hdu.header.get("NAXIS", 0):
            return hdu.header
    return hdul[0].header


def extract_obscore_from_fits(fileobj: BinaryIO) -> dict[str, Any]:
    """Return a dict of extracted form-field values from a FITS bytestream.

    Only non-None values are returned, so the caller can iterate the
    dict and populate empty form fields safely.
    """
    # Lazy import keeps the rest of SKAVA snappy at boot.
    from astropy.io import fits

    with fits.open(fileobj, memmap=False) as hdul:
        header = _select_primary_header(hdul)

        out: dict[str, Any] = {}

        # Direct mappings — keys must match the form input ``name=``.
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

        # Heuristic dataproduct type from NAXIS / STOKES.
        dptype = _detect_dataproduct_type(header)
        if dptype:
            out["dataproduct_type"] = dptype

        # Many archives use BSCALE/BZERO/BITPIX to infer calib level;
        # we don't attempt that and leave calib_level for the operator
        # because the convention varies wildly across surveys.

        out.update(_extract_spatial(header))
        out.update(_extract_time(header))
        out.update(_extract_spectral(header))

        # Sensible defaults the operator can override.
        out.setdefault("access_format", "image/fits")

    return out
