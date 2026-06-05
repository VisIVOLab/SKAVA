# Extractors

An **extractor** is a small Python class that takes a file path and
returns a dict of ObsCore-shaped metadata. The publisher ships three
built-ins (FITS, HDF5, PSRFITS) and registers them via Python entry
points so third-party plugins can extend the set without touching
the publisher's source.

## Built-in extractors

```{list-table}
:header-rows: 1
:widths: 18 32 50

* - Name
  - File patterns
  - What it extracts
* - ``fits``
  - ``*.fits``, ``*.fit``, ``*.fts``, ``*.fits.gz``, ``*.fits.fz``
  - target / facility / instrument; WCS-based RA/Dec/FoV; time from
    MJD-OBS + EXPTIME or DATE-OBS; spectral from RESTFREQ or any
    FREQ / WAVE / VOPT / VRAD axis; dataproduct_type heuristic.
* - ``hdf5``
  - ``*.h5``, ``*.hdf5``
  - LOFAR ICD-3 root attributes (POINTING_RA, OBSERVATION_*_MJD,
    OBSERVATION_FREQUENCY_*), with fallbacks for generic
    dynamic-spectrum files.
* - ``psrfits``
  - ``.fits``/``.sf`` with ``FITSTYPE=PSRFITS`` or ``EXTNAME=SUBINT``
  - STT_IMJD/STT_SMJD/STP_MJD time; OBSFREQ/OBSBW spectral band;
    SRC_NAME / TELESCOP / BACKEND.
```

Every extractor is best-effort: missing or malformed headers cause
the corresponding field to be omitted from the result, not raised.
The operator is expected to review the resulting manifest before
publishing high-stakes data.

## The contract

```python
from pathlib import Path
from typing import Any
from skava_publisher.extractors.base import Extractor


class MyExtractor(Extractor):
    name = "myformat"

    def supports(self, path: Path) -> bool:
        """Fast filename / extension check."""
        return path.suffix == ".myext"

    def extract(self, path: Path) -> dict[str, Any]:
        """Parse the file and return a dict.

        Recognised keys (match form input names in the admin UI):
          obs_id, obs_title, obs_collection, dataproduct_type,
          calib_level, target_name, facility_name, instrument_name,
          s_ra, s_dec, s_fov,
          t_min, t_max,            # MJD
          em_min, em_max,           # metres
          access_format, access_estsize  # KB

        Omit keys you can't infer. The publisher's manifest builder
        overlays your dict on top of the config defaults; absent
        keys fall through to the default value.
        """
        return {
            "target_name": ...,
            "facility_name": ...,
            # ... whatever you can recover
        }
```

Rules:

* `supports()` must be fast — it runs against every file in the scan
  walk. Cheap extension check is enough; detailed format checks
  belong in `extract()`.
* `extract()` may raise — the publisher catches and records the
  failure in state.db with the error string.
* Don't perform network I/O. Extractors are pure local-FS readers.
* Don't import the SKAVA app code. Extractors live in a separate
  Python package.

## Registering a plugin

Create a new package, e.g. `skava-publisher-casa/`:

```toml
# pyproject.toml
[project]
name = "skava-publisher-casa"
version = "0.1.0"
dependencies = ["casacore>=0.6", "skava-publisher>=0.1"]

[project.entry-points."skava_publisher.extractors"]
casa = "skava_publisher_casa.extractor:CasaExtractor"
```

```python
# skava_publisher_casa/extractor.py
from pathlib import Path
from skava_publisher.extractors.base import Extractor

class CasaExtractor(Extractor):
    name = "casa"

    def supports(self, path: Path) -> bool:
        return path.suffix == ".ms" and path.is_dir()

    def extract(self, path):
        # ... call into python-casacore to read the Measurement Set
        ...
```

Install it next to the publisher:

```bash
pip install skava-publisher-casa
# or, inside the Apptainer image, rebuild with the plugin pinned:
#   pip install skava-publisher-casa==0.1.0
```

The next time the publisher runs, the new extractor is discovered
via the entry point and added to the resolution chain.

## Resolution order

When the scanner finds a file, it iterates the discovered extractors
in **lexical order of their entry-point name** and uses the first
one whose `supports()` returns true. So if multiple plugins claim
the same file:

* `casa` (lex order: c) wins over `fits` (lex order: f) for a
  `.fits` file if `casa.supports()` returns true first.
* Re-name your entry point if you need a specific priority.

This is intentional — predictable across deployments — but if you
need richer priority semantics, write a single "router" extractor
that delegates internally and register only that one.

## Re-using the built-in helpers

The shared `_opt_float`, `_opt_str`, `_dataproduct_type`,
`_spatial`, `_time`, `_spectral` helpers in
`skava_publisher.extractors.fits` are not yet exposed as a public API
— they're internal to the FITS extractor. Phase 4 will extract them
into `skava_publisher.extractors.helpers` so plugins can reuse the
WCS / time / frequency logic without copying.

For now, copy the relevant snippets directly into your plugin.

## Testing your extractor

```python
# tests/test_my_extractor.py
from pathlib import Path
import pytest
from my_plugin import MyExtractor


def test_supports_extension(tmp_path):
    f = tmp_path / "sample.myext"
    f.touch()
    assert MyExtractor().supports(f)


def test_extract_from_sample_file():
    sample = Path(__file__).parent / "data" / "sample.myext"
    out = MyExtractor().extract(sample)
    assert out["target_name"] == "Crab Pulsar"
    assert "s_ra" in out
```

The Apptainer image bakes Python 3.12 + pytest, so the same tests
run in CI inside the container the operator will deploy.

## Common pitfalls

```{list-table}
:header-rows: 1
:widths: 35 65

* - Pitfall
  - Fix
* - Plugin not picked up
  - Confirm the entry point: ``pip show skava-publisher-casa`` →
    look at the entry-points section. Or:
    ``python -c "from importlib.metadata import entry_points;
    print(list(entry_points(group='skava_publisher.extractors')))"``.
* - ``supports`` returns true for files you can't handle
  - The publisher will treat extraction errors as failed-once, retry
    next run. Tighten ``supports``.
* - Returning ``None`` for missing fields
  - Don't — just omit the key. The manifest builder distinguishes
    "absent" from "explicit None" and the latter currently sets
    DB columns to NULL even if a default exists.
* - Returning Astropy units instead of plain floats
  - Always call ``.to_value("deg")`` / ``.to_value("m")`` etc.
    before returning. JSON can't serialise ``Quantity``.
```

## Roadmap

* Phase 4: ``skava_publisher.extractors.helpers`` public API.
* Phase 4: ``--extractor=...`` CLI override for testing a specific
  one against a single file.
* Phase 5: per-file timing / size metrics emitted as JSON for
  Prometheus scrape.
