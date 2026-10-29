# skava-publisher

Co-located publisher CLI for the SKAVA Data Discovery Service. Runs on
each data node, walks the filesystem, extracts ObsCore-shaped metadata
from FITS / HDF5 / PSRFITS files, and uploads JSON manifests to SKAVA's
internal ingestion API.

**SKAVA hosts metadata, not files.** The publisher is what moves the
metadata; the files stay where they are and SKAVA points at them via
the per-node `file_serve_url_pattern`.

## Why a CLI on the node

| Anti-pattern | Right pattern |
|---|---|
| Operator downloads a 50 GB cube from Power9 to laptop → uploads to SKAVA UI | Publisher on Power9 reads headers in place → POSTs ~5 KB of JSON to SKAVA |
| Scaling: one file at a time, manually | Scaling: cron every 6 h auto-detects new files |
| URL composition: typed by hand | URL composition: derived from `{relpath}` template |
| Idempotency: hope for the best | Idempotency: `state.db` skips already-published files |
| Audit: none | Audit: SHA256 per file in `provenance_json` |

## Install

### Apptainer (recommended for HPC / shared nodes)

```bash
cd SKAVA/tools/skava-publisher
apptainer build --fakeroot publisher.sif apptainer/publisher.def

# Bind data + config + state dir
apptainer run \
    --bind /data:/data \
    --bind /etc/skava-publisher.yaml:/etc/skava-publisher.yaml \
    --bind /var/lib/skava-publisher:/var/lib/skava-publisher \
    --env SKAVA_INTERNAL_API_KEY="..." \
    publisher.sif -c /etc/skava-publisher.yaml scan -o /tmp/manifest.json
```

### pip

From a local SKAVA checkout (most robust — no repo access needed):

```bash
pip install /path/to/SKAVA/tools/skava-publisher
skava-publisher --version
```

Or directly from the repo (needs access; prompts for credentials if private):

```bash
pip install "git+https://github.com/VisIVOLab/SKAVA.git#subdirectory=tools/skava-publisher"
```

## Configuration

Copy `example-config.yaml` to `/etc/skava-publisher.yaml` (or anywhere)
and edit. **Secrets must come from environment variables.** The config
loader expands `${VAR}` references; missing vars surface as Pydantic
validation errors at startup, not as confusing HTTP 401s later.
`--config` / `-c` goes before the subcommand, or set
`SKAVA_PUBLISHER_CONFIG`.

```bash
export SKAVA_INTERNAL_API_KEY="<openssl rand -hex 32>"
skava-publisher --config /etc/skava-publisher.yaml status
```

## Workflows — three levels of automation

### 1. Manual review (paranoid mode)

```bash
# Scan + write JSON, no network call
skava-publisher -c config.yaml scan -o /tmp/manifest.json
less /tmp/manifest.json                  # operator review
diff /tmp/manifest.json /tmp/yesterday.json

# Validate vs SKAVA (dry-run, no DB writes)
skava-publisher -c config.yaml validate -m /tmp/manifest.json

# When happy, publish
skava-publisher -c config.yaml publish -m /tmp/manifest.json
```

### 2. Semi-auto (single command, operator-triggered)

```bash
skava-publisher -c config.yaml publish -y
# = scan + publish in one shot (no separate dry-run)
# Summary: scanned 1003, skipped_unchanged 1000, extracted 3
# "✓ Published 3 record(s)." followed by SKAVA's JSON response
```

### 3. Full-auto (cron + watch mode)

```cron
# Every 6 hours
0 */6 * * * apptainer run --bind /data:/data --bind /etc/skava-publisher.yaml:/etc/skava-publisher.yaml \
                          --env-file /etc/skava-publisher.env \
                          /opt/skava/publisher.sif -c /etc/skava-publisher.yaml watch --once \
            >> /var/log/skava-publisher.log 2>&1
```

Or a long-running daemon:

```bash
apptainer instance start --bind /data:/data ... publisher.sif skava-watch
apptainer exec instance://skava-watch skava-publisher -c /etc/skava-publisher.yaml watch
```

## Subcommands

