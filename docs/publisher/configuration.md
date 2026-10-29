# Publisher configuration

The publisher's behaviour is controlled by a single YAML file passed
via `--config` / `-c` (before the subcommand) or the
`SKAVA_PUBLISHER_CONFIG` environment variable. Environment variables
can be interpolated with `${VAR}` (upper-case names only; an unset
variable becomes an empty string). This page is the full key
reference; `example-config.yaml` in the repo is a fully-commented
example you can copy.

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
HTTP 4xx. Unknown top-level keys are rejected; unknown keys inside a
section are ignored.

## `skava:` — where to publish

```yaml
skava:
  api_url:          https://skava.inaf.it       # required
  internal_api_key: ${SKAVA_INTERNAL_API_KEY}    # required, ≥ 8 chars
  timeout_seconds:  60.0                         # default 60
  verify_tls:       true                         # default true
```

`internal_api_key`: the value of `SKAVA_INTERNAL_API_KEY` configured
on the SKAVA api container; it is sent as the `X-Internal-Api-Key`
header. **Always** read from an env var so the YAML can
be committed without leaking secrets.

`verify_tls: false` for dev SKAVA with self-signed certs. Never in
production.

## `node:` — who is publishing

```yaml
node:
  code: POWER9                                                # required
  file_serve_url_pattern: "http://pleiadi:8001/data/{relpath}" # required
```

`code` (max 32 chars) must match a `Node.code` registered in SKAVA.
Create the Node in the admin UI before the first publish — otherwise
SKAVA skips every record with `node_not_found` ("Node not found:
POWER9").

`file_serve_url_pattern` turns a file's path RELATIVE to the scan
root into the record's `access_url`, which SKAVA stores as the
Replica's `access_endpoint`. `{relpath}` is the only placeholder and
must be present. The URL needs a scheme (`http://`, `file://`, ...);
for a node with a co-located VisIVO backend, `file://` URLs are what
let the backend open the file in place. Common patterns:

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
  - ``*.fits``, ``*.fits.gz``, ``*.h5``, ``*.hdf5``
  - Glob patterns matched against the **filename** (not the path).
    Add ``*.fit``, ``*.fts``, ``*.fits.fz`` or ``*.sf`` (PSRFITS)
    explicitly if you have them.
* - ``exclude``
  - ``**/tmp/**``, ``**/.staging/**``, ``*.partial``, ``*~``
  - Glob patterns (``fnmatch``) matched against the **path relative
    to the scan root**, so ``**/tmp/**`` excludes a ``tmp``
    directory below the first level (``a/tmp/x.fits``); add
    ``tmp/*`` for one directly under the root.
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
process at a time should use a given state DB; nothing enforces
this, so do not let a cron run overlap a running `watch`.

## `watch:` — periodic mode

```yaml
watch:
  enabled:          true
  interval_seconds: 21600    # 6 h
```

With `enabled: false` the `watch` subcommand does nothing, with or
without `--once` (a node that publishes only by hand or by `publish`).
`interval_seconds` is the pause between iterations (minimum 60,
overridable with `--interval`). Use
`--once` for a single iteration (cron) or omit it for a long-running
daemon (SystemD service).

## Top-level: safety nets

```yaml
extract_failure_threshold: 10
log_level: INFO
```

* `extract_failure_threshold` — abort the scan when N records fail
  extraction. Catches "the disk filled with corrupted files" before
  thousands of garbage rows hit SKAVA.
* `log_level` — DEBUG / INFO / WARNING / ERROR. SKAVA's response
  to `validate` / `publish` is always printed to stdout as JSON.

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
  Value error, file_serve_url_pattern must contain the {relpath} placeholder.
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
