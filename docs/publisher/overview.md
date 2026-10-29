# skava-publisher overview

`skava-publisher` is a CLI tool that **runs on each data node**,
walks the local filesystem, extracts ObsCore metadata from FITS /
HDF5 / PSRFITS files, and uploads JSON manifests to SKAVA's internal
ingestion API.

It is the production path to register data with SKAVA. The admin UI
form is a fallback for one-offs; the publisher handles thousands of
files at a time.

## Why a CLI on the node

```{list-table}
:header-rows: 1
:widths: 50 50

* - Anti-pattern (download + admin UI)
  - Right pattern (publisher on the node)
* - Operator downloads a 50 GB cube from Power9 to laptop, then
    uploads to SKAVA UI.
  - Publisher on Power9 reads the header in place and POSTs ~2 KB
    of JSON to SKAVA.
* - One dataset at a time, manually.
  - 1 000 datasets per scan, cron-friendly.
* - URL composition typed by hand.
  - URL derived from a per-node ``file_serve_url_pattern`` template.
* - Idempotency: hope.
  - Local SQLite ``state.db`` skips already-published files.
* - Audit: none.
  - SHA256 of each file written to ``provenance_json``.
```

## Three levels of automation

Same binary, different subcommand:

### 1. Manual review

```bash
# Scan + write JSON, no network
skava-publisher -c config.yaml scan -o /tmp/manifest.json

# Validate against SKAVA (dry-run, no DB writes)
skava-publisher -c config.yaml validate -m /tmp/manifest.json

# When happy, publish
skava-publisher -c config.yaml publish -m /tmp/manifest.json
```

Use case: first-time onboarding of a new node; high-stakes
re-publication.

### 2. Semi-auto

```bash
skava-publisher -c config.yaml publish -y
# = scan + publish in one shot; state.db skips unchanged files
```

Use case: daily operator-triggered run via ssh from a manager host.

### 3. Full-auto

```text
0 */6 * * * apptainer run --bind /data:/data --bind /etc/skava-publisher.yaml:/etc/skava-publisher.yaml \
                          --env-file /etc/skava-publisher.env \
                          /opt/skava/publisher.sif \
                          -c /etc/skava-publisher.yaml watch --once \
              >> /var/log/skava-publisher.log 2>&1
```

Or a long-running daemon:

```bash
apptainer instance start ... publisher.sif skava-watch
apptainer exec instance://skava-watch \
    skava-publisher -c /etc/skava-publisher.yaml watch
```

Use case: production data flow once the config is stable.

## Subcommands at a glance

```{list-table}
:header-rows: 1
:widths: 18 12 12 16 42

* - Command
  - Network
  - Writes SKAVA
  - Updates state.db
  - Use case
* - ``scan``
  - no
  - no
  - yes (file index)
  - review JSON
* - ``validate``
  - yes (dry-run)
  - no
  - file index only, when it scans (no ``-m``)
  - sanity check
* - ``publish``
  - yes
  - **yes**
  - yes, when it scans (not with ``-m``)
  - real ingestion
* - ``watch --once``
  - yes
  - **yes**
  - yes
  - cron-friendly periodic run
* - ``watch`` (no ``--once``)
  - yes
  - **yes**
  - yes
  - long-running daemon
* - ``status``
  - no
  - no
  - no
  - inspect state.db
```

Every subcommand takes the config as a group option placed **before**
the subcommand (`skava-publisher -c config.yaml scan`), or from the
`SKAVA_PUBLISHER_CONFIG` environment variable.

## File-format support

| Format | Extractor | Detection rule |
|---|---|---|
| FITS imaging / cube | `FitsExtractor` (`fits`) | `*.fits`, `*.fit`, `*.fts`, `*.fits.gz`, `*.fits.fz` |
| HDF5 (LOFAR ICD-3 dynspec) | `Hdf5Extractor` (`hdf5`) | `*.h5`, `*.hdf5` |
| PSRFITS | `PsrFitsExtractor` (`psrfits`) | `.fits`/`.sf` with ``FITSTYPE=PSRFITS`` or ``EXTNAME=SUBINT`` |