| Command | Network call | Writes SKAVA | Updates state.db | Use case |
|---|---|---|---|---|
| `scan` | no | no | yes (file index only) | review JSON before publish |
| `validate` | yes (dry-run) | no | file index only, when it scans (no `-m`) | sanity check |
| `publish` | yes | **yes** | yes (marks published), not with `-m` | actual ingestion |
| `watch --once` | yes | **yes** | yes | cron-friendly periodic run |
| `watch` (no `--once`) | yes | **yes** | yes | long-running daemon |
| `status` | no | no | no | inspect state.db summary |

Each file is marked by what SKAVA did with its record: `published`
when SKAVA took it, `failed` with SKAVA's reason when SKAVA skipped it
(`validation_errors` in the response) or the upload failed. Failed
files are sent again by the next run; `status` lists them.

## Supported file formats

| Format | Extractor | Detection | Notes |
|---|---|---|---|
| FITS (imaging / spectral) | `FitsExtractor` | `*.fits`, `*.fit`, `*.fts`, `*.fits.gz`, `*.fits.fz` | WCS + RA/DEC fallback, MJD-OBS + EXPTIME, RESTFREQ + spectral axis |
| HDF5 (LOFAR ICD-3 dynspec) | `Hdf5Extractor` | `*.h5`, `*.hdf5` | root attributes (POINTING_RA, OBSERVATION_FREQUENCY_MIN, …) |
| PSRFITS (pulsar / FRB) | `PsrFitsExtractor` | `.fits`/`.sf` with `FITSTYPE=PSRFITS` or `EXTNAME=SUBINT` | STT_IMJD/STT_SMJD, OBSFREQ/OBSBW, sexagesimal RA/DEC |

Extractors are tried by priority, then by entry-point name, and the
first match wins: `PsrFitsExtractor` (priority 10) recognises PSRFITS
by its header and comes before `FitsExtractor`, so a PSRFITS file named
`*.fits` is tagged `dynspec`. The default `scan.include` is `*.fits`,
`*.fits.gz`, `*.h5`, `*.hdf5`, `*.sf`; add the other suffixes you need.

### Adding a new extractor

Subclass `skava_publisher.extractors.base.Extractor` and register it
via an entry point in your own `pyproject.toml`:

```toml
[project.entry-points."skava_publisher.extractors"]
casa = "my_pkg.extractors:CasaExtractor"
```

The publisher discovers it on the next launch.

## State.db

SQLite at the path configured in `state.db_path`. One row per file:

```
path           TEXT PK    absolute filesystem path
size_bytes     INTEGER
mtime_ns       INTEGER    nanosecond mtime → cheap "has it changed?" check
sha256         TEXT       null when checksum was skipped (large files)
obs_id         TEXT       recorded once published (header OBS_ID or a path hash)
first_seen     TEXT       ISO-8601 UTC
last_published TEXT       ISO-8601 UTC; null until first successful publish
last_status    TEXT       pending | published | failed
last_error     TEXT       truncated error string for failed attempts
```

Inspect with `skava-publisher status` or any sqlite3 client:

```bash
sqlite3 /var/lib/skava-publisher/state.db \
    "SELECT path, last_error FROM files WHERE last_status='failed';"
```

## Security notes

* The internal API key is sent on every request as `X-Internal-Api-Key`.
* TLS verification is on by default; only disable (`verify_tls: false`)
  for dev SKAVA with a self-signed cert.
* The publisher needs READ access on the data tree and READ+WRITE on
  `state.db_path`. It does NOT need write access to the data.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `validation error … internal_api_key` | env var not set / typo in `${VAR}` |
| Every run reports 0 new files | `include` patterns don't match — try `scan --no-state` |
| `Aborting: N extraction failures (>= extract_failure_threshold)` | one specific file corrupts the run; see logs, exclude it |
| `last_status='failed'` rows | extraction errors; check `last_error` |
| Records missing in SKAVA although state.db says `published` | SKAVA skipped them (e.g. `node_not_found`, missing `dataproduct_type`); see `validation_errors` in the publish output, fix, re-run with `--force` |
| Watch loops but never publishes | files match `exclude` patterns; see scanner debug at `log_level: DEBUG` |
