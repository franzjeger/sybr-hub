"""A deploy reaches every browser on its next load, without a hard reload.

Asset URLs carried hand-bumped ?v= numbers. A file changed without its number,
browsers kept their cached copy, and the change reached nobody: an onboarding
fix sat behind an old app-chrome.js because its number was never touched.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.web.routes import frontend
from app.web.server import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _asset_versions(html: str) -> dict[str, str]:
    return dict(re.findall(r'(/static/app[A-Za-z-]*\.js)\?v=([0-9a-f]{12})"', html))


def test_the_shell_names_each_asset_by_its_content_hash(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"
    versions = _asset_versions(r.text)
    assert "/static/app.js" in versions and "/static/app-chrome.js" in versions
    path = frontend._STATIC_DIR / "app.js"
    assert versions["/static/app.js"] == frontend._file_digest(path)


def test_changing_a_file_changes_its_url(client, tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text('<script src="/static/app.js?v=1001"></script>')
    (static / "app.js").write_text("var a = 1;")
    monkeypatch.setattr(frontend, "_STATIC_DIR", static)
    first = client.get("/").text
    (static / "app.js").write_text("var a = 2; // a deploy")
    second = client.get("/").text
    assert first != second
    assert "v=1001" not in first and "v=1001" not in second


def test_a_hashed_url_is_cacheable_and_any_other_revalidates(client):
    digest = frontend._file_digest(frontend._STATIC_DIR / "app.js")
    pinned = client.get(f"/static/app.js?v={digest}")
    assert "immutable" in pinned.headers["cache-control"]
    stale = client.get("/static/app.js?v=1001")
    assert stale.headers["cache-control"] == "no-cache"
    bare = client.get("/static/app.js")
    assert bare.headers["cache-control"] == "no-cache"


def test_the_translations_url_is_versioned_too(client):
    """app.js fetches ui_i18n.json itself, so the shell hands it the URL."""
    html = client.get("/").text
    digest = frontend._file_digest(frontend._STATIC_DIR / "ui_i18n.json")
    assert f'<meta name="sybr-i18n" content="/static/ui_i18n.json?v={digest}">' in html
