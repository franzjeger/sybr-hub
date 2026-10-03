"""Run the real audit collectors against fake clients, and read back what they wrote.

Why
---
A parser test that hands the parser a fixture written by hand tests the parser
against its author's idea of the format, not against the format. When the
collector and that idea drift apart, the test keeps passing. The Azure backup
parser is the case that made this rig: its tests fed it a "Vault: x" block and
a "Name  Type  Status" table that the collector never wrote, while the
collector wrote each protected item as "      - <name>  Status:...", a line the
parser skipped because it starts with "-". For months every VM read as having
no backup, with a high-priority recommendation naming each one, and every test
was green. A test built on this rig runs the collector that writes the file,
so the parser reads exactly what a real run leaves on disk.

What it fakes
-------------
Microsoft Graph, at the HTTP layer. ``FakeGraph`` puts an
``httpx.MockTransport`` under a real ``GraphClient``, so the client's own code
runs as it does in production: ``get_all`` follows ``@odata.nextLink`` page by
page, a 401/403 becomes ``GraphPermissionError``, a 404 an ``HTTPStatusError``.
The test supplies a dict from Graph path to answer, and hands ``fake.client``
to the section::

    async with FakeGraph({"users": [...]}, page_size=2) as fake:
        section = UsersSection(tmp_path, fake.client)
        files = await run_sections(section)

Azure, at the SDK client. ``FakeAzureAuth`` stands in for ``AuthManager``: its
``compute_client_for`` and the other ``*_client_for`` factories return fake SDK
clients built from a dict of operation path to result::

    auth = FakeAzureAuth(
        compute={"virtual_machines.list_all": [vm]},
        recovery={"vaults.list_by_subscription_id": [vault]},
        backup={"backup_protected_items.list": items_of_vault},
    ).install(monkeypatch)
    await AzureComputeSection(tmp_path, auth, sub_id=SUB)._collect_vms()

Reading back. ``read_output(out_dir)`` returns ``{file name: text}`` for every
.txt and .json in the run directory, decrypted with ``encrypted_read_text`` and
with a file that holds a collector's error blanked, which is how
``build_report_context`` reads a run. ``sidecars=False`` drops the .json files
and so reads a run recorded before a collector wrote one.

Not faked here: Exchange takes its data from the PowerShell helper as a dict,
so pass that dict to ``ExchangeSection`` directly; DNS resolves through
``dns._check_domain``, which a test monkeypatches.

Adding an endpoint
------------------
Graph: add the path as a key, exactly as the section passes it to ``get`` or
``get_all`` (no version prefix, no query string; a usage report is
``reports/<name>(period='<period>')``), and the answer as its value:

* a list is a collection, served as ``{"value": [...]}`` in pages of
  ``page_size`` with ``@odata.nextLink`` between them;
* ``refused()`` answers with a Graph error, 403 by default;
* ``CsvReport(rows)`` answers a usage report (``get_report``) as CSV;
* an exception instance is raised as a transport failure;
* a callable is called with the ``httpx.Request`` and its result served
  as above, for an answer that depends on the query;
* anything else (a dict, a number) is served as JSON as it is.

A key may start with ``beta/`` or ``v1.0/`` to answer one Graph version only.
A path with no key gets a 404 and is recorded in ``fake.unrouted``, so a test
can assert that every call it meant to answer was answered. Every request is
kept in ``fake.requests``. Only GET is served: an audit reads, and a collector
that writes gets a 405.

Azure: add the client kind as a keyword (``compute``, ``network``,
``resource``, ``storage``, ``monitor``, ``advisor``, ``recovery``,
``log_analytics``, ``avd``, or ``backup`` for the
``RecoveryServicesBackupClient`` the backup collector builds itself, which
``install(monkeypatch)`` puts in place), and in it the operation path as the
collector calls it. Values follow the same rules:
an exception is raised, a callable is called with the call's arguments, and
anything else is returned. A kind or operation that is not configured raises,
which the collectors handle as a failed read. ``subscriptions={sub_id: {...}}``
gives one subscription its own clients.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

from app.core.encryption import encrypted_read_text
from app.modules.base import BaseSection
from app.modules.m365_audit.graph_client import GraphClient
from app.reports.parsers import _is_error_payload

# ── Reading a run back ────────────────────────────────────────────────────────


def read_output(
    out_dir: Path, *, sidecars: bool = True, blank_errors: bool = True
) -> dict[str, str]:
    """Every .txt and .json the collectors wrote, as build_report_context reads them.

    Sorted by name and decrypted. A file holding a collector's error instead of
    its data is blanked to "" as the report does (blank_errors=False keeps the
    text, for a test about the error itself). sidecars=False leaves out the
    .json files: a run from before the collectors wrote them.
    """
    suffixes = (".txt", ".json") if sidecars else (".txt",)
    files: dict[str, str] = {}
    for path in sorted(out_dir.iterdir()):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        text = encrypted_read_text(path)
        if blank_errors and _is_error_payload(text):
            text = ""
        files[path.name] = text
    return files


async def run_sections(*sections: BaseSection, sidecars: bool = True) -> dict[str, str]:
    """Run each section's collect() in order, then read back their run directory."""
    out_dirs = {section.out_dir for section in sections}
    if len(out_dirs) != 1:
        raise ValueError("the sections must share one run directory")
    for section in sections:
        await section.collect()
    return read_output(out_dirs.pop(), sidecars=sidecars)


