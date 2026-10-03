"""Route introspection that does not depend on FastAPI internals.

The auth-coverage guards need every dependency callable reachable from a
route, including nested ones. FastAPI ships ``get_flat_dependant`` for this,
but it is an internal — it was removed in a later release, and the guards
died with an ImportError on a machine whose ``fastapi>=0.111.0,<1.0`` range
resolved newer than the one CI happened to have cached. The tests that exist
to prove every route is authenticated are the worst possible thing to have
break on a dependency bump, since a collection error looks nothing like
"routes are unguarded" and both stop the suite the same way.

``Dependant.dependencies`` and ``Dependant.call`` are the documented shape of
the tree and have been stable for years, so walk it here instead.
"""

from __future__ import annotations

from typing import Any


def flat_dependency_calls(route: Any) -> list:
    """Every dependency callable reachable from *route*, flattened.

    Iterative and id-deduplicated: the tree can share sub-dependencies, and a
    shared node would otherwise be visited once per path to it.
    """
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return []

    calls: list = []
    seen: set[int] = set()
    stack: list = list(getattr(dependant, "dependencies", []))
    while stack:
        dep = stack.pop()
        if id(dep) in seen:
            continue
        seen.add(id(dep))
        call = getattr(dep, "call", None)
        if call is not None:
            calls.append(call)
        stack.extend(getattr(dep, "dependencies", []))
    return calls


def has_dependency_named(route: Any, prefix: str) -> bool:
    """True when any reachable dependency's qualname starts with *prefix*.

    Dependency factories return closures defined inside them, so the closure's
    ``__qualname__`` carries the factory name — matching on that is what lets
    ``require_role(...)`` and ``require_customer_access(...)`` be recognised.
    """
    return any(
        getattr(call, "__qualname__", "").startswith(prefix)
        for call in flat_dependency_calls(route)
    )
