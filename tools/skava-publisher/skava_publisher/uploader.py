# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""HTTP client for SKAVA's internal ingestion endpoints.

Wraps ``/internal/ingestion/dry-run`` and ``/internal/ingestion/run``
with retries, timeouts and a clear error envelope so the CLI can
distinguish "SKAVA is down" from "your records are malformed".
"""
from __future__ import annotations

import json
import logging
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx

from skava_publisher.config import PublisherConfig

logger = logging.getLogger("skava.publisher.uploader")


class UploadError(RuntimeError):
    """Raised when the SKAVA endpoint returns a non-2xx response."""


def _client(cfg: PublisherConfig) -> httpx.Client:
    return httpx.Client(
        base_url=str(cfg.skava.api_url),
        timeout=httpx.Timeout(cfg.skava.timeout_seconds),
        verify=cfg.skava.verify_tls,
        headers={"X-Internal-Api-Key": cfg.skava.internal_api_key},
    )


def _post_manifest(
    cfg: PublisherConfig,
    *,
    endpoint: str,
    records: list[dict[str, Any]],
    source_ref: str | None,
) -> dict[str, Any]:
    """POST the manifest as a JSON file upload."""
    payload = json.dumps({"records": records}, default=str, ensure_ascii=False)
    files = {
        "file": ("manifest.json", BytesIO(payload.encode("utf-8")),
                  "application/json"),
    }
    data: dict[str, Any] = {"format": "json"}
    if source_ref:
        data["source_ref"] = source_ref
        data["source_type"] = "skava-publisher"

    with _client(cfg) as client:
        try:
            r = client.post(endpoint, data=data, files=files)
        except httpx.HTTPError as exc:
            raise UploadError(f"Network error talking to SKAVA: {exc}") from exc
    if r.status_code >= 400:
        raise UploadError(
            f"SKAVA {endpoint} returned {r.status_code}: {r.text[:600]}"
        )
    try:
        return r.json()
    except json.JSONDecodeError as exc:
        raise UploadError(
            f"SKAVA returned non-JSON ({r.status_code}): {r.text[:600]}"
        ) from exc


def validate(
    cfg: PublisherConfig,
    records: list[dict[str, Any]],
    *,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """POST to /internal/ingestion/dry-run — no writes on SKAVA's side."""
    return _post_manifest(
        cfg, endpoint="/internal/ingestion/dry-run",
        records=records, source_ref=source_ref,
    )


def publish(
    cfg: PublisherConfig,
    records: list[dict[str, Any]],
    *,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """POST to /internal/ingestion/run — real ingestion."""
    return _post_manifest(
        cfg, endpoint="/internal/ingestion/run",
        records=records, source_ref=source_ref,
    )
