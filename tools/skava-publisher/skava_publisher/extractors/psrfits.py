"""PSRFITS extractor — pulsar / FRB search and timing files.

PSRFITS is a FITS layout with mandatory ``SUBINT``, ``HISTORY``, and
``PARAM`` extensions. The primary header carries observation-level
metadata distinct from the imaging FITS keys, so we extract them
specifically rather than fall through to the general FITS extractor.

Files with a SUBINT extension are tagged ``dataproduct_type=dynspec``
to distinguish them from imaging cubes.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from skava_publisher.extractors.base import Extractor

logger = logging.getLogger("skava.publisher.psrfits")

_C_M_S = 299_792_458.0


def _opt_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    s = str(value).strip()
    return s or None


def _opt_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        f = float(value)
        if f == f and f not in (float("inf"), float("-inf")):
            return f
    return None


class PsrFitsExtractor(Extractor):
    name = "psrfits"
    # Before the generic FITS extractor: a PSRFITS file is a .fits file too,
    # and supports() below tells it apart by its header.
    priority = 10

    # PSRFITS files keep .fits extension but vary; we detect by checking
    # the FITSTYPE keyword in primary header.

    def supports(self, path: Path) -> bool:
        name = path.name.lower()
        if not (name.endswith(".fits") or name.endswith(".sf")):
            return False
        # Cheap peek at the primary header without fully opening the file.
        try:
            from astropy.io import fits
            with fits.open(path, memmap=True, lazy_load_hdus=True) as hdul:
                ftype = str(hdul[0].header.get("FITSTYPE", "")).upper().strip()
                if "PSRFITS" in ftype:
                    return True
                # No FITSTYPE — does it have a SUBINT extension?
                for hdu in hdul:
                    if str(hdu.header.get("EXTNAME", "")).upper() == "SUBINT":
                        return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("Cannot peek %s as PSRFITS: %s", path, exc)
        return False

    def extract(self, path: Path) -> dict[str, Any]:
        from astropy.io import fits
        out: dict[str, Any] = {
            "access_format": "application/x-psrfits",
            "dataproduct_type": "dynspec",
        }
        with fits.open(path, memmap=True) as hdul:
            primary = hdul[0].header

            obs_id = _opt_str(
                primary.get("OBS_ID")
                or primary.get("OBSID")
                or primary.get("FILEID")
            )
            if obs_id:
                out["obs_id"] = obs_id

            obj = _opt_str(primary.get("SRC_NAME") or primary.get("OBJECT"))
            if obj:
                out["target_name"] = obj

            telescop = _opt_str(primary.get("TELESCOP"))
            if telescop:
                out["facility_name"] = telescop

            instrume = _opt_str(
                primary.get("BACKEND") or primary.get("INSTRUME")
            )
            if instrume:
                out["instrument_name"] = instrume

            # Spatial — PSRFITS uses RA / DEC in HH:MM:SS strings,
            # so try the FITS-standard numeric variants first.
            for ra_key in ("RA", "RA_DEG"):
                ra = _opt_float(primary.get(ra_key))
                if ra is not None:
                    out["s_ra"] = ra
                    break
            for dec_key in ("DEC", "DEC_DEG"):
                dec = _opt_float(primary.get(dec_key))
                if dec is not None:
                    out["s_dec"] = dec
                    break
            # Fallback: parse the sexagesimal strings.
            if "s_ra" not in out:
                ra_str = _opt_str(primary.get("RA"))
                dec_str = _opt_str(primary.get("DEC"))
                if ra_str and dec_str:
                    try:
                        from astropy.coordinates import SkyCoord
                        c = SkyCoord(ra_str, dec_str, unit=("hourangle", "deg"))
                        out["s_ra"] = float(c.ra.deg)
                        out["s_dec"] = float(c.dec.deg)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("RA/DEC sexagesimal parse failed: %s", exc)

            # Time
            stt_mjd = _opt_float(
                primary.get("STT_IMJD") or primary.get("MJD_START")
            )
            stt_smjd = _opt_float(primary.get("STT_SMJD"))
            if stt_mjd is not None:
                start_mjd = stt_mjd + (
                    (stt_smjd / 86400.0) if stt_smjd is not None else 0.0
                )
                out["t_min"] = start_mjd
                # End MJD if recorded.
                end_mjd = _opt_float(primary.get("STP_MJD"))
                if end_mjd is not None:
                    out["t_max"] = end_mjd
                else:
                    # Fall back to start (no duration info).
                    out["t_max"] = start_mjd

            # Spectral — observing band centre + bandwidth.
            obsfreq = _opt_float(primary.get("OBSFREQ"))   # MHz
            obsbw = _opt_float(primary.get("OBSBW"))       # MHz
            if obsfreq is not None and obsfreq > 0:
                if obsbw is not None and obsbw > 0:
                    f_lo_mhz = obsfreq - obsbw / 2.0
                    f_hi_mhz = obsfreq + obsbw / 2.0
                else:
                    f_lo_mhz = f_hi_mhz = obsfreq
                # MHz → Hz → wavelength m
                f_lo_hz = f_lo_mhz * 1e6
                f_hi_hz = f_hi_mhz * 1e6
                out["em_min"] = _C_M_S / f_hi_hz
                out["em_max"] = _C_M_S / f_lo_hz

        return out