# ── Microsoft Graph ───────────────────────────────────────────────────────────

_GRAPH_ORIGIN = "https://graph.microsoft.com"
_VERSIONS = ("v1.0", "beta")


@dataclass(frozen=True)
class Refusal:
    """A Graph error response. Made by refused()."""

    status: int
    code: str
    message: str


def refused(
    status: int = 403,
    code: str = "Authorization_RequestDenied",
    message: str = "Insufficient privileges to complete the operation.",
) -> Refusal:
    """Answer with a Graph error. The default is the 403 of a missing permission."""
    return Refusal(status, code, message)


@dataclass(frozen=True)
class CsvReport:
    """A usage report as Graph serves it to get_report: CSV, one dict per row."""

    rows: list[dict[str, str]] = field(default_factory=list)


class _Credential:
    """A token credential that never leaves the process."""

    async def get_token(self, *_scopes, **_kwargs):
        return SimpleNamespace(token="collector-rig-token")


class FakeGraph:
    """Graph for a real GraphClient, answering by path from a dict.

    See the module docstring for what a route may answer with.
    """

    def __init__(self, routes: dict[str, Any], *, page_size: int = 100) -> None:
        if page_size < 1:
            raise ValueError("page_size must be at least 1")
        self.routes = dict(routes)
        self.page_size = page_size
        self.requests: list[httpx.Request] = []
        self.unrouted: list[str] = []
        self.client = GraphClient(_Credential())
        self.client._http = httpx.AsyncClient(transport=httpx.MockTransport(self._handle))

    async def __aenter__(self) -> FakeGraph:
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self.client._http.aclose()

    def requested(self, path: str) -> list[httpx.Request]:
        """The requests made for one path, every page and version included."""
        return [r for r in self.requests if _split(r)[1] == path]

    # The transport. Runs inside GraphClient's own request loop.

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        version, path = _split(request)
        if request.method != "GET":
            return _error(request, 405, "Request_BadRequest", "the collector rig serves GET only")
        for key in (f"{version}/{path}", path):
            if key in self.routes:
                return self._answer(request, version, path, self.routes[key])
        self.unrouted.append(path)
        return _error(request, 404, "Request_ResourceNotFound", f"no route for {path}")

    def _answer(
        self, request: httpx.Request, version: str, path: str, answer: Any
    ) -> httpx.Response:
        if callable(answer) and not isinstance(answer, type):
            answer = answer(request)
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, Refusal):
            return _error(request, answer.status, answer.code, answer.message)
        if isinstance(answer, CsvReport):
            return _csv(request, answer.rows)
        if isinstance(answer, list):
            return self._page(request, version, path, answer)
        return httpx.Response(200, json=answer, request=request)

    def _page(self, request: httpx.Request, version: str, path: str, items: list) -> httpx.Response:
        page = int(request.url.params.get("$skiptoken", "0"))
        start = page * self.page_size
        body: dict[str, Any] = {"value": items[start : start + self.page_size]}
        if start + self.page_size < len(items):
            body["@odata.nextLink"] = f"{_GRAPH_ORIGIN}/{version}/{path}?$skiptoken={page + 1}"
        return httpx.Response(200, json=body, request=request)


def _split(request: httpx.Request) -> tuple[str, str]:
    """("v1.0", "users/u1/authentication/methods") from a request URL."""
    version, _, path = request.url.path.lstrip("/").partition("/")
    if version not in _VERSIONS:
        return "", request.url.path.lstrip("/")
    return version, path


