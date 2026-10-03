"""Risk radar chart data and SVG rendering."""

from __future__ import annotations

from app.reports.i18n import T

# ── Risk radar ─────────────────────────────────────────────────────────────────


def _build_risk_radar(context: dict, lang: str = "no") -> dict:
    """Compute risk scores per category for radar chart.

    Only axes backed by data we actually collected are returned. An axis whose
    source section failed, was throttled out, or never ran is *omitted* — not
    plotted at some neutral-looking default. A fabricated 80 on the Azure axis
    reads to a technician as "we checked Azure and it is fine", which is the
    opposite of the truth, and a fabricated 0 sends them chasing a finding that
    does not exist. Both are worse than an absent axis.

    Returns an empty dict when nothing can be scored. `_render_radar_svg`
    additionally declines to draw fewer than three axes, and the template hides
    the whole block when no SVG comes back.
    """
    t = T(lang)

    risk = context.get("risk", {})
    if risk.get("blocking_data_gaps"):
        return {}

    categories: dict[str, int] = {}

    # ── Identity (MFA + CA + admin roles) ────────────────────────────
    # Average over the inputs that were measured, not over all three. A failed
    # /identity/conditionalAccess/policies fetch reads as "0 policies enabled"
    # in the parsed dict, which used to drag this axis toward red on its own.
    identity_parts: list[float] = []
    mfa = context.get("mfa", {})
    if mfa.get("has_data"):
        identity_parts.append(min(100, mfa.get("pct", 0)))
    ca = context.get("ca", {})
    if ca.get("has_data"):
        ca_enabled = ca.get("enabled", 0)
        identity_parts.append(100 if ca_enabled >= 3 else ca_enabled * 30)
    admin_roles = context.get("admin_roles", {})
    if admin_roles.get("has_data"):
        ga = admin_roles.get("global_admin_count", 0)
        identity_parts.append(
            100 if 2 <= ga <= 4 else max(0, 100 - (ga - 4) * 20) if ga > 4 else 50
        )
    if identity_parts:
        categories[t.radar_identity] = min(100, int(sum(identity_parts) / len(identity_parts)))

    # ── Devices — read the verdict the CIS device controls already reached ──
    # The axis used to be raw compliance_pct, gated only on has_data and
    # total>0. But Intune marks an unmanaged device "compliant" by default, so a
    # tenant with devices enrolled and *zero* compliance policies scored ~100
    # here while CIS 6.1.1 — which checks that policies exist at all — FAILed the
    # same tenant on the same report. The radar drew the reassuring-but-false
    # half. Score off the compliance map instead, exactly as the Email axis does
    # below: pass = full credit, partial = half, fail = none, and "info"
    # (could-not-verify) excluded just as compliance_pct excludes it — so the
    # radar and the table can never disagree. No assessable device control (the
    # Intune section never ran, or every device control is info) means no axis,
    # the same rule every other axis here follows.
    _device_credit = {"pass": 1.0, "partial": 0.5, "fail": 0.0}
    device_controls = [
        c
        for c in context.get("compliance", [])
        if c.get("category") == t.cis_cat_devices and c.get("status") in _device_credit
    ]
    if device_controls:
        device_score = sum(_device_credit[c["status"]] for c in device_controls) / len(
            device_controls
        )
        categories[t.radar_devices] = round(device_score * 100)

    # ── Email — read the verdict the CIS email controls already reached ──
    # The axis used to run its own SPF/DMARC ladder that knew only MISSING and
    # WEAK, so a DMARC p=quarantine (which the collector tokenises as "WARN")
    # and a missing DKIM — both graded by the CIS Email controls — deducted
    # nothing, and the axis sat at 100 while the compliance table showed those
    # very controls failing. That contradiction is exactly what a reader loses
    # trust over. Score the axis off the compliance map instead: pass = full
    # credit, partial = half, fail = none, and "info" (could-not-verify)
    # excluded exactly as compliance_pct excludes it. One source of truth, so
    # the radar and the table can never disagree again. No assessable email
    # control (every domain ignored, or the DNS section never ran) means no
    # axis — a fabricated 100 there would be an assurance we never earned, the
    # same rule every other axis on this chart already follows.
    #
    # "warn" is half credit, as the report's own summary counts it with
    # "partial". Left out, it was excluded like "info", though compliance_pct
    # counts it against the tenant: external forwarding (4.4), no Safe Links
    # policy (4.5) or a domain whose mail goes unsigned (5.2.3) lifted the axis
    # instead of lowering it.
    _email_credit = {"pass": 1.0, "partial": 0.5, "warn": 0.5, "fail": 0.0}
    email_controls = [
        c
        for c in context.get("compliance", [])
        if c.get("category") == t.cis_cat_email and c.get("status") in _email_credit
    ]
    if email_controls:
        email_score = sum(_email_credit[c["status"]] for c in email_controls) / len(email_controls)
        categories[t.radar_email] = round(email_score * 100)

    # ── Azure ────────────────────────────────────────────────────────
    azure = context.get("azure", {})
    if azure.get("has_data"):
        azure_score = 80  # baseline for a subscription we could enumerate
        if azure.get("orphaned", 0) > 0:
            azure_score -= 10
        if azure.get("advisor_recs", 0) > 20:
            azure_score -= 20
        elif azure.get("advisor_recs", 0) > 5:
            azure_score -= 10
        categories[t.radar_azure] = max(0, azure_score)

    # ── Data Protection ──────────────────────────────────────────────
    # _parse_purview only sets has_data once it has found at least one label,
    # DLP policy, or retention policy, so the 50 baseline is a floor this axis
    # never actually lands on. That is deliberate: a tenant with none of the
    # three is indistinguishable from one where Purview was never collected,
    # and the honest rendering of "indistinguishable" is no axis at all.
    purview = context.get("purview", {})
    if purview.get("has_data"):
        data_score = 50  # baseline
        if purview.get("sensitivity_label_count", 0) > 0:
            data_score += 20
        if purview.get("dlp_policy_count", 0) > 0:
            data_score += 20
        if purview.get("retention_policy_count", 0) > 0:
            data_score += 10
        categories[t.radar_data] = min(100, data_score)

    return categories


