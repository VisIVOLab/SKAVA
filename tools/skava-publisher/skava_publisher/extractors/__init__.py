"""Plugin registry for file-format-specific metadata extractors.

Each extractor implements ``Extractor`` and is registered as an
entry point in ``[project.entry-points."skava_publisher.extractors"]``
of ``pyproject.toml``. Third-party plugins can register additional
extractors by exposing their own entry points under the same group.

Resolution at scan time:

    for candidate in registered_extractors:   # by priority, then name
        if candidate.supports(path):
            return candidate.extract(path)
    raise NoExtractorFound(path)
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from importlib.metadata import entry_points
from pathlib import Path

from skava_publisher.extractors.base import Extractor

logger = logging.getLogger("skava.publisher.extractors")


def discover() -> list[Extractor]:
    """Instantiate every extractor exposed via entry points.

    The list is ordered by each extractor's ``priority`` (lower first), then
    by entry point name, so the resolution order is deterministic across
    runs and environments and a content-sniffing extractor (PSRFITS) is
    asked before the extension-only one (FITS).
    """
    found: list[tuple[str, Extractor]] = []
    eps: Iterable
    try:
        eps = entry_points(group="skava_publisher.extractors")
    except TypeError:
        # Python < 3.10 fallback (defensive — pyproject requires 3.10+)
        eps = entry_points().get("skava_publisher.extractors", [])  # type: ignore[attr-defined]
    for ep in eps:
        try:
            cls = ep.load()
            inst = cls()
            if not isinstance(inst, Extractor):
                logger.warning(
                    "Extractor entry point %r is not an Extractor subclass; skipping.",
                    ep.name,
                )
                continue
            found.append((ep.name, inst))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load extractor %r: %s", ep.name, exc)
    found.sort(key=lambda item: (getattr(item[1], "priority", 100), item[0]))
    return [inst for (_, inst) in found]


def find_extractor(extractors: list[Extractor], path: Path) -> Extractor | None:
    for ex in extractors:
        if ex.supports(path):
            return ex
    return None
