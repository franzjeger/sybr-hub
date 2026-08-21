"""What an account may reach, in one table both the server and the screen read.

Roles were applied a route at a time: 84 of 331 endpoints carried a
``require_role``, and the interface hid nothing at all. So a viewer saw the
whole menu, clicked into things, and met a wall — or worse, met no wall,
because the route that needed the check was one of the 247 without one.

Decorating the remaining 247 is 247 chances to forget one, and the forgotten
one is the one that matters. The same argument as the write guard, and the same
answer: name the *features*, not the routes.

A feature is a thing a person goes to do — administer users, reach a customer's
network over VPN, deploy a policy. Each names the role floor and the capability
it needs. Routes ask this table what they require; ``/auth/me`` sends the list
this account resolves to, and the interface hides ``data-requires`` elements
that are not in it.

One source, two readers. A screen cannot drift from the rule it displays,
because it is not holding a copy of the rule.

**A feature is not a permission to write.** ``can_write`` still decides that,
in the middleware, for every mutating request. This decides what is *reachable*
at all, which is the axis roles were always meant to cover and never did.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.user import Role


@dataclass(frozen=True)
class Feature:
    """One thing a person goes to do, and what it takes to reach it."""

    key: str
    role: Role
    # Capability names from the user record. Empty means the role is the whole
    # requirement — most features are like that.
    needs: tuple[str, ...] = ()
    # Views this feature owns, so the interface can hide them by name without
    # a second table mapping one to the other.
    views: tuple[str, ...] = ()


# Ordered as the navigation is, so a reader can check it against the menu.
FEATURES: tuple[Feature, ...] = (
    # ── What everybody who signs in can do ──
    Feature("dashboard", Role.viewer, views=("overview", "home", "customer-detail")),
    Feature("customers", Role.viewer, views=("customers", "history", "history-report", "files")),
    # Browsing named baselines and reading a customer's conformance is a read,
    # the same one the customer card already shows a viewer — so viewer-level,
    # with per-tenant access still enforced on the evaluate route itself.
    Feature("assessments", Role.viewer, views=("assessments",)),
    # The policy overview is the same read, one screen: what the customer has
    # in production, what moved since last run, and the Sybr standard's gaps.
    # Read-only, and the underlying inventory is already a customer-read, so
    # viewer-level, with per-tenant access enforced on the route itself.
    Feature("policy_overview", Role.viewer, views=("policy-overview",)),
    Feature("reports", Role.viewer, views=()),
    Feature("documentation", Role.viewer, views=("docs",)),

    # ── Technician: reaching customer systems ──
    Feature("audit", Role.technician, views=("audit",)),
    Feature("network", Role.technician, views=("network", "tls", "tailscale")),
    Feature("remote", Role.technician, views=("hosts", "terminal", "rdp", "ssh", "browser")),
    Feature("vpn", Role.technician, views=("vpn",)),
    Feature("integrations", Role.technician, views=("integrations",)),
    Feature("ai", Role.technician, views=("ai",)),

    # ── Admin: changing how the toolkit itself behaves ──
    Feature("settings", Role.admin, views=("setup",)),
    Feature("users", Role.admin, views=()),
    Feature("provisioning", Role.admin, views=("provision",)),
    Feature("logs", Role.admin, views=("logs",)),

    # ── The one that writes into somebody else's production ──
    Feature("policy_deploy", Role.technician, needs=("tenant_write",), views=("policy-deploy",)),
)

_BY_KEY = {f.key: f for f in FEATURES}


class UnknownFeature(KeyError):
    """A route asked for a feature that does not exist.

    Loud rather than permissive: a typo that silently granted access would be
    the worst possible failure for this table.
    """


def get(key: str) -> Feature:
    if key not in _BY_KEY:
        raise UnknownFeature(
            f"No feature {key!r}. Known: {', '.join(sorted(_BY_KEY))}"
        )
    return _BY_KEY[key]


def allows(user, feature: Feature) -> bool:
    """Whether this account reaches this feature."""
    role = getattr(user, "role", None)
    if role is None or not role >= feature.role:
        return False
    return all(getattr(user, capability, False) for capability in feature.needs)


def available_to(user) -> list[str]:
    """The feature keys this account resolves to, for /auth/me."""
    return [f.key for f in FEATURES if allows(user, f)]


def views_for(user) -> list[str]:
    """The views this account may open.

    Sent alongside the feature keys because the interface hides by view name in
    the navigation and by feature key on individual controls, and deriving one
    from the other in JavaScript would be the copy of the rule this exists to
    avoid.
    """
    return sorted({v for f in FEATURES if allows(user, f) for v in f.views})
