# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Filesystem scanner — walks configured roots, applies include/exclude.

Returns a stream of ``(absolute_path, relative_path)`` tuples ordered
by depth-first traversal. Symlinks are NOT followed unless
``follow_symlinks=True`` in the config (default false — avoids loops
and cross-mount surprises).
"""
from __future__ import annotations

import fnmatch
import logging
from collections.abc import Iterator
from pathlib import Path

from skava_publisher.config import ScanConfig

logger = logging.getLogger("skava.publisher.scanner")


def _matches_any(name_or_path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name_or_path, p) for p in patterns)


def walk(scan: ScanConfig) -> Iterator[tuple[Path, Path]]:
    """Yield ``(abs_path, rel_path)`` for every file passing the filter.

    ``rel_path`` is relative to the root that contained the file. When
    multiple roots are configured, each file's rel_path is computed
    against its own root so the ``{relpath}`` URL substitution works
    consistently regardless of which root the file came from.
    """
    for root in scan.roots:
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            logger.warning("Scan root does not exist or is not a dir: %s", root)
            continue
        yield from _walk_root(root, scan)


def _walk_root(root: Path, scan: ScanConfig) -> Iterator[tuple[Path, Path]]:
    # Use Path.rglob with iterdir for symlink control. We do a manual
    # stack-based walk to honour ``follow_symlinks`` properly.
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except (PermissionError, FileNotFoundError) as exc:
            logger.warning("Cannot list %s: %s", current, exc)
            continue
        for entry in entries:
            try:
                if entry.is_symlink() and not scan.follow_symlinks:
                    continue
                if entry.is_dir():
                    stack.append(entry)
                    continue
                if not entry.is_file():
                    continue
                rel = entry.relative_to(root)
                rel_posix = rel.as_posix()
                # Excludes are matched against the full relative path
                # so patterns like ``**/tmp/**`` work the way operators
                # expect them to.
                if scan.exclude and _matches_any(rel_posix, scan.exclude):
                    continue
                # Includes are matched against the bare filename so
                # ``*.fits`` does not need to be ``**/*.fits``.
                if scan.include and not _matches_any(entry.name, scan.include):
                    continue
                yield entry, rel
            except OSError as exc:
                logger.warning("Skipping %s: %s", entry, exc)
