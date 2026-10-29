# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
import math
from sqlalchemy import Select, and_, func, or_

from app.models.dataset import Dataset
from app.vo.query_params import CirclePos, NumericInterval


def apply_pos_filter(stmt: Select[tuple[Dataset]], pos: CirclePos | None, *,
                     footprint: bool = True) -> Select[tuple[Dataset]]:
    """Datasets matching a cone, with one of two predicates.

    ``footprint=True`` (the discovery API's ``POS``, as SIA and ObsCore read
    a position constraint): the cone intersects the dataset's footprint,
    taken as a circle of radius ``s_fov/2`` around its centre, an
    approximation of the footprint ``s_region`` would describe exactly.
    ``footprint=False`` (ADQL ``CONTAINS(POINT(s_ra, s_dec), CIRCLE(...))``):
    the dataset's centre lies inside the cone.
    """
    if not pos:
        return stmt

    # Footprint: overlap between the query circle and a circle of radius
    # s_fov/2 around the dataset's centre (s_ra, s_dec); centre: radius 0. The
    # spherical distance between the centres is at most the sum of the radii.
    # In haversine form, stable for small angles (a dataset at the centre of
    # a tiny cone is found), at the poles and across RA 0/360 alike:
    #   sin^2(dDec/2) + cos d1 cos d2 sin^2(dRA/2) <= sin^2((r + s_fov/2)/2)
    # A sum of radii of 180 deg or more covers the sky. A full scan with this
    # predicate; the sky-cell key is a separate filter (SPATIAL_CELL).
    cos_dq = math.cos(math.radians(pos.dec))
    half_ddec = func.sin(func.radians(Dataset.s_dec - pos.dec) / 2.0)
    half_dra = func.sin(func.radians(Dataset.s_ra - pos.ra) / 2.0)
    hav_sep = half_ddec * half_ddec + cos_dq * func.cos(func.radians(Dataset.s_dec)) * half_dra * half_dra
    allowed = (pos.radius + func.coalesce(Dataset.s_fov, 0.0) / 2.0) if footprint else pos.radius
    half_allowed = func.sin(func.radians(allowed) / 2.0)

    return stmt.where(
        and_(
            Dataset.s_ra.is_not(None),
            Dataset.s_dec.is_not(None),
            or_(allowed >= 180.0, hav_sep <= half_allowed * half_allowed),
        )
    )


def apply_band_filter(stmt: Select[tuple[Dataset]], band: NumericInterval | None) -> Select[tuple[Dataset]]:
    if not band:
        return stmt
    return stmt.where(
        and_(
            Dataset.em_min.is_not(None),
            Dataset.em_max.is_not(None),
            Dataset.em_min <= band.max_value,
            Dataset.em_max >= band.min_value,
        )
    )


def apply_time_filter(stmt: Select[tuple[Dataset]], time_value: NumericInterval | None) -> Select[tuple[Dataset]]:
    if not time_value:
        return stmt
    return stmt.where(
        and_(
            Dataset.t_min.is_not(None),
            Dataset.t_max.is_not(None),
            Dataset.t_min <= time_value.max_value,
            Dataset.t_max >= time_value.min_value,
        )
    )

