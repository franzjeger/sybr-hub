"""Internationalisation for reports — Norwegian (default) and English."""

from __future__ import annotations

TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── Report titles ──
    "report_title_customer": {
        "no": "IT-Sikkerhetsrapport",
        "en": "IT Security Report",
    },
    "report_title_tech": {
        "no": "Teknisk Auditrapport",
        "en": "Technical Audit Report",
    },
    "report_subtitle": {
        "no": "Microsoft 365 & Azure Sikkerhetsvurdering",
        "en": "Microsoft 365 & Azure Security Assessment",
    },
    "confidential": {
        "no": "Konfidensiell",
        "en": "Confidential",
    },
    "page_of": {
        "no": "Side",
        "en": "Page",
    },
    "of": {
        "no": "av",
        "en": "of",
    },
    # ── TOC & sections ──
    "toc_title": {
        "no": "Innhold",
        "en": "Table of Contents",
    },
    "summary": {
        "no": "Sammendrag",
        "en": "Summary",
    },
    "key_findings": {
        "no": "Nøkkelfunn",
        "en": "Key Findings",
    },
    "main_findings": {
        "no": "Hovedfunn",
        "en": "Main Findings",
    },
    "security_posture": {
        "no": "Sikkerhetspostur",
        "en": "Security Posture",
    },
    "recommendations": {
        "no": "Anbefalte tiltak",
        "en": "Recommended Actions",
    },
    "action_plan": {
        "no": "Handlingsplan",
        "en": "Action Plan",
    },
    "identity_access": {
        "no": "Identitet og tilgang",
        "en": "Identity & Access",
    },
    "devices": {
        "no": "Enheter",
        "en": "Devices",
    },
    "data_collaboration": {
        "no": "Data og samarbeid",
        "en": "Data & Collaboration",
    },
    "email_exchange": {
        "no": "E-post (Exchange)",
        "en": "Email (Exchange)",
    },
    "apps_integrations": {
        "no": "Apper og integrasjoner",
        "en": "Apps & Integrations",
    },
    "data_protection": {
        "no": "Databeskyttelse",
        "en": "Data Protection",
    },
    "azure_infrastructure": {
        "no": "Azure-infrastruktur",
        "en": "Azure Infrastructure",
    },
    "compliance": {
        "no": "Samsvar",
        "en": "Compliance",
    },
    "environment_overview": {
        "no": "Miljøoversikt",
        "en": "Environment Overview",
    },
    # ── Metrics ──
    "mfa_coverage": {
        "no": "MFA-dekning",
        "en": "MFA Coverage",
    },
    "secure_score": {
        "no": "Secure Score",
        "en": "Secure Score",
    },
    "risk_score": {
        "no": "Sikkerhetsscore",
        "en": "Security Score",
    },
    "users_without_mfa": {
        "no": "Brukere uten MFA",
        "en": "Users Without MFA",
    },
    "total_users": {
        "no": "Totalt brukere",
        "en": "Total Users",
    },
    "active": {
        "no": "Aktive",
        "en": "Active",
    },
    "disabled": {
        "no": "Deaktivert",
        "en": "Disabled",
    },
    "guests": {
        "no": "Gjester",
        "en": "Guests",
    },
    # ── Findings ──
    "mfa_missing_title": {
        "no": "{count} bruker(e) mangler tofaktorautentisering",
        "en": "{count} user(s) missing multi-factor authentication",
    },
    "mfa_ok_title": {
        "no": "Alle brukere har tofaktorautentisering aktivert",
        "en": "All users have multi-factor authentication enabled",
    },
    "mfa_missing_desc": {
        "no": "Brukere uten tofaktorautentisering (MFA) er betydelig mer utsatt for kontoovertakelse. Dette er en av de hyppigste årsakene til dataangrep mot bedrifter.",
        "en": "Users without multi-factor authentication (MFA) are significantly more vulnerable to account takeover. This is one of the most common causes of cyberattacks against businesses.",
    },
    "ext_fwd_title": {
        "no": "{count} postkasse(r) videresender til eksterne adresser",
        "en": "{count} mailbox(es) forwarding to external addresses",
    },
    "ext_fwd_desc": {
        "no": "Følgende postkasser er satt opp til å automatisk videresende e-post ut av organisasjonen:",
        "en": "The following mailboxes are configured to automatically forward email outside the organization:",
    },
    "risky_users_title": {
        "no": "{count} risikobruker(e) oppdaget",
        "en": "{count} risky user(s) detected",
    },
    "risky_users_desc": {
        "no": "Microsoft Entra ID Protection har flagget brukerkontoer for mistenkelig aktivitet.",
        "en": "Microsoft Entra ID Protection has flagged user accounts for suspicious activity.",
    },
    # ── Badges & labels ──
    "critical": {
        "no": "Kritisk",
        "en": "Critical",
    },
    "high_risk": {
        "no": "Høy risiko",
        "en": "High Risk",
    },
    "ok": {
        "no": "OK",
        "en": "OK",
    },
    "warning": {
        "no": "Advarsel",
        "en": "Warning",
    },
    "passed": {
        "no": "Bestått",
        "en": "Passed",
    },
    "failed": {
        "no": "Ikke bestått",
        "en": "Failed",
    },
    "partial": {
        "no": "Delvis",
        "en": "Partial",
    },
    "info": {
        "no": "Info",
        "en": "Info",
    },
    # ── Actions ──
    "show_details": {
        "no": "Vis detaljer",
        "en": "Show details",
    },
    "hide_details": {
        "no": "Skjul detaljer",
        "en": "Hide details",
    },
    "show_n_unprotected": {
        "no": "Vis {count} ubeskyttede brukere",
        "en": "Show {count} unprotected users",
    },
    "show_n_forwarding": {
        "no": "Vis {count} videresendinger",
        "en": "Show {count} forwarding rules",
    },
    "show_n_risky": {
        "no": "Vis {count} risikobrukere",
        "en": "Show {count} risky users",
    },
    "show_n_global_admins": {
        "no": "Vis {count} Global Administrator(er)",
        "en": "Show {count} Global Administrator(s)",
    },
    "show_n_noncompliant": {
        "no": "Vis {count} ikke-samsvarende enhet(er)",
        "en": "Show {count} non-compliant device(s)",
    },
    "show_n_other_state": {
        "no": "Vis {count} enhet(er) uten avklart status (ukjent, i nådeperiode eller feil)",
        "en": "Show {count} device(s) without a settled state (unknown, in grace period or error)",
    },
    "in_grace_period_label": {
        "no": "I nådeperiode",
        "en": "In grace period",
    },
    "compliance_unknown_label": {
        "no": "Ukjent",
        "en": "Unknown",
    },
    "show_n_apps": {
        "no": "Vis {count} app(er)",
        "en": "Show {count} app(s)",
    },
    "see_recommendation": {
        "no": "Se anbefaling #{num}",
        "en": "See recommendation #{num}",
    },
    "related_finding": {
        "no": "Relatert funn",
        "en": "Related finding",
    },
    "device_name": {
        "no": "Enhetsnavn",
        "en": "Device Name",
    },
    "os": {
        "no": "OS",
        "en": "OS",
    },
    "compliance_state": {
        "no": "Samsvarsstatus",
        "en": "Compliance State",
    },
    "last_sync": {
        "no": "Siste synk",
        "en": "Last Sync",
    },
    "app_name": {
        "no": "App",
        "en": "App",
    },
    "permissions": {
        "no": "Tillatelser",
        "en": "Permissions",
    },
    "role": {
        "no": "Rolle",
        "en": "Role",
    },
    # ── Table headers ──
    "user": {
        "no": "Bruker",
        "en": "User",
    },
    "email_upn": {
        "no": "E-post / UPN",
        "en": "Email / UPN",
    },
    "mfa_registered": {
        "no": "MFA registrert",
        "en": "MFA Registered",
    },
    "ca_coverage": {
        "no": "CA-dekning",
        "en": "CA Coverage",
    },
    "reason": {
        "no": "Årsak",
        "en": "Reason",
    },
    "mailbox": {
        "no": "Postkasse",
        "en": "Mailbox",
    },
    "forwarded_to": {
        "no": "Videresendes til",
        "en": "Forwarded To",
    },
    "risk_level": {
        "no": "Risikonivå",
        "en": "Risk Level",
    },
    "status": {
        "no": "Status",
        "en": "Status",
    },
    "priority": {
        "no": "Prioritet",
        "en": "Priority",
    },
    "effort": {
        "no": "Innsats",
        "en": "Effort",
    },
    "low": {
        "no": "Lav",
        "en": "Low",
    },
    "medium": {
        "no": "Middels",
        "en": "Medium",
    },
    "high": {
        "no": "Høy",
        "en": "High",
    },
    "immediate": {
        "no": "Umiddelbar",
        "en": "Immediate",
    },
    # ── Cover / meta ──
    "primary_domain": {
        "no": "Primærdomene",
        "en": "Primary Domain",
    },
    "report_date": {
        "no": "Rapportdato",
        "en": "Report Date",
    },
    "prepared_by": {
        "no": "Utarbeidet av",
        "en": "Prepared By",
    },
    "customer": {
        "no": "Kunde",
        "en": "Customer",
    },
    "domain": {
        "no": "Domene",
        "en": "Domain",
    },
    "generated_by": {
        "no": "Generert av",
        "en": "Generated By",
    },
    # ── Risk descriptions ──
    "risk_excellent": {
        "no": "Utmerket sikkerhetsnivå",
        "en": "Excellent security level",
    },
    "risk_good": {
        "no": "Godt sikkerhetsnivå med noen forbedringspunkter",
        "en": "Good security level with some improvements needed",
    },
    "risk_moderate": {
        "no": "Moderat sikkerhetsnivå: flere forbedringer anbefales",
        "en": "Moderate security level — several improvements recommended",
    },
    "risk_poor": {
        "no": "Svakt sikkerhetsnivå: umiddelbare tiltak nødvendig",
        "en": "Poor security level — immediate action required",
    },
    "risk_critical": {
        "no": "Kritisk sikkerhetsnivå: alvorlige sårbarheter funnet",
        "en": "Critical security level — serious vulnerabilities found",
    },
    # ── Misc ──
    "no_data": {
        "no": "Ingen data tilgjengelig",
        "en": "No data available",
    },
    "yes": {
        "no": "Ja",
        "en": "Yes",
    },
    "no_word": {
        "no": "Nei",
        "en": "No",
    },
    "excluded": {
        "no": "Ekskludert",
        "en": "Excluded",
    },
    "none": {
        "no": "Ingen",
        "en": "None",
    },
    "detected": {
        "no": "Oppdaget",
        "en": "Detected",
    },
    # ── Cover / footer ──
    "confidential_notice": {
        "no": "Denne rapporten er konfidensiell og kun beregnet for {customer} og autorisert personell.",
        "en": "This report is confidential and intended only for {customer} and authorised personnel.",
    },
    # ── Executive summary ──
    "executive_summary_intro": {
        "no": "En oppsummering av de viktigste funnene fra gjennomgangen av {customer}s Microsoft 365- og Azure-miljø.",
        "en": "A summary of the most important findings from the review of {customer}'s Microsoft 365 and Azure environment.",
    },
    # ── Security posture ──
    "your_security_status": {
        "no": "Din sikkerhetsstatus",
        "en": "Your Security Status",
    },
    "posture_intro": {
        "no": "Vi har gjennomgått hele Microsoft 365- og Azure-miljøet ditt. Her er en oppsummering av hva vi fant.",
        "en": "We have reviewed your entire Microsoft 365 and Azure environment. Here is a summary of what we found.",
    },
    "posture_grade_a": {
        "no": "Miljøet er generelt godt sikret. Noen forbedringspunkter er identifisert, men ingen kritiske risikoer.",
        "en": "The environment is generally well secured. Some areas for improvement have been identified, but no critical risks.",
    },
    "posture_grade_b": {
        "no": "Miljøet er tilfredsstillende sikret, men det finnes viktige forbedringsområder som bør prioriteres.",
        "en": "The environment is adequately secured, but there are important areas for improvement that should be prioritised.",
    },
    "posture_grade_c": {
        "no": "Miljøet har flere sikkerhetsproblemer som krever tiltak. Vi anbefaler at disse prioriteres.",
        "en": "The environment has several security issues that require action. We recommend these be prioritised.",
    },
    "posture_grade_d": {
        "no": "Miljøet har kritiske sikkerhetsrisikoer. Umiddelbare tiltak er nødvendig.",
        "en": "The environment has critical security risks. Immediate action is required.",
    },
    "of_100_points": {
        "no": "av 100 poeng",
        "en": "of 100 points",
    },
    # ── Trend labels ──
    "trend_mfa_coverage": {
        "no": "MFA-dekning",
        "en": "MFA Coverage",
    },
    "trend_secure_score": {
        "no": "Secure Score",
        "en": "Secure Score",
    },
    "trend_users": {
        "no": "Brukere",
        "en": "Users",
    },
    "trend_without_mfa": {
        "no": "Uten MFA",
        "en": "Without MFA",
    },
    "trend_ca_policies": {
        "no": "CA-policyer",
        "en": "CA Policies",
    },
    "trend_device_compliance": {
        "no": "Enhetssamsvar",
        "en": "Device Compliance",
    },
    "trend_devices": {
        "no": "Enheter",
        "en": "Devices",
    },
    "trend_global_admins": {
        "no": "Globale adm.",
        "en": "Global Admins",
    },
    "trend_warnings": {
        "no": "Advarsler",
        "en": "Warnings",
    },
    "trend_risk_score": {
        "no": "Sikkerhetsscore",
        "en": "Security Score",
    },
    # ── Metric labels ──
    "total_users_label": {
        "no": "Brukere totalt",
        "en": "Total Users",
    },
    "active_n_disabled": {
        "no": "{enabled} aktive \u00b7 {disabled} deaktivert",
        "en": "{enabled} active \u00b7 {disabled} disabled",
    },
    "microsoft_secure_score": {
        "no": "Microsoft Secure Score",
        "en": "Microsoft Secure Score",
    },
    "device_compliance": {
        "no": "Enhetssamsvar",
        "en": "Device Compliance",
    },
    "ca_rules": {
        "no": "Tilgangsregler (CA)",
        "en": "Access Policies (CA)",
    },
    "n_report_mode": {
        "no": "{count} i rapport-modus",
        "en": "{count} in report-only mode",
    },
    "global_admins": {
        "no": "Globale administratorer",
        "en": "Global Administrators",
    },
    "n_role_assignments_total": {
        "no": "{count} rolletildelinger totalt",
        "en": "{count} role assignments total",
    },
    # ── Key findings section ──
    "what_we_found": {
        "no": "Hva vi fant",
        "en": "What We Found",
    },
    "key_findings_intro": {
        "no": "Vi har vurdert sikkerhetsnivået på tvers av identitet, e-post, tilgangsstyring og infrastruktur.",
        "en": "We have assessed the security level across identity, email, access management and infrastructure.",
    },
    "mfa_ok_desc": {
        "no": "{covered} av {total} aktive brukere er beskyttet med MFA.",
        "en": "{covered} of {total} active users are protected with MFA.",
    },
    "excluded_from_ca": {
        "no": "Ekskludert fra CA-policy",
        "en": "Excluded from CA policy",
    },
    "no_mfa_no_ca": {
        "no": "Ingen MFA-metoder registrert, ikke dekket av Conditional Access",
        "en": "No MFA methods registered, not covered by Conditional Access",
    },
    "mfa_registered_excluded": {
        "no": "MFA registrert, men unntatt fra håndhevelse av Conditional Access",
        "en": "MFA registered but excluded from enforcement by Conditional Access",
    },
    # ── Admin roles findings ──
    "ga_accounts_title": {
        "no": "{count} Global Administrator-kontoer",
        "en": "{count} Global Administrator accounts",
    },
    "ga_accounts_desc": {
        "no": "Microsoft anbefaler maks 2-4 Global Administratorer. For mange kontoer med fulle rettigheter øker angrepsflaten betydelig.",
        "en": "Microsoft recommends a maximum of 2\u20134 Global Administrators. Too many accounts with full privileges significantly increases the attack surface.",
    },
    "recommended_action": {
        "no": "Anbefalt tiltak",
        "en": "Recommended Action",
    },
    "ga_ok_title": {
        "no": "{count} Global Administrator-konto(er), innenfor anbefalt grense",
        "en": "{count} Global Administrator account(s) \u2014 within recommended limit",
    },
    "ga_ok_desc": {
        "no": "Antall Global Administratorer er i tråd med Microsofts anbefalinger.",
        "en": "The number of Global Administrators is in line with Microsoft\u2019s recommendations.",
    },
    # ── Intune / device findings ──
    "intune_noncompliant_title": {
        "no": "{count} enhet(er) er ikke i samsvar",
        "en": "{count} device(s) are non-compliant",
    },
    "intune_noncompliant_desc": {
        "no": "{pct}% av {total} enheter oppfyller organisasjonens samsvarspolicyer. Ikke-samsvarende enheter kan være sårbare.",
        "en": "{pct}% of {total} devices meet the organisation\u2019s compliance policies. Non-compliant devices may be vulnerable.",
    },
    "action_needed": {
        "no": "Tiltak",
        "en": "Action",
    },
    "intune_all_compliant_title": {
        "no": "Alle {count} enheter er i samsvar",
        "en": "All {count} devices are compliant",
    },
    "intune_all_compliant_desc": {
        "no": "Samtlige administrerte enheter oppfyller organisasjonens samsvarspolicyer.",
        "en": "All managed devices meet the organisation\u2019s compliance policies.",
    },
    # ── SharePoint findings ──
    "sp_sharing_open_title": {
        "no": "SharePoint ekstern deling er åpent",
        "en": "SharePoint external sharing is open",
    },
    "sp_sharing_open_desc": {
        "no": "{label}. Vurder å begrense til kun autentiserte gjester for å redusere risikoen for utilsiktet datalekkasje.",
        "en": "{label}. Consider restricting to authenticated guests only to reduce the risk of unintended data leakage.",
    },
    # ── Email security findings ──
    "email_security_title": {
        "no": "E-postsikkerhet kan forbedres på {domain}",
        "en": "Email security can be improved for {domain}",
    },
    "spf_missing": {
        "no": "SPF-posten mangler. Avsendere kan forfalske e-post fra domenet.",
        "en": "SPF record is missing \u2014 senders can spoof email from the domain.",
    },
    "dmarc_missing": {
        "no": "DMARC-posten mangler. Det finnes ingen beskyttelse mot e-postforfalskning.",
        "en": "DMARC record is missing \u2014 there is no protection against email spoofing.",
    },
    "dmarc_weak": {
        "no": "DMARC-policyen er satt til «p=none».",
        "en": 'DMARC policy is set to "none".',
    },
    # ── Conditional Access findings ──
    "no_ca_title": {
        "no": "Ingen aktive tilgangsregler (Conditional Access)",
        "en": "No active access policies (Conditional Access)",
    },
    "no_ca_desc": {
        "no": "Tilgangsregler lar dere styre hvem som kan logge inn, fra hvor, og under hvilke betingelser.",
        "en": "Access policies allow you to control who can sign in, from where, and under what conditions.",
    },
    "ca_ok_title": {
        "no": "{count} aktive tilgangsregler (Conditional Access) er på plass",
        "en": "{count} active access policies (Conditional Access) are in place",
    },
    "ca_ok_desc": {
        "no": "Tilgangsregler er konfigurert og begrenser hvem som kan logge inn og under hvilke betingelser.",
        "en": "Access policies are configured and restrict who can sign in and under what conditions.",
    },
    # ── OAuth findings ──
    "oauth_high_priv_title": {
        "no": "{count} app(er) med brede tillatelser",
        "en": "{count} app(s) with broad permissions",
    },
    "oauth_high_priv_desc": {
        "no": "Disse appene har vide tilgangsrettigheter til organisasjonens data. Gjennomgå og fjern tilganger som ikke lenger er nødvendige.",
        "en": "These apps have broad access rights to the organisation\u2019s data. Review and remove access that is no longer needed.",
    },
    # ── Secure Score findings ──
    "secure_score_low_title": {
        "no": "Microsoft Secure Score er lav ({pct}%)",
        "en": "Microsoft Secure Score is low ({pct}%)",
    },
    "secure_score_low_desc": {
        "no": "Lav score betyr at det finnes mange sikkerhetsforbedringer som kan gjøres i Microsoft 365.",
        "en": "A low score means there are many security improvements that can be made in Microsoft 365.",
    },
    "secure_score_mid_title": {
        "no": "Microsoft Secure Score kan forbedres ({pct}%)",
        "en": "Microsoft Secure Score can be improved ({pct}%)",
    },
    "secure_score_mid_desc": {
        "no": "Det finnes konkrete tiltak som kan forbedre sikkerhetsnivået i Microsoft 365.",
        "en": "There are concrete actions that can improve the security level in Microsoft 365.",
    },
    "improvement_possible": {
        "no": "Forbedring mulig",
        "en": "Improvement possible",
    },
    "secure_score_good_title": {
        "no": "Solid Microsoft Secure Score ({pct}%)",
        "en": "Solid Microsoft Secure Score ({pct}%)",
    },
    "secure_score_good_desc": {
        "no": "Dere scorer godt på Microsofts sikkerhetsmålinger.",
        "en": "You score well on Microsoft\u2019s security metrics.",
    },
    "good": {
        "no": "Bra",
        "en": "Good",
    },
    # ── Recommendations section ──
    "what_we_recommend": {
        "no": "Hva vi anbefaler",
        "en": "What We Recommend",
    },
    "recommendations_intro": {
        "no": "Disse tiltakene er sortert etter prioritet. De med høyest prioritet bør gjøres først.",
        "en": "These actions are sorted by priority. Those with the highest priority should be done first.",
    },
    "show_all_n_details": {
        "no": "Vis alle {count} detaljer",
        "en": "Show all {count} details",
    },
    "effort_label": {
        "no": "Innsats: {effort}",
        "en": "Effort: {effort}",
    },
    # ── Action plan section ──
    "prioritised_action_plan": {
        "no": "Prioritert handlingsplan",
        "en": "Prioritised Action Plan",
    },
    "action_plan_intro": {
        "no": "Denne planen kan brukes som et arbeidsdokument for å følge opp anbefalte tiltak. Fyll inn ansvarlig person, frist og status etter hvert som tiltak gjennomføres.",
        "en": "This plan can be used as a working document to follow up on recommended actions. Fill in the responsible person, deadline and status as actions are completed.",
    },
    "action_column": {
        "no": "Tiltak",
        "en": "Action",
    },
    "responsible": {
        "no": "Ansvarlig",
        "en": "Responsible",
    },
    "deadline": {
        "no": "Frist",
        "en": "Deadline",
    },
    "status_not_started": {
        "no": "Ikke startet",
        "en": "Not started",
    },
    # ── Identity & Access section ──
    "admin_roles_and_groups": {
        "no": "Administratorroller og grupper",
        "en": "Admin Roles and Groups",
    },
    "identity_access_intro": {
        "no": "Oversikt over hvem som har administrative rettigheter og hvordan grupper er organisert.",
        "en": "Overview of who has administrative privileges and how groups are organised.",
    },
    "admin_roles_label": {
        "no": "Administratorroller",
        "en": "Admin Roles",
    },
    "total_role_assignments": {
        "no": "Totalt rolletildelinger",
        "en": "Total Role Assignments",
    },
    "unique_roles": {
        "no": "Unike roller",
        "en": "Unique Roles",
    },
    "global_admins_label": {
        "no": "Globale administratorer",
        "en": "Global Administrators",
    },
    "count": {
        "no": "Antall",
        "en": "Count",
    },
    "groups_label": {
        "no": "Grupper",
        "en": "Groups",
    },
    "total_groups": {
        "no": "Totalt grupper",
        "en": "Total Groups",
    },
    "dynamic_groups": {
        "no": "Dynamiske grupper",
        "en": "Dynamic Groups",
    },
    "empty_groups": {
        "no": "Tomme grupper",
        "en": "Empty Groups",
    },
    # ── Devices section ──
    "device_management": {
        "no": "Enhetsadministrasjon (Intune)",
        "en": "Device Management (Intune)",
    },
    "devices_intro": {
        "no": "Status for administrerte enheter og samsvar med organisasjonens policyer.",
        "en": "Status of managed devices and compliance with the organisation\u2019s policies.",
    },
    "total_devices": {
        "no": "Enheter totalt",
        "en": "Total Devices",
    },
    "compliant": {
        "no": "I samsvar",
        "en": "Compliant",
    },
    "not_compliant": {
        "no": "Ikke i samsvar",
        "en": "Non-Compliant",
    },
    "compliance_rate": {
        "no": "Samsvarsgrad",
        "en": "Compliance Rate",
    },
    # ── Data & Collaboration section ──
    "sharepoint_and_teams": {
        "no": "SharePoint og Teams",
        "en": "SharePoint and Teams",
    },
    "data_collab_intro": {
        "no": "Innstillinger for fildeling, samarbeid og ekstern tilgang.",
        "en": "Settings for file sharing, collaboration and external access.",
    },
    "external_sharing": {
        "no": "Ekstern deling",
        "en": "External Sharing",
    },
    "legacy_auth": {
        "no": "Eldre autentisering",
        "en": "Legacy Authentication",
    },
    "enabled_label": {
        "no": "Aktivert",
        "en": "Enabled",
    },
    "disabled_label": {
        "no": "Deaktivert",
        "en": "Disabled",
    },
    "total_sites": {
        "no": "Totalt nettsteder",
        "en": "Total Sites",
    },
    "personal_onedrive": {
        "no": "Personlige (OneDrive)",
        "en": "Personal (OneDrive)",
    },
    "team_sites": {
        "no": "Teamnettsteder",
        "en": "Team Sites",
    },
    "active_policies": {
        "no": "{count} aktive policyer",
        "en": "{count} active policies",
    },
    "m365_groups_incl_teams": {
        "no": "M365-grupper (inkl. Teams)",
        "en": "M365 Groups (incl. Teams)",
    },
    # ── Exchange section ──
    "email_label": {
        "no": "E-post",
        "en": "Email",
    },
    "exchange_online": {
        "no": "Exchange Online",
        "en": "Exchange Online",
    },
    "exchange_intro": {
        "no": "Oversikt over e-postkonfigurasjon og sikkerhet.",
        "en": "Overview of email configuration and security.",
    },
    "mailboxes": {
        "no": "Postbokser",
        "en": "Mailboxes",
    },
    "n_user_n_shared": {
        "no": "{user} bruker \u00b7 {shared} delte",
        "en": "{user} user \u00b7 {shared} shared",
    },
    "transport_rules": {
        "no": "Transportregler",
        "en": "Transport Rules",
    },
    "forwarding": {
        "no": "Videresending",
        "en": "Forwarding",
    },
    "ext_fwd_detected_title": {
        "no": "Ekstern e-postvideresending oppdaget",
        "en": "External email forwarding detected",
    },
    "ext_fwd_detected_desc": {
        "no": "En eller flere postkasser videresender e-post til eksterne adresser. Dette er en høyrisikoindikator for dataeksfiltrering.",
        "en": "One or more mailboxes are forwarding email to external addresses. This is a high-risk indicator for data exfiltration.",
    },
    "security_policies": {
        "no": "Sikkerhetspolicyer",
        "en": "Security Policies",
    },
    "antiphish_policies": {
        "no": "Anti-phishing-policyer",
        "en": "Anti-phishing policies",
    },
    "antispam_policies": {
        "no": "Anti-spam-policyer",
        "en": "Anti-spam policies",
    },
    "connectors": {
        "no": "Koblinger (connectors)",
        "en": "Connectors",
    },
    "forwarding_label": {
        "no": "Videresending",
        "en": "Forwarding",
    },
    "mailbox_forwarding": {
        "no": "Videresending fra postbokser",
        "en": "Mailbox forwarding",
    },
    "external_forwarding": {
        "no": "Ekstern videresending",
        "en": "External forwarding",
    },
    "inbox_rules_ext_fwd": {
        "no": "Innboksregler (ekstern fwd)",
        "en": "Inbox rules (external fwd)",
    },
    "forwarding_unverified": {
        "no": "Videresending (mottaker ikke avgjort)",
        "en": "Forwarding (recipient not determined)",
    },
    "inbox_rules_unverified": {
        "no": "Innboksregler (mottaker ikke avgjort)",
        "en": "Inbox rules (recipient not determined)",
    },
    # ── Apps & Integrations section ──
    "oauth_permissions_title": {
        "no": "OAuth-tillatelser og tredjepartsapper",
        "en": "OAuth Permissions and Third-Party Apps",
    },
    "apps_intro": {
        "no": "Oversikt over apper som har tilgang til organisasjonens data via Microsoft 365.",
        "en": "Overview of apps that have access to the organisation\u2019s data via Microsoft 365.",
    },
    "unique_apps": {
        "no": "Unike apper",
        "en": "Unique Apps",
    },
    "total_grants": {
        "no": "Totalt tildelinger",
        "en": "Total Grants",
    },
    "broad_permissions": {
        "no": "Brede tillatelser",
        "en": "Broad Permissions",
    },
    "apps_broad_permissions_label": {
        "no": "Apper med brede tillatelser:",
        "en": "Apps with broad permissions:",
    },
    # ── Purview / Data Protection section ──
    "microsoft_purview": {
        "no": "Microsoft Purview",
        "en": "Microsoft Purview",
    },
    "purview_intro": {
        "no": "Oversikt over sensitivitetsmerking, DLP-policyer og oppbevaringspolicyer.",
        "en": "Overview of sensitivity labelling, DLP policies and retention policies.",
    },
    "sensitivity_labels": {
        "no": "Sensitivitetsmerker",
        "en": "Sensitivity Labels",
    },
    # Shown in place of a count when the collector could not reach the data.
    # A zero and an unasked question look the same on a report otherwise.
    "not_measured": {
        "no": "Ikke m\u00e5lt",
        "en": "Not measured",
    },
    "not_measured_note": {
        "no": "Kunne ikke hentes fra Microsoft 365. Tallet er ikke null, det er ukjent.",
        "en": "Could not be retrieved from Microsoft 365. The figure is unknown, not zero.",
    },
    "dlp_policies": {
        "no": "DLP-policyer",
        "en": "DLP Policies",
    },
    "retention_policies": {
        "no": "Oppbevaringspolicyer",
        "en": "Retention Policies",
    },
    "active_label": {
        "no": "Aktiv",
        "en": "Active",
    },
    "inactive_label": {
        "no": "Inaktiv",
        "en": "Inactive",
    },
    # ── Azure section ──
    "azure_resources": {
        "no": "Azure-ressurser",
        "en": "Azure Resources",
    },
    "azure_intro": {
        "no": "Oversikt over Azure-abonnementer og ressurser.",
        "en": "Overview of Azure subscriptions and resources.",
    },
    "subscriptions": {
        "no": "Abonnementer",
        "en": "Subscriptions",
    },
    "total_resources": {
        "no": "Ressurser totalt",
        "en": "Total Resources",
    },
    "virtual_machines": {
        "no": "Virtuelle maskiner",
        "en": "Virtual Machines",
    },
    "vm_label": {
        "no": "VM",
        "en": "VM",
    },
    "location": {
        "no": "Lokasjon",
        "en": "Location",
    },
    "os_label": {
        "no": "OS",
        "en": "OS",
    },
    "size_label": {
        "no": "Størrelse",
        "en": "Size",
    },
    "backup_coverage": {
        "no": "Backup-dekning",
        "en": "Backup Coverage",
    },
    "backup_coverage_unknown": {
        "no": "Backup-dekning kunne ikke fastslås fordi data fra Recovery Services Vault mangler. Verifiser backup manuelt før dette rapporteres.",
        "en": "Backup coverage could not be determined — Recovery Services "
        "Vault data is missing. Verify backup manually before reporting.",
    },
    "vms_total": {
        "no": "VMs totalt",
        "en": "VMs total",
    },
    "with_backup": {
        "no": "Med backup",
        "en": "With backup",
    },
    "without_backup": {
        "no": "Uten backup",
        "en": "Without backup",
    },
    "vms_without_backup": {
        "no": "VMs uten backup:",
        "en": "VMs without backup:",
    },
    # ── Backup of the Microsoft 365 data (34_m365_backup) ──
    "m365_backup_label": {
        "no": "Backup",
        "en": "Backup",
    },
    "m365_backup_title": {
        "no": "Backup av Microsoft 365-data",
        "en": "Backup of Microsoft 365 data",
    },
    "m365_backup_intro": {
        "no": "Microsoft 365 tar ikke backup av dataene for kunden. Slettede elementer kan bare hentes tilbake i en begrenset periode, og løsepengevirus eller en feil synkronisering kan overskrive dem. Auditen ser etter to ting: Microsoft 365 Backup, som er Microsofts egen tjeneste, og apper fra kjente backupleverandører med tilgang til dataene.",
        "en": "Microsoft 365 does not back up the customer's data. Deleted items can be recovered only for a limited period, and ransomware or a faulty sync can overwrite them. The audit looks for two things: Microsoft 365 Backup, Microsoft's own service, and apps from known backup vendors with access to the data.",
    },
    "m365_backup_proof_note": {
        "no": "En backupapp med tilgang viser at produktet er installert og får lese dataene. Om backupen faktisk kjører og kan gjenopprettes, må sjekkes i produktet selv.",
        "en": "A backup app with access shows that the product is installed and allowed to read the data. Whether its backups actually run and can be restored has to be checked in the product itself.",
    },
    "m365_backup_and": {
        "no": "og",
        "en": "and",
    },
    "m365_backup_wl_exchange": {
        "no": "E-post (Exchange)",
        "en": "Email (Exchange)",
    },
    "m365_backup_wl_onedrive": {
        "no": "OneDrive",
        "en": "OneDrive",
    },
    "m365_backup_wl_sharepoint": {
        "no": "SharePoint",
        "en": "SharePoint",
    },
    "m365_backup_wl_teams": {
        "no": "Teams",
        "en": "Teams",
    },
    "m365_backup_access_exchange": {
        "no": "e-post",
        "en": "email",
    },
    "m365_backup_access_onedrive": {
        "no": "OneDrive",
        "en": "OneDrive",
    },
    "m365_backup_access_sharepoint": {
        "no": "SharePoint",
        "en": "SharePoint",
    },
    "m365_backup_access_teams": {
        "no": "Teams-chat",
        "en": "Teams chats",
    },
    "m365_backup_col_workload": {
        "no": "Arbeidslast",
        "en": "Workload",
    },
    "m365_backup_col_status": {
        "no": "Status",
        "en": "Status",
    },
    "m365_backup_col_native": {
        "no": "Microsoft 365 Backup",
        "en": "Microsoft 365 Backup",
    },
    "m365_backup_col_third_party": {
        "no": "Backupapper",
        "en": "Backup apps",
    },
    "m365_backup_verdict_native": {
        "no": "Microsoft 365 Backup",
        "en": "Microsoft 365 Backup",
    },
    "m365_backup_verdict_third_party": {
        "no": "Backupapp funnet",
        "en": "Backup app found",
    },
    "m365_backup_verdict_none": {
        "no": "Ingen backup funnet",
        "en": "No backup found",
    },
    "m365_backup_verdict_unknown": {
        "no": "Kunne ikke leses",
        "en": "Could not be read",
    },
    "m365_backup_verdict_files_only": {
        "no": "Filer via SharePoint",
        "en": "Files via SharePoint",
    },
    "m365_backup_native_covered": {
        "no": "{count} beskyttet",
        "en": "{count} protected",
    },
    "m365_backup_native_covered_of": {
        "no": "{count} av {total} beskyttet",
        "en": "{count} of {total} protected",
    },
    "m365_backup_native_full_service": {
        "no": "hele tjenesten beskyttes",
        "en": "the whole service is protected",
    },
    "m365_backup_native_in_progress": {
        "no": "{count} under oppsett",
        "en": "{count} being set up",
    },
    "m365_backup_native_failed": {
        "no": "{count} feilet",
        "en": "{count} failed",
    },
    "m365_backup_native_units_unknown": {
        "no": "policyen er aktiv, men antallet beskyttede kunne ikke leses",
        "en": "the policy is active, but the number protected could not be read",
    },
    "m365_backup_native_disabled": {
        "no": "Microsoft 365 Backup er ikke aktivert",
        "en": "Microsoft 365 Backup is not enabled",
    },
    "m365_backup_native_locked": {
        "no": "Microsoft 365 Backup er låst ({status}) og tar ikke ny backup",
        "en": "Microsoft 365 Backup is locked ({status}) and takes no new backups",
    },
    "m365_backup_native_no_policy": {
        "no": "Ingen policy i Microsoft 365 Backup",
        "en": "No Microsoft 365 Backup policy",
    },
    "m365_backup_native_inactive": {
        "no": "Policyen i Microsoft 365 Backup er inaktiv",
        "en": "The Microsoft 365 Backup policy is inactive",
    },
    "m365_backup_native_no_units": {
        "no": "Policyen i Microsoft 365 Backup beskytter ingenting ennå",
        "en": "The Microsoft 365 Backup policy protects nothing yet",
    },
    "m365_backup_native_teams": {
        "no": "Microsoft 365 Backup dekker ikke chat og kanalmeldinger i Teams. Filene i Teams ligger i SharePoint.",
        "en": "Microsoft 365 Backup does not cover Teams chats and channel messages. Files in Teams live in SharePoint.",
    },
    "m365_backup_unread_permission": {
        "no": "Microsoft 365 Backup kunne ikke leses fordi Graph avviste lesingen. Oftest mangler appen tillatelsen {permission}, eller den er ikke godkjent av en administrator.",
        "en": "Microsoft 365 Backup could not be read because Graph refused the read. Most often the app lacks the {permission} permission, or it has not been admin-consented.",
    },
    "m365_backup_unread_licence": {
        "no": "Microsoft 365 Backup kunne ikke leses fordi tenanten mangler lisensen tjenesten krever.",
        "en": "Microsoft 365 Backup could not be read because the tenant lacks the licence the service requires.",
    },
    "m365_backup_unread_not_found": {
        "no": "Microsoft 365 Backup kunne ikke leses fordi Graph svarte 404 (ikke funnet), så status er ukjent.",
        "en": "Microsoft 365 Backup could not be read because Graph answered 404 (not found), so its status is unknown.",
    },
    "m365_backup_unread_error": {
        "no": "Microsoft 365 Backup kunne ikke leses på grunn av en feil, så status er ukjent.",
        "en": "Microsoft 365 Backup could not be read because of an error, so its status is unknown.",
    },
    "m365_backup_unread_short_permission": {
        "no": "Ikke lest: Graph avviste lesingen",
        "en": "Not read: Graph refused the read",
    },
    "m365_backup_unread_short_licence": {
        "no": "Ikke lest: tenanten mangler lisensen",
        "en": "Not read: the tenant lacks the licence",
    },
    "m365_backup_unread_short_not_found": {
        "no": "Ikke lest: Graph svarte 404",
        "en": "Not read: Graph answered 404",
    },
    "m365_backup_unread_short_error": {
        "no": "Ikke lest: lesingen feilet",
        "en": "Not read: the read failed",
    },
    "m365_backup_app_unread_short": {
        "no": "Ikke lest: tjenestekontoene kunne ikke leses",
        "en": "Not read: the service principals could not be read",
    },
    "m365_backup_app_found": {
        "no": "Fant backupappen {apps} med tilgang",
        "en": "Found the backup app {apps} with access",
    },
    "m365_backup_app_access": {
        "no": "Fant backupappen {app} med tilgang til {access}",
        "en": "Found the backup app {app} with access to {access}",
    },
    "m365_backup_app_none": {
        "no": "Ingen kjent backupapp har tilgang",
        "en": "No known backup app has access",
    },
    "m365_backup_app_none_teams": {
        "no": "Ingen kjent backupapp har tilgang til chat",
        "en": "No known backup app has access to chats",
    },
    "m365_backup_app_unread": {
        "no": "Tjenestekontoene i tenanten kunne ikke leses, så det er ukjent om en backupapp har tilgang.",
        "en": "The tenant's service principals could not be read, so it is unknown whether a backup app has access.",
    },
    "m365_backup_app_permissions_unread": {
        "no": "Fant {app}, men tilgangene kunne ikke leses",
        "en": "Found {app}, but its permissions could not be read",
    },
    "m365_backup_app_disabled": {
        "no": "deaktivert",
        "en": "disabled",
    },
    "m365_backup_grant_hint": {
        "no": "For å lese Microsoft 365 Backup trenger audit-appen Graph-tillatelsene BackupRestore-Control.Read.All og BackupRestore-Configuration.Read.All med administratorgodkjenning. «Sjekk tillatelser» på kundekortet viser hva som mangler.",
        "en": "To read Microsoft 365 Backup the audit app needs the Graph permissions BackupRestore-Control.Read.All and BackupRestore-Configuration.Read.All with admin consent. 'Check Permissions' on the customer card shows what is missing.",
    },
    "m365_backup_service_heading": {
        "no": "Microsoft 365 Backup (Microsofts egen tjeneste)",
        "en": "Microsoft 365 Backup (Microsoft's own service)",
    },
    "m365_backup_service_status": {
        "no": "Tjenestestatus",
        "en": "Service status",
    },
    "m365_backup_consumer": {
        "no": "Styres av",
        "en": "Controlled by",
    },
    "m365_backup_disable_reason": {
        "no": "Årsak til deaktivering",
        "en": "Reason disabled",
    },
    "m365_backup_policies_heading": {
        "no": "Beskyttelsespolicyer",
        "en": "Protection policies",
    },
    "m365_backup_no_policies": {
        "no": "Ingen beskyttelsespolicyer i Microsoft 365 Backup.",
        "en": "No protection policies in Microsoft 365 Backup.",
    },
    "m365_backup_col_policy": {
        "no": "Policy",
        "en": "Policy",
    },
    "m365_backup_col_mode": {
        "no": "Modus",
        "en": "Mode",
    },
    "m365_backup_col_protected": {
        "no": "Beskyttet",
        "en": "Protected",
    },
    "m365_backup_col_in_progress": {
        "no": "Under oppsett",
        "en": "Being set up",
    },
    "m365_backup_col_failed": {
        "no": "Feilet",
        "en": "Failed",
    },
    "m365_backup_col_total": {
        "no": "Totalt i policyen",
        "en": "Total in policy",
    },
    "m365_backup_col_counted": {
        "no": "Auditen telte",
        "en": "Audit counted",
    },
    "m365_backup_apps_heading": {
        "no": "Backupapper fra tredjepart",
        "en": "Third-party backup apps",
    },
    "m365_backup_apps_scanned": {
        "no": "Lette blant {count} tjenestekontoer etter kjente backupprodukter.",
        "en": "Searched {count} service principals for known backup products.",
    },
    "m365_backup_no_apps": {
        "no": "Ingen kjent backupapp funnet.",
        "en": "No known backup app found.",
    },
    "m365_backup_col_product": {
        "no": "Produkt",
        "en": "Product",
    },
    "m365_backup_col_app": {
        "no": "App i tenanten",
        "en": "App in the tenant",
    },
    "m365_backup_col_match": {
        "no": "Gjenkjent på",
        "en": "Recognised by",
    },
    "m365_backup_col_access": {
        "no": "Tilgang til",
        "en": "Access to",
    },
    "m365_backup_col_permissions": {
        "no": "Tillatelser",
        "en": "Permissions",
    },
    "m365_backup_match_name": {
        "no": "navn",
        "en": "name",
    },
    "m365_backup_match_app_id": {
        "no": "app-ID",
        "en": "app ID",
    },
    "m365_backup_match_generic": {
        "no": "«backup» i navnet",
        "en": "'backup' in the name",
    },
    "m365_backup_unread_heading": {
        "no": "Det som ikke kunne leses",
        "en": "What could not be read",
    },
    "m365_backup_graph_said": {
        "no": "Graph svarte",
        "en": "Graph said",
    },
    "rec_m365_backup_title": {
        "no": "Microsoft 365: ingen backup funnet for {count} arbeidslast(er)",
        "en": "Microsoft 365: no backup found for {count} workload(s)",
    },
    "rec_m365_backup_detail": {
        "no": "Auditen fant ingen tegn til backup av disse dataene: Microsoft 365 Backup beskytter dem ikke, og ingen kjent backupapp har tilgang. Microsoft 365 tar ikke backup for kunden, og slettede eller krypterte data kan bare hentes tilbake i en begrenset periode. Sjekk først om kunden bruker en backuptjeneste auditen ikke kjenner igjen. Hvis ikke, sett opp Microsoft 365 Backup i Microsoft 365 admin center (Innstillinger > Microsoft 365 Backup, betales via et Azure-abonnement) med en policy for hver arbeidslast, eller ta i bruk en backuptjeneste fra tredjepart.",
        "en": "The audit found no sign of backup for this data: Microsoft 365 Backup does not protect it, and no known backup app has access. Microsoft 365 does not back up the customer's data, and deleted or encrypted data can be recovered only for a limited period. First check whether the customer uses a backup service the audit does not recognise. If not, set up Microsoft 365 Backup in the Microsoft 365 admin center (Settings > Microsoft 365 Backup, billed through an Azure subscription) with a policy for each workload, or adopt a third-party backup service.",
    },
    "cis_m365_backup_pass": {
        "no": "Microsoft 365 Backup beskytter e-post, OneDrive og SharePoint",
        "en": "Microsoft 365 Backup protects email, OneDrive and SharePoint",
    },
    "cis_m365_backup_fail": {
        "no": "Ingen tegn til backup for {workloads}",
        "en": "No sign of backup for {workloads}",
    },
    "cis_m365_backup_third_party": {
        "no": "Backupapp med tilgang funnet ({apps}), men om backupen kjører kan ikke leses fra tenanten",
        "en": "A backup app with access was found ({apps}), but whether its backups run cannot be read from the tenant",
    },
    "cis_m365_backup_unknown": {
        "no": "Kan ikke verifiseres. {reason}",
        "en": "Cannot be verified. {reason}",
    },
    "cis_m365_backup_not_run": {
        "no": "Kan ikke verifiseres fordi backupseksjonen ikke ble kjørt",
        "en": "Cannot be verified because the backup section did not run",
    },
    "n_resources": {
        "no": "{count} ressurser",
        "en": "{count} resources",
    },
    "n_more": {
        "no": "... +{count} flere",
        "en": "... +{count} more",
    },
    "resource_types_total": {
        "no": "Ressurstyper (totalt)",
        "en": "Resource Types (total)",
    },
    "type_label": {
        "no": "Type",
        "en": "Type",
    },
    "and_n_more_types": {
        "no": "... og {count} flere typer",
        "en": "... and {count} more types",
    },
    # ── Baseline & drift reason codes (one vocabulary, shared with ui_i18n.json) ──
    # The params carry the internal path a check reads ("mfa.has_data"); the
    # sentences do not use it. The requirement's title says what is measured,
    # and a customer reading the report has no use for our field names.
    "bl_met": {
        "no": "Målt: {actual}",
        "en": "Measured: {actual}",
    },
    "bl_unmet": {
        "no": "Målt: {actual}, kravet er {op} {expected}",
        "en": "Measured: {actual}, the requirement is {op} {expected}",
    },
    "bl_guard_unset": {
        "no": "Ikke vurdert: grunnlaget kravet leser ble ikke samlet inn i denne kjøringen.",
        "en": "Not assessed: the evidence this requirement reads was not collected in this run.",
    },
    "bl_field_absent": {
        "no": "Ikke vurdert: tallet manglet i kjøringen selv om delen ble lest. Det er en feil hos oss, ikke et funn om tenanten.",
        "en": "Not assessed: the figure was missing from the run although that part was read. That is a fault on our side, not a finding about the tenant.",
    },
    "bl_incomparable": {
        "no": "Ikke vurdert: verdien {actual} kan ikke sammenlignes med kravet {expected}.",
        "en": "Not assessed: the value {actual} cannot be compared with the requirement {expected}.",
    },
    "drift_no_runs": {
        "no": "Denne kunden har ingen audit-kjøringer ennå.",
        "en": "This customer has no audit runs yet.",
    },
    "drift_no_snapshots_in_run": {
        "no": "Denne kjøringen fanget ingen policy-snapshots, så det fantes ingenting å sammenligne.",
        "en": "This run captured no policy snapshots, so there was nothing to compare.",
    },
    "drift_no_earlier_snapshots": {
        "no": "Ingen tidligere kjøring for denne kunden har policy-snapshots, så dette er første måling og ikke en sammenligning.",
        "en": "No earlier run of this customer holds policy snapshots, so this is a first measurement rather than a comparison.",
    },
    "drift_nothing_comparable": {
        "no": "Ingen snapshot i denne kjøringen kunne sammenlignes med {run}.",
        "en": "No snapshot in this run could be compared with {run}.",
    },
    "drift_comparison_failed": {
        "no": "Sammenligningen mot forrige kjøring kunne ikke fullføres.",
        "en": "The comparison against the previous run could not be completed.",
    },
    "drift_predecessor_lacked_snapshot": {
        "no": "{run} fanget ikke {name}.",
        "en": "{run} did not capture {name}.",
    },
    "drift_snapshot_unreadable": {
        "no": "{name} kunne ikke leses for sammenligning.",
        "en": "{name} could not be read for comparison.",
    },
    # ── Sybr Standard (baseline) & policy drift ──
    "baseline_label": {
        "no": "Vår standard",
        "en": "Our standard",
    },
    "baseline_intro": {
        "no": "CIS beskriver god praksis i bransjen. Denne delen viser hva Sybr krever av en kunde vi drifter. Et krav kan derfor være strengere enn CIS på identitet og mildere der det forutsetter lisenser dere ikke nødvendigvis har. Versjonsnummeret står på standarden, slik at en rapport fra i fjor fortsatt kan leses mot kravene som gjaldt da.",
        "en": "CIS describes good practice in general. This section shows what Sybr "
        "requires of a customer we run — a requirement may therefore be "
        "stricter than CIS on identity and milder where it assumes licences "
        "you may not hold. The standard carries a version, so last year's "
        "report can still be read against the requirements that applied then.",
    },
    "baseline_conformance": {
        "no": "Etterlevelse",
        "en": "Conformance",
    },
    "baseline_met": {
        "no": "Oppfylt",
        "en": "Met",
    },
    "baseline_deviation": {
        "no": "Avvik",
        "en": "Deviation",
    },
    "baseline_requirement": {
        "no": "Krav",
        "en": "Requirement",
    },
    "baseline_why": {
        "no": "Hvorfor kravet finnes",
        "en": "Why the requirement exists",
    },
    "baseline_basis": {
        "no": "Prosenten er regnet av {assessed} av {total} krav. {skipped} kunne "
        "ikke vurderes fordi datagrunnlaget mangler, og teller verken som "
        "oppfylt eller som avvik.",
        "en": "The percentage is based on {assessed} of {total} requirements. "
        "{skipped} could not be assessed for lack of data, and count neither "
        "as met nor as deviations.",
    },
    "baseline_nothing_assessed": {
        "no": "Ingen av kravene kunne vurderes i denne kjøringen. Det sier noe om innsamlingen, ikke om tenanten. Derfor oppgis ingen prosent.",
        "en": "Not one requirement could be assessed in this run. That says "
        "something about the collection, not about the tenant — so no "
        "percentage is quoted.",
    },
    "sev_critical": {"no": "Kritisk", "en": "Critical"},
    "sev_high": {"no": "Høy", "en": "High"},
    "sev_medium": {"no": "Middels", "en": "Medium"},
    "drift_heading": {
        "no": "Endringer siden forrige gjennomgang",
        "en": "Changes since the previous review",
    },
    "drift_intro": {
        "no": "Sikkerhetspolicyene sammenlignes med forrige gjennomgang. En policy som forsvinner senker sjelden Secure Score merkbart og varsles ikke av Microsoft. Den er bare borte. Derfor står endringene her, enten de er tilsiktet eller ikke.",
        "en": "The security policies are compared with the previous review. A policy "
        "that disappears rarely moves the Secure Score noticeably and raises no "
        "alert from Microsoft — it is simply gone. So changes are listed here, "
        "whether they were intended or not.",
    },
    "drift_summary": {
        "no": "Sammenlignet med gjennomgangen {run}: {added} lagt til, {removed} "
        "fjernet, {changed} endret.",
        "en": "Compared with the {run} review: {added} added, {removed} removed, "
        "{changed} changed.",
    },
    "drift_quiet": {
        "no": "Ingen av policyene er endret siden gjennomgangen {run}.",
        "en": "None of the policies have changed since the {run} review.",
    },
    "drift_not_measured": {
        "no": "Ikke sammenlignet",
        "en": "Not compared",
    },
    "drift_added": {"no": "Lagt til", "en": "Added"},
    "drift_removed": {"no": "Fjernet", "en": "Removed"},
    "drift_changed": {"no": "Endret", "en": "Changed"},
    "drift_fields": {
        "no": "Felter som er endret",
        "en": "Fields changed",
    },
    "drift_policy": {
        "no": "Policy",
        "en": "Policy",
    },
    "drift_unnamed": {
        "no": "(uten navn)",
        "en": "(unnamed)",
    },
    # ── CIS Compliance section ──
    "cis_benchmark": {
        "no": "CIS Benchmark",
        "en": "CIS Benchmark",
    },
    "compliance_intro": {
        "no": "Vurdering mot CIS Microsoft 365 Foundations Benchmark. Status viser om konfigurasjonen oppfyller anbefalte kontroller.",
        "en": "Assessment against the CIS Microsoft 365 Foundations Benchmark. Status shows whether the configuration meets recommended controls.",
    },
    "partial_warning": {
        "no": "Delvis / Advarsel",
        "en": "Partial / Warning",
    },
    "not_passed": {
        "no": "Ikke bestått",
        "en": "Not Passed",
    },
    "not_assessed": {
        "no": "Ikke vurdert",
        "en": "Not Assessed",
    },
    "evidence_label": {
        "no": "Grunnlag:",
        "en": "Evidence:",
    },
    "compliance_basis": {
        "no": "Prosenten er regnet av {assessed} av {total} kontroller. "
        "{skipped} kunne ikke vurderes fordi datagrunnlaget mangler, "
        "og teller verken som bestått eller som avvik.",
        "en": "The percentage is based on {assessed} of {total} controls. "
        "{skipped} could not be assessed for lack of data, and count "
        "neither as passed nor as findings.",
    },
    "error_files_heading": {
        "no": "Seksjoner som ikke kunne leses",
        "en": "Sections that could not be read",
    },
    "error_files_desc": {
        "no": "Disse filene inneholdt en feilmelding i stedet for data, og ble derfor "
        "ikke tolket. Kontrollene som er listet ved siden av hver fil er merket "
        "«Kan ikke verifiseres» av denne grunnen, og ikke fordi konfigurasjonen "
        "er funnet mangelfull. Innsamlingen bør kjøres på nytt for disse.",
        "en": "These files held an error message instead of data and were not parsed. "
        "The controls listed beside each file read as not verifiable for that "
        "reason, and not because the configuration was found wanting. "
        "Collection should be re-run for these.",
    },
    "error_files_affects": {
        "no": "Kontroller:",
        "en": "Controls:",
    },
    "cis_id": {
        "no": "CIS ID",
        "en": "CIS ID",
    },
    "control": {
        "no": "Kontroll",
        "en": "Control",
    },
    "category": {
        "no": "Kategori",
        "en": "Category",
    },
    "details": {
        "no": "Detaljer",
        "en": "Details",
    },
    # ── Environment overview section ──
    "your_m365_environment": {
        "no": "Ditt Microsoft 365-miljø",
        "en": "Your Microsoft 365 Environment",
    },
    "env_overview_intro": {
        "no": "En oversikt over brukere, sikkerhet, e-post og lisenser.",
        "en": "An overview of users, security, email and licences.",
    },
    "users_label": {
        "no": "Brukere",
        "en": "Users",
    },
    "total_user_count": {
        "no": "Totalt antall brukere",
        "en": "Total number of users",
    },
    "active_users": {
        "no": "Aktive brukere",
        "en": "Active users",
    },
    "disabled_users": {
        "no": "Deaktiverte brukere",
        "en": "Disabled users",
    },
    "guest_users": {
        "no": "Gjestebrukere",
        "en": "Guest users",
    },
    "hybrid_synced": {
        "no": "Hybrid-synkronisert (AD)",
        "en": "Hybrid-synced (AD)",
    },
    "security_label": {
        "no": "Sikkerhet",
        "en": "Security",
    },
    "ca_policies_label": {
        "no": "Conditional Access-policyer",
        "en": "Conditional Access policies",
    },
    # ── Email security per domain ──
    "email_security_per_domain": {
        "no": "E-postsikkerhet per domene",
        "en": "Email Security Per Domain",
    },
    "missing_label": {
        "no": "Mangler",
        "en": "Missing",
    },
    "weak_label": {
        "no": "Svak",
        "en": "Weak",
    },
    "found_label": {
        "no": "Funnet",
        "en": "Found",
    },
    # ── Licences ──
    "licences_label": {
        "no": "Lisenser",
        "en": "Licences",
    },
    "product": {
        "no": "Produkt",
        "en": "Product",
    },
    "used": {
        "no": "Brukt",
        "en": "Used",
    },
    "purchased": {
        "no": "Kjopt",
        "en": "Purchased",
    },
    "utilisation": {
        "no": "Utnyttelse",
        "en": "Utilisation",
    },
    "near_limit": {
        "no": "Nær grense",
        "en": "Near limit",
    },
    # ── Page footer (CSS @page) ──
    "page_footer_left_tech": {
        "no": "{company} · Teknisk Auditrapport",
        "en": "{company} \u2014 Technical Audit Report",
    },
    # ── Tech report specific ──
    "cover_tech_subtitle": {
        "no": "Full sikkerhetsgjennomgang",
        "en": "Full Security Audit",
    },
    "security_summary": {
        "no": "Sikkerhetsoppsummering",
        "en": "Security Summary",
    },
    "sections_run": {
        "no": "Seksjoner kj\u00f8rt",
        "en": "Sections Run",
    },
    "completed": {
        "no": "Fullf\u00f8rt",
        "en": "Completed",
    },
    "warnings_label": {
        "no": "Varsler",
        "en": "Warnings",
    },
    "failed_label": {
        "no": "Feilet",
        "en": "Failed",
    },
    "key_metrics": {
        "no": "N\u00f8kkeltall",
        "en": "Key Metrics",
    },
    "points_of_100": {
        "no": "/ 100 poeng",
        "en": "/ 100 points",
    },
    "risk_based_on_desc": {
        "no": "Basert p\u00e5 MFA-dekning, e-postsikkerhet, Secure Score, administratorroller, enhetssamsvar og kritiske funn",
        "en": "Based on MFA coverage, email security, Secure Score, admin roles, device compliance, and critical findings",
    },
    "audit_section_status": {
        "no": "Audit-seksjonsstatus",
        "en": "Audit Section Status",
    },
    "section": {
        "no": "Seksjon",
        "en": "Section",
    },
    "files": {
        "no": "Filer",
        "en": "Files",
    },
    "errors": {
        "no": "Feil",
        "en": "Errors",
    },
    "done": {
        "no": "Ferdig",
        "en": "Done",
    },
    "error_status": {
        "no": "Feil",
        "en": "Error",
    },
    "skipped": {
        "no": "Hoppet over",
        "en": "Skipped",
    },
    "users_and_mfa": {
        "no": "Brukere og MFA",
        "en": "Users & MFA",
    },
    "total": {
        "no": "Totalt",
        "en": "Total",
    },
    "without_mfa": {
        "no": "Uten MFA",
        "en": "Without MFA",
    },
    "click_to_see_unprotected": {
        "no": "Klikk for \u00e5 se ubeskyttede brukere",
        "en": "Click to see unprotected users",
    },
    "mfa_missing_alert": {
        "no": "{count} bruker(e) mangler MFA",
        "en": "{count} user(s) missing MFA",
    },
    "mfa_all_registered": {
        "no": "Alle aktive brukere har MFA registrert",
        "en": "All active users have MFA registered",
    },
    "mfa_status_per_user": {
        "no": "MFA-status per bruker",
        "en": "MFA Status Per User",
    },
    "mfa_label": {
        "no": "MFA",
        "en": "MFA",
    },
    "excl_short": {
        "no": "Ekskl.",
        "en": "Excl.",
    },
    "methods": {
        "no": "Metoder",
        "en": "Methods",
    },
    "signin_analysis": {
        "no": "Innloggingsanalyse",
        "en": "Sign-in Analysis",
    },
    "signin_no_data_license": {
        "no": "Innloggingsloggen kunne ikke hentes: den krever Microsoft Entra ID P1 "
        "(eller P2), og tenanten har ikke den lisensen. Uten den finnes det ingen "
        "sporbarhet på pålogginger, mislykkede forsøk eller mistenkelig aktivitet.",
        "en": "The sign-in log could not be retrieved: it requires Microsoft Entra ID P1 "
        "(or P2), and this tenant does not have that licence. Without it there is no "
        "record of sign-ins, failed attempts or suspicious activity.",
    },
    "signin_no_data_not_collected": {
        "no": "Innloggingsloggen ble ikke hentet i denne auditen. Sannsynlig årsak: "
        "app-registreringen mangler AuditLog.Read.All eller admin-samtykke. "
        "Merk at endepunktet i tillegg krever Microsoft Entra ID P1.",
        "en": "The sign-in log was not retrieved in this audit. Likely cause: the app "
        "registration lacks AuditLog.Read.All or its admin consent. Note that the "
        "endpoint additionally requires Microsoft Entra ID P1.",
    },
    "total_signins": {
        "no": "Totalt p\u00e5logginger",
        "en": "Total Sign-ins",
    },
    "failed_attempts": {
        "no": "Mislykkede fors\u00f8k",
        "en": "Failed Attempts",
    },
    "unique_users": {
        "no": "Unike brukere",
        "en": "Unique Users",
    },
    "brute_force_warning": {
        "no": "Mistenkelig innloggingsaktivitet oppdaget",
        "en": "Suspicious sign-in activity detected",
    },
    "brute_force_desc": {
        "no": "F\u00f8lgende bruker(e) har 50+ mislykkede p\u00e5loggingsfors\u00f8k:",
        "en": "The following user(s) have 50+ failed sign-in attempts:",
    },
    "stale_cred_warning": {
        "no": "Sannsynlig utdatert/bufret passord",
        "en": "Probable stale/cached credential",
    },
    "stale_cred_desc": {
        "no": "Følgende konto(er) har mange mislykkede pålogginger blandet med vellykkede. Dette er typisk et lagret passord på en enhet, ikke et angrep:",
        "en": "The following account(s) have many failed sign-ins interleaved with successful ones. This is typically a stored password on a device, not an attack:",
    },
    "top_failure_users": {
        "no": "Brukere med flest mislykkede fors\u00f8k",
        "en": "Users with Most Failed Attempts",
    },
    "count_header": {
        "no": "Antall",
        "en": "Count",
    },
    "common_failure_reasons": {
        "no": "Vanligste feil\u00e5rsaker",
        "en": "Most Common Failure Reasons",
    },
    "top_error_codes": {
        "no": "Vanligste feilkoder",
        "en": "Top Error Codes",
    },
    "top_source_countries": {
        "no": "Kilde-land for mislykkede fors\u00f8k",
        "en": "Top Source Countries",
    },
    "error_code": {
        "no": "Feilkode",
        "en": "Error Code",
    },
    "country": {
        "no": "Land",
        "en": "Country",
    },
    "admin_roles_pim": {
        "no": "Administratorroller og PIM",
        "en": "Admin Roles & PIM",
    },
    "too_many_global_admins": {
        "no": "For mange Global Administratorer ({count})",
        "en": "Too Many Global Administrators ({count})",
    },
    "too_many_global_admins_desc": {
        "no": "Microsoft anbefaler maks 2-4 Global Administrator-kontoer. Vurder mer spesifikke roller.",
        "en": "Microsoft recommends a maximum of 2-4 Global Administrator accounts. Consider more specific roles.",
    },
    "email_header": {
        "no": "E-post",
        "en": "Email",
    },
    "no_admin_roles": {
        "no": "Ingen administratorroller funnet",
        "en": "No admin roles found",
    },
    "emergency_access_heading": {
        "no": "N\u00f8dtilgang / Break-Glass",
        "en": "Emergency Access / Break-Glass",
    },
    "emergency_access_analysis": {
        "no": "Analyse av nødtilgang",
        "en": "Emergency Access Analysis",
    },
    "pim_assignments_heading": {
        "no": "PIM-tildelinger (Privileged Identity Management)",
        "en": "PIM Assignments (Privileged Identity Management)",
    },
    "groups_heading": {
        "no": "Grupper",
        "en": "Groups",
    },
    "dynamic_label": {
        "no": "Dynamiske",
        "en": "Dynamic",
    },
    "empty_label": {
        "no": "Tomme",
        "en": "Empty",
    },
    "group_types_label": {
        "no": "Gruppetyper",
        "en": "Group Types",
    },
    "group_name": {
        "no": "Gruppenavn",
        "en": "Group Name",
    },
    "members": {
        "no": "Medlemmer",
        "en": "Members",
    },
    "no_group_data": {
        "no": "Ingen gruppedata tilgjengelig",
        "en": "No group data available",
    },
    "license_overview": {
        "no": "Lisensoversikt",
        "en": "License Overview",
    },
    "sku_product": {
        "no": "SKU / Produktnavn",
        "en": "SKU / Product Name",
    },
    "utilization": {
        "no": "Utnyttelse",
        "en": "Utilization",
    },
    "license_data": {
        "no": "Lisensdata",
        "en": "License Data",
    },
    "conditional_access": {
        "no": "Conditional Access",
        "en": "Conditional Access",
    },
    "policies_live_heading": {
        "no": "Policyer i drift",
        "en": "Policies in production",
    },
    "policies_live_intro": {
        "no": "Policyene som faktisk er konfigurert i tenanten, slik siste audit fanget dem. Hver linje sier i klartekst hva policyen gjør.",
        "en": "The policies actually configured in the tenant, as the last audit captured them. Each line says in plain language what the policy does.",
    },
    "policy_unnamed": {"no": "(uten navn)", "en": "(unnamed)"},
    "policy_state_on": {"no": "På", "en": "On"},
    "policy_state_report": {"no": "Rapportmodus", "en": "Report-only"},
    "policy_state_off": {"no": "Av", "en": "Off"},
    "policy_state_trusted": {"no": "Betrodd", "en": "Trusted"},
    "active_policies_label": {
        "no": "Aktive policyer",
        "en": "Active Policies",
    },
    "report_mode": {
        "no": "Rapport-modus",
        "en": "Report-only Mode",
    },
    "ca_policies_heading": {
        "no": "Conditional Access-policyer",
        "en": "Conditional Access Policies",
    },
    "email_security": {
        "no": "E-postsikkerhet (SPF / DMARC / DKIM / MTA-STS)",
        "en": "Email Security (SPF / DMARC / DKIM / MTA-STS)",
    },
    "external_fwd_short": {
        "no": "Ekstern fwd",
        "en": "External fwd",
    },
    "external_fwd_detected": {
        "no": "Ekstern e-postvideresending oppdaget",
        "en": "External email forwarding detected",
    },
    "external_fwd_desc": {
        "no": "En eller flere postkasser videresender e-post til eksterne adresser. Dette er en h\u00f8yrisikoindikator for dataeksfiltrering.",
        "en": "One or more mailboxes are forwarding email to external addresses. This is a high-risk indicator of data exfiltration.",
    },
    "mailbox_overview": {
        "no": "Postboksoversikt",
        "en": "Mailbox Overview",
    },
    "user_mailboxes": {
        "no": "Brukerpostbokser",
        "en": "User Mailboxes",
    },
    "shared_mailboxes": {
        "no": "Delte postbokser",
        "en": "Shared Mailboxes",
    },
    "policy_name": {
        "no": "Policynavn",
        "en": "Policy Name",
    },
    "forwarding_and_connectors": {
        "no": "Videresending og koblinger",
        "en": "Forwarding & Connectors",
    },
    "setting": {
        "no": "Innstilling",
        "en": "Setting",
    },
    "value": {
        "no": "Verdi",
        "en": "Value",
    },
    "ms_secure_score": {
        "no": "Microsoft Secure Score",
        "en": "Microsoft Secure Score",
    },
    "points": {
        "no": "Poeng",
        "en": "Points",
    },
    "max_label": {
        "no": "Maks",
        "en": "Max",
    },
    "score": {
        "no": "Score",
        "en": "Score",
    },
    "top_improvements": {
        "no": "Topp forbedringsomr\u00e5der",
        "en": "Top Improvement Areas",
    },
    "action_label": {
        "no": "Tiltak",
        "en": "Action",
    },
    "score_pct": {
        "no": "Score %",
        "en": "Score %",
    },
    "points_left": {
        "no": "Poeng igjen",
        "en": "Points left",
    },
    "devices_intune": {
        "no": "Enheter og Intune",
        "en": "Devices & Intune",
    },
    "compliant_label": {
        "no": "Samsvar",
        "en": "Compliant",
    },
    "noncompliant_label": {
        "no": "Ikke samsvar",
        "en": "Non-compliant",
    },
    "device_compliance_low": {
        "no": "Enhetssamsvar er {pct}%",
        "en": "Device compliance is {pct}%",
    },
    "device_compliance_low_desc": {
        "no": "{non} av {total} enheter oppfyller ikke samsvarspolicyer.",
        "en": "{non} of {total} devices do not meet compliance policies.",
    },
    "device_compliance_ok_pct": {
        "no": "Enhetssamsvar: {pct}%",
        "en": "Device compliance: {pct}%",
    },
    "os_header": {
        "no": "OS",
        "en": "OS",
    },
    "enrolled": {
        "no": "Registrert",
        "en": "Enrolled",
    },
    "compliance_policies_heading": {
        "no": "Samsvarspolicyer",
        "en": "Compliance Policies",
    },
    # Coverage counts a CA-enforced user as protected even with no method
    # registered. That is defensible and it is not what "MFA coverage" sounds
    # like, so the registration figure is named beside it.
    "mfa_registered_note": {
        "no": "{pct}% har registrert en MFA-metode, mens {n} dekkes kun av Conditional Access",
        "en": "{pct}% have registered an MFA method \u2014 {n} are covered by Conditional Access alone",
    },
    "no_intune_devices": {
        "no": "Ingen Intune-enheter funnet",
        "en": "No Intune devices found",
    },
    # Distinct from the line above on purpose: "none found" is a measurement,
    # "not measured" is the absence of one, and a reader acts on them
    # differently. The sentence that follows names which refusal it was.
    "no_intune_but_entra": {
        "no": "Enheter finnes, men ingen er enrollet i Intune. ",
        "en": "Devices exist, but none are enrolled in Intune. ",
    },
    "no_intune_but_entra_desc": {
        "no": "Entra ID kjenner disse enhetene uten at Intune administrerer dem",
        "en": "Entra ID knows these devices, but Intune does not manage them",
    },
    "idle_licences": {
        "no": "Lisenser uten aktivitet. ",
        "en": "Licences with no activity. ",
    },
    "idle_licences_desc": {
        "no": "{count} lisensierte brukere har ingen registrert aktivitet siste {days} dager",
        "en": "{count} licensed users have no recorded activity in the last {days} days",
    },
    "usage_names_concealed": {
        "no": "Brukernavn er anonymisert i bruksrapportene for denne tenanten. Tallene stemmer, men navnene kan ikke knyttes til personer.",
        "en": "User names are concealed in this tenant's usage reports \u2014 the counts are accurate, but the names cannot be matched to people.",
    },
    "unmanaged_endpoints": {
        "no": "Uadministrerte endepunkter. ",
        "en": "Unmanaged endpoints. ",
    },
    "unmanaged_endpoints_desc": {
        "no": "Registrert i Entra ID, men ikke administrert av Intune",
        "en": "Registered in Entra ID but not managed by Intune",
    },
    "intune_not_measured": {
        "no": "Intune-data kunne ikke hentes. ",
        "en": "Intune data could not be collected. ",
    },
    "no_intune_desc": {
        "no": "Enten er Intune ikke konfigurert, eller sa har appen ikke tilstrekkelige rettigheter.",
        "en": "Either Intune is not configured, or the app does not have sufficient permissions.",
    },
    "sharepoint_teams": {
        "no": "SharePoint og Teams",
        "en": "SharePoint & Teams",
    },
    "sharepoint_settings": {
        "no": "SharePoint-innstillinger",
        "en": "SharePoint Settings",
    },
    "assessment": {
        "no": "Vurdering",
        "en": "Assessment",
    },
    "consider": {
        "no": "Vurder",
        "en": "Review",
    },
    "legacy_auth_label": {
        "no": "Eldre autentisering (Legacy Auth)",
        "en": "Legacy Authentication (Legacy Auth)",
    },
    "unmanaged_devices": {
        "no": "Uadministrerte enheter",
        "en": "Unmanaged Devices",
    },
    "allowed": {
        "no": "Tillatt",
        "en": "Allowed",
    },
    "blocked_restricted": {
        "no": "Blokkert/begrenset",
        "en": "Blocked/restricted",
    },
    "sites_total": {
        "no": "Nettsteder totalt",
        "en": "Total Sites",
    },
    "personal_label": {
        "no": "personlige",
        "en": "personal",
    },
    "team_label": {
        "no": "team",
        "en": "team",
    },
    "teams_settings_heading": {
        "no": "Teams-innstillinger",
        "en": "Teams Settings",
    },
    "teams_config": {
        "no": "Teams-konfigurasjon",
        "en": "Teams Configuration",
    },
    "teams_external_access_heading": {
        "no": "Teams ekstern tilgang",
        "en": "Teams External Access",
    },
    "external_access_label": {
        "no": "Ekstern tilgang",
        "en": "External Access",
    },
    "apps_oauth": {
        "no": "Apper og OAuth-tillatelser",
        "en": "Apps & OAuth Permissions",
    },
    "apps_broad_perms_alert": {
        "no": "Apper med brede tillatelser",
        "en": "Apps with broad permissions",
    },
    "delegated_perms": {
        "no": "Delegerte tillatelser (Admin Consent)",
        "en": "Delegated Permissions (Admin Consent)",
    },
    "app_label": {
        "no": "App",
        "en": "App",
    },
    "permissions_scopes": {
        "no": "Tillatelser (scopes)",
        "en": "Permissions (scopes)",
    },
    "app_permissions_heading": {
        "no": "Applikasjonstillatelser",
        "en": "Application Permissions",
    },
    "resource_header": {
        "no": "Ressurs",
        "en": "Resource",
    },
    "no_oauth_grants": {
        "no": "Ingen OAuth-tildelinger funnet",
        "en": "No OAuth grants found",
    },
    "app_registrations_heading": {
        "no": "App-registreringer",
        "en": "App Registrations",
    },
    "purview_data_protection": {
        "no": "Microsoft Purview: databeskyttelse",
        "en": "Microsoft Purview \u2014 Data Protection",
    },
    "sensitivity_labels_heading": {
        "no": "Sensitivitetsmerker",
        "en": "Sensitivity Labels",
    },
    "dlp_policies_heading": {
        "no": "DLP-policyer",
        "en": "DLP Policies",
    },
    "retention_policies_heading": {
        "no": "Oppbevaringspolicyer",
        "en": "Retention Policies",
    },
    "label_header": {
        "no": "Merke",
        "en": "Label",
    },
    "active_status": {
        "no": "Aktiv",
        "en": "Active",
    },
    "inactive_status": {
        "no": "Inaktiv",
        "en": "Inactive",
    },
    "resources_header": {
        "no": "Ressurser",
        "en": "Resources",
    },
    "vms_header": {
        "no": "VMs",
        "en": "VMs",
    },
    "advisor_recs": {
        "no": "Advisor-anbefalinger",
        "en": "Advisor Recommendations",
    },
    "orphaned_label": {
        "no": "Orphaned",
        "en": "Orphaned",
    },
    "resources_per_sub": {
        "no": "Ressurser per abonnement",
        "en": "Resources Per Subscription",
    },
    "resource_type_header": {
        "no": "Ressurstype",
        "en": "Resource Type",
    },
    "and_n_more": {
        "no": "... og {count} flere",
        "en": "... and {count} more",
    },
    "resource_groups_label": {
        "no": "Ressursgrupper",
        "en": "Resource Groups",
    },
    "virtual_machines_n": {
        "no": "Virtuelle maskiner ({count})",
        "en": "Virtual Machines ({count})",
    },
    "resource_group_header": {
        "no": "Ressursgruppe",
        "en": "Resource Group",
    },
    "location_header": {
        "no": "Lokasjon",
        "en": "Location",
    },
    "size_header": {
        "no": "St\u00f8rrelse",
        "en": "Size",
    },
    "storage_accounts_n": {
        "no": "Storage-kontoer ({count})",
        "en": "Storage Accounts ({count})",
    },
    "account_header": {
        "no": "Konto",
        "en": "Account",
    },
    "all_resource_types": {
        "no": "Alle ressurstyper (aggregert)",
        "en": "All Resource Types (aggregated)",
    },
    "no_azure_data": {
        "no": "Ingen Azure-data tilgjengelig",
        "en": "No Azure data available",
    },
    "no_azure_desc": {
        "no": "Enten har kunden ingen Azure-abonnementer, eller appens service principal mangler rollen Reader.",
        "en": "Either the customer has no Azure subscriptions, or the service principal is missing the Reader role.",
    },
    "critical_findings": {
        "no": "Kritiske funn",
        "en": "Critical Findings",
    },
    "active_defender_alerts": {
        "no": "Aktive Microsoft Defender-varsler",
        "en": "Active Microsoft Defender Alerts",
    },
    "inbox_rules_ext_fwd_detected": {
        "no": "Innboksregler videresender til eksterne adresser",
        "en": "Inbox rules forwarding to external addresses",
    },
    "inbox_rules_ext_fwd_header": {
        "no": "Innboksregler med ekstern videresending",
        "en": "Inbox rules with external forwarding",
    },
    "risky_users_idp": {
        "no": "Risikobrukere (Identity Protection)",
        "en": "Risky Users (Identity Protection)",
    },
    "risky_users_header": {
        "no": "Risikobrukere",
        "en": "Risky Users",
    },
    "all_warnings": {
        "no": "Alle varsler",
        "en": "All Warnings",
    },
    "warning_header": {
        "no": "Varsel",
        "en": "Warning",
    },
    "no_critical_findings": {
        "no": "Ingen kritiske funn",
        "en": "No critical findings",
    },
    "no_critical_desc": {
        "no": "Ingen umiddelbare sikkerhetsrisikoer oppdaget.",
        "en": "No immediate security risks detected.",
    },
    "raw_data": {
        "no": "Fullstendig radata",
        "en": "Complete Raw Data",
    },
    "raw_data_desc": {
        "no": "Alle innsamlede datafiler fra audit-kj\u00f8ringen. Filene er listet i kompakt format.",
        "en": "All collected data files from the audit run. Files are listed in compact format.",
    },
    "tab_overview": {
        "no": "Oversikt",
        "en": "Overview",
    },
    "tab_recommendations": {
        "no": "Anbefalinger",
        "en": "Recommendations",
    },
    "tab_identity": {
        "no": "Identitet",
        "en": "Identity",
    },
    "tab_devices": {
        "no": "Enheter",
        "en": "Devices",
    },
    "tab_email": {
        "no": "E-post",
        "en": "Email",
    },
    "tab_apps": {
        "no": "Apper",
        "en": "Apps",
    },
    "tab_azure": {
        "no": "Azure",
        "en": "Azure",
    },
    "tab_compliance": {
        "no": "Samsvar",
        "en": "Compliance",
    },
    "tab_findings": {
        "no": "Kritiske funn",
        "en": "Critical Findings",
    },
    "tab_rawdata": {
        "no": "Radata",
        "en": "Raw Data",
    },
    "search_placeholder": {
        "no": "Søk i rapporten...",
        "en": "Search report...",
    },
    "search_hits": {
        "no": '{count} treff for "{query}"',
        "en": '{count} results for "{query}"',
    },
    "no_results": {
        "no": "Ingen treff",
        "en": "No results",
    },
    "recommendation_label": {
        "no": "Anbefaling",
        "en": "Recommendation",
    },
    "detail_header": {
        "no": "Detalj",
        "en": "Detail",
    },
    "show_n_details": {
        "no": "Vis {count} detaljer",
        "en": "Show {count} details",
    },
    "no_critical_recs": {
        "no": "Ingen kritiske anbefalinger",
        "en": "No critical recommendations",
    },
    "no_immediate_actions": {
        "no": "Ingen umiddelbare tiltak n\u00f8dvendig.",
        "en": "No immediate actions required.",
    },
    "recommendation_heading": {
        "no": "Anbefalinger",
        "en": "Recommendations",
    },
    "page_footer_left": {
        "no": "{company} · IT-Sikkerhetsrapport",
        "en": "{company} \u2014 IT Security Report",
    },
    # ── SharePoint sharing labels (generator._parse_sharepoint_settings) ──
    "sp_sharing_disabled": {
        "no": "Ekstern deling deaktivert",
        "en": "External sharing disabled",
    },
    "sp_sharing_existing_guests": {
        "no": "Kun eksisterende gjester",
        "en": "Existing guests only",
    },
    "sp_sharing_guests_only": {
        "no": "Ekstern deling (kun gjester)",
        "en": "External sharing (guests only)",
    },
    "sp_sharing_guests_anon": {
        "no": "Ekstern deling (gjester + anonyme lenker)",
        "en": "External sharing (guests + anonymous links)",
    },
    "sp_sharing_unknown": {
        "no": "Ukjent",
        "en": "Unknown",
    },
    # ── Risk grade levels (generator._compute_risk) ──
    "risk_level_good": {
        "no": "God",
        "en": "Good",
    },
    "risk_level_satisfactory": {
        "no": "Tilfredsstillende",
        "en": "Satisfactory",
    },
    "risk_level_needs_action": {
        "no": "Krever tiltak",
        "en": "Needs Action",
    },
    "risk_level_weak": {
        "no": "Svakt",
        "en": "Weak",
    },
    "risk_level_critical": {
        "no": "Kritisk",
        "en": "Critical",
    },
    "risk_level_invalid": {
        "no": "Ufullstendige data",
        "en": "Insufficient data",
    },
    # ── What the score could not read (risk._compute_risk) ──
    "risk_gap_mfa": {
        "no": "MFA-dekning utilgjengelig: auditen mangler brukerdata (sjekk Graph-tillatelser)",
        "en": "MFA coverage unavailable: the audit has no user data (check the Graph permissions)",
    },
    "risk_dq_mfa_unavailable": {
        "no": "MFA-dekning utilgjengelig",
        "en": "MFA coverage unavailable",
    },
    "risk_dq_mfa_partial_base": {
        "no": "MFA-dekning målt på {measured} av {total} brukere ({unknown} oppslag feilet)",
        "en": "MFA coverage measured on {measured} of {total} users ({unknown} lookups failed)",
    },
    "risk_dq_secure_score": {
        "no": "Microsoft Secure Score utilgjengelig",
        "en": "Microsoft Secure Score unavailable",
    },
    "risk_dq_email_dns": {
        "no": "E-postsikkerhet ikke vurdert: DNS-oppslag feilet",
        "en": "Email security not assessed: the DNS lookups failed",
    },
    "risk_dq_admin_roles": {
        "no": "Admin-roller utilgjengelig",
        "en": "Admin roles unavailable",
    },
    "risk_dq_intune": {
        "no": "Intune-data utilgjengelig",
        "en": "Intune data unavailable",
    },
    "risk_dq_sharepoint": {
        "no": "SharePoint-konfigurasjon utilgjengelig",
        "en": "SharePoint configuration unavailable",
    },
    "risk_dq_oauth": {
        "no": "OAuth-grants utilgjengelig",
        "en": "OAuth grants unavailable",
    },
    "risk_dq_risky_users": {
        "no": "Risikobrukere ikke vurdert (krever Entra ID P2 og AuditLog-tilgang)",
        "en": "Risky users not assessed (requires Entra ID P2 and AuditLog access)",
    },
    "risk_dq_defender": {
        "no": "Defender-varsler utilgjengelig: aktive varsler er ikke vurdert",
        "en": "Defender alerts unavailable: active alerts were not assessed",
    },
    "risk_dq_section_incomplete": {
        "no": "{section} ble ikke fullført, så funnene derfra mangler i scoren",
        "en": "{section} did not complete, so its findings are missing from the score",
    },
    "risk_dq_network_unreadable": {
        "no": "Nettverksaudit utilgjengelig: {file} kunne ikke leses (scoren mangler inntil 15 poeng straff)",
        "en": "Network audit unavailable: {file} could not be read (the score is missing up to 15 penalty points)",
    },
    "risk_dq_fg_admins": {
        "no": "FortiGate-administratorer kunne ikke leses, så 2FA/trust-host-funn mangler",
        "en": "FortiGate administrators could not be read, so the 2FA and trusted-host findings are missing",
    },
    "risk_dq_fg_policies": {
        "no": "FortiGate-brannmurregler kunne ikke leses, så allow-all/logging-funn mangler",
        "en": "FortiGate firewall rules could not be read, so the allow-all and logging findings are missing",
    },
    "posture_grade_invalid": {
        "no": "Auditen mangler kritiske data (typisk brukerliste eller MFA-status). Et tall-grade her ville vært villedende. Verifiser Graph-tillatelser i app-registreringen og kjør auditen på nytt før resultatet brukes mot kunden.",
        "en": "The audit is missing critical data (typically the user list or MFA status). A numeric grade here would be misleading. Verify Graph permissions on the app registration and re-run the audit before using these results.",
    },
    "posture_blocking_gaps_label": {
        "no": "Manglende data:",
        "en": "Missing data:",
    },
    "data_unavailable": {
        "no": "Ikke tilgjengelig",
        "en": "Not available",
    },
    "data_unavailable_short": {
        "no": "—",
        "en": "—",
    },
    "mfa_data_missing_finding": {
        "no": "MFA-status kunne ikke verifiseres",
        "en": "MFA status could not be verified",
    },
    "mfa_data_missing_desc": {
        "no": "Auditen klarte ikke å hente brukerlisten fra Microsoft Graph, så MFA-dekning er ukjent. Dette betyr ikke at MFA er fraværende, men at vi ikke vet. Verifiser at app-registreringen har User.Read.All og UserAuthenticationMethod.Read.All og kjør auditen på nytt.",
        "en": "The audit could not retrieve the user list from Microsoft Graph, so MFA coverage is unknown. This does not mean MFA is absent — it means we do not know. Verify that the app registration has User.Read.All and UserAuthenticationMethod.Read.All and re-run the audit.",
    },
    # ── CIS compliance details (generator._build_compliance_map) ──
    "cis_cat_identity": {
        "no": "Identitet",
        "en": "Identity",
    },
    "cis_cat_email": {
        "no": "E-post",
        "en": "Email",
    },
    "cis_cat_devices": {
        "no": "Enheter",
        "en": "Devices",
    },
    "cis_cat_data": {
        "no": "Data",
        "en": "Data",
    },
    "cis_cat_general": {
        "no": "Generelt",
        "en": "General",
    },
    "cis_cat_applications": {
        "no": "Applikasjoner",
        "en": "Applications",
    },
    "cis_cat_teams": {
        "no": "Teams",
        "en": "Teams",
    },
    "cis_cat_logging": {
        "no": "Logging og overvåking",
        "en": "Logging & Monitoring",
    },
    "cis_mfa_coverage": {
        "no": "MFA-dekning: {pct:.0f}%",
        "en": "MFA coverage: {pct:.0f}%",
    },
    "cis_mfa_partial": {
        "no": "MFA-dekning: {pct:.0f}% ({no_mfa} brukere uten håndhevet MFA)",
        "en": "MFA coverage: {pct:.0f}% \u2014 {no_mfa} users without enforced MFA",
    },
    "cis_mfa_unavailable": {
        "no": "Kan ikke verifiseres: MFA-data utilgjengelig",
        "en": "Cannot be verified: MFA data unavailable",
    },
    "cis_mfa_none": {
        "no": "Ingen håndhevet MFA: 0% dekning ({no_mfa} brukere uten håndhevet MFA)",
        "en": "No enforced MFA — 0% coverage ({no_mfa} users without enforced MFA)",
    },
    "cis_active_policies": {
        "no": "{count} aktive policyer",
        "en": "{count} active policies",
    },
    "cis_no_active_ca": {
        "no": "Ingen aktive CA-policyer",
        "en": "No active CA policies",
    },
    "cis_ga_count": {
        "no": "{count} Global Administratorer",
        "en": "{count} Global Administrators",
    },
    "cis_ga_too_many": {
        "no": "{count} Global Administratorer (anbefalt maks 4)",
        "en": "{count} Global Administrators \u2014 recommended max 4",
    },
    "cis_ga_too_few": {
        "no": "Kun {count} Global Admin (anbefalt minimum 2)",
        "en": "Only {count} Global Admin \u2014 recommended minimum 2",
    },
    "cis_oauth_warn": {
        "no": "{apps} apper med {grants} tildelinger, {high_priv} med brede rettigheter. {app_regs} app-registreringer.",
        "en": "{apps} apps with {grants} grants, {high_priv} with broad permissions. {app_regs} app registrations.",
    },
    "cis_oauth_info": {
        "no": "{apps} apper med {grants} tildelinger. {app_regs} app-registreringer.",
        "en": "{apps} apps with {grants} grants. {app_regs} app registrations.",
    },
    "cis_spf_missing": {
        "no": "Mangler",
        "en": "Missing",
    },
    "cis_dmarc_missing": {
        "no": "Mangler",
        "en": "Missing",
    },
    "cis_sp_open": {
        "no": "\u00c5pent",
        "en": "Open",
    },
    "cis_compliance_pct": {
        "no": "{pct:.0f}% samsvar",
        "en": "{pct:.0f}% compliance",
    },
    "cis_compliance_partial": {
        "no": "{pct:.0f}% samsvar ({noncompliant} ikke-samsvarende)",
        "en": "{pct:.0f}% compliance \u2014 {noncompliant} non-compliant",
    },
    "cis_entra_devices_unmanaged": {
        "no": "{total} enheter er registrert i Entra ID, men ingen er innrullert i Intune, så ingen samsvarspolicy gjelder for dem",
        "en": "{total} devices registered in Entra ID, none enrolled in Intune \u2014 no compliance policy applies to them",
    },
    "cis_no_intune": {
        "no": "Ingen Intune-enheter funnet",
        "en": "No Intune devices found",
    },
    "cis_legacy_auth_enabled": {
        "no": "Legacy auth aktivert for SharePoint",
        "en": "Legacy auth enabled for SharePoint",
    },
    "cis_legacy_auth_disabled": {
        "no": "Legacy auth deaktivert",
        "en": "Legacy auth disabled",
    },
    # A row with no reading says why: cis_cannot_verify wraps a cis_gap_* reason,
    # cis_not_licensed a cis_lic_* one (compliance._Audit.cannot_verify and
    # .not_licensed).
    "cis_cannot_verify": {
        "no": "Kan ikke verifiseres: {reason}",
        "en": "Cannot be verified: {reason}",
    },
    "cis_not_licensed": {
        "no": "Ikke lisensiert: {reason}",
        "en": "Not licensed: {reason}",
    },
    "cis_joiner_and": {
        "no": " og ",
        "en": " and ",
    },
    "cis_gap_data": {
        "no": "data utilgjengelig",
        "en": "data unavailable",
    },
    "cis_gap_audit_data": {
        "no": "audit-data utilgjengelig",
        "en": "audit data unavailable",
    },
    "cis_gap_field_not_collected": {
        "no": "auditen er kjørt før dette feltet ble samlet inn. Kjør en ny audit",
        "en": "the audit ran before this field was collected. Run a new audit",
    },
    # 1.1.2 phishing-resistant MFA
    "cis_gap_auth_methods_policy": {
        "no": "autentiseringsmetode-policy utilgjengelig",
        "en": "authentication methods policy unavailable",
    },
    "cis_phish_resistant_enabled": {
        "no": "Phishing-resistant metoder aktivert: {methods}",
        "en": "Phishing-resistant methods enabled: {methods}",
    },
    "cis_phish_resistant_none": {
        "no": "Ingen phishing-resistant metoder (FIDO2 / Windows Hello / x509Certificate) er aktivert i autentiseringsmetode-policyen",
        "en": "No phishing-resistant methods (FIDO2 / Windows Hello / x509Certificate) are enabled in the authentication methods policy",
    },
    # 1.1.3 Global Admins
    "cis_gap_admin_roles": {
        "no": "admin-rolle data utilgjengelig",
        "en": "admin role data unavailable",
    },
    "cis_ga_none_standing": {
        "no": "Ingen faste Global Admin-tildelinger funnet. Verifiser PIM/JIT-oppsettet",
        "en": "No standing Global Admin assignments found. Verify the PIM/JIT setup",
    },
    # 1.1.5 PIM
    "cis_gap_pim": {
        "no": "PIM-data utilgjengelig",
        "en": "PIM data unavailable",
    },
    "cis_pim_found": {
        "no": "{count} PIM-berettigede rolletildelinger funnet",
        "en": "{count} PIM-eligible role assignments found",
    },
    "cis_lic_pim": {
        "no": "PIM krever Entra ID P2, som ikke er tildelt noen bruker",
        "en": "PIM requires Entra ID P2, which is not assigned to any user",
    },
    "cis_pim_none": {
        "no": "Ingen PIM-tildelinger funnet, så roller kan være permanent tildelt",
        "en": "No PIM assignments found, so roles may be permanently assigned",
    },
    # 1.1.6 emergency access
    "cis_gap_break_glass_skipped": {
        "no": "break-glass-sjekken ble hoppet over eller mangler oppsummering",
        "en": "the break-glass check was skipped or has no summary",
    },
    "cis_gap_ca_exclusions": {
        "no": "CA-unntak ble ikke samlet inn, så nødtilgangskontoer kan ikke bekreftes",
        "en": "Conditional Access exclusions were not collected, so emergency access accounts cannot be confirmed",
    },
    "cis_break_glass_found": {
        "no": "{count} nødtilgangskonto(er) (break glass) oppdaget",
        "en": "{count} emergency access account(s) (break glass) detected",
    },
    "cis_break_glass_in_use": {
        "no": "Adminkonto(er) er unntatt fra Conditional Access, men ingen fungerer som en gyldig nødtilgangskonto (kontoen(e) er i aktiv bruk)",
        "en": "Admin account(s) are excluded from Conditional Access, but none qualifies as an emergency access account (the account(s) are in active use)",
    },
    "cis_break_glass_none": {
        "no": "Ingen administrator er unntatt fra Conditional Access, og ingen dedikert nødtilgangskonto er konfigurert",
        "en": "No administrator is excluded from Conditional Access, and no dedicated emergency access account is configured",
    },
    # 1.2.1 banned passwords
    "cis_gap_directory_settings": {
        "no": "katalog-innstillinger kunne ikke leses",
        "en": "the directory settings could not be read",
    },
    "cis_banned_pw_active": {
        "no": "Egendefinert forbudt passordliste er aktiv",
        "en": "A custom banned password list is active",
    },
    "cis_lic_banned_pw": {
        "no": "egendefinert passordliste krever Entra ID P1, som ikke er tildelt noen bruker",
        "en": "a custom banned password list requires Entra ID P1, which is not assigned to any user",
    },
    "cis_banned_pw_default_only": {
        "no": "Kun Microsofts standardliste, ingen egendefinerte forbudte passord",
        "en": "Only Microsoft's global list, no custom banned passwords",
    },
    # 1.4 Secure Score
    "cis_gap_secure_score": {
        "no": "Secure Score-data utilgjengelig",
        "en": "Secure Score data unavailable",
    },
    # 5.1.1 legacy authentication
    "cis_gap_ca": {
        "no": "Conditional Access-data utilgjengelig",
        "en": "Conditional Access data unavailable",
    },
    "cis_gap_client_app_scope": {
        "no": "auditen er kjørt før klientapp-omfang ble samlet inn. Kjør en ny audit",
        "en": "the audit ran before the client app scope was collected. Run a new audit",
    },
    "cis_legacy_blocked": {
        "no": "En aktivert CA-policy blokkerer eldre klienter (exchangeActiveSync, other)",
        "en": "An enabled CA policy blocks legacy clients (exchangeActiveSync, other)",
    },
    "cis_legacy_not_blocked": {
        "no": "Ingen aktivert CA-policy blokkerer eldre autentisering",
        "en": "No enabled CA policy blocks legacy authentication",
    },
    # 1.1.7 baseline sign-in protection
    "cis_gap_security_defaults": {
        "no": "Security Defaults-status utilgjengelig",
        "en": "Security Defaults status unavailable",
    },
    "cis_gap_sd_off_ca_unknown": {
        "no": "Security Defaults er av, men CA-data er utilgjengelig",
        "en": "Security Defaults is off, but Conditional Access data is unavailable",
    },
    "cis_sd_enabled": {
        "no": "Security Defaults er aktivert",
        "en": "Security Defaults is enabled",
    },
    "cis_sd_off_ca_active": {
        "no": "Security Defaults er av, men {count} CA-policyer er aktive",
        "en": "Security Defaults is off, but {count} CA policies are active",
    },
    "cis_sd_off_no_ca": {
        "no": "Verken Security Defaults eller aktive CA-policyer",
        "en": "Neither Security Defaults nor any active CA policies",
    },
    # 1.1.8 access reviews
    "cis_gap_access_reviews": {
        "no": "data om tilgangsgjennomganger utilgjengelig",
        "en": "access review data unavailable",
    },
    "cis_access_reviews_found": {
        "no": "{count} tilgangsgjennomgang(er) definert",
        "en": "{count} access review(s) defined",
    },
    "cis_lic_access_reviews": {
        "no": "tilgangsgjennomganger krever Entra ID P2, som ikke er tildelt noen bruker",
        "en": "access reviews require Entra ID P2, which is not assigned to any user",
    },
    "cis_access_reviews_none": {
        "no": "Ingen tilgangsgjennomganger definert",
        "en": "No access reviews defined",
    },
    # 1.1.9 cross-tenant access
    "cis_gap_cross_tenant": {
        "no": "kryssleie-innstillinger utilgjengelig",
        "en": "cross-tenant access settings unavailable",
    },
    "cis_xt_direct_in_allowed": {
        "no": "B2B direct connect inn er tillatt, så eksterne organisasjoner kan nå delte Teams-kanaler uten gjestekonto",
        "en": "Inbound B2B direct connect is allowed, so external organisations can reach shared Teams channels without a guest account",
    },
    "cis_xt_system_default": {
        "no": "Kjører Microsofts systemstandard: kryssleie-tilgang er aldri vurdert",
        "en": "Running on Microsoft's system default: cross-tenant access has never been reviewed",
    },
    "cis_xt_configured": {
        "no": "Kryssleie-tilgang er konfigurert, og direct connect inn er ikke tillatt",
        "en": "Cross-tenant access is configured, and inbound direct connect is not allowed",
    },
    # 2.1.2 app credentials
    "cis_gap_app_registrations": {
        "no": "app-registreringer utilgjengelig",
        "en": "app registrations unavailable",
    },
    "cis_app_creds_none_expired": {
        "no": "Ingen apphemmeligheter eller -sertifikater er utløpt",
        "en": "No expired app credentials",
    },
    "cis_app_creds_expired": {
        "no": "{count} apphemmeligheter eller -sertifikater er utløpt",
        "en": "{count} expired app credentials detected",
    },
    "cis_app_creds_expiring": {
        "no": "{count} apphemmeligheter eller -sertifikater utløper snart (innen {days} dager)",
        "en": "{count} app credentials expire soon (within {days} days)",
    },
    # 3.1.1, 3.2.1, 7.2.2 Purview
    "cis_dlp_count": {
        "no": "{count} DLP-policyer konfigurert",
        "en": "{count} DLP policies configured",
    },
    "cis_dlp_found": {
        "no": "DLP-policyer funnet",
        "en": "DLP policies found",
    },
    "cis_dlp_none": {
        "no": "Ingen DLP-policyer funnet",
        "en": "No DLP policies found",
    },
    "cis_gap_dlp": {
        "no": "Purview DLP-data utilgjengelig",
        "en": "Purview DLP data unavailable",
    },
    "cis_labels_count": {
        "no": "{count} sensitivitetsetiketter publisert",
        "en": "{count} sensitivity labels published",
    },
    "cis_labels_none": {
        "no": "Ingen sensitivitetsetiketter funnet",
        "en": "No sensitivity labels found",
    },
    "cis_gap_labels": {
        "no": "Purview-etikettdata utilgjengelig",
        "en": "Purview label data unavailable",
    },
    "cis_retention_count": {
        "no": "{count} oppbevaringspolicyer",
        "en": "{count} retention policies",
    },
    "cis_retention_none": {
        "no": "Ingen oppbevaringspolicyer funnet",
        "en": "No retention policies found",
    },
    "cis_gap_retention": {
        "no": "Purview-oppbevaringsdata utilgjengelig",
        "en": "Purview retention data unavailable",
    },
    # 7.2.4 anonymous sharing links
    "cis_gap_onedrive": {
        "no": "OneDrive-delingsdata utilgjengelig",
        "en": "OneDrive sharing data unavailable",
    },
    "cis_od_gap_refused": {
        "no": "{count} stasjon(er) kunne ikke leses",
        "en": "{count} drive(s) could not be read",
    },
    "cis_od_gap_discovery": {
        "no": "{count} oppdagelseskall feilet",
        "en": "{count} discovery call(s) failed",
    },
    "cis_od_gap_folders": {
        "no": "{count} mappe(r) kunne ikke leses",
        "en": "{count} folder(s) could not be read",
    },
    "cis_od_gap_limit": {
        "no": "søket nådde en grense før det var ferdig",
        "en": "the scan hit a limit before it finished",
    },
    "cis_od_scope_unknown": {
        "no": "omfanget av søket er ukjent",
        "en": "the scope of the scan is unknown",
    },
    "cis_od_partial": {
        "no": "Ingen anonyme delingslenker funnet i det som ble gjennomsøkt, men {gaps}, så fravær er ikke bekreftet for hele tenanten",
        "en": "No anonymous sharing links found in what was scanned, but {gaps}, so their absence is not confirmed for the whole tenant",
    },
    "cis_od_none": {
        "no": "Ingen anonyme delingslenker funnet i {count} stasjon(er)",
        "en": "No anonymous sharing links found in {count} drive(s)",
    },
    "cis_od_anyone": {
        "no": "{count} anonym(e) delingslenke(r) som kan åpnes uten pålogging",
        "en": "{count} anonymous sharing link(s) that open without sign-in",
    },
    # 7.2.1, 7.2.3 SharePoint
    "cis_gap_sp_tenant": {
        "no": "SharePoint-tenant-innstillinger utilgjengelig",
        "en": "SharePoint tenant settings unavailable",
    },
    "cis_gap_sp_settings": {
        "no": "SharePoint-innstillinger utilgjengelig",
        "en": "SharePoint settings unavailable",
    },
    # 4.1 mailbox audit
    "cis_mailbox_audit_on": {
        "no": "Postbokslogging er aktivert (AuditDisabled=False)",
        "en": "Mailbox auditing is enabled (AuditDisabled=False)",
    },
    "cis_mailbox_audit_off": {
        "no": "Postbokslogging er deaktivert (AuditDisabled=True)",
        "en": "Mailbox auditing is disabled (AuditDisabled=True)",
    },
    "cis_mailbox_audit_unclear": {
        "no": "Kunne ikke fastslå audit-status fra org-config",
        "en": "Could not determine the audit status from the organisation config",
    },
    "cis_gap_exo_org_config": {
        "no": "Exchange-organisasjonsoppsettet ble ikke samlet inn",
        "en": "the Exchange organisation config was not collected",
    },
    # 4.2, 4.3 anti-phishing and anti-spam
    "cis_antiphish_found": {
        "no": "{count} anti-phishing-policy(er) konfigurert",
        "en": "{count} anti-phishing policy(ies) configured",
    },
    "cis_antiphish_none": {
        "no": "Ingen anti-phishing-policyer konfigurert",
        "en": "No anti-phishing policies configured",
    },
    "cis_gap_antiphish": {
        "no": "anti-phishing-data utilgjengelig",
        "en": "anti-phishing data unavailable",
    },
    "cis_antispam_found": {
        "no": "{count} anti-spam-policy(er) konfigurert",
        "en": "{count} anti-spam policy(ies) configured",
    },
    "cis_antispam_none": {
        "no": "Ingen anti-spam-policyer konfigurert",
        "en": "No anti-spam policies configured",
    },
    "cis_gap_antispam": {
        "no": "anti-spam-data utilgjengelig (kjør Get-HostedContentFilterPolicy i EOP)",
        "en": "anti-spam data unavailable (run Get-HostedContentFilterPolicy in EOP)",
    },
    # 4.4 external forwarding
    "cis_fwd_external": {
        "no": "Ekstern videresending oppdaget på en eller flere postbokser",
        "en": "External forwarding detected on one or more mailboxes",
    },
    "cis_fwd_unverified_mailboxes": {
        "no": "{count} postboks(er)",
        "en": "{count} mailbox(es)",
    },
    "cis_fwd_unverified_rules": {
        "no": "{count} innboksregel(er)",
        "en": "{count} inbox rule(s)",
    },
    "cis_fwd_unverified": {
        "no": "{what} videresender til en mottaker auditen ikke kunne plassere innenfor eller utenfor tenanten",
        "en": "{what} forward to a recipient the audit could not place inside or outside the tenant",
    },
    "cis_fwd_none": {
        "no": "Ingen ekstern videresending oppdaget",
        "en": "No external forwarding detected",
    },
    "cis_gap_forwarding": {
        "no": "videresendingsdata utilgjengelig",
        "en": "forwarding data unavailable",
    },
    # 4.5, 4.6 Safe Links and Safe Attachments ({policy} is the product name)
    "cis_defender_active": {
        "no": "{count} aktiv(e) {policy}-policy(er)",
        "en": "{count} active {policy} policy(ies)",
    },
    "cis_defender_disabled": {
        "no": "{policy}-policy(er) finnes men er deaktivert",
        "en": "{policy} policy(ies) exist but are disabled",
    },
    "cis_lic_defender": {
        "no": "{policy} krever Defender for Office 365 Plan 1",
        "en": "{policy} requires Defender for Office 365 Plan 1",
    },
    "cis_defender_none": {
        "no": "Ingen {policy}-policyer funnet",
        "en": "No {policy} policies found",
    },
    "cis_gap_defender_policies": {
        "no": "Defender-policydata utilgjengelig",
        "en": "Defender policy data unavailable",
    },
    # 5.2.1-5.2.3 SPF, DMARC and DKIM, per domain
    "cis_gap_spf_lookup": {
        "no": "SPF-oppslaget for {domain} feilet med {result}",
        "en": "the SPF lookup for {domain} failed with {result}",
    },
    "cis_dmarc_monitor_only": {
        "no": "p=none (kun overvåking): {record}",
        "en": "p=none (monitoring only): {record}",
    },
    "cis_gap_dmarc_lookup": {
        "no": "DMARC-oppslaget for {domain} feilet med {result}",
        "en": "the DMARC lookup for {domain} failed with {result}",
    },
    "cis_dkim_exchange_signs": {
        "no": "DKIM-signering er aktivert i Exchange Online for {domain}",
        "en": "DKIM signing is enabled in Exchange Online for {domain}",
    },
    "cis_dkim_no_mail": {
        "no": "{domain} sender ikke e-post (SPF: v=spf1 -all), så DKIM trengs ikke",
        "en": "{domain} sends no mail (SPF: v=spf1 -all), so DKIM is not needed",
    },
    "cis_dkim_third_party_signs": {
        "no": "{domain} sender e-post via {name}, som har publisert DKIM-nøkkel (selektor {selector})",
        "en": "{domain} sends mail through {name}, which has published a DKIM key (selector {selector})",
    },
    "cis_dkim_third_party_unsigned": {
        "no": "{domain} sender e-post via {senders}, men ingen DKIM-nøkkel for avsenderen er funnet",
        "en": "{domain} sends mail through {senders}, but no DKIM key for the sender was found",
    },
    "cis_dkim_exchange_not_signing": {
        "no": "DKIM-signering er ikke aktivert i Exchange Online for {domain}",
        "en": "DKIM signing is not enabled in Exchange Online for {domain}",
    },
    "cis_gap_dkim_lookup": {
        "no": "DKIM-oppslaget for M365-selektorene til {domain} feilet med {result}",
        "en": "the DKIM lookup for the M365 selectors of {domain} failed with {result}",
    },
    "cis_gap_dkim_not_fetched": {
        "no": "DKIM-signeringen i Exchange Online for {domain} ble ikke hentet, men M365-selektorene er publisert i DNS",
        "en": "Exchange Online's DKIM signing for {domain} was not fetched, but the M365 selectors are published in DNS",
    },
    "cis_gap_dkim_unchecked": {
        "no": "DKIM ikke kontrollert for dette domenet",
        "en": "DKIM not checked for this domain",
    },
    "cis_dkim_no_m365_selectors": {
        "no": "Ingen M365 DKIM-selektorer er publisert for {domain}, så Exchange Online signerer ikke e-posten med domenet",
        "en": "No M365 DKIM selectors are published for {domain}, so Exchange Online does not sign mail with the domain",
    },
    "cis_dkim_key_scope": {
        "no": "{detail}; DKIM-nøkkelen for {names} gjelder bare e-post {names} sender",
        "en": "{detail}; the DKIM key for {names} covers only mail {names} sends",
    },
    "cis_dkim_key_scope_exchange_too": {
        "no": "{detail}; DKIM-nøkkelen for {names} gjelder bare e-post {names} sender, og SPF viser at Exchange Online også sender for domenet",
        "en": "{detail}; the DKIM key for {names} covers only mail {names} sends, and SPF shows that Exchange Online also sends for the domain",
    },
    # 6.1.1 device compliance
    "cis_gap_intune": {
        "no": "Intune-data utilgjengelig",
        "en": "Intune data unavailable",
    },
    "cis_gap_intune_policies": {
        "no": "Intune-samsvarspolicyer utilgjengelig",
        "en": "Intune compliance policies unavailable",
    },
    "cis_devices_no_policies": {
        "no": "Enheter er innrullert, men ingen Intune-samsvarspolicyer er konfigurert",
        "en": "Devices are enrolled, but no Intune compliance policies are configured",
    },
    "cis_policies_no_devices": {
        "no": "{count} samsvarspolicy(er) konfigurert (ingen enheter innrullert)",
        "en": "{count} compliance policy(ies) configured (no devices enrolled)",
    },
    # 8.1.1, 8.1.2 Teams
    "cis_gap_teams_external": {
        "no": "data om ekstern tilgang i Teams utilgjengelig",
        "en": "Teams external access data unavailable",
    },
    "cis_gap_teams_policy_default": {
        "no": "kryssleie-tilgangspolicy ikke innsamlet eller tenant på Microsoft-standard",
        "en": "cross-tenant access policy not collected, or the tenant is on Microsoft's default",
    },
    "cis_teams_direct_open": {
        "no": "B2B Direct Connect innkommende tillater ekstern tilgang uten begrensning",
        "en": "Inbound B2B Direct Connect allows external access without restriction",
    },
    "cis_teams_collab_open": {
        "no": "B2B Collaboration innkommende tillater ekstern tilgang og bør begrenses mot policy",
        "en": "Inbound B2B Collaboration allows external access and should be restricted to policy",
    },
    "cis_teams_restricted": {
        "no": "Ekstern tilgang er begrenset",
        "en": "External access is restricted",
    },
    "cis_teams_unrestricted": {
        "no": "Ekstern tilgang er uten begrensninger (anyone-mode)",
        "en": "External access has no restrictions (anyone mode)",
    },
    "cis_teams_limited": {
        "no": "Ekstern tilgang er aktivert med begrensninger og bør gjennomgås mot policy",
        "en": "External access is enabled with restrictions and should be reviewed against policy",
    },
    "cis_gap_guest_settings": {
        "no": "gjesteinnstillinger ble ikke hentet",
        "en": "guest settings were not fetched",
    },
    "cis_guest_settings": {
        "no": "Invitasjoner: {invites}. Gjesterolle: {role}",
        "en": "Invitations: {invites}. Guest role: {role}",
    },
    "cis_guest_role_unknown": {
        "no": "ukjent",
        "en": "unknown",
    },
    "cis_guest_same_as_member": {
        "no": "{detail}. Gjester har samme tilgang som ansatte",
        "en": "{detail}. Guests have the same access as employees",
    },
    "cis_guest_can_invite": {
        "no": "{detail}. Gjester kan invitere flere gjester",
        "en": "{detail}. Guests can invite more guests",
    },
    "cis_guest_members_invite": {
        "no": "{detail}. Alle ansatte kan invitere gjester",
        "en": "{detail}. Every employee can invite guests",
    },
    # 9.1-9.3 logging and monitoring
    "cis_ual_on": {
        "no": "Unified Audit Log-ingestion er aktivert (UnifiedAuditLogIngestionEnabled=True)",
        "en": "Unified Audit Log ingestion is enabled (UnifiedAuditLogIngestionEnabled=True)",
    },
    "cis_ual_off": {
        "no": "Unified Audit Log-ingestion er deaktivert (UnifiedAuditLogIngestionEnabled=False). Kjør Set-AdminAuditLogConfig -UnifiedAuditLogIngestionEnabled $true",
        "en": "Unified Audit Log ingestion is disabled (UnifiedAuditLogIngestionEnabled=False). Run Set-AdminAuditLogConfig -UnifiedAuditLogIngestionEnabled $true",
    },
    "cis_gap_ual": {
        "no": "Unified Audit Log-innstillingen ble ikke hentet. Verifiser Set-AdminAuditLogConfig -UnifiedAuditLogIngestionEnabled manuelt",
        "en": "the Unified Audit Log setting was not fetched. Verify Set-AdminAuditLogConfig -UnifiedAuditLogIngestionEnabled manually",
    },
    "cis_defender_alerts_open": {
        "no": "{count} aktive Defender-varsler krever oppfølging",
        "en": "{count} active Defender alerts need follow-up",
    },
    "cis_defender_alerts_none": {
        "no": "Ingen aktive Defender-varsler",
        "en": "No active Defender alerts",
    },
    "cis_gap_defender_alerts": {
        "no": "Defender-varseldata utilgjengelig",
        "en": "Defender alert data unavailable",
    },
    "cis_gap_risky_users": {
        "no": "data om risikobrukere utilgjengelig (krever Entra ID P2)",
        "en": "risky users data unavailable (requires Entra ID P2)",
    },
    "cis_risky_high": {
        "no": "{count} brukere med høy eller middels risiko er oppdaget og må undersøkes",
        "en": "{count} users at high or medium risk were detected and must be investigated",
    },
    "cis_risky_low": {
        "no": "{count} brukere er flagget med lav risiko og bør gjennomgås",
        "en": "{count} users are flagged at low risk and should be reviewed",
    },
    "cis_risky_none": {
        "no": "Ingen risikobrukere oppdaget",
        "en": "No risky users detected",
    },
    # ── Recommendation titles/details (generator._build_recommendations) ──
    "rec_mfa_title": {
        "no": "Aktiver MFA for {count} bruker(e) uten beskyttelse",
        "en": "Enable MFA for {count} user(s) without protection",
    },
    "rec_mfa_detail": {
        "no": "{registered} brukere har MFA-metoder registrert og {ca_covered} er dekket via Conditional Access. {no_mfa_registered} bruker(e) har ingen MFA-metode registrert; {registered_but_excluded} har MFA registrert, men er unntatt fra håndhevelse av en Conditional Access-policy.",
        "en": "{registered} users have MFA methods registered and {ca_covered} are covered by Conditional Access. {no_mfa_registered} user(s) have no MFA method registered; {registered_but_excluded} have MFA registered but are excluded from enforcement by a Conditional Access policy.",
    },
    "rec_mfa_excluded_title": {
        "no": "{count} høyrisiko-konto(er) er unntatt fra MFA-håndhevelse",
        "en": "{count} high-risk account(s) are excluded from MFA enforcement",
    },
    "rec_mfa_excluded_detail": {
        "no": "En Conditional Access-ekskludering betyr at MFA ikke håndheves ved pålogging, så kontoen nås med passord alene. Kontoene under er både unntatt og enten globale administratorer eller under aktivt passordangrep. Fjern ekskluderingen og bytt til phishing-resistent MFA.",
        "en": "A Conditional Access exclusion means MFA is not enforced at sign-in — the account opens with a password alone. The accounts below are both excluded and either Global Administrators or under an active password attack. Remove the exclusion and move them to phishing-resistant MFA.",
    },
    "rec_mfa_excluded_ga": {
        "no": "global administrator",
        "en": "Global Administrator",
    },
    "rec_mfa_excluded_bruteforce": {
        "no": "under aktivt passordangrep",
        "en": "under active password attack",
    },
    "rec_effort_low": {
        "no": "Lav",
        "en": "Low",
    },
    "rec_effort_medium": {
        "no": "Middels",
        "en": "Medium",
    },
    "rec_effort_immediate": {
        "no": "Umiddelbar",
        "en": "Immediate",
    },
    "rec_dmarc_title": {
        "no": "DMARC mangler eller er svak p\u00e5 {domain}",
        "en": "DMARC is missing or weak on {domain}",
    },
    "rec_dmarc_detail": {
        "no": "Uten DMARC kan avsendere forfalske e-post fra domenet deres. Sett opp DMARC med p=quarantine eller p=reject.",
        "en": "Without DMARC, senders can spoof email from your domain. Set up DMARC with p=quarantine or p=reject.",
    },
    "rec_spf_title": {
        "no": "SPF mangler eller er kritisk svak p\u00e5 {domain}",
        "en": "SPF is missing or critically weak on {domain}",
    },
    "rec_spf_detail": {
        "no": "SPF-posten beskytter mot e-postforfalskning. Sett opp en korrekt SPF-post med -all (hardfail).",
        "en": "The SPF record protects against email spoofing. Set up a correct SPF record with -all (hardfail).",
    },
    "rec_ext_fwd_unknown_count": {
        "no": "Ukjent antall",
        "en": "Unknown count",
    },
    "rec_ext_fwd_title": {
        "no": "Ekstern e-postvideresending oppdaget ({count} postkasse(r))",
        "en": "External email forwarding detected ({count} mailbox(es))",
    },
    "rec_ext_fwd_detail": {
        "no": "Postkasser videresender e-post til eksterne adresser. Dette er en h\u00f8yrisikoindikator for dataeksfiltrering eller kompromittering. Unders\u00f8k hver videresending umiddelbart.",
        "en": "Mailboxes are forwarding email to external addresses. This is a high-risk indicator of data exfiltration or compromise. Investigate each forwarding rule immediately.",
    },
    "rec_risky_users_title": {
        "no": "Risikobrukere oppdaget i Identity Protection ({count} bruker(e))",
        "en": "Risky users detected in Identity Protection ({count} user(s))",
    },
    "rec_risky_users_detail": {
        "no": "Microsoft Entra ID Protection har flagget brukere med mistenkelig aktivitet. Unders\u00f8k og bekreft/avvis disse umiddelbart.",
        "en": "Microsoft Entra ID Protection has flagged users with suspicious activity. Investigate and confirm/dismiss these immediately.",
    },
    "rec_risky_user_line": {
        "no": "{upn} (risikonivå: {level}, status: {state})",
        "en": "{upn} \u2014 Risk level: {level}, Status: {state}",
    },
    "rec_secure_score_title": {
        "no": "Microsoft Secure Score er {pct:.0f}% ({count} forbedringer identifisert)",
        "en": "Microsoft Secure Score is {pct:.0f}% \u2014 {count} improvements identified",
    },
    "rec_secure_score_detail": {
        "no": "Secure Score er {pct:.0f}% ({current:.0f} av {max:.0f} poeng).",
        "en": "Secure Score is {pct:.0f}% ({current:.0f} of {max:.0f} points).",
    },
    "rec_license_title": {
        "no": "Lisens n\u00e6r kapasitetsgrense: {part}",
        "en": "License near capacity: {part}",
    },
    "rec_license_detail": {
        "no": "{used} av {total} lisenser i bruk ({pct:.0f}%). Vurder \u00e5 kj\u00f8pe flere lisenser snart.",
        "en": "{used} of {total} licenses in use ({pct:.0f}%). Consider purchasing additional licenses soon.",
    },
    "rec_ga_title": {
        "no": "Reduser antall Global Administrator-kontoer ({count})",
        "en": "Reduce number of Global Administrator accounts ({count})",
    },
    "rec_ga_detail": {
        "no": "Microsoft anbefaler maks 2-4 Global Administratorer. Bruk mer spesifikke roller (f.eks. Exchange Administrator, Security Administrator) i henhold til minste privilegium-prinsippet.",
        "en": "Microsoft recommends a maximum of 2\u20134 Global Administrators. Use more specific roles (e.g. Exchange Administrator, Security Administrator) in accordance with the principle of least privilege.",
    },
    "rec_intune_title": {
        "no": "Intune: {count} enhet(er) er ikke i samsvar",
        "en": "Intune: {count} device(s) are non-compliant",
    },
    "rec_intune_detail_no_pct": {
        "no": "Noen enheter oppfyller ikke organisasjonens samsvarspolicyer. Undersøk ikke-samsvarende enheter og oppdater policyer ved behov.",
        "en": "Some devices do not meet the organisation\u2019s compliance policies. Investigate non-compliant devices and update policies as needed.",
    },
    "rec_intune_detail": {
        "no": "Bare {pct:.0f}% av enhetene oppfyller organisasjonens samsvarspolicyer. Unders\u00f8k ikke-samsvarende enheter og oppdater policyer ved behov.",
        "en": "Only {pct:.0f}% of devices meet the organisation\u2019s compliance policies. Investigate non-compliant devices and update policies as needed.",
    },
    "rec_auth_lockout_title": {
        "no": "{count} bruker(e) kan bli utestengt: alle registrerte metoder er avslått i policyen",
        "en": "{count} user(s) may be locked out: every registered method is disabled in the policy",
    },
    "rec_auth_lockout_detail": {
        "no": "Disse brukerne har kun autentiseringsmetoder som er avslått i tenantens authentication methods policy. Hvis MFA håndheves, kan de ikke logge inn. Verifiser policyen og migrer brukerne til en aktivert metode før håndhevelse.",
        "en": "These users have only authentication methods that are disabled in the tenant's authentication methods policy. If MFA is enforced they cannot sign in. Verify the policy and migrate these users to an enabled method before enforcing.",
    },
    "rec_entra_unmanaged_title": {
        "no": "{count} enhet(er) er registrert i Entra, men ikke administrert av Intune",
        "en": "{count} device(s) are registered in Entra but not managed by Intune",
    },
    "rec_entra_unmanaged_detail": {
        "no": "{unmanaged} av {total} Entra-registrerte enheter er ikke Intune-administrert, og er dermed utenfor samsvars- og sikkerhetspolicyer. Meld dem inn i Intune eller begrens tilgangen deres.",
        "en": "{unmanaged} of {total} Entra-registered devices are not managed by Intune, so they fall outside compliance and security policies. Enrol them in Intune or restrict their access.",
    },
    "rec_sp_sharing_title": {
        "no": "SharePoint ekstern deling er satt til mest tillatende niv\u00e5",
        "en": "SharePoint external sharing is set to the most permissive level",
    },
    "rec_sp_sharing_detail": {
        "no": "Alle kan dele filer med eksterne brukere, inkludert anonyme lenker. Vurder \u00e5 begrense til autentiserte gjester eller kun eksisterende gjester.",
        "en": "Anyone can share files with external users, including anonymous links. Consider restricting to authenticated guests or existing guests only.",
    },
    "rec_sp_legacy_title": {
        "no": "Eldre autentisering er aktivert for SharePoint",
        "en": "Legacy authentication is enabled for SharePoint",
    },
    "rec_sp_legacy_detail": {
        "no": "Legacy-autentisering st\u00f8tter ikke MFA og er en vanlig angrepsvektor. Deaktiver eldre autentisering i SharePoint-innstillingene.",
        "en": "Legacy authentication does not support MFA and is a common attack vector. Disable legacy authentication in the SharePoint settings.",
    },
    "rec_oauth_title": {
        "no": "Gjennomg\u00e5 {count} app(er) med brede tillatelser",
        "en": "Review {count} app(s) with broad permissions",
    },
    "rec_oauth_detail": {
        "no": "Verifiser at tilgangene er n\u00f8dvendige og fjern ubrukte apper.",
        "en": "Verify that the permissions are necessary and remove unused apps.",
    },
    "rec_nsg_title": {
        "no": "Azure: {count} farlig(e) NSG-regel(er) tillater trafikk fra internett",
        "en": "Azure: {count} dangerous NSG rule(s) allow traffic from the internet",
    },
    "rec_nsg_detail": {
        "no": "Begrens kildene til kjente IP-adresser eller bruk Azure Bastion.",
        "en": "Restrict sources to known IP addresses or use Azure Bastion.",
    },
    "rec_advisor_cat_security": {
        "no": "Sikkerhet",
        "en": "Security",
    },
    "rec_advisor_cat_ha": {
        "no": "H\u00f8y tilgjengelighet",
        "en": "High Availability",
    },
    "rec_advisor_cat_cost": {
        "no": "Kostnadsoptimalisering",
        "en": "Cost Optimisation",
    },
    "rec_advisor_cat_performance": {
        "no": "Ytelse",
        "en": "Performance",
    },
    "rec_advisor_cat_ops": {
        "no": "Drift",
        "en": "Operations",
    },
    "rec_advisor_title": {
        "no": "Azure Advisor ({category_label}): {count} anbefaling(er)",
        "en": "Azure Advisor \u2014 {category_label}: {count} recommendation(s)",
    },
    "rec_advisor_detail": {
        "no": "{high_count} med høy prioritet.",
        "en": "{high_count} with high priority.",
    },
    "rec_orphaned_title": {
        "no": "Azure: {count} foreldrel\u00f8se ressurs(er) oppdaget",
        "en": "Azure: {count} orphaned resource(s) detected",
    },
    "rec_orphaned_detail": {
        "no": "Fjern ubrukte ressurser for \u00e5 spare kostnader og redusere angrepsflaten.",
        "en": "Remove unused resources to save costs and reduce the attack surface.",
    },
    "rec_stale_title": {
        "no": "{count} lisensierte bruker(e) har ikke logget inn p\u00e5 90+ dager",
        "en": "{count} licensed user(s) have not signed in for 90+ days",
    },
    "rec_stale_detail": {
        "no": "Disse kontoene bruker lisenser men er inaktive. Vurder \u00e5 deaktivere kontoene og frigj\u00f8re lisensene, eller unders\u00f8k om brukerne fortsatt er ansatt.",
        "en": "These accounts use licenses but are inactive. Consider disabling the accounts and freeing the licenses, or investigate whether the users are still employed.",
    },
    "rec_cred_expiry_title": {
        "no": "App-registreringer: {count} credential(s) utg\u00e5tt eller utg\u00e5r snart",
        "en": "App registrations: {count} credential(s) expired or expiring soon",
    },
    "rec_cred_expiry_detail": {
        "no": "{expired} utgåtte og {critical} som utgår innen 30 dager. Utgått legitimasjon vil bryte integrasjoner. Forny umiddelbart i Entra ID > Appregistreringer.",
        "en": "{expired} expired and {critical} expiring within 30 days. Expired credentials will break integrations. Renew immediately in Entra ID > App registrations.",
    },
    "rec_backup_title": {
        "no": "Azure: {count} VM(er) mangler backup",
        "en": "Azure: {count} VM(s) missing backup",
    },
    "rec_backup_detail": {
        "no": "Disse virtuelle maskinene er ikke beskyttet av Azure Backup. Ved datatap eller ransomware vil disse ikke kunne gjenopprettes.",
        "en": "These virtual machines are not protected by Azure Backup. In case of data loss or ransomware, these cannot be recovered.",
    },
    "rec_network_audit_unreadable_title": {
        "no": "Nettverksaudit kunne ikke leses ({file})",
        "en": "Network audit could not be read ({file})",
    },
    "rec_network_audit_unreadable_detail": {
        "no": "Filen finnes, men innholdet lot seg ikke tolke. Nettverksfunnene og poengtrekket de gir i sikkerhetsscoren mangler i denne rapporten. Scoren kan derfor være for høy, men ikke for lav. Kjør nettverksauditen på nytt.",
        "en": "The file is present but its contents could not be parsed. Network findings and the points they deduct from the security score are missing from this report — the score may therefore be too high, never too low. Re-run the network audit.",
    },
    "rec_brute_force_title": {
        "no": "Mulig brute force-angrep mot {count} bruker(e)",
        "en": "Possible brute force attack against {count} user(s)",
    },
    "rec_brute_force_detail": {
        "no": "En eller flere brukere har 50+ mislykkede p\u00e5loggingsfors\u00f8k. Dette kan indikere et p\u00e5g\u00e5ende brute force-angrep. Unders\u00f8k umiddelbart og vurder \u00e5 blokkere kildene.",
        "en": "One or more users have 50+ failed sign-in attempts. This may indicate an ongoing brute force attack. Investigate immediately and consider blocking the sources.",
    },
    "rec_stale_cred_title": {
        "no": "Sannsynlig utdatert passord på {count} konto(er)",
        "en": "Probable stale password on {count} account(s)",
    },
    "rec_stale_cred_detail": {
        "no": "Disse kontoene har mange mislykkede pålogginger blandet med vellykkede, som regel et lagret/bufret passord på en enhet og ikke et eksternt angrep. Oppdater det lagrede passordet på enheten. Ingen umiddelbar blokkering nødvendig.",
        "en": "These accounts have many failed sign-ins interleaved with successful ones, typically a stored/cached password on a device rather than an external attack. Update the saved credential on the device. No immediate blocking needed.",
    },
    # ── Executive summary bullets (generator._build_executive_summary) ──
    "exec_env_size": {
        "no": "Milj\u00f8et har {total} brukere ({enabled} aktive, {guests} gjester) og {azure_resources} Azure-ressurser fordelt p\u00e5 {subscriptions} abonnement(er).",
        "en": "The environment has {total} users ({enabled} active, {guests} guests) and {azure_resources} Azure resources across {subscriptions} subscription(s).",
    },
    "exec_env_size_unavailable": {
        "no": "Miljøets størrelse kunne ikke fastslås fordi auditen ikke returnerte brukerdata.",
        "en": "Environment size could not be determined — the audit returned no user data.",
    },
    "exec_mfa_good": {
        "no": "MFA-dekningen er {pct:.0f}%, som gir god beskyttelse mot kontoovertakelse.",
        "en": "MFA coverage is {pct:.0f}% \u2014 well protected against account takeover.",
    },
    "exec_mfa_partial": {
        "no": "MFA-dekningen er {pct:.0f}%. {no_mfa} bruker(e) har ikke håndhevet MFA.",
        "en": "MFA coverage is {pct:.0f}%. {no_mfa} user(s) do not have enforced MFA.",
    },
    "exec_mfa_unavailable": {
        "no": "MFA-data er ikke tilgjengelig for denne kunden.",
        "en": "MFA data is not available for this customer.",
    },
    "exec_mfa_subset": {
        "no": "MFA-dekningen er {pct:.0f}%, men målt på kun {measured} av {total} brukere fordi {unknown} ikke kunne kontrolleres (throttling eller manglende tilgang).",
        "en": "MFA coverage is {pct:.0f}%, but measured on only {measured} of {total} users — {unknown} could not be checked (throttling or missing access).",
    },
    "exec_ss_good": {
        "no": "Microsoft Secure Score er {pct:.0f}%, som er over anbefalt minstenivå.",
        "en": "Microsoft Secure Score is {pct:.0f}% \u2014 above the recommended minimum level.",
    },
    "exec_ss_low": {
        "no": "Microsoft Secure Score er {pct:.0f}%, under anbefalt 75%. Det finnes {count} konkrete forbedringsomr\u00e5der.",
        "en": "Microsoft Secure Score is {pct:.0f}%, below the recommended 75%. There are {count} concrete areas for improvement.",
    },
    "exec_intune_noncompliant": {
        "no": "{noncompliant} av {total} enheter ({pct:.0f}%) er ikke i samsvar med organisasjonens policyer.",
        "en": "{noncompliant} of {total} devices ({pct:.0f}%) are non-compliant with the organisation\u2019s policies.",
    },
    "exec_intune_ok": {
        "no": "Alle {total} enheter er i samsvar med samsvarspolicyer.",
        "en": "All {total} devices are compliant with compliance policies.",
    },
    "exec_intune_partial": {
        "no": "{compliant} av {total} enheter er bekreftet i samsvar; {unknown} er ikke evaluert (nådeperiode eller ikke vurdert).",
        "en": "{compliant} of {total} devices are confirmed compliant; {unknown} are not evaluated (grace period or not assessed).",
    },
    "exec_ca_active": {
        "no": "{count} Conditional Access-policyer er aktive og beskytter milj\u00f8et.",
        "en": "{count} Conditional Access policies are active and protecting the environment.",
    },
    "exec_critical_findings": {
        "no": "Det er identifisert {count} kritisk(e) funn som krever umiddelbar handling: {titles}.",
        "en": "{count} critical finding(s) have been identified that require immediate action: {titles}.",
    },
    "exec_high_findings": {
        "no": "I tillegg er det {count} funn med h\u00f8y prioritet som b\u00f8r adresseres.",
        "en": "Additionally, there are {count} high-priority finding(s) that should be addressed.",
    },
    "exec_ga_too_many": {
        "no": "Det er {count} Global Administrator-kontoer, mens Microsoft anbefaler maks 4.",
        "en": "There are {count} Global Administrator accounts \u2014 Microsoft recommends a maximum of 4.",
    },
    "exec_overall": {
        "no": "Samlet sikkerhetspostur er vurdert til karakter {grade} ({score}/100): {description}.",
        "en": "Overall security posture is assessed at grade {grade} ({score}/100) \u2014 {description}.",
    },
    "exec_overall_invalid": {
        "no": "Samlet sikkerhetspostur kan ikke vurderes fordi auditen mangler nødvendige data.",
        "en": "Overall security posture cannot be assessed \u2014 the audit is missing required data.",
    },
    "exec_grade_a": {
        "no": "godt sikret",
        "en": "well secured",
    },
    "exec_grade_b": {
        "no": "tilfredsstillende",
        "en": "satisfactory",
    },
    "exec_grade_c": {
        "no": "krever forbedring",
        "en": "needs improvement",
    },
    "exec_grade_d": {
        "no": "kritisk",
        "en": "critical",
    },
    "exec_grade_f": {
        "no": "svært kritisk",
        "en": "severely deficient",
    },
    "exec_grade_unknown": {
        "no": "ukjent",
        "en": "unknown",
    },
    # ── Risk radar category names (generator._build_risk_radar) ──
    "radar_identity": {
        "no": "Identitet",
        "en": "Identity",
    },
    "radar_devices": {
        "no": "Enheter",
        "en": "Devices",
    },
    "radar_email": {
        "no": "E-post",
        "en": "Email",
    },
    "radar_azure": {
        "no": "Azure",
        "en": "Azure",
    },
    "radar_data": {
        "no": "Data",
        "en": "Data",
    },
    # ── License Optimization ──
    "lo_title": {
        "no": "Lisensoptimalisering",
        "en": "License Optimization",
    },
    "lo_estimated_waste": {
        "no": "Estimert månedlig sløsing",
        "en": "Estimated Monthly Waste",
    },
    "lo_per_month": {
        "no": "kr/mnd",
        "en": "NOK/mo",
    },
    "lo_unused_licenses": {
        "no": "Ubrukte lisenser (inaktive brukere)",
        "en": "Unused Licenses (Inactive Users)",
    },
    "lo_over_provisioned": {
        "no": "Overallokerte lisenser",
        "en": "Over-Provisioned Licenses",
    },
    "lo_downgrade_candidates": {
        "no": "Mulige nedgraderinger",
        "en": "Potential Downgrades",
    },
    "lo_suggestions": {
        "no": "Optimaliseringsforslag",
        "en": "Optimization Suggestions",
    },
    "lo_user": {
        "no": "Bruker",
        "en": "User",
    },
    "lo_inactive": {
        "no": "Inaktiv",
        "en": "Inactive",
    },
    "lo_days": {
        "no": "dager",
        "en": "days",
    },
    "lo_never_signed_in": {
        "no": "Aldri logget inn",
        "en": "Never signed in",
    },
    "lo_sku": {
        "no": "Lisens (SKU)",
        "en": "License (SKU)",
    },
    "lo_assigned": {
        "no": "Tildelt",
        "en": "Assigned",
    },
    "lo_unused_count": {
        "no": "Ubrukt",
        "en": "Unused",
    },
    "lo_waste": {
        "no": "Sløsing",
        "en": "Waste",
    },
    "lo_savings": {
        "no": "Mulig besparelse",
        "en": "Potential Savings",
    },
    "lo_no_data": {
        "no": "Ingen påloggingsdata tilgjengelig: signInActivity krever Microsoft Entra ID P1 (tidligere Azure AD Premium P1).",
        "en": "No sign-in data available — requires Microsoft Entra ID P1 (formerly Azure AD Premium P1) for signInActivity.",
    },
    "lo_not_collected": {
        "no": "Stale-konto-deteksjon ble ikke utført i denne auditen. Sannsynlig årsak: app-registreringen mangler AuditLog.Read.All-consent, eller PowerShell-versjonen av auditen henter ikke signInActivity-feltet. Kjør auditen på nytt etter å ha verifisert tillatelser.",
        "en": "Stale-account detection was not performed in this audit. Likely cause: the app registration lacks AuditLog.Read.All consent, or the PowerShell variant of the audit does not fetch the signInActivity field. Re-run the audit after verifying permissions.",
    },
    "lo_no_issues": {
        "no": "Ingen vesentlige optimaliseringsmuligheter funnet.",
        "en": "No significant optimization opportunities found.",
    },
    "lo_note_estimates": {
        "no": "Prisestimatene er basert på veiledende listepriser og kan avvike fra faktisk avtale.",
        "en": "Price estimates are based on approximate list prices and may differ from your actual agreement.",
    },
    "lo_suggest_remove_unused": {
        "no": "Fjern lisenser fra {count} inaktive bruker(e)",
        "en": "Remove licenses from {count} inactive user(s)",
    },
    "lo_suggest_remove_unused_detail": {
        "no": "{count} bruker(e) med lisens har ikke logget inn på 90+ dager. Estimert sløsing: {amount} kr/mnd.",
        "en": "{count} licensed user(s) have not signed in for 90+ days. Estimated waste: {amount} NOK/mo.",
    },
    "lo_suggest_shared_licensed": {
        "no": "Fjern lisens fra {count} delt/rom-postboks",
        "en": "Remove license from {count} shared/room mailbox(es)",
    },
    "lo_suggest_shared_licensed_detail": {
        "no": "{count} delt/rom-postboks er inaktiv fordi den ikke logger inn, men ligger med lisens. En delt postboks under 50 GB trenger ingen lisens. Estimert sløsing: {amount} kr/mnd.",
        "en": "{count} shared/room mailbox(es) show as inactive because they never sign in, yet carry a license. A shared mailbox under 50 GB needs none. Estimated waste: {amount} NOK/mo.",
    },
    "lo_suggest_reduce_sku": {
        "no": "Reduser antall {part}-lisenser",
        "en": "Reduce {part} license count",
    },
    "lo_suggest_reduce_sku_detail": {
        "no": "{part}: {unused} av {total} lisenser er ubrukt ({used} tildelt). Estimert sløsing: {amount} kr/mnd.",
        "en": "{part}: {unused} of {total} licenses unused ({used} assigned). Estimated waste: {amount} NOK/mo.",
    },
    "lo_suggest_downgrade": {
        "no": "Vurder nedgradering fra {part} til E3",
        "en": "Consider downgrading {part} to E3",
    },
    "lo_suggest_downgrade_detail": {
        "no": "{users} brukere på {part}. Hvis noen kun bruker E3-funksjoner, kan du spare {saving} kr/bruker/mnd (opptil {total} kr/mnd totalt).",
        "en": "{users} users on {part}. If some only use E3 features, you could save {saving} NOK/user/mo (up to {total} NOK/mo total).",
    },
    "lo_priority_high": {
        "no": "Høy",
        "en": "High",
    },
    "lo_priority_medium": {
        "no": "Middels",
        "en": "Medium",
    },
    "lo_priority_low": {
        "no": "Lav",
        "en": "Low",
    },
    # ── Network audit (FortiGate / UniFi) ──────────────────────────────
    "section_network": {
        "no": "Nettverkssikkerhet",
        "en": "Network Security",
    },
    "section_fortigate": {
        "no": "FortiGate brannmur",
        "en": "FortiGate Firewall",
    },
    "section_unifi": {
        "no": "UniFi nettverk",
        "en": "UniFi Network",
    },
    # Labels in the customer report's network section
    "net_model": {
        "no": "Modell",
        "en": "Model",
    },
    "net_firmware": {
        "no": "Firmware",
        "en": "Firmware",
    },
    "net_firewall_rules": {
        "no": "Brannmurregler",
        "en": "Firewall rules",
    },
    "net_admins": {
        "no": "Admins",
        "en": "Admins",
    },
    "net_vpn_tunnels": {
        "no": "VPN-tunneler",
        "en": "VPN tunnels",
    },
    "net_ha_mode": {
        "no": "HA-modus",
        "en": "HA mode",
    },
    "net_administrators": {
        "no": "Administratorer",
        "en": "Administrators",
    },
    "net_name": {
        "no": "Navn",
        "en": "Name",
    },
    "net_profile": {
        "no": "Profil",
        "en": "Profile",
    },
    "net_trusted_hosts": {
        "no": "IP-begrensning",
        "en": "IP restriction",
    },
    "net_firewall_warnings": {
        "no": "Brannmur-advarsler",
        "en": "Firewall warnings",
    },
    "net_ssids": {
        "no": "SSID-er",
        "en": "SSIDs",
    },
    "net_networks": {
        "no": "Nettverk",
        "en": "Networks",
    },
    "net_active_alarms": {
        "no": "Aktive alarmer",
        "en": "Active alarms",
    },
    "net_reachable": {
        "no": "Tilgjengelige",
        "en": "Reachable",
    },
    "net_default_passwords": {
        "no": "Standard-passord",
        "en": "Default passwords",
    },
    "net_outdated_firmware": {
        "no": "Utdatert firmware",
        "en": "Outdated firmware",
    },
    "net_device_overview": {
        "no": "Enhetsoversikt",
        "en": "Device overview",
    },
    "net_device": {
        "no": "Enhet",
        "en": "Device",
    },
    "net_clients": {
        "no": "Klienter",
        "en": "Clients",
    },
    "net_wireless_networks": {
        "no": "Trådløse nettverk",
        "en": "Wireless networks",
    },
    "net_guest": {
        "no": "Gjest",
        "en": "Guest",
    },
    # FortiGate findings
    "rec_fg_admin_no_2fa_title": {
        "no": "{count} FortiGate-admin(er) uten to-faktor",
        "en": "{count} FortiGate admin(s) without two-factor",
    },
    "rec_fg_admin_no_2fa_detail": {
        "no": "Administratorer uten to-faktor-autentisering kan kompromitteres via passordangrep.",
        "en": "Administrators without two-factor authentication can be compromised via password attacks.",
    },
    "rec_fg_allow_all_title": {
        "no": "{count} allow-all-regel(er) i FortiGate",
        "en": "{count} allow-all rule(s) in FortiGate",
    },
    "rec_fg_allow_all_detail": {
        "no": "Brannmurregler som tillater all trafikk (src=all, dst=all, service=ALL) bryter med prinsippet om minste tilgang.",
        "en": "Firewall rules that allow all traffic (src=all, dst=all, service=ALL) violate the principle of least privilege.",
    },
    "rec_fg_no_logging_title": {
        "no": "{count} FortiGate-regel(er) uten logging",
        "en": "{count} FortiGate rule(s) without logging",
    },
    "rec_fg_no_logging_detail": {
        "no": "Brannmurregler uten logging gjør det umulig å oppdage og etterforskebrudd.",
        "en": "Firewall rules without logging make it impossible to detect and investigate breaches.",
    },
    "rec_fg_no_trusthost_title": {
        "no": "{count} FortiGate-admin(er) uten IP-begrensning",
        "en": "{count} FortiGate admin(s) without IP restriction",
    },
    "rec_fg_no_trusthost_detail": {
        "no": "Admin-kontoer uten trusted host-begrensning kan nås fra vilkårlig IP-adresse.",
        "en": "Admin accounts without trusted host restriction can be accessed from any IP address.",
    },
    # UniFi findings
    "rec_uf_default_creds_title": {
        "no": "{count} UniFi-enhet(er) med standard-passord",
        "en": "{count} UniFi device(s) with default password",
    },
    "rec_uf_default_creds_detail": {
        "no": "Enheter med standard-passord (ubnt/ubnt) kan kompromitteres av hvem som helst med nettverkstilgang.",
        "en": "Devices with default credentials (ubnt/ubnt) can be compromised by anyone with network access.",
    },
    "rec_uf_outdated_fw_title": {
        "no": "{count} UniFi-enhet(er) med utdatert firmware",
        "en": "{count} UniFi device(s) with outdated firmware",
    },
    "rec_uf_outdated_fw_detail": {
        "no": "Utdatert firmware kan inneholde kjente sikkerhetssårbarheter. Oppdater til siste stabile versjon.",
        "en": "Outdated firmware may contain known security vulnerabilities. Update to the latest stable version.",
    },
    "rec_uf_eol_title": {
        "no": "{count} UniFi-enhet(er) har nådd end-of-life",
        "en": "{count} UniFi device(s) have reached end-of-life",
    },
    "rec_uf_eol_detail": {
        "no": "End-of-life enheter mottar ikke lenger sikkerhetsoppdateringer og bør erstattes.",
        "en": "End-of-life devices no longer receive security updates and should be replaced.",
    },
    "rec_uf_open_wifi_title": {
        "no": "Åpent trådløst nettverk uten kryptering",
        "en": "Open wireless network without encryption",
    },
    "rec_uf_open_wifi_detail": {
        "no": "Trådløse nettverk uten kryptering lar all trafikk avlyttes. Aktiver WPA2/WPA3.",
        "en": "Wireless networks without encryption allow all traffic to be intercepted. Enable WPA2/WPA3.",
    },
    "rec_uf_factory_default_title": {
        "no": "{count} UniFi-enhet(er) med fabrikkinnstillinger",
        "en": "{count} UniFi device(s) with factory default config",
    },
    "rec_uf_factory_default_detail": {
        "no": "Enheter med standardkonfigurasjon er ikke sikret. Konfigurer og adopter dem til en kontroller.",
        "en": "Devices with factory default configuration are not secured. Configure and adopt them to a controller.",
    },
    # ── CIS control titles (compliance._CONTROLS) ──
    # The product's own wording in the benchmark's style, so it is translated
    # like any other sentence; the CIS id beside it is the reference.
    "cis_title_mfa_all_users": {
        "no": "Sørg for at MFA er aktivert for alle brukere",
        "en": "Ensure MFA is enabled for all users",
    },
    "cis_title_phishing_resistant_mfa": {
        "no": "Sørg for at phishing-resistente MFA-metoder er aktivert",
        "en": "Ensure phishing-resistant MFA methods are enabled",
    },
    "cis_title_global_admins": {
        "no": "Sørg for færre enn 5 globale administratorer",
        "en": "Ensure fewer than 5 Global Admins",
    },
    "cis_title_ca_policies": {
        "no": "Sørg for at Conditional Access-policyer er konfigurert",
        "en": "Ensure Conditional Access policies are configured",
    },
    "cis_title_pim": {
        "no": "Sørg for at PIM brukes til aktivering av privilegerte roller",
        "en": "Ensure PIM is used for privileged role activation",
    },
    "cis_title_emergency_access": {
        "no": "Sørg for at nødtilgangskontoer er satt opp",
        "en": "Ensure emergency access accounts are configured",
    },
    "cis_title_banned_passwords": {
        "no": "Sørg for at egendefinerte forbudte passord er konfigurert",
        "en": "Ensure custom banned passwords are configured",
    },
    "cis_title_secure_score": {
        "no": "Sørg for at Microsoft Secure Score er over 75%",
        "en": "Ensure Microsoft Secure Score is above 75%",
    },
    "cis_title_third_party_apps": {
        "no": "Sørg for at tredjepartsapper er gjennomgått",
        "en": "Ensure third-party apps are reviewed",
    },
    "cis_title_app_credentials": {
        "no": "Sørg for at legitimasjonen til apper ikke er utløpt",
        "en": "Ensure app credentials are not expired",
    },
    "cis_title_dlp": {
        "no": "Sørg for at DLP-policyer er konfigurert",
        "en": "Ensure DLP policies are configured",
    },
    "cis_title_sensitivity_labels": {
        "no": "Sørg for at følsomhetsetiketter er publisert",
        "en": "Ensure sensitivity labels are published",
    },
    "cis_title_mailbox_audit": {
        "no": "Sørg for at postbokslogging er aktivert",
        "en": "Ensure mailbox audit logging is enabled",
    },
    "cis_title_anti_phishing": {
        "no": "Sørg for at anti-phishing-policyer er konfigurert",
        "en": "Ensure anti-phishing policies are configured",
    },
    "cis_title_anti_spam": {
        "no": "Sørg for at anti-spam-policyer er konfigurert",
        "en": "Ensure anti-spam policies are configured",
    },
    "cis_title_external_forwarding": {
        "no": "Sørg for at videresending av e-post til eksterne domener er begrenset",
        "en": "Ensure mail forwarding to external domains is restricted",
    },
    "cis_title_safe_links": {
        "no": "Sørg for at Safe Links er aktivert",
        "en": "Ensure Safe Links is enabled",
    },
    "cis_title_safe_attachments": {
        "no": "Sørg for at Safe Attachments er aktivert",
        "en": "Ensure Safe Attachments is enabled",
    },
    "cis_title_legacy_auth": {
        "no": "Sørg for at eldre autentisering er blokkert",
        "en": "Ensure legacy authentication is blocked",
    },
    "cis_title_signin_protection": {
        "no": "Sørg for at grunnleggende påloggingsbeskyttelse er på plass",
        "en": "Ensure baseline sign-in protection is in place",
    },
    "cis_title_access_reviews": {
        "no": "Sørg for at tilgangsgjennomganger er satt opp",
        "en": "Ensure access reviews are configured",
    },
    "cis_title_cross_tenant": {
        "no": "Sørg for at innstillingene for tilgang på tvers av tenanter er gjennomgått",
        "en": "Ensure cross-tenant access settings are reviewed",
    },
    "cis_title_anonymous_links": {
        "no": "Sørg for at anonyme delingskoblinger ikke er i bruk",
        "en": "Ensure anonymous sharing links are not in use",
    },
    "cis_title_sharepoint_legacy_auth": {
        "no": "Sørg for at eldre autentiseringsprotokoller er deaktivert i SharePoint",
        "en": "Ensure legacy authentication protocols are disabled in SharePoint",
    },
    "cis_title_spf": {
        "no": "Sørg for at SPF er konfigurert",
        "en": "Ensure SPF is configured",
    },
    "cis_title_dmarc": {
        "no": "Sørg for at DMARC er konfigurert",
        "en": "Ensure DMARC is configured",
    },
    "cis_title_dkim": {
        "no": "Sørg for at DKIM er aktivert",
        "en": "Ensure DKIM is enabled",
    },
    "cis_title_device_compliance": {
        "no": "Sørg for at samsvarspolicyer for enheter er konfigurert",
        "en": "Ensure device compliance policies are configured",
    },
    "cis_title_sharepoint_sharing": {
        "no": "Sørg for at ekstern deling i SharePoint er styrt",
        "en": "Ensure SharePoint external sharing is managed",
    },
    "cis_title_retention": {
        "no": "Sørg for at oppbevaringspolicyer er konfigurert",
        "en": "Ensure data retention policies are configured",
    },
    "cis_title_m365_backup": {
        "no": "Sørg for at Microsoft 365-data sikkerhetskopieres",
        "en": "Ensure Microsoft 365 data is backed up",
    },
    "cis_title_teams_external": {
        "no": "Sørg for at ekstern tilgang i Teams er styrt",
        "en": "Ensure external access in Teams is managed",
    },
    "cis_title_teams_guests": {
        "no": "Sørg for at gjestetilgang i Teams er begrenset",
        "en": "Ensure Teams guest access is restricted",
    },
    "cis_title_unified_audit_log": {
        "no": "Sørg for at enhetlig revisjonslogging er aktivert",
        "en": "Ensure unified audit logging is enabled",
    },
    "cis_title_security_alerts": {
        "no": "Sørg for at sikkerhetsvarsler overvåkes",
        "en": "Ensure security alerts are monitored",
    },
    "cis_title_risky_users": {
        "no": "Sørg for at oppdagede risikobrukere undersøkes",
        "en": "Ensure risky user detections are investigated",
    },
    # ── Entra ID Protection's own values, in a risky user's line ──
    # Graph returns riskLevel and riskState as enum names ("high", "atRisk").
    # A value without a key here is shown as Graph wrote it.
    "risk_value_low": {"no": "lav", "en": "low"},
    "risk_value_medium": {"no": "middels", "en": "medium"},
    "risk_value_high": {"no": "høy", "en": "high"},
    "risk_value_hidden": {"no": "skjult", "en": "hidden"},
    "risk_value_none": {"no": "ingen", "en": "none"},
    "risk_state_atrisk": {"no": "i faresonen", "en": "at risk"},
    "risk_state_confirmedcompromised": {
        "no": "bekreftet kompromittert",
        "en": "confirmed compromised",
    },
    "risk_state_remediated": {"no": "utbedret", "en": "remediated"},
    "risk_state_dismissed": {"no": "avvist", "en": "dismissed"},
    "risk_state_confirmedsafe": {"no": "bekreftet trygg", "en": "confirmed safe"},
    # ── Template words that were written into the templates in English ──
    "pim_eligible_assignments": {
        "no": "Berettigede PIM-rolletildelinger",
        "en": "PIM Eligible Assignments",
    },
    "intune_compliance_policies": {
        "no": "Intune-samsvarspolicyer",
        "en": "Intune Compliance Policies",
    },
    "entra_app_registrations": {
        "no": "Appregistreringer i Entra ID",
        "en": "Entra ID App Registrations",
    },
    "defender_alerts_header": {
        "no": "Defender-varsler",
        "en": "Defender Alerts",
    },
    "subscription": {
        "no": "Abonnement",
        "en": "Subscription",
    },
    "type": {
        "no": "Type",
        "en": "Type",
    },
    "net_eol": {
        "no": "Utgått (EOL)",
        "en": "End-of-life",
    },
    "net_online": {
        "no": "Tilkoblet",
        "en": "Online",
    },
    "net_offline": {
        "no": "Frakoblet",
        "en": "Offline",
    },
    # A WLAN's security as the UniFi collector labels it
    # (unifi_api.wlan_security_label). WPA2 and WPA3 are names and stay.
    "wlan_security_open": {
        "no": "Åpen",
        "en": "Open",
    },
    "wlan_security_wep": {
        "no": "WEP (usikker)",
        "en": "WEP (insecure)",
    },
    "wlan_security_unknown": {
        "no": "Ukjent",
        "en": "Unknown",
    },
    "wlan_security_unknown_value": {
        "no": "Ukjent ({value})",
        "en": "Unknown ({value})",
    },
    # ── Beside the score: what it could not measure (risk.data_quality_issues) ──
    "risk_not_in_score_label": {
        "no": "Ikke målt, og derfor ikke med i scoren:",
        "en": "Not measured, so not in the score:",
    },
    # ── CSV export (/report/csv) ──
    "csv_category": {"no": "Kategori", "en": "Category"},
    "csv_metric": {"no": "Metrikk", "en": "Metric"},
    "csv_value": {"no": "Verdi", "en": "Value"},
    "csv_status": {"no": "Status", "en": "Status"},
    "csv_cat_customer": {"no": "Kunde", "en": "Customer"},
    "csv_cat_security": {"no": "Sikkerhet", "en": "Security"},
    "csv_cat_users": {"no": "Brukere", "en": "Users"},
    "csv_cat_mfa": {"no": "MFA", "en": "MFA"},
    "csv_cat_secure_score": {"no": "Secure Score", "en": "Secure Score"},
    "csv_cat_ca": {"no": "Conditional Access", "en": "Conditional Access"},
    "csv_cat_intune": {"no": "Intune", "en": "Intune"},
    "csv_cat_admin": {"no": "Administratorer", "en": "Admin"},
    "csv_cat_licence": {"no": "Lisens", "en": "Licence"},
    "csv_cat_recommendation": {"no": "Anbefaling", "en": "Recommendation"},
    "csv_cat_warning": {"no": "Varsel", "en": "Warning"},
    "csv_name": {"no": "Navn", "en": "Name"},
    "csv_domain": {"no": "Domene", "en": "Domain"},
    "csv_report_date": {"no": "Rapportdato", "en": "Report date"},
    "csv_risk_grade": {"no": "Karakter", "en": "Grade"},
    "csv_risk_score": {"no": "Sikkerhetsscore", "en": "Security score"},
    "csv_of_100": {"no": "av 100", "en": "of 100"},
    "csv_not_measured": {"no": "ikke målt", "en": "not measured"},
    "csv_total": {"no": "Totalt", "en": "Total"},
    "csv_enabled": {"no": "Aktive", "en": "Enabled"},
    "csv_guests": {"no": "Gjester", "en": "Guests"},
    "csv_coverage_pct": {"no": "Dekning %", "en": "Coverage %"},
    "csv_without_mfa": {"no": "Uten MFA", "en": "Without MFA"},
    "csv_score_pct": {"no": "Score %", "en": "Score %"},
    "csv_enabled_policies": {"no": "Aktive policyer", "en": "Enabled policies"},
    "csv_devices_total": {"no": "Enheter totalt", "en": "Total devices"},
    "csv_compliant_pct": {"no": "Samsvar %", "en": "Compliant %"},
    "csv_noncompliant": {"no": "Ikke i samsvar", "en": "Non-compliant"},
    "csv_global_admins": {"no": "Globale administratorer", "en": "Global admins"},
    "csv_role_assignments": {"no": "Rolletildelinger", "en": "Role assignments"},
    "csv_critical": {"no": "Kritisk", "en": "Critical"},
    "csv_ok": {"no": "OK", "en": "OK"},
    "csv_licence_warning": {"no": "Advarsel", "en": "Warning"},
    "csv_priority_critical": {"no": "Kritisk", "en": "Critical"},
    "csv_priority_high": {"no": "Høy", "en": "High"},
    "csv_priority_medium": {"no": "Middels", "en": "Medium"},
    "csv_priority_low": {"no": "Lav", "en": "Low"},
    "csv_unknown_customer": {"no": "Ukjent kunde", "en": "Unknown customer"},
}


