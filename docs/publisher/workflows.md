# Publisher workflows

The same `skava-publisher` binary supports three escalating
automation levels. This page walks each one with full commands and
expected output.

## Level 1 — Manual review

When to use: first-run, "I want to see the manifest before anything
hits SKAVA", high-stakes ingestion.

```bash
# 1. Scan locally — no network
skava-publisher -c /etc/skava-publisher.yaml scan -o /tmp/manifest.json

# Output:
#   Wrote 1003 records to /tmp/manifest.json
#   ─── Summary ────────────────────────────
#                    scanned: 1003
#          skipped_unchanged: 0
#        skipped_unsupported: 0
#                  extracted: 1003
#             extract_failed: 0
#   ────────────────────────────────────────
```

The state DB is touched (file index is updated) but no record is
marked published yet.

```bash
# 2. Operator reviews
less /tmp/manifest.json
diff /tmp/manifest.json /tmp/yesterday.json  # against last run
jq '.records | length' /tmp/manifest.json    # quick count
jq '.records | group_by(.dataproduct_type) | map({type:.[0].dataproduct_type, n:length})' \
    /tmp/manifest.json
```

```bash
# 3. Validate vs SKAVA — dry-run, no DB writes
skava-publisher -c /etc/skava-publisher.yaml validate -m /tmp/manifest.json

# Output:
#   Validated 1003 records.
#   {
#     "job": { "job_id": 41, "dry_run": true, "status": "...", ... },
#     "summary": {
#       "processed": 1003,
#       "inserted_datasets": 1003,
#       "updated_datasets": 0,
#       "inserted_replicas": 1003,
#       "updated_replicas": 0,
#       "skipped": 0,
#       "validation_errors": []
#     }
#   }
```

"Validated" only means SKAVA answered; read `skipped` and
`validation_errors`. If they are not empty (e.g. `node_not_found`,
"Node not found: POWER9", because you forgot to create the node in
the admin UI, or "Missing required field: dataproduct_type"), fix and
re-validate.

```bash
# 4. Real publish
skava-publisher -c /etc/skava-publisher.yaml publish -m /tmp/manifest.json
# About to publish 1003 record(s) to https://skava.inaf.it as node POWER9.
# Proceed? [Y/n]: y
# 2026-06-05T16:45:43 INFO httpx — HTTP Request: POST .../run "HTTP/1.1 200 OK"
# ✓ Published 1003 record(s).
```

With `-m` the state DB is not updated: the files the `scan` step
recorded stay `pending`, so the next `publish` without `-m`
re-extracts and re-posts them once (harmless, the ingestion is
idempotent on `obs_id`) and then marks them `published`.

## Level 2 — Semi-auto

When to use: daily operator-driven runs, "I trust the config but
want a human in the loop".

```bash
skava-publisher -c /etc/skava-publisher.yaml publish -y
```

The `-y` skips the confirmation prompt. The publisher scans, builds
the manifest, POSTs it to SKAVA's `/internal/ingestion/run` (there is
no separate dry-run step) and records each file's outcome in
state.db — all in one command.

