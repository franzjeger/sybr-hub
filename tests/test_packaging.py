"""Keep the wheel entry point and runtime dependency metadata installable."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_console_entry_point_module_is_included_in_wheel():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert config["project"]["scripts"]["sybr-hub"] == "main:run"
    assert "main" in config["tool"]["setuptools"]["py-modules"]


def test_web_and_report_assets_are_declared_as_package_data():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    package_data = set(config["tool"]["setuptools"]["package-data"]["app"])
    assert {
        "baselines/*.json",
        "reports/templates/*",
        "web/static/*",
        "web/static/icons/*",
        "web/static/vendor/*",
    } <= package_data


def test_declared_runtime_dependencies_cover_imported_features():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dependencies = {item.split("[")[0].split("<")[0].split(">=")[0].lower() for item in config["project"]["dependencies"]}
    required = {
        "python-multipart",
        "websockets",
        "textual",
        "azure-mgmt-costmanagement",
        "azure-mgmt-authorization",
        "azure-mgmt-resource-subscriptions",
        "pyopenssl",
        "pychrome",
        "anthropic",
        "nh3",
    }
    assert required <= dependencies
