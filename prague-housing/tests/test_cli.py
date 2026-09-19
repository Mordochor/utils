from __future__ import annotations

from pathlib import Path

from prague_housing.cli import main


def test_init_writes_config(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dest = tmp_path / "config.yaml"
    assert main(["init", "--dest", str(dest)]) == 0
    assert dest.exists()
    assert "destinations:" in dest.read_text(encoding="utf-8")
    assert main(["init", "--dest", str(dest)]) == 1
