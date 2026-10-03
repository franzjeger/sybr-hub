"""Every Azure SDK class the audit imports exists in the installed SDK.

The imports are function-local, so nothing runs them until an Azure audit
does. azure-mgmt-resource 24 stopped exporting ResourceManagementClient from
the package root, and the suite would have stayed green while the first real
audit failed. CI installs the newest versions pyproject allows, so this test
is where an upgrade that moves a class shows up.
"""

from __future__ import annotations

import ast
import importlib
import pathlib

import pytest

APP = pathlib.Path(__file__).resolve().parent.parent / "app"


def _azure_imports() -> list[tuple[str, str, str]]:
    found = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("azure."):
                for alias in node.names:
                    found.append((str(path.relative_to(APP)), node.module, alias.name))
    return found


IMPORTS = _azure_imports()


def test_the_scan_finds_the_azure_clients():
    names = {name for _, _, name in IMPORTS}
    assert {"ResourceManagementClient", "RecoveryServicesBackupClient"} <= names


@pytest.mark.parametrize(("where", "module", "name"), IMPORTS)
def test_the_class_exists_where_the_code_imports_it(where, module, name):
    assert hasattr(importlib.import_module(module), name), f"{where}: {module}.{name}"
