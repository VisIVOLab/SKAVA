#!/usr/bin/env bash
# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
#
# Register (or update) a node with a co-located VisIVO backend in the SKAVA
# catalogue run by docker-compose.yml. Idempotent. The node's datasets are
# then published with skava-publisher, not by this script.
#
# Usage:
#   scripts/register_node.sh <CODE> "<name>" <backend-url-as-SKAVA-reaches-it> [requires-token: true|false]
#
# Example:
#   scripts/register_node.sh PLEIADI-GPU "INAF PLEIADI-GPU (Catania)" http://host.docker.internal:18900 true

set -euo pipefail

CODE="${1:?usage: register_node.sh <CODE> <name> <backend-url> [requires-token]}"
NAME="${2:?missing the node name}"
URL="${3:?missing the backend URL}"
AUTH="${4:-true}"
case "$CODE" in *[!A-Za-z0-9_-]*) echo "CODE may contain letters, digits, - and _ only" >&2; exit 2;; esac
case "$AUTH" in true|false) ;; *) echo "requires-token must be true or false" >&2; exit 2;; esac
case "$URL" in http://*|https://*) ;; *) echo "the backend URL must be http(s)" >&2; exit 2;; esac
esc() { printf '%s' "$1" | sed "s/'/''/g"; }

COMPOSE="docker compose -f ${SKAVA_COMPOSE_FILE:-docker-compose.yml}"
$COMPOSE exec -T db psql -v ON_ERROR_STOP=1 -U skava -d skava <<EOF
INSERT INTO nodes (code, name, base_url, is_enabled, is_available,
                   latency_score, load_score, capability_score,
                   visivo_backend_url, visivo_backend_requires_auth)
VALUES ('$(esc "$CODE")', '$(esc "$NAME")', '$(esc "$URL")', true, true, 10.0, 0.1, 1.0,
        '$(esc "$URL")', $AUTH)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    base_url = EXCLUDED.base_url,
    visivo_backend_url = EXCLUDED.visivo_backend_url,
    visivo_backend_requires_auth = EXCLUDED.visivo_backend_requires_auth,
    is_enabled = true,
    is_available = true;
EOF
echo "Node $CODE registered with backend $URL (token required: $AUTH)."
