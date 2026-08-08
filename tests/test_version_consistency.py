"""The product version has one source and every shipped surface follows it."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from app.core.version import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_package_metadata_reads_the_core_version_attribute():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert "version" in config["project"]["dynamic"]
    assert config["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "app.core.version.__version__",
    }
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_static_surfaces_do_not_ship_unrelated_legacy_versions():
    index = (ROOT / "app/web/static/index.html").read_text()
    worker = (ROOT / "app/web/static/sw.js").read_text()
    assert "v9.2.0" not in index
    assert f"const CACHE_VERSION = 'msptoolkit-v{__version__}'" in worker
    assert 'id="api-version-label"' in index
