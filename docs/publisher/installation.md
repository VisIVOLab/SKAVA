# Publisher installation

Two paths: Apptainer (recommended for production), or pip install
in a Python venv (recommended for dev).

## Path 1 — Apptainer container

Best for HPC nodes, shared SRCs, ppc64le / aarch64 / x86_64 with the
same image. See [Apptainer image](apptainer) for the full recipe.

Short version:

```bash
git clone https://github.com/VisIVOLab/SKAVA.git
cd SKAVA/tools/skava-publisher

apptainer build --fakeroot publisher.sif apptainer/publisher.def
# ~25-30 min on ppc64le cold cache, ~5 min on x86_64 warm cache

apptainer run \
    --bind /data:/data \
    --bind /etc/skava-publisher.yaml:/etc/skava-publisher.yaml \
    --bind /var/lib/skava-publisher:/var/lib/skava-publisher \
    --env SKAVA_INTERNAL_API_KEY="$SKAVA_INTERNAL_API_KEY" \
    publisher.sif --config /etc/skava-publisher.yaml status
```

## Path 2 — pip in a venv

Best for local development and testing the publisher logic without
container overhead.

### Prerequisites

* Python ≥ 3.10
* `pip` (any modern version)

### Install

```bash
cd ~/work/SKAVA/tools/skava-publisher

# Isolate the publisher from the system Python
python3 -m venv .venv
source .venv/bin/activate

# Editable install — edits to skava_publisher/*.py are visible
# without reinstalling
pip install -e .
```

Verify:

```bash
skava-publisher --version
# skava-publisher, version 0.1.0
```

### Dependencies

`pip install -e .` pulls:

* ``click`` — CLI ergonomics
* ``pyyaml``, ``pydantic``, ``pydantic-settings`` — config
* ``httpx`` — HTTP client to SKAVA
* ``astropy`` — FITS / PSRFITS parsing (also pulls numpy, scipy)
* ``h5py`` — HDF5 parsing

Total install size ~250 MB on x86_64, ~400 MB on ppc64le (where
some wheels are built from source).

### Tests (optional)

```bash
pip install -e ".[dev]"
pytest -q
```

## Path 3 — pip from GitHub directly

For sites that want to install without cloning:

```bash
pip install "git+https://github.com/VisIVOLab/SKAVA.git#subdirectory=tools/skava-publisher"
```

This is the right choice when the publisher is one of many
non-overlapping tools on a node and you don't want a full SKAVA
checkout.

## Where to install on a production node

Recommended:

* Container path: ``/opt/skava/publisher.sif``
* Config path:    ``/etc/skava-publisher.yaml``
* State path:     ``/var/lib/skava-publisher/state.db``
* Log path:       ``/var/log/skava-publisher.log``

A SystemD timer can wrap the cron-style run:

```ini
# /etc/systemd/system/skava-publisher.service
[Unit]
Description=SKAVA publisher one-shot publish
After=network-online.target

[Service]
Type=oneshot
User=skava
EnvironmentFile=/etc/skava-publisher.env
ExecStart=/usr/bin/apptainer run \
    --bind /data:/data \
    --bind /etc/skava-publisher.yaml:/etc/skava-publisher.yaml \
    --bind /var/lib/skava-publisher:/var/lib/skava-publisher \
    /opt/skava/publisher.sif \
    --config /etc/skava-publisher.yaml \
    watch --once
```

```ini
# /etc/systemd/system/skava-publisher.timer
[Unit]
Description=Periodic SKAVA publish

[Timer]
OnUnitActiveSec=6h
Persistent=true

[Install]
WantedBy=timers.target
```

Enable: ``systemctl enable --now skava-publisher.timer``.

## Verifying the install

```bash
skava-publisher --help
skava-publisher --version
skava-publisher --config /etc/skava-publisher.yaml status
# Counts by status: (empty — no files seen yet)
```

If ``status`` returns without errors, the config is valid and the
state DB is writeable. Proceed to your first scan in
[Workflows](workflows).
