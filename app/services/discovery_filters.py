from sqlalchemy import Select, and_, case, func

from app.models.dataset import Dataset
from app.vo.query_params import CirclePos, NumericInterval


def apply_pos_filter(stmt: Select[tuple[Dataset]], pos: CirclePos | None) -> Select[tuple[Dataset]]:
    if not pos:
        return stmt

    # Approximate overlap using dataset center (s_ra/s_dec) and optional s_fov angular diameter.
    # This is a practical precursor to full region geometry support.
    delta_ra = func.abs(Dataset.s_ra - pos.ra)
    delta_ra_wrapped = case((delta_ra > 180.0, 360.0 - delta_ra), else_=delta_ra)
    delta_dec = func.abs(Dataset.s_dec - pos.dec)
    distance_sq = (delta_ra_wrapped * delta_ra_wrapped) + (delta_dec * delta_dec)

    dataset_radius = func.coalesce(Dataset.s_fov, 0.0) / 2.0
    allowed_radius = pos.radius + dataset_radius
    allowed_sq = allowed_radius * allowed_radius

    return stmt.where(
        and_(
            Dataset.s_ra.is_not(None),
            Dataset.s_dec.is_not(None),
            distance_sq <= allowed_sq,
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