def _render_radar_svg(categories: dict) -> str:
    """Render a radar/spider chart as inline SVG."""
    import math

    cats = list(categories.items())
    n = len(cats)
    if n < 3:
        return ""

    cx, cy = 150, 150  # center
    max_r = 120  # max radius

    # Build SVG
    svg = [
        '<svg viewBox="0 0 300 320" xmlns="http://www.w3.org/2000/svg" style="max-width:400px;width:100%;">'
    ]

    # Background circles (grid)
    for pct in [25, 50, 75, 100]:
        r = max_r * pct / 100
        svg.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#e5e7eb" stroke-width="0.5"/>'
        )

    # Axis lines and labels
    for i, (label, score) in enumerate(cats):
        angle = (2 * math.pi * i / n) - math.pi / 2  # start from top
        x_end = cx + max_r * math.cos(angle)
        y_end = cy + max_r * math.sin(angle)
        svg.append(
            f'<line x1="{cx}" y1="{cy}" x2="{x_end:.1f}" y2="{y_end:.1f}" stroke="#d0d7de" stroke-width="0.5"/>'
        )

        # Label. Escaped even though the categories are fixed names today: the
        # result is injected into the report via {{ radar_svg | safe }}, so an
        # unescaped label would be an injection sink the moment a category name
        # ever becomes data-derived.
        from html import escape as _xml_escape

        lx = cx + (max_r + 20) * math.cos(angle)
        ly = cy + (max_r + 20) * math.sin(angle)
        anchor = "middle"
        if lx < cx - 10:
            anchor = "end"
        elif lx > cx + 10:
            anchor = "start"
        svg.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" font-size="11" fill="#6b7280" font-family="sans-serif" dominant-baseline="middle">{_xml_escape(str(label))}</text>'
        )

        # Score label
        sx = cx + (max_r * score / 100 + 12) * math.cos(angle)
        sy = cy + (max_r * score / 100 + 12) * math.sin(angle)
        svg.append(
            f'<text x="{sx:.1f}" y="{sy:.1f}" text-anchor="middle" font-size="10" fill="#0f4c81" font-weight="700" font-family="sans-serif" dominant-baseline="middle">{score}</text>'
        )

    # Data polygon
    points = []
    for i, (_label, score) in enumerate(cats):
        angle = (2 * math.pi * i / n) - math.pi / 2
        r = max_r * score / 100
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        points.append(f"{x:.1f},{y:.1f}")

    svg.append(
        f'<polygon points="{" ".join(points)}" fill="rgba(15,76,129,0.15)" stroke="#0f4c81" stroke-width="2"/>'
    )

    # Data points
    for i, (_label, score) in enumerate(cats):
        angle = (2 * math.pi * i / n) - math.pi / 2
        r = max_r * score / 100
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#0f4c81"/>')

    svg.append("</svg>")
    return "\n".join(svg)
