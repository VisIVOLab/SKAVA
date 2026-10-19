"""A constrained — but genuinely useful — ADQL WHERE parser for the TAP
ObsCore profile.

This lifts the TAP endpoint from "equality on three columns" to a real
ObsTAP-style query surface that VO tools (TOPCAT, pyvo) actually emit:

* **Spatial** — the canonical ObsTAP cone query
  ``1 = CONTAINS(POINT('ICRS', s_ra, s_dec), CIRCLE('ICRS', ra, dec, radius))``
  → a centre-based overlap (the same approximation discovery uses).
* **Range / equality** — comparisons (``= != <> < <= > >=``) on whitelisted
  ObsCore columns. Temporal and spectral filtering fall out of this
  naturally, e.g. ``t_min <= 60000 AND t_max >= 59000`` (time overlap) or
  ``em_min <= 1.4e-6 AND em_max >= 1.3e-6`` (band overlap).

It is deliberately NOT a full ADQL engine: predicates are AND-joined,
``OR`` is rejected, and only the column whitelist below is queryable. That
keeps the surface bounded and production-safe while remaining
spec-recognisable. The parser returns a ``CirclePos`` (or ``None``) plus a
list of SQLAlchemy conditions that ``DiscoveryService.search`` applies
directly — no second filtering implementation.
"""
from __future__ import annotations

import re

from app.errors import InvalidQueryError
from app.models.dataset import Dataset
from app.vo.query_params import CirclePos

# Queryable ObsCore columns. Keeping an explicit whitelist (rather than
# reflecting the model) means an accidental column rename can never silently
# widen the TAP attack surface.
_STRING_COLUMNS = {
    "obs_id",
    "obs_collection",
    "obs_title",
    "dataproduct_type",
    "target_name",
    "facility_name",
    "instrument_name",
    "source_type",
    "source_ref",
    "access_format",
    "spatial_index_cell",
    "doi",
    "pid",
    "license",
}
_NUMERIC_COLUMNS = {
    "calib_level",
    "s_ra",
    "s_dec",
    "s_fov",
    "t_min",
    "t_max",
    "em_min",
    "em_max",
    "access_estsize",
    "spatial_index_order",
}

# ``1 = CONTAINS(...)`` or ``CONTAINS(...) = 1`` cone search. The first
# argument is the dataset's position: either the ObsTAP point built from
# (s_ra, s_dec), or the ObsCore geometry column ``s_pos`` — the form the
# SRCNet architecture uses in its example query,
# ``CONTAINS(obscore.s_pos, CIRCLE('ICRS',202,47,1))=1``. The CIRCLE carries
# the literal centre + radius (degrees). Table qualifiers are stripped first.
_CONTAINS_RE = re.compile(
    r"(?:1\s*=\s*)?CONTAINS\s*\(\s*"
    r"(?:POINT\s*\(\s*'[^']*'\s*,\s*s_ra\s*,\s*s_dec\s*\)|s_pos)\s*,\s*"
    r"CIRCLE\s*\(\s*'[^']*'\s*,\s*"
    r"([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\)\s*\)"
    r"(?:\s*=\s*1)?",
    re.IGNORECASE,
)

_GEOMETRY_TOKENS_RE = re.compile(
    r"\b(CONTAINS|INTERSECTS|POINT|CIRCLE|POLYGON|BOX|REGION)\b", re.IGNORECASE
)

# A single ``col OP value`` predicate. Longest operators first so ``<=`` is
# not split into ``<`` + ``=``.
_TERM_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(<=|>=|<>|!=|=|<|>)\s*(.+?)\s*$"
)


def _apply_op(column, op: str, value):
    if op == "=":
        return column == value
    if op in ("!=", "<>"):
        return column != value
    if op == "<":
        return column < value
    if op == "<=":
        return column <= value
    if op == ">":
        return column > value
    if op == ">=":
        return column >= value
    raise InvalidQueryError(f"Unsupported operator '{op}'")


