# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""CSV streaming export utilities for the admin UI.

All exports use :class:`StreamingResponse` so a single request can dump
hundreds of thousands of rows without buffering the whole result set in
memory. Each export function yields a single header row followed by one
row per record.

Conventions:

* Dates emitted as RFC 3339 (``2026-06-06T16:42:00+00:00``) so spreadsheets
  pick them up as datetime cells without locale heuristics.
* JSON columns serialised compactly (one line each) — Excel handles them
  as strings, downstream tools can ``json.loads`` them as needed.
* Newlines inside cells use ``\r\n`` per RFC 4180. Quoting is handled by
  :class:`csv.writer` with the default dialect.
"""
from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from typing import Any

from fastapi import Response
from fastapi.responses import StreamingResponse


def _format_value(value: Any) -> str:
    """Render an arbitrary cell value to a CSV-safe string."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        # Treat naive timestamps as UTC so spreadsheets don't shift them.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), default=str)
    return str(value)


def stream_csv(
    *,
    header: list[str],
    rows: Iterable[Iterable[Any]],
    filename: str,
) -> Response:
    """Return a :class:`StreamingResponse` that emits the given CSV.

    Parameters
    ----------
    header
        Column names for the first row.
    rows
        Iterable of iterables; each inner iterable becomes one CSV row.
        Values are converted by :func:`_format_value`.
    filename
        Browser-suggested filename (``Content-Disposition: attachment``).

    The CSV is generated lazily — passing a generator for ``rows`` keeps
    memory flat regardless of result-set size.
    """

    def _generate() -> Iterator[str]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate()
        for row in rows:
            writer.writerow([_format_value(v) for v in row])
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate()

    return StreamingResponse(
        _generate(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Hint browsers/Excel to treat the body as UTF-8 (BOM optional;
            # we omit it because LibreOffice and modern Excel detect UTF-8
            # from the Content-Type already, and a BOM confuses awk/csvkit).
            "Cache-Control": "no-store",
        },
    )
