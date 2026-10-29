"""The publisher's file outcomes and its extractor order.

Run from tools/skava-publisher with the package installed:
``pip install -e . pytest && pytest``.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from click.testing import CliRunner

from skava_publisher import cli
from skava_publisher.extractors import discover, find_extractor
from skava_publisher.state import open_state


def _plain_fits(path: Path, obs_id: str) -> Path:
    hdu = fits.PrimaryHDU(np.zeros((4, 4), dtype=np.float32))
    hdu.header["OBS_ID"] = obs_id
    hdu.writeto(path)
    return path


def _psrfits(path: Path) -> Path:
    primary = fits.PrimaryHDU()
    primary.header["FITSTYPE"] = "PSRFITS"
    subint = fits.BinTableHDU.from_columns([fits.Column(name="DATA", format="E", array=np.zeros(2))],
                                           name="SUBINT")
    fits.HDUList([primary, subint]).writeto(path)
    return path


@pytest.fixture
def config(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    cfg = tmp_path / "publisher.yaml"
    cfg.write_text(json.dumps({
        "skava": {"api_url": "http://skava.invalid", "internal_api_key": "test-internal-key"},
        "node": {"code": "N1", "file_serve_url_pattern": "file:///data/{relpath}"},
        "scan": {"roots": [str(data)], "compute_checksum": False},
        "state": {"db_path": str(tmp_path / "state.db")},
        "watch": {"enabled": True},
    }))
    return cfg


def _status(tmp_path: Path) -> dict[str, tuple[str, str | None]]:
    with open_state(tmp_path / "state.db") as state:
        rows = state.conn.execute("SELECT path, last_status, last_error FROM files").fetchall()
    return {Path(r["path"]).name: (r["last_status"], r["last_error"]) for r in rows}


def test_psrfits_is_tried_before_plain_fits(tmp_path: Path):
    extractors = discover()
    assert [e.name for e in extractors].index("psrfits") < [e.name for e in extractors].index("fits")
    assert find_extractor(extractors, _psrfits(tmp_path / "pulsar.fits")).name == "psrfits"
    assert find_extractor(extractors, _plain_fits(tmp_path / "image.fits", "img")).name == "fits"


def test_only_the_records_skava_took_are_marked_published(tmp_path, config, monkeypatch):
    data = tmp_path / "data"
    _plain_fits(data / "a.fits", "obs-a")
    _plain_fits(data / "b.fits", "obs-b")
    posted: list[list[dict]] = []

    def fake_publish(cfg, records, *, source_ref=None):
        posted.append(records)
        bad = next(i for i, r in enumerate(records) if r["obs_id"] == "obs-b")
        return {"summary": {"processed": 2, "skipped": 1, "validation_errors": [
            {"index": bad, "code": "node_not_found", "message": "Node not found: N1"}]}}

    monkeypatch.setattr(cli, "do_publish", fake_publish)
    result = CliRunner().invoke(cli.main, ["-c", str(config), "publish", "--yes"])
    assert result.exit_code == 0, result.output
    status = _status(tmp_path)
    assert status["a.fits"] == ("published", None)
    assert status["b.fits"][0] == "failed"
    assert "node_not_found" in status["b.fits"][1]

    # The next run sends only the refused file again.
    CliRunner().invoke(cli.main, ["-c", str(config), "publish", "--yes"])
    assert [r["obs_id"] for r in posted[1]] == ["obs-b"]


def test_a_failed_upload_marks_every_file_failed(tmp_path, config, monkeypatch):
    _plain_fits(tmp_path / "data" / "a.fits", "obs-a")

    def boom(cfg, records, *, source_ref=None):
        raise cli.UploadError("SKAVA /internal/ingestion/run returned 503")

    monkeypatch.setattr(cli, "do_publish", boom)
    result = CliRunner().invoke(cli.main, ["-c", str(config), "publish", "--yes"])
    assert result.exit_code == 2
    status, error = _status(tmp_path)["a.fits"]
    assert status == "failed" and "503" in error


def _scan_to(config: Path, manifest: Path) -> None:
    result = CliRunner().invoke(cli.main, ["-c", str(config), "scan", "--no-state", "-o", str(manifest)])
    assert result.exit_code == 0, result.output


def _publish_manifest(config: Path, manifest: Path, monkeypatch, result=None):
    monkeypatch.setattr(cli, "do_publish",
                        lambda cfg, records, *, source_ref=None: result or {"summary": {}})
    out = CliRunner().invoke(cli.main, ["-c", str(config), "publish", "-m", str(manifest), "--yes"])
    assert out.exit_code == 0, out.output
    return out


def test_publishing_a_manifest_updates_the_state(tmp_path, config, monkeypatch):
    _plain_fits(tmp_path / "data" / "a.fits", "obs-a")
    manifest = tmp_path / "manifest.json"
    _scan_to(config, manifest)
    _publish_manifest(config, manifest, monkeypatch)
    assert _status(tmp_path)["a.fits"] == ("published", None)


def test_a_file_changed_after_the_manifest_is_not_marked_published(tmp_path, config, monkeypatch):
    path = _plain_fits(tmp_path / "data" / "a.fits", "obs-a")
    manifest = tmp_path / "manifest.json"
    _scan_to(config, manifest)
    path.unlink()
    _plain_fits(path, "obs-a-v2")                      # new contents, new size/mtime
    import os
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    out = _publish_manifest(config, manifest, monkeypatch)
    assert "state.db is not updated" in out.output
    assert "a.fits" not in _status(tmp_path)           # the next scan extracts it again


def test_same_relative_path_under_two_roots_keeps_each_files_outcome(tmp_path, config, monkeypatch):
    root_b = tmp_path / "data-b"
    root_b.mkdir()
    payload = json.loads(config.read_text())
    payload["scan"]["roots"].append(str(root_b))
    config.write_text(json.dumps(payload))
    _plain_fits(tmp_path / "data" / "x.fits", "obs-a")
    _plain_fits(root_b / "x.fits", "obs-b")
    manifest = tmp_path / "manifest.json"
    _scan_to(config, manifest)
    records = json.loads(manifest.read_text())["records"]
    bad = next(i for i, r in enumerate(records) if r["obs_id"] == "obs-b")
    _publish_manifest(config, manifest, monkeypatch, result={"summary": {"validation_errors": [
        {"index": bad, "code": "validation_error", "message": "bad"}]}})
    with open_state(tmp_path / "state.db") as state:
        rows = {r["path"]: r["last_status"] for r in state.conn.execute("SELECT path, last_status FROM files")}
    assert rows[str((tmp_path / "data" / "x.fits").resolve())] == "published"
    assert rows[str((root_b / "x.fits").resolve())] == "failed"


def test_a_manifest_without_file_fingerprints_leaves_the_state_alone(tmp_path, config, monkeypatch):
    _plain_fits(tmp_path / "data" / "a.fits", "obs-a")
    manifest = tmp_path / "manifest.json"
    _scan_to(config, manifest)
    payload = json.loads(manifest.read_text())
    manifest.write_text(json.dumps({"records": payload["records"]}))   # hand-made, older publisher
    _publish_manifest(config, manifest, monkeypatch)
    assert _status(tmp_path) == {}


def test_watch_does_nothing_when_disabled(tmp_path, config, monkeypatch):
    payload = json.loads(config.read_text())
    payload["watch"]["enabled"] = False
    config.write_text(json.dumps(payload))
    _plain_fits(tmp_path / "data" / "a.fits", "obs-a")
    monkeypatch.setattr(cli, "do_publish", lambda *a, **k: pytest.fail("must not publish"))
    result = CliRunner().invoke(cli.main, ["-c", str(config), "watch", "--once"])
    assert result.exit_code == 0
    assert "not watching" in result.output


def test_a_file_changed_during_the_upload_is_extracted_again(tmp_path, config, monkeypatch):
    import os
    path = _plain_fits(tmp_path / "data" / "a.fits", "obs-a")
    manifest = tmp_path / "manifest.json"
    _scan_to(config, manifest)

    def publish_while_the_file_changes(cfg, records, *, source_ref=None):
        st = path.stat()
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
        return {"summary": {}}

    monkeypatch.setattr(cli, "do_publish", publish_while_the_file_changes)
    out = CliRunner().invoke(cli.main, ["-c", str(config), "publish", "-m", str(manifest), "--yes"])
    assert out.exit_code == 0, out.output
    with open_state(tmp_path / "state.db") as state:
        # Published as the manifest described it; the newer file is not that one.
        assert state.needs_extraction(str(path.resolve()), mtime_ns=path.stat().st_mtime_ns)
