"""Abstract base class for file-format-specific metadata extractors."""
from __future__ import annotations

import abc
from pathlib import Path
from typing import Any


class Extractor(abc.ABC):
    """Subclass for each supported file format.

    Implementations MUST be cheap to instantiate (no I/O at construction
    time) — the registry creates one instance per format and reuses it
    across the entire scan.
    """

    #: Human-readable label, used in scan output and log lines.
    name: str = "extractor"

    #: Resolution order: lower is tried first, ties by ``name``. An
    #: extractor that recognises its format by content (PSRFITS inside a
    #: ``.fits``) must come before one that matches the extension alone.
    priority: int = 100

    @abc.abstractmethod
    def supports(self, path: Path) -> bool:
        """Return True if this extractor can handle ``path``.

        Implementations should be fast (file-extension match is
        enough); detailed format checks belong in ``extract``.
        """

    @abc.abstractmethod
    def extract(self, path: Path) -> dict[str, Any]:
        """Return a dict of ObsCore-shaped metadata keys.

        Keys that are not applicable to the file should be omitted from
        the dict (not set to None or ""). Caller composes the final
        record by overlaying these with config defaults.

        Recognised keys (see SKAVA's ObsCore model for full reference):
        * ``obs_id`` ``obs_title`` ``obs_collection`` ``dataproduct_type``
        * ``calib_level`` ``target_name`` ``facility_name`` ``instrument_name``
        * ``s_ra`` ``s_dec`` ``s_fov``
        * ``t_min`` ``t_max`` (MJD)
        * ``em_min`` ``em_max`` (metres)
        * ``access_format`` ``access_estsize`` (KB)
        """
