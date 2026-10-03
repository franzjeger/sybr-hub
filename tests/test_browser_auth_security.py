"""Browser auth must stay in HttpOnly cookies, not JavaScript storage or URLs."""

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "web" / "static"


def test_frontend_never_persists_bearer_tokens():
    scripts = "\n".join(path.read_text() for path in STATIC.glob("*.js"))
    assert "localStorage.getItem('msptk_token')" not in scripts
    assert "localStorage.setItem('msptk_token'" not in scripts
    assert "localStorage.getItem('msptk_refresh')" not in scripts
    assert "localStorage.setItem('msptk_refresh'" not in scripts


def test_frontend_does_not_put_access_token_in_websocket_url():
    terminal_js = (STATIC / "app-infra.js").read_text()
    assert "ws/terminal?token=" not in terminal_js


def test_old_persisted_tokens_are_removed_during_upgrade():
    app_js = (STATIC / "app.js").read_text()
    assert "localStorage.removeItem('msptk_token')" in app_js
    assert "localStorage.removeItem('msptk_refresh')" in app_js
