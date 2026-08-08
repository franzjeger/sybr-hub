"""The git tag is the product version and every shipped surface follows it."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from app.core.version import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_package_metadata_is_derived_from_the_git_tag():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert "version" in config["project"]["dynamic"]
    assert "setuptools_scm" in config["tool"]
    # A hand-maintained attribute is what setuptools-scm replaces. Leaving the
    # old wiring in place would silently win over it.
    assert "version" not in config["tool"].get("setuptools", {}).get("dynamic", {})
    assert any("setuptools-scm" in r for r in config["build-system"]["requires"])


def test_the_static_fallback_is_well_formed():
    # A source checkout has neither a built _version.py nor installed metadata,
    # so this is the last-resort literal. get_build_info() prefers git describe,
    # which is what the deployed host actually reports.
    assert re.match(r"\d+\.\d+", __version__)


def test_ci_fetches_tags_so_a_build_can_resolve_the_version():
    # setuptools-scm reads `git describe`. actions/checkout defaults to a
    # depth-1 fetch carrying no tags, which yields 0.1.devN+g<sha> instead of
    # the release — with no error to notice.
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert workflow.count("fetch-depth: 0") == workflow.count("actions/checkout@")


def test_static_surfaces_do_not_ship_unrelated_legacy_versions():
    index = (ROOT / "app/web/static/index.html").read_text()
    worker = (ROOT / "app/web/static/sw.js").read_text()
    assert "v9.2.0" not in index
    # The service worker ships a placeholder. app/web/routes/frontend.py
    # rewrites CACHE_VERSION with the live version and a static-asset digest
    # before any browser sees it, so asserting a release number here would
    # reinstate the hand-bump this file no longer needs.
    assert "const CACHE_VERSION = 'msptoolkit-" in worker
    assert re.search(r"const CACHE_VERSION = 'msptoolkit-v\d+\.\d+\.\d+'", worker) is None
    assert 'id="api-version-label"' in index
