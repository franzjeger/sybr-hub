"""A deploy reaches every browser on its next load, without a hard reload.

Asset URLs carried hand-bumped ?v= numbers. A file changed without its number,
browsers kept their cached copy, and the change reached nobody: an onboarding
fix sat behind an old app-chrome.js because its number was never touched.

The interface is ES modules now. The shell names one, main.js; the rest are
reached through imports, which a browser resolves without the importing URL's
query. So the server writes ?v= into the imports as well, one digest over the
whole module graph, and the shell's main.js carries the same one.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.web.routes import frontend
from app.web.server import create_app

# A relative module specifier in served source, with whatever query it has.
_SPECIFIER = re.compile(r"""(['"])\./([A-Za-z0-9_-]+\.js)(\?v=[^'"]*)?\1""")


@pytest.fixture()
def client():
    return TestClient(create_app())


def _entry_version(html: str) -> str:
    match = re.search(r'<script type="module" src="/static/main\.js\?v=([0-9a-f]{12})">', html)
    assert match, "the shell must load main.js as a module, with ?v="
    return match.group(1)


def test_the_shell_names_each_asset_by_its_content_hash(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"
    for name in ("app.css", "theme-init.js", "guacamole.min.js"):
        digest = frontend._file_digest(frontend._STATIC_DIR / name)
        assert f"/static/{name}?v={digest}" in r.text, name


def test_the_shell_loads_one_module_versioned_by_the_whole_graph(client):
    html = client.get("/").text
    assert re.findall(r'<script\b[^>]*type="module"', html) == ['<script type="module"'], (
        "one entry module"
    )
    assert not re.search(r'<script src="/static/app[\w-]*\.js', html), "no classic app scripts"
    modules, digest = frontend._module_graph()
    assert _entry_version(html) == digest
    names = {path.name for path in modules}
    assert {"main.js", "app.js", "app-esc.js", "app-chrome.js", "app-markup-handlers.js"} <= names


def test_every_import_a_served_module_makes_carries_the_graph_version(client):
    """No module is reachable under a URL the version does not cover."""
    modules, digest = frontend._module_graph()
    assert len(modules) > 20
    for path in sorted(modules):
        r = client.get(f"/static/{path.name}?v={digest}")
        assert r.status_code == 200, path.name
        assert r.headers["content-type"].startswith("text/javascript"), path.name
        specifiers = _SPECIFIER.findall(r.text)
        if path.name == "main.js":
            assert len(specifiers) >= 20, "main.js imports every module"
        for _, name, query in specifiers:
            assert query == f"?v={digest}", f"{path.name} imports ./{name}{query}"
            assert (frontend._STATIC_DIR / name).is_file(), (
                f"{path.name} imports a missing ./{name}"
            )


def test_a_change_to_any_module_moves_every_module_url(client):
    """A leaf at the bottom of the graph is the case a per-file hash misses:
    the modules importing it are unchanged, so their URLs would not move and
    the browser would keep them, importing the old leaf."""
    leaf = frontend._STATIC_DIR / "app-esc.js"
    original = leaf.read_bytes()
    before = _entry_version(client.get("/").text)
    try:
        leaf.write_bytes(original + b"\n// a deploy\n")
        after = _entry_version(client.get("/").text)
        assert after != before
        served = client.get(f"/static/app.js?v={after}").text
        assert f"'./app-esc.js?v={after}'" in served
        assert f"?v={before}" not in served
    finally:
        leaf.write_bytes(original)
    assert _entry_version(client.get("/").text) == before, "and back when the bytes are"


def test_a_module_under_the_graph_version_is_immutable_and_any_other_revalidates(client):
    _, digest = frontend._module_graph()
    pinned = client.get(f"/static/app-ui.js?v={digest}")
    assert "immutable" in pinned.headers["cache-control"]
    stale = client.get("/static/app-ui.js?v=000000000000")
    assert stale.headers["cache-control"] == "no-cache"
    assert f"./app-esc.js?v={digest}" in stale.text, "an old URL serves the current graph"
    bare = client.get("/static/app-ui.js")
    assert bare.headers["cache-control"] == "no-cache"
    # A file's own content hash is not the graph's: it does not pin a module.
    own = frontend._file_digest(frontend._STATIC_DIR / "app-ui.js")
    assert client.get(f"/static/app-ui.js?v={own}").headers["cache-control"] == "no-cache"


def test_a_revalidated_module_answers_304_when_unchanged(client):
    first = client.get("/static/app-api.js")
    etag = first.headers["etag"]
    again = client.get("/static/app-api.js", headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["etag"] == etag
    other = client.get("/static/app-ui.js", headers={"If-None-Match": etag})
    assert other.status_code == 200, "another module's tag does not match"
    stale = client.get("/static/app-api.js", headers={"If-None-Match": '"old-tag"'})
    assert stale.status_code == 200


def test_the_rewrite_follows_a_graph_it_has_not_seen(client, tmp_path, monkeypatch):
    """On a synthetic tree: multi-line imports, side-effect imports, an import
    of a module the shell never names, and a version written into the file
    by hand (replaced, not doubled)."""
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text(
        '<link rel="stylesheet" href="/static/a.css">'
        '<script type="module" src="/static/main.js"></script>'
    )
    (static / "a.css").write_text("body{}")
    (static / "main.js").write_text(
        "import './a.js';\nimport {\n  b,\n  c,\n} from \"./b.js?v=1001\";\nb(c);\n"
    )
    (static / "a.js").write_text("import {b} from './b.js';\nexport const a = b;\n")
    (static / "b.js").write_text("export function b() {}\nexport const c = 1;\n")
    (static / "unused.js").write_text("export const u = 1;\n")
    monkeypatch.setattr(frontend, "_STATIC_DIR", static)

    modules, digest = frontend._module_graph()
    assert {p.name for p in modules} == {"main.js", "a.js", "b.js"}
    assert _entry_version(client.get("/").text) == digest
    main = client.get(f"/static/main.js?v={digest}").text
    assert f"import './a.js?v={digest}';" in main
    assert f'}} from "./b.js?v={digest}";' in main
    assert "1001" not in main
    assert f"from './b.js?v={digest}'" in client.get("/static/a.js").text
    # Not in the graph: served as it is, by its own content hash.
    unused = client.get("/static/unused.js")
    assert unused.headers["cache-control"] == "no-cache"
    assert "etag" in unused.headers

    (static / "b.js").write_text("export function b() {}\nexport const c = 2;  // a deploy\n")
    _, after = frontend._module_graph()
    assert after != digest
    assert _entry_version(client.get("/").text) == after
    assert f"from './b.js?v={after}'" in client.get("/static/a.js").text


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
    digest = frontend._file_digest(frontend._STATIC_DIR / "app.css")
    pinned = client.get(f"/static/app.css?v={digest}")
    assert "immutable" in pinned.headers["cache-control"]
    stale = client.get("/static/app.css?v=1001")
    assert stale.headers["cache-control"] == "no-cache"
    bare = client.get("/static/app.css")
    assert bare.headers["cache-control"] == "no-cache"


def test_the_translations_url_is_versioned_too(client):
    """app-i18n.js fetches ui_i18n.json itself, so the shell hands it the URL."""
    html = client.get("/").text
    digest = frontend._file_digest(frontend._STATIC_DIR / "ui_i18n.json")
    assert f'<meta name="sybr-i18n" content="/static/ui_i18n.json?v={digest}">' in html


def test_the_service_worker_cache_version_covers_every_module():
    """The worker serves /static/ cache-first and evicts only when its version
    changes, so a module the digest left out would be held across deploys."""
    covered = set(frontend._digest_inputs())
    modules, _ = frontend._module_graph()
    assert modules <= covered, sorted(p.name for p in modules - covered)
    leaf = frontend._STATIC_DIR / "app-hooks.js"
    original = leaf.read_bytes()
    before = frontend._static_digest()
    try:
        leaf.write_bytes(original + b"\n// a deploy\n")
        assert frontend._static_digest() != before
    finally:
        leaf.write_bytes(original)
    assert frontend._static_digest() == before
