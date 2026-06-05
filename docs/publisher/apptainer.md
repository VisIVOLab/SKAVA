# Apptainer image

Recommended way to ship the publisher to HPC nodes / shared SRC
infrastructure. The image bundles Python 3.12, the publisher CLI,
astropy, h5py and every extractor — no Python install needed on
the host.

## Build

From a host with `apptainer` (≥ 1.1) installed:

```bash
git clone https://github.com/VisIVOLab/SKAVA.git
cd SKAVA/tools/skava-publisher

apptainer build --fakeroot publisher.sif apptainer/publisher.def
```

Build time:

* **x86_64 warm cache** ~3 min
* **ppc64le cold** ~25-30 min (wheels are built from source for
  numpy / scipy / h5py / healpy on Power architecture)
* **aarch64 warm cache** ~5 min

Output: a single ~600 MB SIF file.

## Run shape

```bash
apptainer run \
    --bind /data:/data \
    --bind /etc/skava-publisher.yaml:/etc/skava-publisher.yaml \
    --bind /var/lib/skava-publisher:/var/lib/skava-publisher \
    --env SKAVA_INTERNAL_API_KEY="$SKAVA_INTERNAL_API_KEY" \
    publisher.sif \
    --config /etc/skava-publisher.yaml \
    <subcommand>
```

Three binds are required:

1. **`/data:/data`** — read access to the scan roots configured in
   YAML. Read-only is fine; the publisher never writes to the data
   tree.
2. **`/etc/skava-publisher.yaml`** — the config file. Mount as
   read-only (`:/etc/...:ro`) in production.
3. **`/var/lib/skava-publisher`** — directory holding the state DB.
   Read-write.

The `SKAVA_INTERNAL_API_KEY` env var is `${SKAVA_INTERNAL_API_KEY}`-
substituted into the YAML at load time.

## Why Apptainer, not Docker

* **Multi-arch with one recipe.** Same `.def` builds x86_64,
  ppc64le, aarch64.
* **No root daemon required.** Apptainer runs entirely in user
  space, which most HPC sites mandate.
* **Bind mounts behave like host paths** rather than copying through
  a virtual filesystem layer — important when scanning multi-TB
  directories.
* **GPU support is a flag** (`--nv` for NVIDIA, `--rocm` for AMD)
  rather than an installation chain.

## Apptainer recipe (`publisher.def`)

Excerpt of the key sections — the full file is in
`tools/skava-publisher/apptainer/publisher.def`:

```bash
Bootstrap: docker
From: python:3.12-slim

%post
    # ── System deps ────────────────────────────────────────────
    # Build toolchain for ppc64le sdist builds (idle on x86_64).
    apt-get update -qq
    apt-get install -y --no-install-recommends \
        build-essential gcc g++ gfortran make automake autoconf \
        libtool cmake libffi-dev libssl-dev libhdf5-dev \
        libopenblas-dev liblapack-dev libfftw3-dev libcfitsio-dev \
        pkg-config

    pip install --no-cache-dir --upgrade pip

    # ── Install publisher (source copied via %setup) ───────────
    pip install --no-cache-dir /srv/publisher_src

%setup
    # Copy source from host into the building rootfs
    cp -r "$PWD" "$APPTAINER_ROOTFS/srv/publisher_src/"

%runscript
    #!/bin/bash
    exec skava-publisher "$@"
```

The recipe is identical for production / dev — what changes is the
host filesystem bind mounts.

## Bind mount checklist

```{list-table}
:header-rows: 1
:widths: 22 18 60

* - Path inside container
  - Mode
  - Source on host
* - ``/data``
  - ``:ro`` (recommended)
  - ``/srv/share/<survey>/`` or wherever your data lives.
* - ``/etc/skava-publisher.yaml``
  - ``:ro``
  - ``/etc/skava-publisher.yaml`` — the production config.
* - ``/var/lib/skava-publisher``
  - rw
  - same path on host. Pre-create with
    ``mkdir -p && chown publisher:publisher``.
```

## Environment variables passed through

The publisher reads these from the container env (set with
``--env`` or ``--env-file``):

* `SKAVA_INTERNAL_API_KEY` — required (referenced from YAML)
* `SKAVA_PUBLISHER_CONFIG` — optional override for the config path
* `LANG=C.UTF-8` — set by the recipe

`--env-file /etc/skava-publisher.env` is the recommended pattern,
where the file has `0600` permissions and only contains:

```
SKAVA_INTERNAL_API_KEY=...
```

## Running from cron

```cron
0 */6 * * * /usr/bin/apptainer run \
    --bind /srv/data:/data \
    --bind /etc/skava-publisher.yaml:/etc/skava-publisher.yaml:ro \
    --bind /var/lib/skava-publisher:/var/lib/skava-publisher \
    --env-file /etc/skava-publisher.env \
    /opt/skava/publisher.sif \
    --config /etc/skava-publisher.yaml \
    watch --once \
    >> /var/log/skava-publisher.log 2>&1
```

## Running as a long-running instance

```bash
apptainer instance start \
    --bind /srv/data:/data \
    --bind /etc/skava-publisher.yaml:/etc/skava-publisher.yaml:ro \
    --bind /var/lib/skava-publisher:/var/lib/skava-publisher \
    --env-file /etc/skava-publisher.env \
    /opt/skava/publisher.sif \
    skava-watch

apptainer exec instance://skava-watch \
    skava-publisher -c /etc/skava-publisher.yaml watch
```

Stop with `apptainer instance stop skava-watch`.

## Updating the image

```bash
git pull
cd tools/skava-publisher
apptainer build --fakeroot publisher.sif.new apptainer/publisher.def
mv publisher.sif.new /opt/skava/publisher.sif
systemctl restart skava-publisher.timer  # or whatever wraps it
```

Roll back by keeping the previous SIF:

```bash
mv /opt/skava/publisher.sif /opt/skava/publisher-prev.sif
```

## Caveats

```{list-table}
:header-rows: 1
:widths: 35 65

* - Caveat
  - Mitigation
* - Apptainer copies the SIF on every ``apptainer run`` invocation
    (creates an ephemeral overlay). Cron-triggered runs are slow.
  - Use ``apptainer instance`` + ``apptainer exec`` for cron; the
    instance keeps the rootfs warm.
* - Network egress can be blocked on SRC nodes
  - Whitelist the SKAVA URL on the egress firewall. The publisher
    only talks to SKAVA — no other outbound calls.
* - State.db is local to the node
  - That's by design: each node publishes its own data. If multiple
    nodes publish the same files, register the same Node code on
    SKAVA — ingestion will update existing rows rather than duplicate.
* - Apptainer 1.x ``--fakeroot`` sometimes can't ``%setup``
  - Some SRC sites disable it for security. Fall back to mounting
    the source via ``--bind`` and ``pip install /srv/source`` inside
    the container.
```

## Verifying after build

```bash
apptainer run publisher.sif --version
# skava-publisher, version 0.1.0

apptainer run publisher.sif --help
```

The `%test` section of the recipe runs an extractor-discovery
self-check at build time, so a successful `apptainer build` means
all three extractors loaded.
