# Extending the publisher

Walkthrough of adding a new extractor as a third-party plugin. We
build a fictional "CASA Measurement Set" extractor as a worked
example.

## Anatomy of a plugin package

```
skava-publisher-casa/
├── pyproject.toml
├── README.md
├── skava_publisher_casa/
│   ├── __init__.py
│   └── extractor.py
└── tests/
    └── test_extractor.py
```

Two requirements:

1. A class subclassing ``skava_publisher.extractors.base.Extractor``.
2. An entry-point declaration in ``pyproject.toml`` under the group
   ``skava_publisher.extractors``.

## Step 1 — pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "skava-publisher-casa"
version = "0.1.0"
description = "CASA Measurement Set extractor for skava-publisher."
requires-python = ">=3.10"
dependencies = [
  "skava-publisher>=0.1",
  "python-casacore>=3.5",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.entry-points."skava_publisher.extractors"]
casa = "skava_publisher_casa.extractor:CasaExtractor"

[tool.setuptools.packages.find]
include = ["skava_publisher_casa*"]
```

The entry-point key `casa` is also the resolution priority — see
the [extractors page](../publisher/extractors.md#resolution-order).

## Step 2 — the extractor class

```python
# skava_publisher_casa/extractor.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from skava_publisher.extractors.base import Extractor

logger = logging.getLogger("skava.publisher.casa")


class CasaExtractor(Extractor):
    name = "casa"

    # MS is a directory, not a file — supports() must allow that.
    def supports(self, path: Path) -> bool:
        return path.suffix == ".ms" and path.is_dir()

    def extract(self, path: Path) -> dict[str, Any]:
        # Lazy import keeps publisher boot fast for installs without casa.
        from casacore.tables import table

        out: dict[str, Any] = {
            "dataproduct_type": "ms",          # SKAVA-specific kind
            "access_format":    "x-casa/ms",
        }

        with table(str(path)) as ms:
            # OBSERVATION subtable carries the most useful header bits.
            with table(str(path / "OBSERVATION")) as obs:
                obs_row = obs[0]
                if obs_row.get("TELESCOPE_NAME"):
                    out["facility_name"] = obs_row["TELESCOPE_NAME"]
                if obs_row.get("PROJECT"):
                    out["instrument_name"] = obs_row["PROJECT"]
                tmin, tmax = obs_row.get("TIME_RANGE", (None, None))
                if tmin is not None:
                    # MJD seconds → MJD days
                    out["t_min"] = float(tmin) / 86400.0
                if tmax is not None:
                    out["t_max"] = float(tmax) / 86400.0

            # FIELD subtable for the pointing centre (radians → degrees).
            try:
                with table(str(path / "FIELD")) as fld:
                    if len(fld) > 0:
                        ra_rad, dec_rad = fld[0]["PHASE_DIR"][0]
                        import math
                        out["s_ra"] = math.degrees(ra_rad)
                        out["s_dec"] = math.degrees(dec_rad)
            except Exception as exc:
                logger.debug("FIELD subtable parse failed: %s", exc)

        return out
```

Rules to follow:

* `supports()` must be fast — extension + ``is_dir()`` check is fine.
* `extract()` may raise; the publisher catches and records the
  failure in state.db with the error string, and aborts the scan once
  the failures reach the config's `extract_failure_threshold`.
* Omit keys that do not apply rather than setting them to `None`:
  the publisher overlays the result on the config defaults.
* Lazy import of heavy deps (``casacore``) keeps boot fast.
* Return plain Python primitives (str, float, int, bool). Never
  ``Quantity`` / ``numpy.ndarray``.

## Step 3 — register and install

Install the plugin in the same Python environment that has
``skava-publisher``:

```bash
pip install -e ./skava-publisher-casa
```

Verify discovery picks it up:

```bash
python -c "
from skava_publisher.extractors import discover
for e in discover():
    print(e.name)
"
# casa
# fits
# hdf5
# psrfits
```

(By priority, then name: an extractor that sets ``priority`` below 100 is asked before ``fits``.)

## Step 4 — exercise it

```bash
skava-publisher --config /path/to/config.yaml scan -o /tmp/manifest.json
jq '.records[] | select(.dataproduct_type == "ms")' /tmp/manifest.json
```

## Tests

```python
# tests/test_extractor.py
from pathlib import Path
from skava_publisher_casa.extractor import CasaExtractor


def test_supports_ms_directory(tmp_path):
    ms = tmp_path / "obs.ms"
    ms.mkdir()
    assert CasaExtractor().supports(ms)


def test_does_not_support_plain_file(tmp_path):
    f = tmp_path / "obs.ms"
    f.touch()
    assert not CasaExtractor().supports(f)


def test_extract_against_sample(sample_ms):
    out = CasaExtractor().extract(sample_ms)
    assert out["facility_name"] == "ASKAP"
    assert "s_ra" in out
```

Generate a ``sample_ms`` fixture in ``conftest.py`` (or commit a
small synthetic one as test data).

## Distribution

Three options, increasingly automated:

1. **Local-only**. ``pip install -e ./skava-publisher-casa`` on each
   node. Fine for first-week development.
2. **GitHub release**. Tag the repo, push, install with
   ``pip install
   git+https://github.com/.../skava-publisher-casa@v0.1.0``.
3. **Internal PyPI**. Publish to a private index (Nexus, Artifactory,
   GitLab Packages). Update the Apptainer recipe to install from
   that index.

For the SKAVA Apptainer image, add the plugin to ``%post``, after
the line that installs the publisher itself:

```bash
# tools/skava-publisher/apptainer/publisher.def
%post
    ...
    pip install --no-cache-dir "$SRC_DIR"
    pip install --no-cache-dir "skava-publisher-casa==0.1.0"
```

Rebuild with the plugin baked in. The recipe's ``%test`` section
asserts that the built-in ``fits``, ``hdf5`` and ``psrfits``
extractors are registered; extend it with yours.

## Resolution order pitfalls

If two plugins claim the same file:

* The extractor with the lower ``priority`` class attribute wins
  (default 100; the built-in ``psrfits`` uses 10); between equal
  priorities, the entry-point name earliest in lexical order.
* For exclusive ownership (a `.fits` file with a specific keyword
  goes to your extractor, not the built-in), have ``supports()`` peek
  at the header and set ``priority`` below 100, as ``psrfits`` does.

## Sharing back

If your extractor is general-purpose (not site-specific), open a PR
against ``VisIVOLab/SKAVA`` proposing inclusion as a built-in. We
prefer plugins that:

* handle a widely-used format
* have a permissive license
* come with tests + a small sample file

Niche / site-specific extractors should stay as separate plugins.

## See also

* [Publisher / extractors](../publisher/extractors.md) — the plugin
  contract reference.
* [Architecture / components](../architecture/components.md) for where
  the publisher sits in the wider SKAVA picture.
