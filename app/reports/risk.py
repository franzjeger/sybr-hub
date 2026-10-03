"""Risk scoring over parsed audit sections."""

from __future__ import annotations

from app.reports.evidence import _evidence_unavailable, _reported_count
from app.reports.i18n import T
from app.reports.parsers.common import _sidecar
from app.reports.parsers.email import _external_forwarding_items


def _is_open_wlan(wlan: dict) -> bool:
    """True only when this WLAN is positively identified as unencrypted.

    Reports are rendered from audit JSON saved on disk, so this has to cope
    with three vintages: files written before ``security_label`` existed,
    files where the controller never returned a security field at all, and
    current files. In every one of them, "we could not tell" must come back
    False — an open-WiFi finding is critical-priority and named by SSID in
    the report, so it has to rest on a reading.
    """
    from app.services.unifi_api import is_open_wlan_security

    label = wlan.get("security_label")
    if label is not None:
        return label == "Open"
    return is_open_wlan_security(wlan.get("security"))


def _compute_network_risk(network: dict) -> dict:
    """Compute network-specific risk factors. Returns {penalty, findings}."""
    penalty = 0
    findings: list[str] = []

    fg = network.get("fortigate")
    if fg and "error" not in fg:
        # Admin without 2FA
        admins_no_2fa = [a for a in fg.get("admins", []) if not a.get("two_factor")]
        if admins_no_2fa:
            penalty += min(5, len(admins_no_2fa) * 2)
            findings.append(f"{len(admins_no_2fa)} FortiGate-admin uten 2FA")
        # Allow-all policies
        allow_all = [w for w in fg.get("policy_warnings", []) if "allow-all" in w.lower()]
        if allow_all:
            penalty += min(5, len(allow_all) * 3)
            findings.append(f"{len(allow_all)} allow-all-regler")
        # No-logging policies
        no_log = [w for w in fg.get("policy_warnings", []) if "logging" in w.lower()]
        if no_log:
            penalty += min(3, len(no_log))
            findings.append(f"{len(no_log)} regler uten logging")

    uf = network.get("unifi")
    if uf and "error" not in uf:
        # Default credentials
        default_creds = uf.get("default_creds_count", 0)
        if default_creds:
            penalty += min(10, default_creds * 5)
            findings.append(f"{default_creds} enheter med standard-passord")
        # Outdated firmware
        outdated = uf.get("outdated_firmware_count", 0)
        eol = uf.get("eol_count", 0)
        if eol:
            penalty += min(5, eol * 3)
            findings.append(f"{eol} EOL-enheter")
        if outdated:
            penalty += min(3, outdated * 2)
            findings.append(f"{outdated} enheter med utdatert firmware")
        # Check for open WiFi in controller mode
        if uf.get("mode") == "controller":
            for w in uf.get("wlans", []):
                if _is_open_wlan(w) and w.get("enabled", True):
                    penalty += 5
                    findings.append("Åpent WiFi-nettverk")
                    break

    return {"penalty": min(15, penalty), "findings": findings}


