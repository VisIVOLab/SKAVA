#!/usr/bin/env bash
# Register the INAF Power9 node and ingest a sample dataset manifest
# pointing at it. Idempotent — safe to re-run.
#
# Usage:
#   scripts/register_power9_testbed.sh <power9_hostname:port> <obs_id> <access_url>
#
# Example:
#   scripts/register_power9_testbed.sh \
#       pleiadi-gpu.oact.inaf.it:8000 \
#       power9-test-001 \
#       http://pleiadi-gpu.oact.inaf.it:8000/data/test.fits

set -euo pipefail

POWER9_URL="${1:-pleiadi-gpu.oact.inaf.it:8000}"
OBS_ID="${2:-power9-test-001}"
ACCESS_URL="${3:-http://${POWER9_URL}/data/test.fits}"

COMPOSE="docker compose -f docker-compose.local.yml"

echo "[1/4] Upsert Node POWER9 (visivo_backend_url=http://${POWER9_URL})"
$COMPOSE exec -T db psql -U skava -d skava <<EOF
INSERT INTO nodes (code, name, base_url, is_enabled, is_available,
                   latency_score, load_score, capability_score,
                   visivo_backend_url, visivo_backend_requires_auth)
VALUES ('POWER9', 'INAF Power9 (Catania)',
        'http://${POWER9_URL}',
        true, true, 10.0, 0.05, 1.0,
        'http://${POWER9_URL}', true)
ON CONFLICT (code) DO UPDATE SET
    visivo_backend_url = EXCLUDED.visivo_backend_url,
    visivo_backend_requires_auth = EXCLUDED.visivo_backend_requires_auth,
    base_url = EXCLUDED.base_url,
    is_available = true;
EOF

echo "[2/4] Build CSV manifest for ${OBS_ID}"
TMP=$(mktemp /tmp/power9-manifest-XXXX.csv)
cat > "$TMP" <<EOF
obs_id,obs_collection,dataproduct_type,calib_level,target_name,s_ra,s_dec,t_min,t_max,em_min,em_max,access_format,access_estsize,node_id,access_url,is_public
${OBS_ID},inaf-power9,cube,2,Test_Cube,266.4,-29.0,59010.0,59010.5,2.1e-3,2.1e-3,image/fits,4096,POWER9,${ACCESS_URL},true
EOF

echo "[3/4] Ingest manifest via internal API"
KEY=$($COMPOSE exec -T api printenv INTERNAL_API_KEY | tr -d '\r')
if [ -z "$KEY" ]; then
    echo "ERROR: INTERNAL_API_KEY not set in api container env" >&2
    exit 1
fi
curl -fsS -X POST http://localhost:8000/internal/ingestion/run \
    -H "X-Internal-Key: $KEY" \
    -F "file=@${TMP}" -F "format=csv" \
    -F "source_ref=power9-testbed" | python -m json.tool
rm -f "$TMP"

echo "[4/4] Verify visivo-backend descriptor"
curl -fsS "http://localhost:8000/datalink/${OBS_ID}" \
    | python -m json.tool \
    | grep -A 5 '"visivo-backend"' \
    || { echo "WARN: visivo-backend descriptor not found in DataLink response" >&2; exit 1; }

echo
echo "✓ Done. From the desktop client:"
echo "  Settings → Remote Backends → Add:"
echo "    id=src-power9  url=http://${POWER9_URL}  srcCode=POWER9"
echo "  SKAVA tab → search obs_id=${OBS_ID} → Open"
echo "  Status bar badge should turn blue: \"Backend: INAF Power9\""
