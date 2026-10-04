"""The interface's typeface is served from this host, not from Google Fonts.

app.css imported Cairo from fonts.googleapis.com at runtime, so every page
load told Google which address was using the hub, and offline the interface
fell back to a system font. The font files are vendored, hashed in the vendor
manifest, and the CSP no longer names Google's font hosts.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from app.web.server import create_app

STATIC = pathlib.Path(__file__).resolve().parent.parent / "app" / "web" / "static"


@pytest.fixture
def client():
    return TestClient(create_app())


def test_app_css_loads_nothing_from_another_origin():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert not re.search(r"@import\s+url\(\s*['\"]?https?://", css)
    assert not re.search(r"url\(\s*['\"]?(https?:)?//", css), "a font or image from another origin"
    assert "vendor/cairo-latin.woff2" in css


def test_the_font_files_are_vendored_and_hashed():
    manifest = json.loads((STATIC / "vendor" / "manifest.json").read_text(encoding="utf-8"))
    for name in ("cairo-latin.woff2", "cairo-latin-ext.woff2", "cairo-OFL.txt"):
        assert name in manifest, name
        assert (STATIC / "vendor" / name).is_file(), name
    assert (STATIC / "vendor" / "cairo-latin.woff2").read_bytes()[:4] == b"wOF2"


def test_the_csp_names_no_google_font_host(client):
    csp = client.get("/").headers.get("content-security-policy", "")
    assert "fonts.googleapis.com" not in csp
    assert "fonts.gstatic.com" not in csp
    assert "font-src 'self'" in csp


def test_the_font_is_served_as_a_font(client):
    r = client.get("/static/vendor/cairo-latin.woff2")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("font/woff2")
    assert r.content[:4] == b"wOF2"