def _compute_risk(
    secure_score: dict,
    mfa: dict,
    spf_dmarc: list[dict],
    all_warns: list[str],
    ext_fwd: str,
    risky_users: str,
    defender: str,
    admin_roles: dict | None = None,
    intune: dict | None = None,
    sharepoint: dict | None = None,
    oauth: dict | None = None,
    network: dict | None = None,
    lang: str = "no",
    unavailable_sections: list[str] | None = None,
    file_contents: dict[str, str] | None = None,
) -> dict:
    """Compute a security health score from 0 (worst) to 100 (best).

    ``file_contents`` gives the external forwarding rows, the risky-user count
    and the Defender-alert count from their JSON sidecars; without it, or for a
    run without them, they are read from the ``ext_fwd``, ``risky_users`` and
    ``defender`` text.

    Weight budget (100 points total):
      - MFA coverage:         35 pts
      - Secure Score:         20 pts
      - Email security:       10 pts
      - External forwarding:  10 pts  (critical finding)
      - Defender alerts:      10 pts  (critical finding)
      - Risky users:           5 pts
      - Admin roles:           5 pts
      - Intune compliance:     5 pts
      - SharePoint / OAuth:    variable (bonus deductions)
      - Network security:     15 pts  (FortiGate + UniFi findings)
    """
    t = T(lang)
    score = 100
    data_quality_issues: list[str] = []  # Track missing/unverifiable data
    blocking_data_gaps: list[str] = []  # Gaps that invalidate the whole grade

    # ── MFA coverage (up to 35 pts) ──────────────────────────────────
    if mfa.get("has_data"):
        mfa_pct = mfa.get("pct", 0)
        no_mfa = mfa.get("no_mfa", 0)
        mfa_penalty = round(35 * (1 - mfa_pct / 100))
        mfa_penalty_abs = min(35, no_mfa * 2)
        score -= max(mfa_penalty, mfa_penalty_abs)
        # The collector keeps unknowns out of both sides of the fraction,
        # which is right — a throttled lookup is not a user without MFA. But
        # the percentage that survives is then measured on a subset, and
        # nothing said so. Ninety of a hundred lookups failing still read as
        # "100% MFA coverage, grade A" on the strength of ten users.
        _unknown = mfa.get("unknown", 0)
        if _unknown:
            data_quality_issues.append(
                t(
                    "risk_dq_mfa_partial_base",
                    measured=mfa.get("measured", 0),
                    total=mfa.get("total", 0),
                    unknown=_unknown,
                )
            )
    else:
        # MFA is the largest single weight (35/100). Without it, any computed
        # grade is fiction — flag as blocking so the grade renders as INVALID
        # rather than fabricating a B/70 from partial inputs.
        data_quality_issues.append(t.risk_dq_mfa_unavailable)
        blocking_data_gaps.append(t.risk_gap_mfa)

    # ── Secure Score (up to 20 pts) ──────────────────────────────────
    if secure_score.get("has_data"):
        ss_pct = secure_score.get("pct", 0)
        score -= round(20 * (1 - ss_pct / 100))
    else:
        data_quality_issues.append(t.risk_dq_secure_score)

    # ── Email security (up to 10 pts) ────────────────────────────────
    # A failed DoH lookup comes back as "ERROR (...)", never MISSING/WEAK, so an
    # errored domain silently contributes 0 penalty. Track whether any domain
    # produced a real verdict: if the whole set errored, the 10 points are not
    # "earned clean", they are unmeasured — flag it like every other axis. And
    # match p=none on the classifier's actual token ("p=none"), not "NONE", which
    # never matched and let a monitor-only DMARC policy score clean (accuracy sweep).
    email_penalty = 0
    email_measured = 0
    for d in spf_dmarc:
        spf = d.get("spf", "")
        dmarc = d.get("dmarc", "")
        spf_errored = spf.strip().upper().startswith("ERROR")
        dmarc_errored = dmarc.strip().upper().startswith("ERROR")
        if not (spf_errored and dmarc_errored):
            email_measured += 1
        if not spf_errored:
            if "MISSING" in spf or "CRITICAL" in spf:
                email_penalty = max(email_penalty, 10)
            elif "WEAK" in spf or "WARN" in spf:
                email_penalty = max(email_penalty, 5)
        if not dmarc_errored:
            if "MISSING" in dmarc:
                email_penalty = max(email_penalty, 8)
            elif "p=none" in dmarc.lower() or "WEAK" in dmarc.upper():
                email_penalty = max(email_penalty, 5)
            elif "quarantine" in dmarc.lower():
                # p=quarantine is CIS "partial", not a clean pass — reject is the
                # target. The classifier tokenises it as "WARN (p=quarantine)",
                # which matched none of the branches above, so a monitor-stronger-
                # than-none-but-not-reject policy scored as clean here just as it
                # did on the radar. Small penalty, mirroring the partial credit.
                email_penalty = max(email_penalty, 3)
    score -= email_penalty
    if spf_dmarc and email_measured == 0:
        data_quality_issues.append(t.risk_dq_email_dns)

    # ── Admin roles (up to 5 pts) ────────────────────────────────────
    # Only score when we actually have role data — has_data=False means the
    # /directoryRoles fetch failed, so a 0-admin reading is missing data,
    # not "no admin sprawl". Same pattern repeats for SharePoint and OAuth.
    if admin_roles and admin_roles.get("has_data"):
        ga = admin_roles.get("global_admin_count", 0)
        if ga > 4:
            score -= 5
        elif ga > 2:
            score -= 3
    elif admin_roles is not None:
        data_quality_issues.append(t.risk_dq_admin_roles)

    # ── Intune compliance (up to 5 pts) ──────────────────────────────
    if intune and intune.get("has_data") and intune.get("total", 0) > 0:
        cpct = intune.get("compliance_pct", 0)
        if cpct < 50:
            score -= 5
        elif cpct < 80:
            score -= 3
    elif intune is not None and not intune.get("has_data"):
        data_quality_issues.append(t.risk_dq_intune)

    # ── SharePoint sharing ───────────────────────────────────────────
    if sharepoint and sharepoint.get("has_data"):
        sharing = sharepoint.get("sharing_level")
        if sharing == "warning":
            score -= 3
        if sharepoint.get("legacy_auth"):
            score -= 2
        # has_data means the site *list* was read; the tenant sharing/legacy-auth
        # settings are a separate admin read that can fail while the sites
        # succeed. When those fields were never established, that is unmeasured,
        # not a clean pass — flag it (accuracy sweep).
        if sharing in (None, "unknown") or not sharepoint.get("legacy_auth_known"):
            data_quality_issues.append(t.risk_dq_sharepoint)
    elif sharepoint is not None and not sharepoint.get("has_data"):
        data_quality_issues.append(t.risk_dq_sharepoint)

    # ── OAuth high-privilege apps ────────────────────────────────────
    if oauth and oauth.get("has_data"):
        if len(oauth.get("high_privilege_apps", [])) > 5:
            score -= 3
        # has_data can be True from app registrations alone; if the consent-grants
        # read itself failed, the high-privilege count is incomplete, not clean.
        if not oauth.get("grants_read", True):
            data_quality_issues.append(t.risk_dq_oauth)
    elif oauth is not None and not oauth.get("has_data"):
        data_quality_issues.append(t.risk_dq_oauth)

    # ── Critical findings ────────────────────────────────────────────

    # External forwarding (up to 10 pts) — any active forwarding is severe
    if ext_fwd and ext_fwd.strip():
        # Count only the actual "mailbox → target" rows — the same arrow the
        # finding-fwd rec keys on. The old banner/prose filter still counted a
        # header line as a rule, over-penalising by one (accuracy sweep). The
        # min-5 floor keeps "any forwarding present is severe".
        # The 28b sidecar's rows when the run has one (file_contents).
        fwd_lines = _external_forwarding_items(file_contents or {})
        if fwd_lines is None:
            fwd_lines = [line for line in ext_fwd.splitlines() if "→" in line]
        score -= min(10, max(5, len(fwd_lines) * 2))

    # Risky users (up to 5 pts). The guard against reading a refusal as a
    # finding was already here; what was missing is that it said nothing. A
    # tenant without Entra ID P2, or one where the fetch was refused, scored
    # identically to one verified to have no risky users.
    risky_sidecar = _sidecar(file_contents or {}, "18_risky_users.txt")
    _risky_n = (
        int(risky_sidecar.get("count") or 0)
        if risky_sidecar is not None
        else _reported_count(risky_users)
    )
    if risky_sidecar is None and _evidence_unavailable(risky_users):
        # Only when the file exists and turned out to be prose. An absent file
        # means the section never ran, and that is already declared by name
        # through unavailable_sections; this branch covers the case that one
        # cannot see — the section reported DONE and one fetch inside it did not.
        if risky_users and risky_users.strip():
            data_quality_issues.append(t.risk_dq_risky_users)
    elif _risky_n is not None:
        if _risky_n > 0:
            score -= 5
    elif risky_users and "No risky" not in risky_users and risky_users.strip():
        score -= 5

    # Defender alerts (up to 10 pts) — scale with number of alerts.
    # The collector writes "Error: {ex}" into this file when the fetch fails,
    # and that stub is truthy, does not say "No active", and is not empty — so
    # it counted as one alert and cost four points. A 403 on the Defender
    # endpoint scored the same as a tenant with a live phishing alert, with
    # nothing to say the alert was invented. Every other reader of this file
    # already checks; the score was the one that did not.
    defender_sidecar = _sidecar(file_contents or {}, "19b_defender_active_alerts.txt")
    if defender_sidecar is None and _evidence_unavailable(defender):
        if defender and defender.strip():
            data_quality_issues.append(t.risk_dq_defender)
    else:
        alert_count = (
            int(defender_sidecar.get("count") or 0)
            if defender_sidecar is not None
            else _reported_count(defender)
        )
        if alert_count is None and defender and "No active" not in defender and defender.strip():
            # No count in the header. Fall back to counting rows, as before.
            alert_lines = [
                line
                for line in defender.strip().splitlines()
                if line.strip()
                and not line.strip().startswith("=")
                and not line.strip().startswith("-")
            ]
            alert_count = max(1, len(alert_lines))
        if alert_count:
            # 3 pts base + 1 per alert, capped at 10
            score -= min(10, 3 + alert_count)

    # ── Network security (up to 15 pts) ────────────────────────────
    if network and network.get("has_data"):
        net_risk = _compute_network_risk(network)
        score -= net_risk["penalty"]
    # A file that would not parse is an input this function could not read, and
    # that is what data_quality_issues is for — every other unverifiable input
    # is declared there. Not blocking: the network is worth 15 points against
    # MFA's 35, so refusing to grade the whole tenant over one corrupt file is
    # heavier than the gap warrants. But it must be visible beside the score,
    # not only in a recommendation further down the report.
    # A section that did not run keeps its points. The collector records the
    # failure and the report counts it, but the count never reached the score,
    # so a tenant whose Exchange collection failed — which the collector itself
    # calls a routine outcome — scored as though Exchange were clean, with
    # nothing beside the score to say otherwise.
    for _section in unavailable_sections or []:
        data_quality_issues.append(t("risk_dq_section_incomplete", section=_section))

    for _unreadable in (network or {}).get("unreadable", []):
        data_quality_issues.append(t("risk_dq_network_unreadable", file=_unreadable))

    # A FortiGate that answered its status probe but refused the admin or policy
    # sub-read reports those counts as None. The admin/policy findings key on the
    # (now empty) lists, so a refused read renders "no 2FA/trust-host/allow-all
    # issues" — a false clean. Declare it, matching the whole-section contract.
    _fg = (network or {}).get("fortigate")
    if isinstance(_fg, dict) and "error" not in _fg:
        if _fg.get("admin_count") is None:
            data_quality_issues.append(t.risk_dq_fg_admins)
        if _fg.get("policy_count") is None:
            data_quality_issues.append(t.risk_dq_fg_policies)

    score = max(0, min(100, score))

    # If essential inputs are missing, refuse to grade. Returning a number here
    # would be misleading — the score function literally cannot evaluate the
    # tenant. Consumers should display "Ufullstendige data" and the gap list.
    if blocking_data_gaps:
        return {
            "score": None,
            "grade": "?",
            "level": t.risk_level_invalid,
            "color": "gray",
            "data_quality_issues": data_quality_issues,
            "blocking_data_gaps": blocking_data_gaps,
            "has_full_data": False,
        }

    # ── Grade thresholds: A(80-100), B(60-79), C(40-59), D(20-39), F(0-19) ──
    if score >= 80:
        grade, level, color = "A", t.risk_level_good, "green"
    elif score >= 60:
        grade, level, color = "B", t.risk_level_satisfactory, "blue"
    elif score >= 40:
        grade, level, color = "C", t.risk_level_needs_action, "orange"
    elif score >= 20:
        grade, level, color = "D", t.risk_level_weak, "red"
    else:
        grade, level, color = "F", t.risk_level_critical, "darkred"

    return {
        "score": score,
        "grade": grade,
        "level": level,
        "color": color,
        "data_quality_issues": data_quality_issues,
        "blocking_data_gaps": [],
        "has_full_data": len(data_quality_issues) == 0,
    }


def _apply_critical_floor(risk: dict, recs: list[dict], lang: str = "no") -> dict:
    """Cap the letter grade when there are unaddressed critical findings.

    A weighted numeric score can average a critical away: a tenant with two
    critical findings and 0% Intune compliance read "B / Satisfactory" because
    the score still cleared 60. The number is kept, but the grade is floored so
    the headline cannot say "good" over an open critical — cap at C for one or
    two criticals, D for more (M365 review, F9). Mutates and returns risk.
    """
    if risk.get("score") is None:  # "?" / invalid — nothing to floor
        return risk
    criticals = sum(1 for r in recs if r.get("priority") == "critical")
    if criticals == 0:
        return risk
    t = T(lang)
    order = ["A", "B", "C", "D", "F"]
    cap = "C" if criticals <= 2 else "D"
    cap_meta = {"C": (t.risk_level_needs_action, "orange"), "D": (t.risk_level_weak, "red")}
    grade = risk.get("grade", "A")
    if grade in order and order.index(grade) < order.index(cap):
        risk["grade"] = cap
        risk["level"], risk["color"] = cap_meta[cap]
        risk["capped_by_criticals"] = criticals
    return risk
