"""YAML configuration loader.

The publisher's behaviour is controlled by a single YAML file whose path
is passed via ``--config``. Environment variables can be interpolated
with ``${VAR}`` so secrets (SKAVA internal API key) live outside the
checked-in config:

    skava:
      api_url: https://skava.inaf.it
      internal_api_key: ${SKAVA_INTERNAL_API_KEY}

Validation is Pydantic-based: malformed config crashes at load time
with a precise error, instead of failing mid-publish with a confusing
HTTP 4xx from SKAVA.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


_ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _substitute_env(raw: str) -> str:
    """Replace every ``${VAR}`` with ``os.environ[VAR]``; missing → empty.

    A missing variable is left blank rather than raising so the operator
    can detect it via Pydantic validation downstream (the resulting
    empty ``api_key`` triggers a clear "field required" error).
    """
    def _swap(match: re.Match) -> str:
        return os.environ.get(match.group(1), "")
    return _ENV_PATTERN.sub(_swap, raw)


def _interpolate(payload: Any) -> Any:
    if isinstance(payload, str):
        return _substitute_env(payload)
    if isinstance(payload, list):
        return [_interpolate(item) for item in payload]
    if isinstance(payload, dict):
        return {k: _interpolate(v) for k, v in payload.items()}
    return payload


# ─── Schema ─────────────────────────────────────────────────────────────────


class SkavaConfig(BaseModel):
    api_url: HttpUrl
    internal_api_key: str = Field(min_length=8, repr=False)
    # Network timeout (seconds) on every SKAVA POST. Long enough for a
    # large manifest, short enough that a crashed SKAVA doesn't wedge
    # cron loops.
    timeout_seconds: float = 60.0
    # Verify TLS certificate. Set False for self-signed dev SKAVA only.
    verify_tls: bool = True


class NodeConfig(BaseModel):
    code: str = Field(min_length=1, max_length=32,
                       description="Matches the SKAVA Node.code for this site.")
    # Template producing the dataset access URL from the file's path
    # RELATIVE to the scanned root. ``{relpath}`` is the only allowed
    # placeholder. Example: "http://host:8001/data/{relpath}"
    file_serve_url_pattern: str = Field(min_length=1)

    @field_validator("file_serve_url_pattern")
    @classmethod
    def _check_placeholder(cls, v: str) -> str:
        if "{relpath}" not in v:
            raise ValueError(
                "file_serve_url_pattern must contain the {relpath} placeholder."
            )
        return v


class ScanConfig(BaseModel):
    roots: list[Path] = Field(min_length=1)
    include: list[str] = Field(
        default_factory=lambda: ["*.fits", "*.fits.gz", "*.h5", "*.hdf5", "*.sf"],
        description="Glob patterns matched against each file's name.",
    )
    exclude: list[str] = Field(
        default_factory=lambda: [
            "**/tmp/**", "**/.staging/**", "*.partial", "*~",
        ],
        description="Glob patterns matched against each file's full path.",
    )
    follow_symlinks: bool = False
    # Files larger than this are still ingested, but their SHA256 is
    # NOT computed (cost: ~1 GB/s on modern disk). Lets you decide the
    # CPU budget per scan.
    checksum_max_bytes: int = 50 * 1024 * 1024 * 1024  # 50 GB
    compute_checksum: bool = True


class DefaultsConfig(BaseModel):
    obs_collection: str | None = None
    license: str | None = None
    is_public: bool = True
    # Filled into provenance_json on every record.
    publisher_label: str | None = None


class StateConfig(BaseModel):
    db_path: Path = Field(
        default=Path("/var/lib/skava-publisher/state.db"),
        description="SQLite file tracking already-published files.",
    )


class WatchConfig(BaseModel):
    enabled: bool = True
    interval_seconds: int = Field(default=21600, ge=60)


class PublisherConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skava: SkavaConfig
    node: NodeConfig
    scan: ScanConfig
    defaults: DefaultsConfig = DefaultsConfig()
    state: StateConfig = StateConfig()
    watch: WatchConfig = WatchConfig()
    # Stop the entire scan when this many records fail extraction. A
    # safety net against publishing thousands of half-broken records
    # because of one bad disk sector.
    extract_failure_threshold: int = Field(default=10, ge=1)
    # Log level for the publisher itself; SKAVA's responses are always
    # logged at INFO regardless.
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


# ─── Loader ──────────────────────────────────────────────────────────────────


def load_config(path: Path) -> PublisherConfig:
    """Parse + validate + return a frozen config object."""
    if not path.is_file():
        raise FileNotFoundError(f"Config not found: {path}")
    raw_yaml = path.read_text(encoding="utf-8")
    expanded = _interpolate(yaml.safe_load(raw_yaml) or {})
    return PublisherConfig(**expanded)
