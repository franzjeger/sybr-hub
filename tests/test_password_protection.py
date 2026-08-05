"""Password protection read the wrong endpoint, then drew a conclusion anyway.

/v1.0/settings is not a segment — it is the beta alias, and v1.0 answers 400
"Resource not found for the segment 'settings'". So the directory settings
list was empty on every run since this shipped.

The section then warned "Custom banned password list is not configured",
which is a claim about the tenant made from a request that failed. Both
warnings appeared in the same audit: the 400, and the finding drawn from it.
"""

from __future__ import annotations

import asyncio
import pathlib

from app.modules.base import SectionStatus
from app.modules.m365_audit.sections.password_protection import PasswordProtectionSection


class _Graph:
    """Answers the three calls this section makes, whichever way is asked for."""

    def __init__(self, settings=None, fail_settings=False):
        self.settings = settings if settings is not None else []
        self.fail_settings = fail_settings
        self.paths: list[str] = []

    async def get_all(self, path, params=None, beta=False):
        self.paths.append(path)
        if self.fail_settings:
            raise RuntimeError("Client error '400 Bad Request'")
        return self.settings

    async def get(self, path, params=None, beta=False):
        self.paths.append(path)
        return {} if "authenticationMethodsPolicy" in path else None


def _run(graph, tmp_path) -> tuple:
    section = PasswordProtectionSection(pathlib.Path(tmp_path), graph)
    result = asyncio.run(section.collect())
    return result, graph


def test_it_asks_the_endpoint_that_exists(tmp_path):
    _, graph = _run(_Graph(), tmp_path)
    assert "groupSettings" in graph.paths, (
        f"still reading a segment v1.0 does not have: {graph.paths}"
    )
    assert "settings" not in graph.paths


def test_a_failed_read_is_not_reported_as_nothing_configured(tmp_path):
    """The warning and the 400 used to arrive together in the same run."""
    result, _ = _run(_Graph(fail_settings=True), tmp_path)
    warns = " ".join(result.warns)
    assert "fetch failed" in warns, "the failure itself must still be reported"
    assert "not configured" not in warns, (
        "a finding about the tenant was drawn from a request that failed"
    )


def test_a_real_reading_with_no_custom_list_still_warns(tmp_path):
    """The counterpart: a measured absence is a finding and must survive."""
    settings = [{
        "displayName": "Password Rule Settings",
        "values": [
            {"name": "BannedPasswordCheckOnPremisesMode", "value": "Audit"},
            {"name": "EnableBannedPasswordCheckOnPremises", "value": "True"},
            {"name": "BannedPasswordList", "value": ""},
        ],
    }]
    result, _ = _run(_Graph(settings=settings), tmp_path)
    assert "not configured" in " ".join(result.warns)
