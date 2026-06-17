# Publisher configuration

The publisher's behaviour is controlled by a single YAML file passed
via `--config`. Environment variables can be interpolated with
`${VAR}`. This page is the full key reference; `example-config.yaml`
in the repo is a fully-commented example you can copy.

## Top-level structure

```yaml
skava:    {...}
node:     {...}
scan:     {...}
defaults: {...}
state:    {...}
watch:    {...}
extract_failure_threshold: 10
log_level: INFO
```

Every section is validated by Pydantic on load. Malformed config
crashes immediately with a precise error, not later with a confusing
HTTP 4xx.

## `skava:` — where to publish

```yaml
skava:
  api_url:          https://skava.inaf.it       # required
  internal_api_key: ${SKAVA_INTERNAL_API_KEY}    # required, ≥ 8 chars
  timeout_seconds:  60.0                         # default 60
  verify_tls:       true                         # default true
```

`internal_api_key`: the value of `INTERNAL_API_KEY` configured on the
SKAVA api container. **Always** read from an env var so the YAML can
be committed without leaking secrets.

`verify_tls: false` for dev SKAVA with self-signed certs. Never in
production.

## `node:` — who is publishing

```yaml
node:
  code: POWER9                                                # required
  file_serve_url_pattern: "http://pleiadi:8001/data/{relpath}" # required
```

`code` must match a `Node.code` registered in SKAVA. Create the Node
in the admin UI before the first publish — otherwise ingestion will
fail with "unknown node".

`file_serve_url_pattern` turns a file's path RELATIVE to the scan
root into the `access_endpoint` written on the Replica. `{relpath}`
is the only allowed placeholder. Common patterns:

```yaml
# Production node serving via HTTP
file_serve_url_pattern: "http://pleiadi.oact.inaf.it:8001/data/{relpath}"

# Mac dev with local file:// scheme (file lives on the same Mac as
# the VisIVO backend that will consume it)
file_serve_url_pattern: "file:///Users/fvitello/Desktop/tmp_download/{relpath}"

# FTP archive
file_serve_url_pattern: "ftp://archive.eso.org/visible/{relpath}"
```

## `scan:` — what to publish

```yaml
scan:
  roots:
    - /data/ska_2026/cubes
    - /data/ska_2026/dynspec

  include: ["*.fits", "*.fits.gz", "*.h5", "*.hdf5", "*.sf"]
  exclude: ["**/tmp/**", "**/.staging/**", "*.partial", "*~"]
  follow_symlinks: false

  compute_checksum:    true
  checksum_max_bytes:  53687091200   # 50 GB
```

```{list-table}
:header-rows: 1
:widths: 28 14 58

* - Key
  - Default
  - Meaning
* - ``roots``
  - —
  - One or more directories to walk depth-first.
* - ``include``
  - all three formats
  - Glob patterns matched against the **filename** (not the path).
* - ``exclude``
  - tmp / staging
  - Glob patterns matched against the **full relative path**, so
    ``**/tmp/**`` excludes any ``tmp`` directory at any depth.
* - ``follow_symlinks``
  - false
  - Prevents loops and cross-mount surprises. Set true only if you
    really mean it.
* - ``compute_checksum``
  - true
  - When false, SHA256 is never computed; ``provenance_json.sha256``
    is absent.
* - ``checksum_max_bytes``
  - 50 GB
  - Files larger than this are still ingested but their SHA256 is
    skipped. ``1 GB/s`` is a typical SSD read rate; multiply that
    by your bound to estimate the CPU cost.
```

## `defaults:` — fields the extractor can't infer

```yaml
defaults:
  obs_collection:    inaf-power9-ska
  license:           CC-BY-4.0
  is_public:         true
  publisher_label:   skava-publisher@power9
```

Applied per record only when the extractor didn't already provide
the field. Allows fleet-wide defaults without forking the extractor.

## `state:` — local tracking

```yaml
state:
  db_path: /var/lib/skava-publisher/state.db
```

The publisher creates the path if missing. WAL journal mode is
enabled so abrupt crashes leave a clean DB. Only one publisher
process at a time should write — `watch` mode holds the SQLite write
lock implicitly.

## `watch:` — periodic mode

```yaml
watch:
  enabled:          true
  interval_seconds: 21600    # 6 h
```

`enabled` is informational; the actual `watch` subcommand reads
`interval_seconds`. Use `--once` for a single iteration (cron) or
omit it for a long-running daemon (SystemD service).

## Top-level: safety nets

```yaml
extract_failure_threshold: 10
log_level: INFO
```

* `extract_failure_threshold` — abort the scan when N records fail
  extraction. Catches "the disk filled with corrupted files" before
  thousands of garbage rows hit SKAVA.
* `log_level` — DEBUG / INFO / WARNING / ERROR. SKAVA's HTTP
  responses are always logged at INFO regardless.

## Worked example: minimal config for the Mac

```yaml
skava:
  api_url:          http://localhost:8000
  internal_api_key: ${SKAVA_INTERNAL_API_KEY}
  verify_tls:       false

node:
  code: MAC-LOCAL
  file_serve_url_pattern: "file:///Users/fvitello/Desktop/tmp_download/{relpath}"

scan:
  roots:
    - /Users/fvitello/Desktop/tmp_download
  include: ["*.fits", "*.fits.gz", "*.h5", "*.hdf5"]
  exclude: ["**/.DS_Store", "**/tmp/**"]
  follow_symlinks: false

defaults:
  obs_collection:    mac-tmp-download
  license:           CC0
  publisher_label:   skava-publisher@mac

state:
  db_path: /tmp/skava-publisher-state.db

extract_failure_threshold: 100
log_level: INFO
```

Plus in the shell:

```bash
export SKAVA_INTERNAL_API_KEY=<your dev key>
```

## What if the config is wrong?

Pydantic prints a precise message. Examples:

```
ValidationError: 1 validation error for PublisherConfig
node.file_serve_url_pattern
  file_serve_url_pattern must contain the {relpath} placeholder.
```

```
ValidationError: 1 validation error for PublisherConfig
skava.internal_api_key
  String should have at least 8 characters
```

```
ValidationError: 1 validation error for PublisherConfig
scan
  Field required [type=missing, input_value={...}, input_type=dict]
```

Fix and re-run.
