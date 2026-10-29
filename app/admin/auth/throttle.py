# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Failed-login throttle for the admin UI.

Counts failed sign-ins per client address over a sliding minute; once a
client reaches ``ADMIN_LOGIN_RATE_LIMIT_PER_MINUTE`` failures its further
attempts are refused (HTTP 429) without the password being checked, until
the oldest failure leaves the window. A successful sign-in clears the
client's count. 0 or less disables the throttle.

The state lives in the process: each replica of the service throttles on
its own, which bounds a brute force per replica. The client address is the
one the ASGI server reports (behind a proxy, configure the server to take
it from the forwarded headers).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

WINDOW_SECONDS = 60.0

_lock = threading.Lock()
_failures: dict[str, deque[float]] = defaultdict(deque)
_last_sweep = float("-inf")


def _prune(stamps: deque[float], now: float) -> None:
    while stamps and now - stamps[0] >= WINDOW_SECONDS:
        stamps.popleft()


def _sweep(now: float) -> None:
    """Drop the clients whose failures have all left the window, at most once
    per window, so addresses that never come back do not accumulate. Called
    with the lock held."""
    global _last_sweep
    if now - _last_sweep < WINDOW_SECONDS:
        return
    _last_sweep = now
    for client in [c for c, stamps in _failures.items()
                   if not stamps or now - stamps[-1] >= WINDOW_SECONDS]:
        del _failures[client]


def retry_after(client: str, limit: int, *, now: float | None = None) -> int:
    """Seconds until ``client`` may try again; 0 when it may try now."""
    if limit <= 0:
        return 0
    now = time.monotonic() if now is None else now
    with _lock:
        _sweep(now)
        stamps = _failures.get(client)
        if not stamps:
            return 0
        _prune(stamps, now)
        if len(stamps) < limit:
            if not stamps:
                _failures.pop(client, None)
            return 0
        return max(1, int(WINDOW_SECONDS - (now - stamps[0])) + 1)


def record_failure(client: str, *, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    with _lock:
        _sweep(now)
        stamps = _failures[client]
        _prune(stamps, now)
        stamps.append(now)


def record_success(client: str) -> None:
    with _lock:
        _failures.pop(client, None)


def reset() -> None:
    """Forget every client (tests)."""
    global _last_sweep
    with _lock:
        _failures.clear()
        _last_sweep = float("-inf")
