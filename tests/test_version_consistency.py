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


def test_build_info_exposes_a_describe_so_the_card_shows_commits_ahead():
    # The admin version card shows `describe`, not the bare tag `version`: a
    # deployment several commits past the last tag must not read as stuck at that
    # tag (which looked like the self-updater had done nothing). describe is the
    # tag, or the tag plus its commits-ahead (tag-N-gSHA) — either way it carries
    # the clean version as its leading component; the report footer keeps version.
    from app.core.version import get_build_info

    bi = get_build_info()
    assert bi.get("describe"), "the version card needs a describe string"
    assert bi["describe"] == bi["version"] or bi["describe"].startswith(bi["version"] + "-")


def _clear_version_cache(monkeypatch):
    import app.core.version as v

    monkeypatch.setattr(v, "_build_info_cache", None)
    monkeypatch.setattr(v, "_build_info_ts", 0)


def _fake_git(monkeypatch, *, tag: str | None, describe: str | None):
    """Make `git describe` answer with a controlled (possibly stale) tag.

    ``check_output(..., text=True)`` returns ``str``, so the fake must too —
    returning bytes would make ``.startswith("v")`` raise and the caller's
    ``except`` would swallow it, masking the very path under test.
    """
    import app.core.version as v

    def _fake(cmd, **kwargs):
        # check_output takes the command as its first positional arg (a list).
        a = list(cmd)
        if a[:2] == ["git", "describe"] and "--abbrev=0" in a:
            return (tag + "\n") if tag else ""
        if a[:2] == ["git", "describe"]:
            return (describe + "\n") if describe else ""
        if a[:2] == ["git", "rev-parse"]:
            return "abc1234\n"
        if a[:2] == ["git", "log"]:
            return "2026-08-15T00:00:00+00:00\n"
        return ""

    monkeypatch.setattr(v.subprocess, "check_output", _fake)


def test_a_stale_local_tag_does_not_hide_a_newer_changelog_release(tmp_path, monkeypatch):
    """The box that advanced branch-only: git says v1.1.1, changelog says v1.1.3.

    The version badge must name the release the box actually has (the changelog
    one), not the last tag its local repo ever received — otherwise the badge
    and the changelog panel disagree, which is what this whole fix removes.
    """
    import app.core.version as v

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Endringslogg\n\n## v1.1.3 (2026-08-15)\n### Nytt\n- ting\n\n"
        "## v1.1.2 (2026-08-14)\n### Nytt\n- ting\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(v, "_CHANGELOG", changelog)
    _clear_version_cache(monkeypatch)
    _fake_git(monkeypatch, tag="v1.1.1", describe="v1.1.1-3-g4f5c3da")

    bi = v.get_build_info()
    assert bi["version"] == "1.1.3", "the changelog release wins over the stale tag"
    assert bi["describe"] == "1.1.3", "describe must not anchor on the missing old tag"


def test_a_newer_local_tag_still_wins_over_the_changelog(tmp_path, monkeypatch):
    """The fallback only lifts a stale tag; a current tag is the source of truth."""
    import app.core.version as v

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Endringslogg\n\n## v1.1.2 (2026-08-14)\n- ting\n", encoding="utf-8")
    monkeypatch.setattr(v, "_CHANGELOG", changelog)
    _clear_version_cache(monkeypatch)
    _fake_git(monkeypatch, tag="v1.1.3", describe="v1.1.3")

    bi = v.get_build_info()
    assert bi["version"] == "1.1.3", "the tag is authoritative when it is the newest"
    assert bi["describe"] == "1.1.3"


def test_no_local_tag_at_all_falls_back_to_the_changelog(tmp_path, monkeypatch):
    """A checkout with no reachable tag still reports the release it carries."""
    import app.core.version as v

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Endringslogg\n\n## v1.1.3 (2026-08-15)\n- ting\n", encoding="utf-8")
    monkeypatch.setattr(v, "_CHANGELOG", changelog)
    _clear_version_cache(monkeypatch)
    _fake_git(monkeypatch, tag=None, describe=None)

    bi = v.get_build_info()
    assert bi["version"] == "1.1.3"
    assert bi["describe"] == "1.1.3"


def test_a_missing_changelog_does_not_break_version_resolution(monkeypatch):
    """No changelog file and no tag: the static fallback still answers."""
    import app.core.version as v

    _clear_version_cache(monkeypatch)
    monkeypatch.setattr(v, "_latest_changelog_version", lambda: None)
    _fake_git(monkeypatch, tag="v1.1.1", describe="v1.1.1")

    bi = v.get_build_info()
    assert bi["version"] == "1.1.1"
    assert bi["describe"] == "1.1.1"


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
