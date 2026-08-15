"""What the OneDrive sharing scan actually covered.

The section published "Drives scanned: N" and a count of anonymous links, and
neither number meant what it looked like:

* it asked for ``sites/root/drives`` — the document libraries of the *root
  site*. Not the other site collections, and not OneDrive at all, which lives
  under ``users/{id}/drive``. A file headed "ONEDRIVE / SHAREPOINT EXTERNAL
  SHARING AUDIT" was describing one site.
* it read permissions on each drive's root only, so a link on a file inside a
  folder was invisible.
* a drive it could not read was swallowed by a bare ``except: continue`` and
  still counted in "Drives scanned", so "unreadable" and "nothing shared" were
  the same number.

The walk is bounded — it runs against someone's live tenant — so the fix is
not "look everywhere" but "look wider, and say exactly how far you got".
"""

from __future__ import annotations

import httpx
import pytest

from app.core.encryption import encrypted_read_text
from app.modules.m365_audit.graph_client import GraphRequestBudgetExceeded
from app.modules.m365_audit.sections.onedrive_sharing import OneDriveSharingSection


def _http_400(path):
    req = httpx.Request("GET", f"https://graph.microsoft.com/v1.0/{path}")
    return httpx.HTTPStatusError(
        "400 Bad Request", request=req, response=httpx.Response(400, request=req)
    )


def _anon_perm(url="https://x/y"):
    return {"link": {"scope": "anonymous", "type": "view", "webUrl": url},
            "roles": ["read"]}


def _ext_perm(upn="guest_example.com#EXT#@acme.onmicrosoft.com"):
    return {"link": {"scope": "users", "type": "view"},
            "roles": ["read"],
            "grantedToV2": {"user": {"id": "u9", "userPrincipalName": upn}}}


class FakeGraph:
    """Serves a small tenant: two sites, one user OneDrive, a nested folder."""

    def __init__(self, *, sites=None, site_drives=None, user_drives=None,
                 root_perms=None, children=None, refuse=(),
                 expand_unsupported=False, item_perms=None):
        self.sites = sites if sites is not None else [
            {"id": "site-a", "displayName": "Intranett"},
            {"id": "site-b", "displayName": "Prosjekt"},
        ]
        self.site_drives = site_drives if site_drives is not None else {
            "site-a": [{"id": "d-a", "name": "Delte dokumenter"}],
            "site-b": [{"id": "d-b", "name": "Dokumenter"}],
        }
        self.user_drives = user_drives if user_drives is not None else {
            "u1": [{"id": "d-u1", "name": "OneDrive"}],
        }
        self.root_perms = root_perms or {}
        self.children = children or {}
        self.refuse = set(refuse)
        self.expand_unsupported = expand_unsupported
        self.item_perms = item_perms or {}
        self.calls: list[str] = []

    async def get(self, path, **kw):
        raise AssertionError(f"unexpected get({path})")

    async def get_all(self, path, **kw):
        claim = kw.get("before_request")
        if claim is not None and not claim():
            raise GraphRequestBudgetExceeded(path)
        self.calls.append(path)
        if path in self.refuse:
            raise RuntimeError(f"403 {path}")
        if path == "sites":
            return list(self.sites)
        if path.startswith("sites/") and path.endswith("/drives"):
            return list(self.site_drives.get(path.split("/")[1], []))
        if path.startswith("users/") and path.endswith("/drives"):
            return list(self.user_drives.get(path.split("/")[1], []))
        if path.endswith("/root/permissions"):
            return list(self.root_perms.get(path.split("/")[1], []))
        if "/items/" in path and path.endswith("/children"):
            params = kw.get("params") or {}
            if self.expand_unsupported and params.get("$expand"):
                raise _http_400(path)   # Graph rejects $expand=permissions here
            drive_id = path.split("/")[1]
            item_id = path.split("/items/")[1].split("/")[0]
            return list(self.children.get((drive_id, item_id), []))
        if "/items/" in path and path.endswith("/permissions"):
            drive_id = path.split("/")[1]
            item_id = path.split("/items/")[1].split("/")[0]
            return list(self.item_perms.get((drive_id, item_id), []))
        raise AssertionError(f"unexpected get_all({path})")


