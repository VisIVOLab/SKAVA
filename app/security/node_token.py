# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Per-node credentials for the telemetry a node pushes.

A node that reports its own state must be able to speak for itself and for
no other node, and must not hold the catalogue's internal key (which opens
ingestion and the other internal APIs). Its token is therefore derived from
the internal key and the node's code::

    token = HMAC-SHA256(internal_api_key, "skava-node-telemetry:" + code)

The catalogue recomputes it on every report, so nothing is stored, and
changing the internal key revokes every node token at once. Print a node's
token with ``python -m app.security.node_token CODE``.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import sys

from app.config import settings

_CONTEXT = "skava-node-telemetry:"
_HEX64 = re.compile(r"[0-9a-f]{64}")


def node_token(code: str, key: str | None = None) -> str:
    """The telemetry token of node ``code``."""
    secret = key if key is not None else settings.internal_api_key
    if not secret:
        raise RuntimeError("SKAVA_INTERNAL_API_KEY is not configured")
    return hmac.new(secret.encode(), (_CONTEXT + code).encode(), hashlib.sha256).hexdigest()


def verify_node_token(code: str, token: str | None) -> bool:
    # Only a well-formed token reaches the comparison (which refuses non-ASCII text).
    if not token or not settings.internal_api_key or not _HEX64.fullmatch(token):
        return False
    return hmac.compare_digest(node_token(code), token)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m app.security.node_token NODE_CODE", file=sys.stderr)
        return 2
    print(node_token(argv[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