A file is marked `published` only when SKAVA took its record. A record
SKAVA skipped (for example `node_not_found`) marks its file `failed`
with SKAVA's reason, and the next run sends it again; `status` lists
the failures. `publish -m` records outcomes only for the files the
manifest describes and that have not changed since it was written
(the manifest carries each file's path, size and mtime).

Second-day output:

```
─── Summary ────────────────────────────
                 scanned: 1005
       skipped_unchanged: 1003       ← state.db skips!
     skipped_unsupported: 0
               extracted: 2
          extract_failed: 0
────────────────────────────────────────
About to publish 2 record(s)…
✓ Published 2 record(s).
```

If nothing changed:

```
Nothing to publish — no new or modified files.
```

## Level 3 — Full-auto (cron / watch)

When to use: production once the config is stable.

### Cron-style

```text
# /etc/cron.d/skava-publisher
0 */6 * * * skava /usr/bin/apptainer run \
    --bind /data:/data \
    --bind /etc/skava-publisher.yaml:/etc/skava-publisher.yaml \
    --bind /var/lib/skava-publisher:/var/lib/skava-publisher \
    --env-file /etc/skava-publisher.env \
    /opt/skava/publisher.sif \
    -c /etc/skava-publisher.yaml watch --once \
    >> /var/log/skava-publisher.log 2>&1
```

Runs every 6 h, single iteration, exits cleanly.

### Long-running daemon

```bash
apptainer instance start --bind ... publisher.sif skava-watch
apptainer exec instance://skava-watch \
    skava-publisher -c /etc/skava-publisher.yaml watch
```

Loops indefinitely on the configured interval, SIGTERM-safe (finishes
the current iteration before exiting).

### SystemD timer (cleanest)

`/etc/systemd/system/skava-publisher.service`:

```ini
[Unit]
Description=SKAVA publisher one-shot
After=network-online.target

[Service]
Type=oneshot
User=skava
EnvironmentFile=/etc/skava-publisher.env
ExecStart=/usr/bin/apptainer run \
    --bind /data:/data \
    --bind /etc/skava-publisher.yaml:/etc/skava-publisher.yaml \
    --bind /var/lib/skava-publisher:/var/lib/skava-publisher \
    /opt/skava/publisher.sif -c /etc/skava-publisher.yaml watch --once
```

`/etc/systemd/system/skava-publisher.timer`:

```ini
[Unit]
Description=Publish to SKAVA every 6h

[Timer]
OnCalendar=*-*-* 00/6:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl enable --now skava-publisher.timer
journalctl -u skava-publisher -f
```

`Persistent=true` ensures a missed run (e.g. after a reboot) catches
up at the next boot.

## What each subcommand DOES NOT do

```{list-table}
:header-rows: 1
:widths: 22 78

* - Subcommand
  - Will NOT
* - ``scan``
  - hit the network; write to SKAVA; mark anything ``published`` in
    state.db.
* - ``validate``
  - write to SKAVA; mark anything ``published``.
* - ``publish`` (with ``--manifest``)
  - scan the file system or touch state.db; discover new files on
    disk.
* - ``publish`` (without ``--manifest``)
  - re-publish unchanged ``published`` files (use ``--force`` for
    that). Files that failed extraction, or stayed ``pending``, are
    retried automatically.
* - ``watch``
  - retry SKAVA when it returns an error (each iteration is
    independent; files not marked ``published`` are picked up next
    time).
* - ``status``
  - contact SKAVA or change any file's status.
```

## Inspecting what's in state.db

```bash
skava-publisher -c /etc/skava-publisher.yaml status
# State DB: /var/lib/skava-publisher/state.db
# Counts by status:
#       published: 1003
#         failed: 2
# Recent failures (up to 10):
#   /data/.../broken.fits
#     └─ extract: FITS header missing required keyword BITPIX
```

Or read raw:

```bash
sqlite3 /var/lib/skava-publisher/state.db \
    "SELECT path, last_error FROM files WHERE last_status='failed' LIMIT 5;"
```

## Forcing a re-publish

```{important}
**Upgrading from a publisher that did not send checksums.** Earlier builds
of the publisher kept each file's SHA-256 only in ``provenance_json``; the
current one also sends it as the record's ``checksum``, which the catalogue
requires (by default) before it counts a second node's file as a replica of
the same product. Files published by an earlier build are skipped as
unchanged, so after upgrading, on every node, holder nodes first:

1. make sure checksums are computed for the files that have replicas:
   ``scan.compute_checksum: true``, and ``scan.checksum_max_bytes`` above the
   size of the largest such file (50 GB by default; files above the limit get
   no checksum);
2. run one forced publish: ``skava-publisher -c <config> publish -y --force``.

A node joining an already-catalogued dataset is refused as
``replica_unverified`` unless both its record and the catalogue state equal
checksums; the first node to publish a dataset, and a node updating its own
replica, are accepted without one.
```

State.db skips files marked `published`. To force a re-run (e.g.
after fixing a bug in the extractor):

```bash
skava-publisher -c /etc/skava-publisher.yaml publish -y --force
```

`--force` ignores the published flag and re-extracts everything.
SKAVA's ingestion is idempotent on `obs_id`, so duplicates are
updated in place rather than added.

Or, drop the state DB and start over:

```bash
rm /var/lib/skava-publisher/state.db
skava-publisher -c /etc/skava-publisher.yaml publish -y
```

## Combining subcommands in a CI pipeline

```yaml
# .gitlab-ci.yml fragment
publish-srca:
  stage: deploy
  # An image built from testbed/publisher/Dockerfile; its entrypoint is
  # skava-publisher, so reset it for the script shell.
  image:
    name: <your-registry>/skava-publisher:0.1.0
    entrypoint: [""]
  script:
    - skava-publisher --config /run/secrets/skava.yaml scan -o manifest.json
    - jq '.records | length' manifest.json
    - skava-publisher --config /run/secrets/skava.yaml validate -m manifest.json
    - skava-publisher --config /run/secrets/skava.yaml publish -m manifest.json -y
  artifacts:
    paths: [manifest.json]
    expire_in: 30 days
```

Captures the manifest as a CI artefact for forensics — three
months of build artefacts give you a full history of what SKAVA
saw without having to keep the publisher's state DB.