Extractors are tried by priority, then by name, and the first match
wins: `psrfits`, which recognises its files by their header, comes
before the generic `fits`, so a PSRFITS file named `*.fits` is tagged
`dynspec`. The default `scan.include` lists `*.fits`, `*.fits.gz`,
`*.h5`, `*.hdf5` and `*.sf`. See
[extractors](extractors.md#resolution-order).

Plugin system: write a new ``Extractor`` subclass in your own Python
package, register an entry point under
``skava_publisher.extractors`` in its ``pyproject.toml``, and
``pip install`` it into the publisher's environment. The CLI picks
it up on the next launch. See [extractors](extractors.md) for the
contract.

## State tracking

Each run reads / writes a per-node SQLite at the path configured in
`state.db_path` (default ``/var/lib/skava-publisher/state.db``):

```sql
files (
    path            TEXT PRIMARY KEY,      -- abs path
    size_bytes      INTEGER,
    mtime_ns        INTEGER,
    sha256          TEXT,                  -- nullable when skipped
    obs_id          TEXT,                  -- recorded on successful publish
    first_seen      TEXT,                  -- ISO-8601 UTC
    last_published  TEXT,                  -- null until first success
    last_status     TEXT,                  -- pending | published | failed | replaced
    last_error      TEXT,
    access_url      TEXT                   -- the URL it was published with
)
```

Re-runs:

* unchanged ``mtime_ns`` + ``last_status=published`` → skip
* changed mtime → re-extract + re-publish (SKAVA's ingestion is
  idempotent on ``obs_id``)
* ``last_status=failed`` (extraction error) or ``pending`` (seen but
  not published, e.g. after a ``scan`` or a failed POST) → retry

The ``obs_id`` is the one in the file header (``OBS_ID`` and similar)
or, failing that, a stable hash of the node code and the relative
path. After a ``publish`` each file is marked by what SKAVA did with
its record: ``published`` when SKAVA took it, ``failed`` with SKAVA's
reason (from the response's ``validation_errors``) when SKAVA skipped
it or the upload failed, so a failed file is sent again by the next
run. The state keeps the file's size and mtime as they were when it
was extracted: a file changed while it was being published is
extracted again.

One ``obs_id`` is one product in SKAVA, and a node's second record under
an ``obs_id`` is taken as a new version of its first. So the publisher
withholds, and reports, two files of one run that give the same
``obs_id`` from different paths (a Stokes I and a Stokes Q cube of one
observation, say), and a file whose ``obs_id`` this node already
published from another file that still exists. Both are marked
``failed`` with the reason (``obs_id collision: ...``) and reported again
on every run until each product has its own ``OBS_ID``, or the old file
is removed. A file published under the ``obs_id`` of one that is gone
replaces it: it is published, and the old entry becomes ``replaced``.
``scan`` warns about collisions in what it extracted.

## When publisher is the wrong tool

```{list-table}
:header-rows: 1
:widths: 35 65

* - Situation
  - Use this instead
* - Hand-edit a single record after publication
  - Admin UI → Datasets → edit
* - One-off CSV from an external source
  - Either: ``curl /internal/ingestion/run`` with the CSV; or the
    admin UI [Upload](../admin-ui/upload.md) page.
* - Backfill historical data living on an archive HTTP server
  - Either: write a one-off Python script that builds the manifest
    and POSTs it; or stand up a temporary publisher pointed at a
    mounted copy of the archive.
* - Streaming live datasets (telescope on-sky right now)
  - Publisher is batch-oriented. For low-latency use the
    ``/internal/ingestion/run`` endpoint directly from your pipeline.
```

## Next pages

* [Installation](installation.md) — pip + venv on a developer Mac /
  data-node Linux.
* [Apptainer image](apptainer.md) — recommended for HPC / shared SRCs.
* [Configuration](configuration.md) — every YAML key explained.
* [Workflows](workflows.md) — the three automation levels in depth.
* [Extractors](extractors.md) — the plugin contract for new formats.
