"""The policies Sybr deploys, as data.

Same shape as baselines and for the same reason: a technician arguing about
what the standard should contain must not have to touch the code that deploys
it. A template is a JSON document holding Conditional Access policy bodies as
Graph accepts them, plus the placeholders a tenant has to fill in.

**Placeholders are required, not defaulted.** Every policy here excludes a
break-glass group, and the id of that group differs per tenant. A default
would be an id belonging to somebody else's tenant, which Graph would either
reject or — worse — accept as an exclusion that excludes nobody. Rendering
refuses while a placeholder is unfilled.

Bodies carry a ``why`` in both languages. It is stripped before anything is
sent to Graph, and shown to whoever is approving the deployment: a plan that
says "3 policies will be created" is not a plan somebody can consent to.
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
from typing import Any

logger = logging.getLogger(__name__)

TEMPLATE_DIR = pathlib.Path(__file__).parent.parent / "policy_templates"

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")

# Carried for the operator, never sent to Graph. ``why`` explains the policy;
# ``tier`` groups it (essential/recommended/extended); ``requires_license``
# names a licence the policy needs (e.g. entra_p2 for risk-based policies).
# Graph rejects unknown fields, so every one of these is stripped before send.
_ANNOTATIONS = {"why", "tier", "requires_license"}


class TemplateError(Exception):
    """A template is malformed, or cannot be rendered for this tenant."""


def _localised(value: Any, lang: str) -> str:
    if isinstance(value, dict):
        return str(value.get(lang) or value.get("no") or "")
    return str(value or "")


def load_template(template_id: str) -> dict:
    path = TEMPLATE_DIR / f"{template_id}.json"
    if not path.is_file():
        raise TemplateError(f"No policy template {template_id!r}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    for required in ("id", "version", "name", "policies"):
        if required not in doc:
            raise TemplateError(f"Template {template_id!r} is missing {required!r}")
    seen: set[str] = set()
    for policy in doc["policies"]:
        name = policy.get("displayName")
        if not name:
            raise TemplateError(f"A policy in {template_id!r} has no displayName")
        if name in seen:
            raise TemplateError(f"Duplicate policy name {name!r} in {template_id!r}")
        seen.add(name)
    return doc


def list_templates(lang: str = "no") -> list[dict]:
    out = []
    for path in sorted(TEMPLATE_DIR.glob("*.json")):
        try:
            doc = load_template(path.stem)
        except TemplateError as exc:
            logger.warning("Skipping malformed template %s: %s", path.name, exc)
            continue
        out.append({
            "id": doc["id"],
            "version": doc["version"],
            "name": _localised(doc["name"], lang),
            "description": _localised(doc.get("description"), lang),
            "policies": len(doc["policies"]),
            "requires": sorted(doc.get("requires", {})),
        })
    return out


def placeholders_in(doc: dict) -> set[str]:
    return set(_PLACEHOLDER.findall(json.dumps(doc["policies"])))


def render(template_id: str, values: dict[str, str], *, lang: str = "no") -> list[dict]:
    """Fill a template's placeholders for one tenant.

    Refuses on anything unfilled. A half-rendered policy is one whose
    break-glass exclusion is the literal string "{{break_glass_group}}" — an
    exclusion that excludes nobody, in a policy that locks out everybody.
    """
    doc = load_template(template_id)
    needed = placeholders_in(doc)
    missing = sorted(n for n in needed if not str(values.get(n, "")).strip())
    if missing:
        raise TemplateError(
            "Cannot render "
            f"{template_id!r}: {', '.join(missing)} not supplied. Every policy "
            f"here excludes a break-glass group, and an unfilled exclusion "
            f"excludes nobody."
        )

    rendered = json.dumps(doc["policies"])
    for name in needed:
        rendered = rendered.replace("{{" + name + "}}", str(values[name]))
    policies = json.loads(rendered)

    for policy in policies:
        for annotation in _ANNOTATIONS:
            policy.pop(annotation, None)
    return policies


def annotations(template_id: str, lang: str = "no") -> dict[str, str]:
    """{displayName: why}, for the screen where somebody approves this."""
    doc = load_template(template_id)
    return {
        str(p["displayName"]): _localised(p.get("why"), lang)
        for p in doc["policies"]
    }


def metadata(template_id: str, lang: str = "no") -> dict[str, dict]:
    """{displayName: {why, tier, requires_license}} for the selection screen.

    The operator picks which policies to deploy from a comprehensive suite, so
    the interface needs the rationale, the tier, and any licence a policy
    requires — the same annotations render() strips before Graph.
    """
    doc = load_template(template_id)
    return {
        str(p["displayName"]): {
            "why": _localised(p.get("why"), lang),
            "tier": str(p.get("tier") or ""),
            "requires_license": str(p.get("requires_license") or ""),
        }
        for p in doc["policies"]
    }
