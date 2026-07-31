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
        "no": "Compliance",
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
        "no": "Risikoscore",
        "en": "Risk Score",
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
        "no": "Moderat sikkerhetsnivå — flere forbedringer anbefales",
        "en": "Moderate security level — several improvements recommended",
    },
    "risk_poor": {
        "no": "Svakt sikkerhetsnivå — umiddelbare tiltak nødvendig",
        "en": "Poor security level — immediate action required",
    },
    "risk_critical": {
        "no": "Kritisk sikkerhetsnivå — alvorlige sårbarheter funnet",
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
        "no": "Risikoscore",
        "en": "Risk Score",
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
        "no": "{count} Global Administrator-konto(er) \u2014 innenfor anbefalt grense",
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
        "no": "SPF-posten mangler \u2014 avsendere kan forfalske e-post fra domenet.",
        "en": "SPF record is missing \u2014 senders can spoof email from the domain.",
    },
    "dmarc_missing": {
        "no": "DMARC-posten mangler \u2014 det finnes ingen beskyttelse mot e-postforfalskning.",
        "en": "DMARC record is missing \u2014 there is no protection against email spoofing.",
    },
    "dmarc_weak": {
        "no": "DMARC-policyen er satt til \"none\".",
        "en": "DMARC policy is set to \"none\".",
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
    "role": {
        "no": "Rolle",
        "en": "Role",
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
        "no": "Mailbox-videresending",
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
        "no": "Oversikt over Azure-subscriptions og ressurser.",
        "en": "Overview of Azure subscriptions and resources.",
    },
    "subscriptions": {
        "no": "Subscriptions",
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
        "no": "Backup-dekning kunne ikke fastslås — data fra Recovery Services "
              "Vault mangler. Verifiser backup manuelt før dette rapporteres.",
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
        "no": "{company} \u2014 Teknisk Auditrapport",
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
        "no": "Emergency Access-analyse",
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
    "device_name": {
        "no": "Enhetsnavn",
        "en": "Device Name",
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
    "no_intune_devices": {
        "no": "Ingen Intune-enheter funnet",
        "en": "No Intune devices found",
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
        "no": "Microsoft Purview \u2014 Databeskyttelse",
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
        "no": "Ressurser per subscription",
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
        "no": "Enten har kunden ingen Azure-subscriptions, eller service principal mangler Reader-rolle.",
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
        "no": "{count} treff for \"{query}\"",
        "en": "{count} results for \"{query}\"",
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
        "no": "{company} \u2014 IT-Sikkerhetsrapport",
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
        "no": "Auditen klarte ikke å hente brukerlisten fra Microsoft Graph, så MFA-dekning er ukjent. Dette betyr ikke at MFA er fraværende — det betyr at vi ikke vet. Verifiser at app-registreringen har User.Read.All og UserAuthenticationMethod.Read.All og kjør auditen på nytt.",
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
        "no": "MFA-dekning: {pct:.0f}% \u2014 {no_mfa} brukere mangler MFA",
        "en": "MFA coverage: {pct:.0f}% \u2014 {no_mfa} users missing MFA",
    },
    "cis_mfa_unavailable": {
        "no": "Kan ikke verifiseres — MFA-data utilgjengelig",
        "en": "Cannot be verified — MFA data unavailable",
    },
    "cis_mfa_none": {
        "no": "Ingen brukere har MFA — 0% dekning ({no_mfa} brukere ubeskyttet)",
        "en": "No users have MFA — 0% coverage ({no_mfa} users unprotected)",
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
        "no": "{count} Global Administratorer \u2014 anbefalt maks 4",
        "en": "{count} Global Administrators \u2014 recommended max 4",
    },
    "cis_ga_too_few": {
        "no": "Kun {count} Global Admin \u2014 anbefalt minimum 2",
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
        "no": "{pct:.0f}% samsvar \u2014 {noncompliant} ikke-samsvarende",
        "en": "{pct:.0f}% compliance \u2014 {noncompliant} non-compliant",
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

    # ── Recommendation titles/details (generator._build_recommendations) ──
    "rec_mfa_title": {
        "no": "Aktiver MFA for {count} bruker(e) uten beskyttelse",
        "en": "Enable MFA for {count} user(s) without protection",
    },
    "rec_mfa_detail": {
        "no": "{registered} brukere har MFA-metoder registrert, {ca_covered} er dekket via Conditional Access-policyer. {no_mfa} bruker(e) har verken MFA registrert eller CA-dekning.",
        "en": "{registered} users have MFA methods registered, {ca_covered} are covered via Conditional Access policies. {no_mfa} user(s) have neither MFA registered nor CA coverage.",
    },
    "rec_effort_low": {
        "no": "Lav",
        "en": "Low",
    },
    "rec_effort_medium": {
        "no": "Medium",
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
        "no": "Risikobrukere oppdaget i Identity Protection{suffix}",
        "en": "Risky users detected in Identity Protection{suffix}",
    },
    "rec_risky_users_suffix": {
        "no": " ({count} bruker(e))",
        "en": " ({count} user(s))",
    },
    "rec_risky_users_detail": {
        "no": "Microsoft Entra ID Protection har flagget brukere med mistenkelig aktivitet. Unders\u00f8k og bekreft/avvis disse umiddelbart.",
        "en": "Microsoft Entra ID Protection has flagged users with suspicious activity. Investigate and confirm/dismiss these immediately.",
    },
    "rec_risky_user_line": {
        "no": "{upn} \u2014 Risikoniv\u00e5: {level}, Status: {state}",
        "en": "{upn} \u2014 Risk level: {level}, Status: {state}",
    },
    "rec_secure_score_title": {
        "no": "Microsoft Secure Score er {pct:.0f}% \u2014 {count} forbedringer identifisert",
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
    "rec_intune_detail": {
        "no": "Bare {pct:.0f}% av enhetene oppfyller organisasjonens samsvarspolicyer. Unders\u00f8k ikke-samsvarende enheter og oppdater policyer ved behov.",
        "en": "Only {pct:.0f}% of devices meet the organisation\u2019s compliance policies. Investigate non-compliant devices and update policies as needed.",
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
        "no": "Azure Advisor \u2014 {category}: {count} anbefaling(er)",
        "en": "Azure Advisor \u2014 {category}: {count} recommendation(s)",
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
        "no": "{expired} utg\u00e5tte og {critical} som utg\u00e5r innen 30 dager. Utg\u00e5tte credentials vil bryte integrasjoner. Forny umiddelbart i Entra ID > App registrations.",
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
    "rec_brute_force_title": {
        "no": "Mulig brute force-angrep mot {count} bruker(e)",
        "en": "Possible brute force attack against {count} user(s)",
    },
    "rec_brute_force_detail": {
        "no": "En eller flere brukere har 50+ mislykkede p\u00e5loggingsfors\u00f8k. Dette kan indikere et p\u00e5g\u00e5ende brute force-angrep. Unders\u00f8k umiddelbart og vurder \u00e5 blokkere kildene.",
        "en": "One or more users have 50+ failed sign-in attempts. This may indicate an ongoing brute force attack. Investigate immediately and consider blocking the sources.",
    },

    # ── Executive summary bullets (generator._build_executive_summary) ──
    "exec_env_size": {
        "no": "Milj\u00f8et har {total} brukere ({enabled} aktive, {guests} gjester) og {azure_resources} Azure-ressurser fordelt p\u00e5 {subscriptions} subscription(s).",
        "en": "The environment has {total} users ({enabled} active, {guests} guests) and {azure_resources} Azure resources across {subscriptions} subscription(s).",
    },
    "exec_env_size_unavailable": {
        "no": "Miljøets størrelse kunne ikke fastslås — auditen returnerte ingen brukerdata.",
        "en": "Environment size could not be determined — the audit returned no user data.",
    },
    "exec_mfa_good": {
        "no": "MFA-dekningen er {pct:.0f}% \u2014 godt sikret mot kontoovertakelse.",
        "en": "MFA coverage is {pct:.0f}% \u2014 well protected against account takeover.",
    },
    "exec_mfa_partial": {
        "no": "MFA-dekningen er {pct:.0f}%. {no_mfa} bruker(e) mangler MFA-beskyttelse.",
        "en": "MFA coverage is {pct:.0f}%. {no_mfa} user(s) lack MFA protection.",
    },
    "exec_mfa_unavailable": {
        "no": "MFA-data er ikke tilgjengelig for denne kunden.",
        "en": "MFA data is not available for this customer.",
    },
    "exec_ss_good": {
        "no": "Microsoft Secure Score er {pct:.0f}% \u2014 over anbefalt minsteniv\u00e5.",
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
        "no": "Det er {count} Global Administrator-kontoer \u2014 Microsoft anbefaler maks 4.",
        "en": "There are {count} Global Administrator accounts \u2014 Microsoft recommends a maximum of 4.",
    },
    "exec_overall": {
        "no": "Samlet sikkerhetspostur er vurdert til grad {grade} ({score}/100) \u2014 {description}.",
        "en": "Overall security posture is assessed at grade {grade} ({score}/100) \u2014 {description}.",
    },
    "exec_overall_invalid": {
        "no": "Samlet sikkerhetspostur kan ikke vurderes \u2014 auditen mangler n\u00f8dvendige data.",
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
        "no": "Ingen påloggingsdata tilgjengelig — krever Microsoft Entra ID P1 (tidligere Azure AD Premium P1) for signInActivity.",
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
        "no": "Medium",
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
}


def get_translations(lang: str = "no") -> dict[str, str]:
    """Return a flat dict of key -> translated string for the given language."""
    result = {}
    for key, translations in TRANSLATIONS.items():
        result[key] = translations.get(lang, translations.get("no", key))
    return result


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
        return self._strings.get(key, key)

    def __call__(self, key: str, **kwargs) -> str:
        template = self._strings.get(key, key)
        if kwargs:
            return template.format(**kwargs)
        return template
