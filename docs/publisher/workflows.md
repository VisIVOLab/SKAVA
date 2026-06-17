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
#   ─── Summary ────────────────────────────
#               scanned: 1003
#       skipped_unsupported: 0
#       skipped_unchanged: 0
#             extracted: 1003
#       extract_failed: 0
#   ────────────────────────────────────────
#   Wrote 1003 records to /tmp/manifest.json
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
#     "summary": {
#       "processed": 1003,
#       "skipped": 0,
#       "validation_errors": []
#     }
#   }
```

If validation surfaces errors (e.g. `unknown node POWER9` because
you forgot to create it in the admin UI), fix and re-validate.

```bash
# 4. Real publish
skava-publisher -c /etc/skava-publisher.yaml publish -m /tmp/manifest.json
# About to publish 1003 record(s) to https://skava.inaf.it as node POWER9.
# Proceed? [Y/n]: y
# 2026-06-05T16:45:43 INFO httpx — HTTP Request: POST .../run "HTTP/1.1 200 OK"
# ✓ Published 1003 record(s).
```

State DB rows transition `pending → published` with the assigned
`obs_id`.

## Level 2 — Semi-auto

When to use: daily operator-driven runs, "I trust the config but
want a human in the loop".

```bash
skava-publisher -c /etc/skava-publisher.yaml publish -y
```

The `-y` skips the confirmation prompt. The publisher scans, builds
the manifest, validates internally, POSTs to SKAVA, and updates
state.db — all in one command.

Second-day output:

```
─── Summary ────────────────────────────
        scanned: 1005
    skipped_unchanged: 1003       ← state.db skips!
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

```cron
# /etc/cron.d/skava-publisher
0 */6 * * * skava /usr/bin/apptainer run \
    --bind /data:/data \
    --bind /etc/skava-publisher.yaml:/etc/skava-publisher.yaml \
    --bind /var/lib/skava-publisher:/var/lib/skava-publisher \
    --env-file /etc/skava-publisher.env \
    /opt/skava/publisher.sif \
    watch --once \
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
    /opt/skava/publisher.sif watch --once
```

`/etc/systemd/system/skava-publisher.timer`:

```ini
[Unit]
Description=Publish to SKAVA every 6h

[Timer]
OnUnitActiveSec=6h
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
  - touch the file system (besides state.db); discover new files
    on disk.
* - ``publish`` (without ``--manifest``)
  - re-publish unchanged files (state.db skips them); fix already-
    failed records (use ``--force`` for that).
* - ``watch``
  - retry SKAVA when it returns 5xx (each iteration is independent;
    next iteration will pick up).
* - ``status``
  - touch SKAVA or state.db.
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
    "SELECT obs_id, path FROM files WHERE last_status='failed' LIMIT 5;"
```

## Forcing a re-publish

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
  image: registry.inaf.it/skava/publisher:0.1.0
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
