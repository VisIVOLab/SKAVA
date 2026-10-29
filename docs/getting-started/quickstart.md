# Quickstart

End-to-end tour of the SKAVA HTTP surface, taking ~10 minutes. We use
the seed data shipped with a fresh install (three demo nodes `A`, `B`,
`C` and seven demo images, `dataset-1` … `dataset-7`, in collection
`skava-demo`) — no extra setup needed. The seed nodes have no
co-located VisIVO backend, so the compute-next-to-data paths below
answer with their fallbacks; the [testbed](../development/testbed.md)
(four VisIVO backend nodes, a second catalogue, an IAM and a broker
stand-in) shows them working.

Set a base URL once for the rest of this page:

```bash
export SKAVA=http://localhost:8000
```

## 1. Discovery — list datasets

The `/discovery/search` endpoint takes IVOA-style parameters (`POS`,
`BAND`, `TIME`, `COLLECTION`, `DPTYPE`, `SPATIAL_CELL`, `obs_id`) plus
`limit` (default 100, max 1000) and `offset`. Without filters it pages
through the whole catalogue, ordered by `obs_id`:

```bash
curl -s "$SKAVA/discovery/search?limit=3" | jq '.results[] | .metadata.obs_id'
```

Common filters:

```bash
# All "image" datasets
curl -s "$SKAVA/discovery/search?DPTYPE=image&limit=10" \
    | jq '.results[].metadata | {obs_id, target_name, s_ra, s_dec}'

# Spatial cone search: CIRCLE <ra> <dec> <radius>, degrees
curl -s "$SKAVA/discovery/search?POS=CIRCLE%20101%20-21%200.5" \
    | jq '.total'

# Combine: a collection and a wavelength interval (metres)
curl -s "$SKAVA/discovery/search?COLLECTION=skava-demo&BAND=1.0e-6%202.0e-6"
```

Each result carries its `replicas`, ranked best first, the `best_node`
and an `access_url`. Every replica has a `rank_reason` (why the policy
put it there) and, under the resource-aware policy, a `score` (a cost,
lower is better) and the age of the telemetry it was ranked on.

The full parameter list is in the [discovery reference](../api/discovery.md).

## 2. DataLink — resolve a single dataset

Pick an `obs_id` from step 1 and ask for the DataLink envelope:

```bash
OBS=$(curl -s "$SKAVA/discovery/search?limit=1" | jq -r '.results[0].metadata.obs_id')
curl -s "$SKAVA/datalink/$OBS" | jq
```

You get back:

* `dataset` — `obs_id`, collection and product type
* `routing` — `best_node`, the ranking `policy` (`static` or
  `resource_aware`), `replicas[]` ranked best first (each with
  `rank_reason` and `score`) and `excluded[]`, the replicas set aside
  with the reason (node disabled, backend unreachable at the last
  probe, not enough memory, …)
* `primary_access` — the chosen replica's URL, format, estimated size
* `links[]` — DataLink-style links by `rel` (`self`, `direct-download`,
  `alternate-replica`, `soda-sync`, …)
* `service_descriptors[]` — SKAVA's own services, one **visivo-backend**
  descriptor per ranked node with a co-located VisIVO backend (best
  first), and, when a node holds a `file://` replica it can process in
  place, that node's services: `node-soda-sync`, `node-soda-async`
  (UWS) and, for cubes, `visivo-moment` and `visivo-pv`
* `capabilities` — quick boolean flags for clients

The `service_descriptors` is what the VisIVO Visual Analytics desktop
client looks at to decide whether to route compute next to the data.
See [Backend routing](../client-integration/backend-routing.md) for
details. VO clients (pyvo, TOPCAT) ask for the same answer as a
DataLink VOTable:

```bash
curl -s "$SKAVA/datalink/$OBS?RESPONSEFORMAT=votable" | head -20
```

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
curl -s "$SKAVA/discovery/search?COLLECTION=quickstart" \
    | jq '.results[].metadata'
```

## 4. SODA — request a cutout

```{note}
When a node can process the dataset in place (a `file://` replica on a
node with a co-located VisIVO backend), `/soda/sync` answers
**303 See Other** with the node's own SODA service and the replica's ID
filled in: the node cuts the file and SKAVA never handles the bytes.
The node also runs asynchronous UWS jobs (`OPERATION=CUTOUT`, `MOMENT`,
`PV`) at its `/soda/async`. Otherwise `/soda/sync` validates the
request and answers with the routing as JSON. `/soda/execute` is a
non-standard POST proxy: it has the node compute the cutout and streams
the `application/fits` back, or returns a staging-handoff JSON when no
node can. See the [SODA API](../api/soda.md).
```

```bash
# On the seed data: validation + routing JSON (no node can cut in place)
curl -s "$SKAVA/soda/sync?ID=$OBS&POS=CIRCLE%20101%20-21%200.1" | jq

# Where a node can: follow the redirect to the node's SODA service
curl -sL "$SKAVA/soda/sync?ID=$OBS&POS=CIRCLE%20101%20-21%200.1" -o cutout.fits

# Non-standard proxy (cutout, or staging-handoff JSON on the seed data)
curl -s -X POST "$SKAVA/soda/execute?ID=$OBS&POS=CIRCLE%20101%20-21%200.1" -o cutout.fits
```

## 5. TAP — ObsCore queries

```bash
curl -s "$SKAVA/tap/sync?LANG=ADQL&QUERY=SELECT+TOP+10+obs_id,target_name+FROM+ivoa.ObsCore" \
    | head -30
```

Returns a VOTable (`RESPONSEFORMAT=application/json` for JSON). The
VOSI documents a TAP client reads first are at `$SKAVA/tap/tables` and
`$SKAVA/tap/capabilities`. See the [TAP reference](../api/tap.md) for the
supported subset of ADQL.

## 6. Federation and tokens

```bash
# The local catalogue and every sibling in SKAVA_FEDERATED_SRC_URLS
curl -s "$SKAVA/federation/sources" | jq
curl -s "$SKAVA/federation/search?DPTYPE=image&limit=5" | jq '.sources'
```

The answers are merged on `obs_id`; a sibling that also lists a dataset
appears under its `also_at`. A fresh install is open (no token). When
`SKAVA_ACCESS_TOKENS` or an IAM (`IAM_WELLKNOWN_ENDPOINT`) is configured,
the public endpoints need `Authorization: Bearer <token>`, and a request
without one gets a 401 whose `WWW-Authenticate` header carries the
`ivoa_bearer` challenge naming the IAM. See
[Authentication](../api/auth.md) and [Federation](../api/federation.md).

## 7. Admin UI

Open <http://localhost:8000/admin/> in your browser and sign in with
the bootstrap admin you created in [Installation](installation.md).

From the dashboard:

* **Nodes** — register a site and, optionally, the URL of its
  co-located VisIVO backend
* **Datasets** — browse + edit individual entries and their replicas;
  pre-fill a new dataset from a FITS upload (small files only — bulk
  ingestion goes via the publisher)
* **Upload** — a CSV / JSON manifest, with a dry run first
* **History** — the audit log: who changed what, exportable as CSV

The full UI tour lives in [Admin UI / overview](../admin-ui/overview.md).

## Where to next

* Set up the publisher CLI on the node where your data physically
  lives → [skava-publisher / overview](../publisher/overview.md).
* Integrate the VisIVO Visual Analytics desktop client →
  [client-integration / visivo-desktop](../client-integration/visivo-desktop.md).
* Plan a production deployment with proper TLS, secrets and backups →
  [deployment / production](../deployment/production.md).