def _error(request: httpx.Request, status: int, code: str, message: str) -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"code": code, "message": message}}, request=request
    )


def _csv(request: httpx.Request, rows: list[dict[str, str]]) -> httpx.Response:
    out = io.StringIO()
    if rows:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return httpx.Response(
        200,
        content=out.getvalue().encode("utf-8-sig"),
        headers={"Content-Type": "text/csv"},
        request=request,
    )


# ── Azure ─────────────────────────────────────────────────────────────────────

_AZURE_KINDS = (
    "compute",
    "network",
    "resource",
    "storage",
    "monitor",
    "advisor",
    "recovery",
    "log_analytics",
    "avd",
    "backup",
)


def sdk_client(operations: dict[str, Any]) -> SimpleNamespace:
    """A stand-in for an Azure SDK management client.

    Keys are operation paths as the collector calls them,
    "virtual_machines.list_all"; values are what the call returns. An exception
    is raised instead, and a callable is called with the call's arguments, for
    an answer that depends on them (the items of one vault). An operation not
    listed does not exist, so calling it raises AttributeError.
    """
    root = SimpleNamespace()
    for dotted, answer in operations.items():
        *groups, operation = dotted.split(".")
        node = root
        for group in groups:
            if not hasattr(node, group):
                setattr(node, group, SimpleNamespace())
            node = getattr(node, group)
        setattr(node, operation, _operation(answer))
    return root


def _operation(answer: Any) -> Callable[..., Any]:
    def call(*args, **kwargs):
        if isinstance(answer, BaseException):
            raise answer
        if callable(answer):
            return answer(*args, **kwargs)
        return answer

    return call


class _NoCredential:
    """What _az_credential() hands out: a credential that cannot get a token.

    The cost collector asks it for an ARM token before it calls the REST API,
    so this is what keeps that collector off the network.
    """

    def get_token(self, *_scopes, **_kwargs):
        raise RuntimeError("the collector rig makes no network calls")


class FakeAzureAuth:
    """Stands in for AuthManager on the Azure side.

    Keyword arguments configure a client kind for every subscription;
    ``subscriptions`` overrides kinds for one subscription id.
    """

    def __init__(
        self,
        *,
        subscriptions: dict[str, dict[str, dict[str, Any]]] | None = None,
        **clients: dict[str, Any],
    ) -> None:
        unknown = set(clients) | {k for kinds in (subscriptions or {}).values() for k in kinds}
        unknown -= set(_AZURE_KINDS)
        if unknown:
            raise TypeError(f"unknown Azure client kind(s): {sorted(unknown)}")
        self._clients = clients
        self._subscriptions = subscriptions or {}

    def client(self, kind: str, sub_id: str) -> SimpleNamespace:
        operations = self._subscriptions.get(sub_id, {}).get(kind, self._clients.get(kind))
        if operations is None:
            raise RuntimeError(f"no fake {kind} client for subscription {sub_id}")
        return sdk_client(operations)

    def install(self, monkeypatch) -> FakeAzureAuth:
        """Patch the SDK client a collector builds itself instead of asking auth for.

        The backup collector constructs RecoveryServicesBackupClient directly.
        """
        import azure.mgmt.recoveryservicesbackup as rsb

        monkeypatch.setattr(
            rsb,
            "RecoveryServicesBackupClient",
            lambda _credential, subscription_id: self.client("backup", subscription_id),
        )
        return self

    def _az_credential(self) -> _NoCredential:
        return _NoCredential()

    def compute_client_for(self, sub_id: str) -> SimpleNamespace:
        return self.client("compute", sub_id)

    def network_client_for(self, sub_id: str) -> SimpleNamespace:
        return self.client("network", sub_id)

    def resource_client_for(self, sub_id: str) -> SimpleNamespace:
        return self.client("resource", sub_id)

    def storage_client_for(self, sub_id: str) -> SimpleNamespace:
        return self.client("storage", sub_id)

    def monitor_client_for(self, sub_id: str) -> SimpleNamespace:
        return self.client("monitor", sub_id)

    def advisor_client_for(self, sub_id: str) -> SimpleNamespace:
        return self.client("advisor", sub_id)

    def recovery_client_for(self, sub_id: str) -> SimpleNamespace:
        return self.client("recovery", sub_id)

    def log_analytics_client_for(self, sub_id: str) -> SimpleNamespace:
        return self.client("log_analytics", sub_id)

    def avd_client_for(self, sub_id: str) -> SimpleNamespace:
        return self.client("avd", sub_id)