def get_translations(lang: str = "no") -> dict[str, str]:
    """Return a flat dict of key -> translated string for the given language."""
    result = {}
    for key, translations in TRANSLATIONS.items():
        result[key] = translations.get(lang, translations.get("no", key))
    return result


class Localised(str):
    """A rendered string that remembers how it was rendered.

    It *is* the text — templates, f-strings, ``json.dumps`` and every existing
    consumer treat it as an ordinary ``str`` and nothing downstream changes.
    What it adds is the key and the values it was built from, so a reader in
    another language can have the same sentence rebuilt for them.

    That matters because a recommendation is written once, when the audit runs,
    and read for months afterwards. Storing only the finished sentence meant an
    audit collected in Norwegian showed Norwegian to an English reader forever,
    and the only way out was to run the audit again. The alternative — passing
    a key and a params dict explicitly at all twenty-eight places a
    recommendation is built — is twenty-eight chances for the two to drift
    apart. Here they cannot: the string and its recipe are the same object.
    """

    __slots__ = ("key", "params")

    def __new__(cls, text: str, key: str, params: dict) -> Localised:
        obj = super().__new__(cls, text)
        obj.key = key
        obj.params = params
        return obj


class T:
    """Translation helper that can be passed to Jinja2 templates.

    Usage in template: {{ t.key_findings }} or {{ t('mfa_missing_title', count=5) }}
    """

    def __init__(self, lang: str = "no"):
        self.lang = lang
        self._strings = get_translations(lang)

    def __getattr__(self, key: str) -> str:
        if key.startswith("_"):
            raise AttributeError(key)
        return Localised(self._strings.get(key, key), key, {})

    def __call__(self, key: str, **kwargs) -> str:
        template = self._strings.get(key, key)
        text = template.format(**kwargs) if kwargs else template
        return Localised(text, key, kwargs)
