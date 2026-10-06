"""Domain and service modules must not depend on HTTP handlers."""

import ast
from pathlib import Path


def check() -> None:
    violations = []
    for directory in ("app/core", "app/services", "app/modules"):
        for path in Path(directory).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                modules = []
                if isinstance(node, ast.ImportFrom):
                    if node.level:
                        package = list(path.parent.parts)
                        base = package[: len(package) - node.level + 1]
                        module = ".".join([*base, *([node.module] if node.module else [])])
                    else:
                        module = node.module or ""
                    modules = [module, *(module + "." + alias.name for alias in node.names)]
                elif isinstance(node, ast.Import):
                    modules = [a.name for a in node.names]
                if any(m == "app.web" or m.startswith("app.web.") for m in modules):
                    violations.append(f"{path}:{node.lineno}")
    if violations:
        raise SystemExit("HTTP dependencies below the web layer: " + ", ".join(violations))
    print("Core, services and modules have no HTTP-layer imports")


if __name__ == "__main__":
    check()
