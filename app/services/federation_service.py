"""Federated discovery: the local catalogue and the configured sibling SKAVA
instances, asked together and merged.

Each sibling is asked its own ``/discovery/search`` with the caller's query
and the caller's bearer token: SRCNet's IAM is one, so a token the local
instance accepted is valid at a sibling (a static token is forwarded the same
way). The answers are merged on the logical dataset identity, ``obs_id``:
the local catalogue's entry comes first; a sibling's entry for a dataset
already listed adds that sibling as another place the dataset is at
(``also_at``), with the sibling's own best node and access URL. The ranking
stays each site's own: a site ranks the replicas it holds with the telemetry
it has, and the merged answer does not re-rank across sites. A sibling that
fails, times out or refuses the token is reported in ``sources`` and does
not fail the search.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import httpx
from pydantic import ValidationError

from app.config import settings
from app.schemas.discovery import DiscoverySearchResponse
from app.schemas.federation import AlsoAt, FederatedResult, FederatedSearchResponse, FederationSource

logger = logging.getLogger("skava.federation")

LOCAL = "local"
_MAX_WORKERS = 8


def _client() -> httpx.Client:
    """The HTTP client of one fan-out (tests replace it)."""
    return httpx.Client(timeout=settings.federation_timeout_seconds)


class FederationService:
    def __init__(self, token: str | None = None, sources: list[str] | None = None) -> None:
        self._token = token
        self._sources = settings.federated_sources if sources is None else sources

    def sources(self) -> list[dict[str, Any]]:
        return [{"base_url": url, "status": "configured"} for url in self._sources]

    def search(self, params: dict[str, Any], limit: int,
               local: Callable[[], DiscoverySearchResponse] | None = None) -> FederatedSearchResponse:
        """``params`` are the query as the caller sent it (forwarded verbatim
        to the siblings); ``local`` answers it from this instance's catalogue."""
        query = {key: value for key, value in params.items() if value is not None}
        query["limit"] = limit

        answers: list[tuple[str, FederationSource, list]] = []
        if local is not None:
            started = time.perf_counter()
            mine = local()
            answers.append((LOCAL, FederationSource(
                base_url=settings.public_base_url or LOCAL, status="local", returned=mine.returned,
                total=mine.total, elapsed_ms=round((time.perf_counter() - started) * 1000, 2)), mine.results))

        if self._sources:
            with _client() as http, ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(self._sources))) as pool:
                answers.extend(pool.map(lambda url: self._ask(http, url, query), self._sources))

        merged: dict[str, FederatedResult] = {}
        order: list[str] = []
        duplicates = 0
        for name, _source, results in answers:
            for result in results:
                key = result.metadata.obs_id
                if key in merged:
                    duplicates += 1
                    merged[key].also_at.append(AlsoAt(source=name, best_node=result.best_node,
                                                      access_url=result.access_url,
                                                      replicas=len(result.replicas)))
                else:
                    merged[key] = FederatedResult(**result.model_dump(), source=name)
                    order.append(key)
        results = [merged[key] for key in order[:limit]]
        return FederatedSearchResponse(results=results, returned=len(results), limit=limit,
                                       sources=[source for _n, source, _r in answers],
                                       duplicates_merged=duplicates)

    def _ask(self, http: httpx.Client, url: str, query: dict[str, Any]) -> tuple[str, FederationSource, list]:
        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        started = time.perf_counter()

        def failed(status: str, error: str) -> tuple[str, FederationSource, list]:
            logger.warning("[federation] %s: %s (%s)", url, error, status)
            return url, FederationSource(base_url=url, status=status, error=error,
                                         elapsed_ms=round((time.perf_counter() - started) * 1000, 2)), []

        try:
            # A sibling's own catalogue only: /discovery/search never fans out
            # again, so two instances that list each other cannot loop.
            response = http.get(f"{url}/discovery/search", params=query, headers=headers)
        except httpx.TimeoutException:
            return failed("timeout", f"no answer within {settings.federation_timeout_seconds:g} s")
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            # InvalidURL (a misconfigured sibling) is not an HTTPError.
            return failed("error", str(exc) or exc.__class__.__name__)
        if response.status_code in (401, 403):
            return failed("unauthorized", f"HTTP {response.status_code}")
        if response.status_code != 200:
            return failed("error", f"HTTP {response.status_code}")
        try:
            answer = DiscoverySearchResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            return failed("error", f"malformed answer: {str(exc)[:200]}")
        return url, FederationSource(base_url=url, status="ok", returned=answer.returned, total=answer.total,
                                     elapsed_ms=round((time.perf_counter() - started) * 1000, 2)), answer.results
