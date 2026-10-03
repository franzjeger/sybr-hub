"""No custom logo is the normal case, and it is not an error."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.web.server import create_app


def test_no_logo_answers_204_and_a_logo_is_served(tmp_path, monkeypatch):
    import app.core.config as config

    logo = tmp_path / "logo.png"
    monkeypatch.setattr(config, "LOGO_PATH", logo)
    with TestClient(create_app()) as client:
        assert client.get("/api/settings/logo").status_code == 204
        logo.write_bytes(b"\x89PNG\r\n\x1a\n")
        r = client.get("/api/settings/logo")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_the_settings_page_does_not_fetch_the_logo_on_load():
    from pathlib import Path

    html = (Path(__file__).resolve().parent.parent / "app/web/static/index.html").read_text()
    assert 'src="/api/settings/logo"' not in html