def _section(tmp_path, graph, users=None, **kw):
    return OneDriveSharingSection(
        tmp_path, graph, users_ref=users if users is not None else [{"id": "u1", "userPrincipalName": "ola@acme.no"}],
        **kw,
    )


def _out(tmp_path):
    return encrypted_read_text(tmp_path / "25_onedrive_sharing.txt")


class TestTheScanReachesTheWholeTenant:
    async def test_every_site_drive_and_every_user_onedrive_is_visited(self, tmp_path):
        graph = FakeGraph()
        await _section(tmp_path, graph).collect()

        assert "sites" in graph.calls, "site collections were never enumerated"
        assert "users/u1/drives" in graph.calls, "the user's OneDrive was never located"
        assert "users/u1/drive" not in graph.calls, "singular endpoint rejects app-only auth"
        for drive in ("d-a", "d-b", "d-u1"):
            assert f"drives/{drive}/root/permissions" in graph.calls, drive
        assert "Drives scanned       : 3" in _out(tmp_path)

    async def test_a_user_without_a_onedrive_is_not_counted_as_refused(self, tmp_path):
        """A 404 means no OneDrive was ever provisioned. Counting that as a
        refusal would make every tenant look partially unreadable."""
        graph = FakeGraph(user_drives={})
        await _section(tmp_path, graph).collect()
        assert "Drives refused       : 0" in _out(tmp_path)

    async def test_a_refused_user_drive_listing_makes_coverage_partial(self, tmp_path):
        graph = FakeGraph(refuse={"users/u1/drives"})
        await _section(tmp_path, graph).collect()
        out = _out(tmp_path)
        assert "Discovery failures   : 1" in out
        assert "Scan scope           : partial" in out

    async def test_missing_user_prerequisite_is_fetched_instead_of_assumed_empty(self, tmp_path):
        graph = FakeGraph()
        section = OneDriveSharingSection(
            tmp_path,
            graph,
            users_ref=[],
            users_complete=lambda: False,
        )
        # The fake's directory response used by this fallback.
        original_get_all = graph.get_all

        async def get_all(path, **kw):
            if path == "users":
                claim = kw.get("before_request")
                if claim is not None and not claim():
                    raise GraphRequestBudgetExceeded(path)
                graph.calls.append(path)
                return [{"id": "u1", "userPrincipalName": "ola@acme.no"}]
            return await original_get_all(path, **kw)

        graph.get_all = get_all
        await section.collect()

        assert "users" in graph.calls
        assert "users/u1/drives" in graph.calls
        assert "Scan scope           : complete" in _out(tmp_path)

    async def test_zero_discovered_drives_is_not_reported_as_a_clean_tenant(self, tmp_path):
        graph = FakeGraph(sites=[], site_drives={}, user_drives={})
        await _section(tmp_path, graph, users=[]).collect()
        out = _out(tmp_path)
        assert "Drives scanned       : 0" in out
        assert "Discovery failures   : 1" in out
        assert "Scan scope           : partial" in out


