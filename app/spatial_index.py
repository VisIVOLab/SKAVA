DEFAULT_SPATIAL_ORDER = 8


def compute_spatial_cell(ra: float | None, dec: float | None, order: int = DEFAULT_SPATIAL_ORDER) -> str | None:
    """Deterministic sky cell used as a lightweight HEALPix/MOC-ready index key.

    The current implementation intentionally avoids an external HEALPix dependency.
    It provides stable equal-angle bins that can be backfilled or replaced by true
    HEALPix/MOC identifiers without changing API contracts.
    """
    if ra is None or dec is None:
        return None

    clamped_ra = min(max(ra, 0.0), 360.0)
    clamped_dec = min(max(dec, -90.0), 90.0)
    bins = 2**order
    ra_bin = min(int((clamped_ra / 360.0) * bins * 2), (bins * 2) - 1)
    dec_bin = min(int(((clamped_dec + 90.0) / 180.0) * bins), bins - 1)
    return f"order{order}:ra{ra_bin}:dec{dec_bin}"
