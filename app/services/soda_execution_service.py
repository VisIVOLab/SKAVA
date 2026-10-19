"""SODA execution by delegation to a node's co-located VisIVO backend.

This is SKAVA's half of "compute next to data". When a dataset's best
node exposes a VisIVO backend (``Node.visivo_backend_url``) and publishes
its replica as a ``file://`` URL, ``/soda/execute`` does NOT move the
file: it asks that backend to compute the cutout in place and streams
back only the (small) result.

Design boundaries:
* SKAVA never reads the science file itself — it has no filesystem
  access to SRC storage. All byte-level work happens on the node.
* When delegation is not possible (node has no backend, or the replica
  is not a ``file://`` URL the backend can open), :meth:`execute`
  returns ``None`` and the caller falls back to the metadata-cache
  staging handoff. This keeps behaviour graceful for catalogue entries
  that predate the distributed-backend rollout.
* A backend that IS reachable but rejects/fails the request surfaces as
  a :class:`BackendExecutionError` (HTTP 502) — a real error, not a
  silent fallback.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import BackendExecutionError
from app.models.node import Node
from app.services.datalink_service import DataLinkService
from app.vo.query_params import CirclePos, NumericInterval
from app.vo.soda import normalize_interval, normalize_pos

logger = logging.getLogger("skava.soda.exec")


@dataclass
class CutoutBytes:
    content: bytes
    media_type: str
    filename: str
    applied: str  # value of the backend's X-Soda-Applied header (e.g. "pos,band")
    node_code: str


class SodaExecutionService:
    """Delegate a SODA cutout to the best node's VisIVO backend, if any."""

    def __init__(self, db: Session):
        self.db = db
        self.datalink_service = DataLinkService(db)

    def execute(
        self,
        *,
        dataset_id: str,
        pos: CirclePos | None,
        band: NumericInterval | None,
        time_value: NumericInterval | None,
        responseformat: str | None,
    ) -> CutoutBytes | None:
        """Run the cutout on the node backend.

        Returns the cutout bytes on success, or ``None`` when delegation
        is not available (no backend / non-file replica) so the caller
        can fall back to the staging handoff. Returns ``None`` for a
        missing dataset too — the caller maps that to 404 as before.
        """
        datalink = self.datalink_service.resolve(dataset_id)
        if not datalink:
            return None

        # The first replica, in ranking order, that a node backend can cut in
        # place: a file:// copy on a node running a co-located VisIVO backend.
        # Same rule DataLink uses to advertise the cutout (soda_cutout_available),
        # so what is advertised is what runs.
        node = None
        access_url = ""
        for rep in datalink.routing.replicas:
            if not (rep.access_endpoint or "").startswith("file://"):
                continue
            candidate = self.db.scalar(select(Node).where(Node.code == rep.code))
            if candidate and candidate.visivo_backend_url:
                node, access_url = candidate, rep.access_endpoint
                break
        if node is None:
            logger.info(
                "soda_exec_no_backend",
                extra={"dataset": dataset_id, "node": datalink.routing.best_node},
            )
            return None

        payload = {
            "obs_id": dataset_id,
            "access_url": access_url,
            "pos": normalize_pos(pos),
            "band": normalize_interval(band),
            "time": normalize_interval(time_value),
            "responseformat": responseformat or "application/fits",
        }
        headers = {}
        if node.visivo_backend_requires_auth and settings.visivo_backend_token:
            headers["X-Visivo-Token"] = settings.visivo_backend_token

        url = node.visivo_backend_url.rstrip("/") + "/v1/datasets/cutout"
        try:
            resp = httpx.post(
                url,
                json=payload,
                headers=headers,
                timeout=settings.soda_backend_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise BackendExecutionError(
                f"VisIVO backend at node '{node.code}' is unreachable: {exc}"
            ) from exc

        if resp.status_code != 200:
            detail = _safe_detail(resp)
            raise BackendExecutionError(
                f"VisIVO backend at node '{node.code}' returned "
                f"HTTP {resp.status_code}: {detail}"
            )

        logger.info(
            "soda_exec_delegated",
            extra={
                "dataset": dataset_id,
                "node": node.code,
                "bytes": len(resp.content),
                "applied": resp.headers.get("X-Soda-Applied", ""),
            },
        )
        return CutoutBytes(
            content=resp.content,
            media_type=resp.headers.get("content-type", "application/fits"),
            filename=_filename_from(resp, dataset_id),
            applied=resp.headers.get("X-Soda-Applied", ""),
            node_code=node.code,
        )


def _safe_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        return str(body.get("detail", body))[:300]
    except Exception:  # noqa: BLE001 — non-JSON error body
        return resp.text[:300]


def _filename_from(resp: httpx.Response, dataset_id: str) -> str:
    disposition = resp.headers.get("content-disposition", "")
    if "filename=" in disposition:
        return disposition.split("filename=", 1)[1].strip().strip('"')
    return f"{dataset_id}_cutout.fits"