def _build_condition(col: str, op: str, raw: str):
    column = getattr(Dataset, col)
    if col in _STRING_COLUMNS:
        if len(raw) < 2 or raw[0] != "'" or raw[-1] != "'":
            raise InvalidQueryError(
                f"String column '{col}' requires a single-quoted value")
        return _apply_op(column, op, raw[1:-1])
    # numeric
    try:
        value = float(raw)
    except ValueError as exc:
        raise InvalidQueryError(
            f"Numeric column '{col}' requires a numeric value, got {raw!r}"
        ) from exc
    return _apply_op(column, op, value)


# A table name or alias in front of a column (``obscore.s_ra``,
# ``ivoa.obscore.t_min``, ``o.obs_id``). Only removed where a known column or
# ``s_pos`` follows, so a number such as ``1.4e-6`` is never touched (it does
# not start with a letter) and an unknown column still fails loudly below.
_QUALIFIED_COLUMN_RE = None


def strip_qualifiers(text: str) -> str:
    """``obscore.s_ra`` → ``s_ra``; ``ivoa.obscore.t_min`` → ``t_min``."""
    global _QUALIFIED_COLUMN_RE
    if _QUALIFIED_COLUMN_RE is None:
        names = "|".join(sorted(_STRING_COLUMNS | _NUMERIC_COLUMNS | {"s_pos"}, key=len, reverse=True))
        _QUALIFIED_COLUMN_RE = re.compile(
            rf"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)+(?=(?:{names})\b)", re.IGNORECASE)
    return _QUALIFIED_COLUMN_RE.sub("", text)


def parse_where(where_clause: str) -> tuple[CirclePos | None, list]:
    """Parse an ADQL WHERE clause into (CirclePos|None, [SQLAlchemy conditions]).

    Raises :class:`InvalidQueryError` for anything outside the supported
    subset (OR, unsupported geometry, unknown columns, malformed predicates).
    """
    # Strip ORDER BY / GROUP BY tails — ordering is not part of filtering and
    # SKAVA returns a deterministic obs_id order anyway.
    where_clause = re.split(r"\b(?:ORDER|GROUP)\s+BY\b", where_clause, flags=re.IGNORECASE)[0]
    where_clause = strip_qualifiers(where_clause)

    if re.search(r"\bOR\b", where_clause, re.IGNORECASE):
        raise InvalidQueryError("OR is not supported in the TAP WHERE clause; use AND")

    pos: CirclePos | None = None
    m = _CONTAINS_RE.search(where_clause)
    if m:
        pos = CirclePos(
            ra=float(m.group(1)), dec=float(m.group(2)), radius=float(m.group(3))
        )
        where_clause = where_clause[: m.start()] + where_clause[m.end():]

    # Any geometry token left over means an unsupported spatial construct.
    if _GEOMETRY_TOKENS_RE.search(where_clause):
        raise InvalidQueryError(
            "Unsupported geometry; the only supported spatial predicate is "
            "1 = CONTAINS(POINT('ICRS', s_ra, s_dec), CIRCLE('ICRS', ra, dec, radius))"
        )

    conditions: list = []
    for term in re.split(r"\bAND\b", where_clause, flags=re.IGNORECASE):
        term = term.strip().strip("()").strip()
        if not term:
            continue
        tm = _TERM_RE.match(term)
        if not tm:
            raise InvalidQueryError(f"Unsupported ADQL predicate: {term!r}")
        col = tm.group(1).lower()
        if col not in _STRING_COLUMNS and col not in _NUMERIC_COLUMNS:
            raise InvalidQueryError(f"Unsupported or unknown column in WHERE: '{col}'")
        conditions.append(_build_condition(col, tm.group(2), tm.group(3).strip()))

    return pos, conditions


# Columns surfaced in the TAP_SCHEMA / VOSI tableset and in capabilities.
QUERYABLE_COLUMNS = sorted(_STRING_COLUMNS | _NUMERIC_COLUMNS)
