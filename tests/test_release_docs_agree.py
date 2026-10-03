"""The release version must be written identically in every place it is written.

This regression was found 2026-09-21: README said v1.1.8, ROADMAP said
v1.1.1, the CHANGELOG's newest entry was v1.1.8, and the repository had
zero git tags. The three human-maintained statements could drift
independently and nothing checked them. The tag itself cannot be checked
here (a CI checkout does not fetch tag objects), so this test pins the
three files to each other and to the newest ``## vX.Y.Z`` CHANGELOG
header — the same header ``app/core/version.py`` reads as its last
resort when no tag is present.

Releasing: promote ``## Ikke utgitt`` to ``## vX.Y.Z (date)``, update the
README Status line and the ROADMAP Versioning line in the same commit,
and tag that commit. This test fails until all three agree.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _latest_changelog_version() -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^##\s+v?(\d+\.\d+\.\d+)\b", text, flags=re.MULTILINE)
    assert match, "CHANGELOG.md has no '## vX.Y.Z' release header"
    return match.group(1)


def _readme_status_version() -> str:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    section = None
    for chunk in text.split("\n## "):
        if chunk.startswith("Status"):
            section = chunk
            break
    assert section, "README.md has no '## Status' section"
    match = re.search(r"\*\*v?(\d+\.\d+\.\d+)\*\*", section)
    assert match, "README.md Status section has no '**vX.Y.Z**' line"
    return match.group(1)


def _roadmap_release_version() -> str:
    text = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    match = re.search(r"current release is `v?(\d+\.\d+\.\d+)`", text)
    assert match, "ROADMAP.md has no 'current release is vX.Y.Z' line"
    return match.group(1)


def test_release_version_agrees_everywhere() -> None:
    changelog = _latest_changelog_version()
    readme = _readme_status_version()
    roadmap = _roadmap_release_version()
    assert readme == changelog and roadmap == changelog, (
        f"release version drifted: CHANGELOG {changelog}, README {readme}, "
        f"ROADMAP {roadmap} — update all three when cutting a release"
    )
