# Quickstart

End-to-end tour of the SKAVA HTTP surface, taking ~10 minutes. We use
the seed data shipped with a fresh install (three demo nodes A/B/C and
a handful of datasets) — no extra setup needed.

Set a base URL once for the rest of this page:

```bash
export SKAVA=http://localhost:8000
```

## 1. Discovery — list datasets

The `/discovery/search` endpoint accepts the same ObsCore-like fields
that TAP exposes. Without filters it returns the most-recent N
datasets:

```bash
curl -s "$SKAVA/discovery/search?limit=3" | jq '.results[] | .metadata.obs_id'
```

Common filters:

```bash
# All "image" datasets
curl -s "$SKAVA/discovery/search?dataproduct_type=image&limit=10" \
    | jq '.results[].metadata | {obs_id, target_name, s_ra, s_dec}'

# Spatial cone search (degrees)
curl -s "$SKAVA/discovery/search?ra=83.6&dec=22.0&radius=0.5" \
    | jq '.total'

# Combine
curl -s "$SKAVA/discovery/search?obs_collection=mac-tmp-download&em_min_max=2e-3"
```

The full parameter list is in the [discovery reference](../api/discovery).

## 2. DataLink — resolve a single dataset

Pick an `obs_id` from step 1 and ask for the DataLink envelope:

```bash
OBS=$(curl -s "$SKAVA/discovery/search?limit=1" | jq -r '.results[0].metadata.obs_id')
curl -s "$SKAVA/datalink/$OBS" | jq
```

You get back:

* `dataset` — the ObsCore metadata
* `routing.replicas[]` — every node that hosts a copy, ranked
* `primary_access` — the chosen replica's URL, format, estimated size
* `links[]` — IVOA DataLink-style links (`#this`, `preview`, `metadata`, …)
* `service_descriptors[]` — including the **visivo-backend** descriptor
  when the best-ranked node has a co-located VisIVO backend
* `capabilities` — quick boolean flags for clients

The `service_descriptors` is what the VisIVO desktop client looks at
to decide whether to route compute next to the data. See
[Backend routing](../client-integration/backend-routing) for details.

## 3. Internal ingestion — add a dataset

```{warning}
The `/internal/*` endpoints are not public. They require the
`X-Internal-Api-Key` header and are intended for trusted services
(the publisher CLI, the admin UI's CSV upload, automated pipelines).
```

Set the key in your shell:

```bash
export INTERNAL_KEY=<the one you put in docker-compose.yml>
```

Build a tiny manifest:

```bash
cat > /tmp/manifest.csv <<'EOF'
obs_id,obs_collection,dataproduct_type,calib_level,target_name,s_ra,s_dec,t_min,t_max,em_min,em_max,access_format,access_estsize,node_id,access_url,is_public
quickstart-001,quickstart,image,2,Crab,83.6331,22.0145,59010.0,59010.5,2.1e-3,2.1e-3,image/fits,4096,A,http://example.org/data/crab.fits,true
EOF
```

Dry-run first:

```bash
curl -fsS -X POST "$SKAVA/internal/ingestion/dry-run" \
    -H "X-Internal-Api-Key: $INTERNAL_KEY" \
    -F "file=@/tmp/manifest.csv" \
    -F "format=csv" \
    -F "source_ref=quickstart" \
    | jq '.summary'
```

If the dry-run looks fine, commit it:

```bash
curl -fsS -X POST "$SKAVA/internal/ingestion/run" \
    -H "X-Internal-Api-Key: $INTERNAL_KEY" \
    -F "file=@/tmp/manifest.csv" \
    -F "format=csv" \
    -F "source_ref=quickstart" \
    | jq '.summary'
```

And verify:

```bash
curl -s "$SKAVA/discovery/search?obs_collection=quickstart" \
    | jq '.results[].metadata'
```

## 4. SODA — request a cutout

```{note}
`/soda/sync` validates and routes (JSON). `/soda/execute` performs a real
byte-level cutout when the dataset's node has a co-located VisIVO backend
serving a `file://` replica, streaming `application/fits` back; otherwise
it returns a staging-handoff JSON. See [SODA execution](../soda_execution).
```

```bash
# Validate + route
curl -s "$SKAVA/soda/sync?ID=$OBS&POS=CIRCLE%2083.6%2022.0%200.1" | jq

# Execute (real cutout when a co-located backend is available)
curl -s -X POST "$SKAVA/soda/execute?ID=$OBS&POS=CIRCLE%2083.6%2022.0%200.1" -o cutout.fits
```

## 5. TAP — ObsCore queries

```bash
curl -s "$SKAVA/tap/sync?LANG=ADQL&QUERY=SELECT+TOP+10+obs_id,target_name+FROM+ivoa.ObsCore" \
    | head -30
```

Returns a VOTable. See the [TAP reference](../api/tap) for the
supported subset of ADQL.

## 6. Admin UI

Open <http://localhost:8000/admin/> in your browser and sign in with
the bootstrap admin you created in [Installation](installation).

From the dashboard:

* **Nodes** — add the `POWER9` node from the SRC testbed
* **Datasets** — browse + edit individual entries; pre-fill a new
  dataset from a FITS upload (small files only — bulk uploads go via
  the publisher)
* **Audit** *(Phase 3)* — who-changed-what timeline

The full UI tour lives in [Admin UI / overview](../admin-ui/overview).

## Where to next

* Set up the publisher CLI on the node where your data physically
  lives → [skava-publisher / overview](../publisher/overview).
* Integrate the VisIVO desktop client →
  [client-integration / visivo-desktop](../client-integration/visivo-desktop).
* Plan a production deployment with proper TLS, secrets and backups →
  [deployment / production](../deployment/production).
