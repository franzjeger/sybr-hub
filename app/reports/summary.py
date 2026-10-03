"""Executive summary bullets for the report."""

from __future__ import annotations

from app.reports.i18n import T

# ── Executive summary ──────────────────────────────────────────────────────────


def _build_executive_summary(context: dict, lang: str = "no") -> list[str]:
    t = T(lang)
    bullets = []
    users = context.get("users", {})
    mfa = context.get("mfa", {})
    ca = context.get("ca", {})
    ss = context.get("secure_score", {})
    intune = context.get("intune", {})
    azure = context.get("azure", {})
    admin = context.get("admin_roles", {})
    risk = context.get("risk", {})
    recs = context.get("recommendations", [])

    # Environment size. "The environment has 0 users (0 active, 0 guests)" is
    # not a description of a tenant, it is a description of a failed audit —
    # and it opened the summary.
    if users.get("has_data"):
        bullets.append(
            t(
                "exec_env_size",
                total=users.get("total", 0),
                enabled=users.get("enabled", 0),
                guests=users.get("guests", 0),
                azure_resources=azure.get("total_resources", 0) if azure.get("has_data") else 0,
                subscriptions=len(azure.get("subscriptions", [])) if azure.get("has_data") else 0,
            )
        )
    else:
        bullets.append(t.exec_env_size_unavailable)

    # MFA status — gate on has_data, not on pct. A tenant where every user is
    # unprotected scores 0%, and branching on the number alone announced the
    # single worst identity finding in the product as "data not available".
    if not mfa.get("has_data"):
        bullets.append(t.exec_mfa_unavailable)
    else:
        _mpct = mfa.get("pct", 0)
        _mtot = mfa.get("total", 0)
        _munk = mfa.get("unknown", 0)
        # A high percentage measured on a heavily-throttled subset is not "well
        # protected". The score already flags the subset; the exec summary must
        # not contradict it with an all-clear (accuracy sweep).
        if _mtot > 0 and _munk / _mtot >= 0.1:
            bullets.append(
                t(
                    "exec_mfa_subset",
                    pct=_mpct,
                    measured=mfa.get("measured", _mtot - _munk),
                    total=_mtot,
                    unknown=_munk,
                )
            )
        elif _mpct >= 95:
            bullets.append(t("exec_mfa_good", pct=_mpct))
        else:
            bullets.append(t("exec_mfa_partial", pct=_mpct, no_mfa=mfa.get("no_mfa", 0)))

    # Secure Score — same reasoning; 0% is a reading, not a missing reading.
    if ss.get("has_data"):
        if ss.get("pct", 0) >= 75:
            bullets.append(t("exec_ss_good", pct=ss["pct"]))
        else:
            bullets.append(t("exec_ss_low", pct=ss["pct"], count=len(ss.get("improvements", []))))

    # Intune. "All compliant" must mean every device is CONFIRMED compliant, not
    # merely "zero non-compliant" — devices in grace-period / not-evaluated sit in
    # a third (unknown) bucket, and claiming an all-clear over them contradicted
    # compliance_pct and the score's own penalty. The non-compliant percentage is
    # taken from the non-compliant count, not 100-compliance_pct (which folds in
    # the unknown bucket and disagreed with the "{n} of {total}" it sits beside).
    if intune.get("total", 0) > 0:
        _it = intune["total"]
        _inc = intune.get("noncompliant", 0)
        # The real parser always sets "compliant"; fall back to the old binary
        # assumption (total - noncompliant) only when it is absent, so the
        # three-way logic engages exactly when there is a measured unknown bucket.
        _ic = intune.get("compliant", _it - _inc)
        if _inc > 0:
            bullets.append(
                t(
                    "exec_intune_noncompliant",
                    noncompliant=_inc,
                    total=_it,
                    pct=round(_inc / _it * 100),
                )
            )
        elif _ic >= _it:
            bullets.append(t("exec_intune_ok", total=_it))
        else:
            bullets.append(
                t("exec_intune_partial", compliant=_ic, total=_it, unknown=_it - _ic - _inc)
            )

    # CA policies
    if ca.get("enabled", 0) > 0:
        bullets.append(t("exec_ca_active", count=ca["enabled"]))

    # Critical findings
    critical_recs = [r for r in recs if r.get("priority") == "critical"]
    high_recs = [r for r in recs if r.get("priority") == "high"]
    if critical_recs:
        titles = [r["title"] for r in critical_recs[:3]]
        bullets.append(
            t("exec_critical_findings", count=len(critical_recs), titles="; ".join(titles))
        )
    if high_recs:
        bullets.append(t("exec_high_findings", count=len(high_recs)))

    # Admin roles
    ga = admin.get("global_admin_count", 0)
    if ga > 4:
        bullets.append(t("exec_ga_too_many", count=ga))

    # Overall. _compute_risk returns score=None / grade="?" when a blocking gap
    # makes the grade fiction; formatting that into "{score}/100" printed the
    # literal "None/100" in the customer-facing summary.
    if risk.get("score") is None:
        bullets.append(t.exec_overall_invalid)
    else:
        # "F" must map to a description at least as severe as "D" — without it the
        # worst tenants had their posture printed as "unknown" (accuracy sweep).
        grade_text = {
            "A": t.exec_grade_a,
            "B": t.exec_grade_b,
            "C": t.exec_grade_c,
            "D": t.exec_grade_d,
            "F": t.exec_grade_f,
        }
        bullets.append(
            t(
                "exec_overall",
                grade=risk.get("grade", "?"),
                score=risk["score"],
                description=grade_text.get(risk.get("grade", "C"), t.exec_grade_unknown),
            )
        )

    return bullets
