"""``skava-publisher`` command-line interface.

Subcommands (call ``skava-publisher --help`` for a live listing):

* ``scan``      — walk + extract + write JSON manifest. NO network.
* ``validate``  — POST manifest to SKAVA's /internal/ingestion/dry-run.
* ``publish``   — scan + (optionally validate) + POST to /run. Writes state.db.
* ``watch``     — loop publish on ``interval_seconds`` from config.
* ``status``    — print state.db summary (counts, recent failures).
"""
from __future__ import annotations

import hashlib
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click

from skava_publisher import __version__
from skava_publisher.config import PublisherConfig, load_config
from skava_publisher.extractors import discover, find_extractor
from skava_publisher.manifest import build_record, dump_manifest
from skava_publisher.scanner import walk
from skava_publisher.state import StateStore, open_state
from skava_publisher.uploader import UploadError, publish as do_publish, validate as do_validate

logger = logging.getLogger("skava.publisher")


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _sha256_file(path: Path, *, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def _should_checksum(cfg: PublisherConfig, size_bytes: int) -> bool:
    if not cfg.scan.compute_checksum:
        return False
    return size_bytes <= cfg.scan.checksum_max_bytes


def _scan_and_extract(
    cfg: PublisherConfig,
    state: StateStore | None,
    *,
    force: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return (records, summary) — common driver of scan/validate/publish."""
    extractors = discover()
    if not extractors:
        click.secho("No extractors registered. Is the install broken?",
                     fg="red", err=True)
        sys.exit(2)
    logger.info("Loaded extractors: %s", ", ".join(e.name for e in extractors))

    records: list[dict[str, Any]] = []
    summary = {"scanned": 0, "skipped_unchanged": 0,
                "skipped_unsupported": 0, "extracted": 0,
                "extract_failed": 0}

    for abs_path, rel_path in walk(cfg.scan):
        summary["scanned"] += 1
        try:
            stat = abs_path.stat()
        except OSError as exc:
            logger.warning("stat() failed on %s: %s", abs_path, exc)
            continue
        mtime_ns = stat.st_mtime_ns
        size_bytes = stat.st_size

        ext = find_extractor(extractors, abs_path)
        if ext is None:
            summary["skipped_unsupported"] += 1
            continue

        if state is not None and not force \
                and not state.needs_extraction(str(abs_path), mtime_ns=mtime_ns):
            summary["skipped_unchanged"] += 1
            continue

        sha = _sha256_file(abs_path) if _should_checksum(cfg, size_bytes) else None
        if state is not None:
            state.upsert_seen(
                path=str(abs_path),
                size_bytes=size_bytes,
                mtime_ns=mtime_ns,
                sha256=sha,
            )

        try:
            extracted = ext.extract(abs_path)
        except Exception as exc:  # noqa: BLE001 — every extractor lib has its own errors
            summary["extract_failed"] += 1
            logger.exception("Extraction failed for %s: %s", abs_path, exc)
            if state is not None:
                state.mark_failed(path=str(abs_path),
                                    error=f"extract: {exc}")
            if summary["extract_failed"] >= cfg.extract_failure_threshold:
                click.secho(
                    f"Aborting: {summary['extract_failed']} extraction "
                    f"failures (>= extract_failure_threshold).",
                    fg="red", err=True,
                )
                break
            continue

        record = build_record(
            cfg=cfg, abs_path=abs_path, rel_path=rel_path,
            size_bytes=size_bytes, sha256=sha,
            extracted=extracted,
        )
        records.append(record)
        summary["extracted"] += 1

    return records, summary


def _print_summary(summary: dict[str, int]) -> None:
    click.echo("─── Summary ────────────────────────────")
    for k, v in summary.items():
        click.echo(f"  {k:>22}: {v}")
    click.echo("────────────────────────────────────────")


# ─── Click root ──────────────────────────────────────────────────────────────


@click.group()
@click.version_option(__version__, prog_name="skava-publisher")
@click.option(
    "--config", "-c", type=click.Path(exists=True, path_type=Path),
    required=True, envvar="SKAVA_PUBLISHER_CONFIG",
    help="Path to the YAML config (also: env SKAVA_PUBLISHER_CONFIG).",
)
@click.pass_context
def main(ctx: click.Context, config: Path) -> None:
    """SKAVA Publisher — local-node metadata extractor + uploader."""
    cfg = load_config(config)
    _setup_logging(cfg.log_level)
    ctx.obj = cfg


# ─── scan ───────────────────────────────────────────────────────────────────


@main.command()
@click.option(
    "--out", "-o", type=click.Path(path_type=Path),
    default="-",
    help="Output JSON path (- for stdout).",
)
@click.option(
    "--force/--no-force", default=False,
    help="Re-extract even files marked published in state.db.",
)
@click.option(
    "--no-state", is_flag=True, default=False,
    help="Skip the state.db lookup/update — pure ad-hoc scan.",
)
@click.pass_obj
def scan(cfg: PublisherConfig, out: Path, force: bool, no_state: bool) -> None:
    """Walk + extract + write JSON manifest. No network call."""
    state_ctx = open_state(cfg.state.db_path) if not no_state else None
    try:
        state = state_ctx.__enter__() if state_ctx is not None else None
        records, summary = _scan_and_extract(cfg, state, force=force)
    finally:
        if state_ctx is not None:
            state_ctx.__exit__(None, None, None)

    body = json.dumps({"records": records}, indent=2, default=str, ensure_ascii=False)
    if str(out) == "-":
        click.echo(body)
    else:
        dump_manifest(records, out)
        click.echo(f"Wrote {len(records)} records to {out}", err=True)
    _print_summary(summary)


# ─── validate ───────────────────────────────────────────────────────────────


@main.command()
@click.option(
    "--manifest", "-m", type=click.Path(exists=True, path_type=Path),
    required=False,
    help="JSON manifest to validate. If omitted, scans + validates in one pass.",
)
@click.pass_obj
def validate(cfg: PublisherConfig, manifest: Path | None) -> None:
    """POST to SKAVA's /internal/ingestion/dry-run (no DB writes)."""
    if manifest is not None:
        records = json.loads(manifest.read_text(encoding="utf-8")).get("records", [])
        summary = {"loaded_from_file": len(records)}
    else:
        with open_state(cfg.state.db_path) as state:
            records, summary = _scan_and_extract(cfg, state)
    if not records:
        click.secho("No records to validate.", fg="yellow")
        sys.exit(0)
    try:
        result = do_validate(cfg, records,
                              source_ref=f"publisher@{cfg.node.code}")
    except UploadError as exc:
        click.secho(f"Validation failed: {exc}", fg="red", err=True)
        sys.exit(2)
    click.secho(f"Validated {len(records)} records.", fg="green")
    click.echo(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    _print_summary(summary)


# ─── publish ────────────────────────────────────────────────────────────────


@main.command()
@click.option(
    "--manifest", "-m", type=click.Path(exists=True, path_type=Path),
    required=False,
    help="JSON manifest to publish. Default: scan + publish in one pass.",
)
@click.option(
    "--yes", "-y", is_flag=True, default=False,
    help="Skip confirmation prompt (use for cron / scripted runs).",
)
@click.option(
    "--force/--no-force", default=False,
    help="Re-extract + republish files marked published in state.db.",
)
@click.pass_obj
def publish(cfg: PublisherConfig, manifest: Path | None,
             yes: bool, force: bool) -> None:
    """POST to SKAVA's /internal/ingestion/run — REAL ingestion."""
    if manifest is not None:
        records = json.loads(manifest.read_text(encoding="utf-8")).get("records", [])
        state = None
    else:
        state_ctx = open_state(cfg.state.db_path)
        state = state_ctx.__enter__()
        records, summary = _scan_and_extract(cfg, state, force=force)
        _print_summary(summary)

    if not records:
        click.secho("Nothing to publish — no new or modified files.",
                     fg="yellow")
        return

    click.echo(f"About to publish {len(records)} record(s) to "
                f"{cfg.skava.api_url} as node {cfg.node.code}.")
    if not yes and not click.confirm("Proceed?", default=True):
        click.secho("Cancelled by operator.", fg="yellow")
        return

    try:
        result = do_publish(cfg, records,
                             source_ref=f"publisher@{cfg.node.code}")
    except UploadError as exc:
        click.secho(f"Publish failed: {exc}", fg="red", err=True)
        if state is not None:
            for r in records:
                state.mark_failed(path=r["provenance_json"].get("__abs_path", ""),
                                    error=str(exc))
        sys.exit(2)
    click.secho(f"✓ Published {len(records)} record(s).", fg="green")
    click.echo(json.dumps(result, indent=2, default=str, ensure_ascii=False))

    # On success, mark each file as published in state.db.
    if state is not None:
        for r in records:
            obs_id = r.get("obs_id")
            rel = r.get("provenance_json", {}).get("rel_path")
            if obs_id and rel:
                # Find the abs path from the rel by scanning roots — cheap
                # since the path is in the manifest's provenance.
                for root in cfg.scan.roots:
                    candidate = (Path(root) / rel).resolve()
                    if candidate.is_file():
                        state.mark_published(
                            path=str(candidate), obs_id=str(obs_id),
                        )
                        break


# ─── watch ───────────────────────────────────────────────────────────────────


@main.command()
@click.option(
    "--interval", "-i", type=int, default=None,
    help="Override config watch.interval_seconds.",
)
@click.option(
    "--once", is_flag=True, default=False,
    help="Run exactly one loop iteration and exit (useful for cron).",
)
@click.pass_obj
def watch(cfg: PublisherConfig, interval: int | None, once: bool) -> None:
    """Loop: scan + publish every ``interval_seconds``. SIGTERM-safe."""
    interval = interval or cfg.watch.interval_seconds
    stop = {"flag": False}

    def _onsig(signum, _frame):
        click.echo(f"Received signal {signum}; finishing current iteration "
                    "and exiting…", err=True)
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _onsig)
    signal.signal(signal.SIGINT, _onsig)

    iteration = 0
    while not stop["flag"]:
        iteration += 1
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        click.echo(f"[{ts}] watch iteration #{iteration}")
        try:
            with open_state(cfg.state.db_path) as state:
                records, summary = _scan_and_extract(cfg, state)
                _print_summary(summary)
                if records:
                    result = do_publish(cfg, records,
                                          source_ref=f"watch@{cfg.node.code}")
                    click.secho(f"  ✓ published {len(records)} record(s).",
                                  fg="green")
                    for r in records:
                        obs_id = r.get("obs_id")
                        rel = r.get("provenance_json", {}).get("rel_path")
                        if obs_id and rel:
                            for root in cfg.scan.roots:
                                candidate = (Path(root) / rel).resolve()
                                if candidate.is_file():
                                    state.mark_published(
                                        path=str(candidate),
                                        obs_id=str(obs_id),
                                    )
                                    break
                else:
                    click.echo("  nothing to publish.")
        except UploadError as exc:
            click.secho(f"  ✗ iteration failed: {exc}", fg="red", err=True)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Watch iteration crashed: %s", exc)
            click.secho(f"  ✗ iteration crashed: {exc}", fg="red", err=True)
        if once:
            break
        # Sleep but stay SIGTERM-responsive: short sub-sleeps.
        slept = 0
        while slept < interval and not stop["flag"]:
            time.sleep(min(2, interval - slept))
            slept += 2


# ─── status ──────────────────────────────────────────────────────────────────


@main.command()
@click.pass_obj
def status(cfg: PublisherConfig) -> None:
    """Print state.db summary + recent failures."""
    with open_state(cfg.state.db_path) as state:
        counts = state.counts()
        click.echo(f"State DB: {state.path}")
        click.echo("Counts by status:")
        if not counts:
            click.echo("  (empty — no files seen yet)")
        for k, v in counts.items():
            click.echo(f"  {k:>12}: {v}")
        click.echo("Recent failures (up to 10):")
        rows = list(state.conn.execute(
            "SELECT path, last_error FROM files WHERE last_status='failed' "
            "ORDER BY first_seen DESC LIMIT 10"
        ))
        if not rows:
            click.echo("  (none)")
        for row in rows:
            click.echo(f"  {row['path']}")
            click.echo(f"    └─ {row['last_error']}")