class TestALinkInsideAFolderIsFound:
    async def test_a_nested_anonymous_link_is_reported(self, tmp_path):
        graph = FakeGraph(
            sites=[{"id": "site-a", "displayName": "Intranett"}],
            site_drives={"site-a": [{"id": "d-a", "name": "Docs"}]},
            user_drives={},
            children={
                ("d-a", "root"): [
                    {"id": "f1", "name": "Kundeavtaler", "folder": {"childCount": 1},
                     "permissions": []},
                ],
                ("d-a", "f1"): [
                    {"id": "i1", "name": "Avtale.docx", "permissions": [_anon_perm()]},
                ],
            },
        )
        await _section(tmp_path, graph).collect()

        out = _out(tmp_path)
        assert "'Anyone' links       : 1" in out, "a link one folder down was missed"
        assert "Kundeavtaler/Avtale.docx" in out, "the path should say where it is"

    async def test_permissions_come_back_with_the_children_in_one_request(self, tmp_path):
        """$expand=permissions is what makes the walk affordable: one request
        per folder rather than one per item."""
        graph = FakeGraph(
            sites=[{"id": "s", "displayName": "S"}],
            site_drives={"s": [{"id": "d", "name": "D"}]},
            user_drives={},
            children={("d", "root"): [
                {"id": f"i{n}", "name": f"f{n}.docx", "permissions": []} for n in range(50)
            ]},
        )
        await _section(tmp_path, graph).collect()
        per_item = [c for c in graph.calls if "/items/i" in c]
        assert not per_item, f"one request per item: {per_item[:3]}"

    async def test_expand_permissions_400_falls_back_to_per_item_reads(self, tmp_path):
        """Graph 400s on $expand=permissions over children on some tenants. The
        scan must fall back to per-item permission reads and actually find the
        share, not fail every folder and report nothing (SR review, F6)."""
        graph = FakeGraph(
            sites=[{"id": "s", "displayName": "S"}],
            site_drives={"s": [{"id": "d", "name": "D"}]},
            user_drives={},
            expand_unsupported=True,
            children={("d", "root"): [{"id": "i1", "name": "Avtale.docx"}]},
            item_perms={("d", "i1"): [_anon_perm()]},
        )
        await _section(tmp_path, graph).collect()
        out = _out(tmp_path)
        assert "'Anyone' links       : 1" in out, "the fallback did not read permissions"
        assert "drives/d/items/i1/permissions" in graph.calls, "no per-item permission read"
        assert "unsupported on this tenant" in out
        assert "Scan scope           : complete" in out, "a successful fallback is still complete"

    async def test_an_incomplete_scan_does_not_claim_no_external_sharing(self, tmp_path):
        """Fail closed: a scan that could not read a folder must NOT print the
        clean 'no external sharing detected' verdict (SR review, F6)."""
        graph = FakeGraph(
            sites=[{"id": "s", "displayName": "S"}],
            site_drives={"s": [{"id": "d", "name": "D"}]},
            user_drives={},
            children={("d", "root"): [
                {"id": "secret", "name": "secret", "folder": {"childCount": 1}, "permissions": []},
            ]},
            refuse={"drives/d/items/secret/children"},
        )
        await _section(tmp_path, graph).collect()
        out = _out(tmp_path)
        assert "No external sharing or anonymous links detected." not in out
        assert "tenant-wide absence is NOT established" in out

    async def test_an_external_share_deeper_in_is_reported(self, tmp_path):
        graph = FakeGraph(
            sites=[{"id": "s", "displayName": "S"}],
            site_drives={"s": [{"id": "d", "name": "D"}]},
            user_drives={},
            children={("d", "root"): [
                {"id": "i1", "name": "Budsjett.xlsx", "permissions": [_ext_perm()]},
            ]},
        )
        await _section(tmp_path, graph).collect()
        assert "External user shares : 1" in _out(tmp_path)


