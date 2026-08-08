"""The in-app Docs tab: list the repo's markdown, then open one.

The viewer listed ARCHITECTURE, INTEGRATIONS and UPGRADING and answered
"Could not open the document: Error: empty doc" for every one of them. The
list working and the file not is the useful half of that: whatever broke sat
between the two, not in auth and not in the docs directory.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import run_migrations
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

GOOD_PASSWORD = "Str0ng-Passphrase-For-Tests!"


@pytest.fixture(autouse=True)
def _reset_middleware_state():
    import app.web.middleware.rate_limit as rl

    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()
    yield
    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()


@pytest.fixture(autouse=True)
async def _init_db(tmp_path):
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


@pytest.fixture()
async def auth_headers():
    user = await create_user("docsreader", GOOD_PASSWORD, "Docs Reader", role=Role.admin)
    return {"Authorization": f"Bearer {await create_access_token(user)}"}


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def _files(node) -> list[str]:
    if node.get("type") == "file":
        return [node["path"]]
    out: list[str] = []
    for child in node.get("children", []):
        out.extend(_files(child))
    return out


def test_the_list_offers_the_repo_docs(client, auth_headers):
    r = client.get("/api/docs/list", headers=auth_headers)
    assert r.status_code == 200, r.text
    names = _files(r.json()["root"])
    assert "ARCHITECTURE.md" in names, names


def test_every_listed_document_can_actually_be_opened(client, auth_headers):
    """The list and the reader have to agree about the path.

    Offering a file the reader then refuses is worse than not listing it:
    the viewer is the only place a reader learns the docs exist.
    """
    listed = _files(client.get("/api/docs/list", headers=auth_headers).json()["root"])
    assert listed, "nothing listed — the fixture is not exercising anything"

    for path in listed:
        r = client.get("/api/docs/file", params={"path": path}, headers=auth_headers)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
        body = r.json()
        assert body.get("content"), f"{path} came back with no content"
        assert body["size"] > 0


def test_the_viewer_never_opens_a_document_it_has_not_seen_listed():
    """A hardcoded default is a second list, and it had already drifted.

    docsRepoLoad opened USER_GUIDE.md, or no/HURTIGSTART.md on a Norwegian
    UI. docs/ holds neither, so the tab opened on "Could not open the
    document" every time — beside a working list of the files that do exist.

    Naming a preferred candidate is fine; opening one without checking the
    tree is what broke. So the rule is about the call, not the name: every
    docsRepoOpen in the loader takes a variable that came from the listing.
    """
    import pathlib
    import re

    js = pathlib.Path("app/web/static/app-integrations.js").read_text(encoding="utf-8")
    literal_opens = re.findall(r"docsRepoOpen\(\s*['\"][^'\"]*\.md['\"]", js)
    assert not literal_opens, (
        f"a document is opened by name without checking the listing: {literal_opens}"
    )
    assert "_docsFileList(data.root)" in js, (
        "the default is not being chosen from what the listing offered"
    )


def test_the_swagger_link_points_at_the_app_s_own_docs_url():
    """The link is a second copy of a URL FastAPI already decides.

    It read /api/docs, which is the prefix the in-app documentation router
    sits behind — /api/docs/list and /api/docs/file exist there, the bare path
    does not. So the button 404'd, and the only clue was that nothing opened.
    """
    import pathlib
    import re

    from app.web.server import OPENAPI_DOCS_URL

    docs_url = OPENAPI_DOCS_URL

    html = pathlib.Path("app/web/static/index.html").read_text()
    links = re.findall(r'<a href="([^"]+)"[^>]*>Swagger', html)
    assert links, "the Swagger button is gone"
    for href in links:
        assert href == docs_url, (
            f"button points at {href!r}, app serves the UI at {docs_url!r}"
        )


def test_swagger_assets_are_version_pinned(client, auth_headers):
    response = client.get("/docs", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "swagger-ui-dist@5.32.12/" in response.text
    assert "swagger-ui-dist@5/" not in response.text
    assert "fastapi.tiangolo.com/img/favicon" not in response.text
    assert '<script nonce="' in response.text
    assert "'nonce-" in response.headers["content-security-policy"]
    assert "'unsafe-inline'" not in response.headers["content-security-policy"]