class TestTheScanStatesWhatItCovered:
    async def test_a_clean_complete_scan_says_complete(self, tmp_path):
        graph = FakeGraph(user_drives={})
        await _section(tmp_path, graph).collect()
        out = _out(tmp_path)
        assert "Scan scope           : complete" in out
        assert "Drives refused       : 0" in out

    async def test_a_refused_drive_is_counted_not_swallowed(self, tmp_path):
        """The bare except: continue counted an unreadable drive in "Drives
        scanned" and moved on, so refused and empty were the same number."""
        graph = FakeGraph(user_drives={}, refuse={"drives/d-b/root/permissions"})
        await _section(tmp_path, graph).collect()

        out = _out(tmp_path)
        assert "Drives refused       : 1" in out
        assert "Drives scanned       : 1" in out, "a refused drive must not count as scanned"
        assert "Scan scope           : partial" in out

    async def test_hitting_the_folder_limit_is_declared(self, tmp_path):
        graph = FakeGraph(
            sites=[{"id": "s", "displayName": "S"}],
            site_drives={"s": [{"id": "d", "name": "D"}]},
            user_drives={},
            children={
                ("d", "root"): [
                    {"id": f"f{n}", "name": f"dir{n}", "folder": {}, "permissions": []}
                    for n in range(10)
                ],
                **{("d", f"f{n}"): [] for n in range(10)},
            },
        )
        await _section(tmp_path, graph, max_folders_per_drive=3).collect()

        out = _out(tmp_path)
        assert "Scan scope           : partial" in out
        assert "Scan did not complete" in out
        assert "folder limit 3" in out

    async def test_hitting_the_depth_limit_is_declared(self, tmp_path):
        graph = FakeGraph(
            sites=[{"id": "s", "displayName": "S"}],
            site_drives={"s": [{"id": "d", "name": "D"}]},
            user_drives={},
            children={
                ("d", "root"): [{"id": "a", "name": "a", "folder": {}, "permissions": []}],
                ("d", "a"): [{"id": "b", "name": "b", "folder": {}, "permissions": []}],
                ("d", "b"): [{"id": "c", "name": "c", "folder": {}, "permissions": []}],
                ("d", "c"): [{"id": "z", "name": "deep.docx", "permissions": [_anon_perm()]}],
            },
        )
        await _section(tmp_path, graph, max_depth=2).collect()

        out = _out(tmp_path)
        assert "depth limit 2" in out
        assert "Scan scope           : partial" in out
        # And the link below the limit is genuinely not claimed as absent.
        assert "'Anyone' links       : 0" in out

    async def test_an_unreadable_folder_makes_the_scan_partial(self, tmp_path):
        graph = FakeGraph(
            sites=[{"id": "s", "displayName": "S"}],
            site_drives={"s": [{"id": "d", "name": "D"}]},
            user_drives={},
            children={
                ("d", "root"): [
                    {"id": "secret", "name": "secret", "folder": {"childCount": 1},
                     "permissions": []},
                ],
            },
            refuse={"drives/d/items/secret/children"},
        )
        await _section(tmp_path, graph).collect()
        out = _out(tmp_path)
        assert "Folder failures      : 1" in out
        assert "Scan scope           : partial" in out

    async def test_the_request_budget_is_honoured(self, tmp_path):
        graph = FakeGraph()
        await _section(tmp_path, graph, max_requests=3).collect()
        assert len(graph.calls) <= 3, graph.calls
        assert "Scan scope           : partial" in _out(tmp_path)


class TestTheWarningsMatchTheCoverage:
    async def test_an_incomplete_scan_warns_that_absence_is_not_established(self, tmp_path):
        graph = FakeGraph(user_drives={}, refuse={"drives/d-b/root/permissions"})
        result = await _section(tmp_path, graph).collect()
        assert any("do not cover" in w for w in result.warns), result.warns

    async def test_a_clean_complete_scan_raises_nothing(self, tmp_path):
        graph = FakeGraph(user_drives={})
        result = await _section(tmp_path, graph).collect()
        assert result.warns == [], result.warns


@pytest.mark.parametrize("granted,expected", [
    ({"user": {"id": "u", "userPrincipalName": "a_b.com#EXT#@t.onmicrosoft.com"}}, True),
    ({"user": {"email": "x@example.com"}}, True),
    ({"user": {"id": "u", "userPrincipalName": "ola@acme.no"}}, False),
])
def test_external_user_detection(granted, expected):
    assert OneDriveSharingSection._is_external(granted) is expected


def test_all_permission_identity_shapes_are_examined():
    permission = {
        "grantedToV2": {"user": {"id": "internal", "userPrincipalName": "ola@acme.no"}},
        "grantedToIdentitiesV2": [
            {"user": {"id": "guest", "userPrincipalName": "guest#EXT#@acme.no"}},
        ],
    }
    identities = OneDriveSharingSection._granted_identities(permission)
    assert len(identities) == 2
    assert any(OneDriveSharingSection._is_external(item) for item in identities)
