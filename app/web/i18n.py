"""Server-side UI internationalisation helpers.

Centralises the translation strings and helper functions that all route
modules need.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

from fastapi import Request

from app.core.exceptions import ToolkitError
from app.core.messages import MESSAGES as CORE_MESSAGES

_E = TypeVar("_E", bound=ToolkitError)

_UI_STRINGS = {
    "no": {
        "err_no_config": "Ingen kundekonfigurasjon funnet. Kjør oppsett først.",
        "err_customer_not_found": "Kunde ikke funnet",
        "err_missing_customer_id": "Mangler customer_id",
        "err_audit_running": "Audit kjører allerede",
        "err_no_audit_running": "Ingen audit kjører",
        "err_no_customers": "Ingen kunder registrert",
        "err_invalid_path": "Ugyldig sti",
        "err_invalid_status": "Ugyldig status",
        "err_missing_title": "Mangler tittel",
        "err_file_too_large": "Filen er for stor (maks 5 MB)",
        "err_invalid_file_type": "Ugyldig filtype",
        "err_bulk_running": "Masseaudit kjører allerede",
        "err_missing_sections": "Ingen seksjoner valgt",
        "err_preset_builtin": "Kan ikke overskrive innebygd forhåndsinnstilling",
        "msg_settings_saved": "Innstillinger lagret",
        "msg_audit_cancelled": "Audit avbrutt",
        "msg_customer_deleted": "Kunde slettet",
        "msg_customer_wiped": "Kundedata slettet",
        "msg_credentials_renewed": "Tilganger fornyet",
        "err_no_audit_data": "Ingen audit-data tilgjengelig",
        "err_no_audit_results": "Ingen audit-resultater tilgjengelig",
        "err_no_config_to_register": "Ingen konfigurasjon å registrere",
        "err_no_data_files": "Ingen datafiler funnet i mappen",
        "err_no_recipient": "Ingen mottakeradresse angitt",
        "email_test_subject": "Sybr HUB: testepost",
        "email_test_heading": "Testepost",
        "email_test_body": "E-postinnstillingene fungerer.",
        "email_test_footer": "Sendt fra Sybr HUB",
        "err_no_webhook_url": "Ingen webhook-URL",
        "err_no_api_key": "Ingen API-nøkkel konfigurert",
        "err_autotask_not_configured": "Autotask er ikke konfigurert",
        "err_autotask_account_not_found": "Fant ingen Autotask-kunde med denne id-en",
        "err_binding_taken": "Denne kontoen er allerede koblet til en annen kunde",
        "err_no_orgs_selected": "Ingen organisasjoner valgt",
        "err_no_report_files": "Ingen rapportfiler funnet",
        "err_no_customer_config": "Ingen kundekonfigurasjon",
        "err_no_key_provided": "Ingen nøkkel oppgitt",
        "err_invalid_key": "Ugyldig nøkkel. Den må være 32 bytes base64url",
        "err_no_file_path": "Ingen filsti oppgitt",
        "err_file_not_found": "Filen finnes ikke",
        "err_file_must_be_zip": "Filen må være en .zip-fil",
        "err_invalid_backup": "Ugyldig backup: manifest.json mangler",
        "err_preset_not_found": "Preset ikke funnet",
        "err_no_logo": "Ingen logo lastet opp",
        "err_cannot_create_dir": "Kan ikke opprette mappe",
        "err_cannot_create_cert_dir": "Kan ikke opprette sertifikatmappe",
        "err_backup_failed": "Backup feilet",
        "err_restore_failed": "Gjenoppretting feilet",
        "err_name_required": "Navn er påkrevd",
        "err_customer_exists": "En kunde med dette navnet finnes allerede",
        # Refusals from the middleware layer. These are the ones every account
        # meets sooner or later, and they were Norwegian string literals that
        # no language setting could reach.
        "err_write_denied": (
            "Denne handlingen endrer noe og krever skrivetilgang. Kontoen din har lesetilgang."
        ),
        "err_insecure_transport": (
            "Denne tilkoblingen er ukryptert. Innlogging over vanlig HTTP er kun "
            "tillatt fra maskinen selv. Bruk HTTPS (for eksempel «tailscale serve») "
            "for tilgang fra en annen maskin."
        ),
        "err_mfa_verification_required": "MFA-bekreftelse kreves. Logg inn på nytt.",
        "err_mfa_enrolment_required": "Aktiver MFA i brukermenyen før du fortsetter.",
    },
    "en": {
        "err_no_config": "No customer configuration found. Run setup first.",
        "err_customer_not_found": "Customer not found",
        "err_missing_customer_id": "Missing customer_id",
        "err_audit_running": "Audit is already running",
        "err_no_audit_running": "No audit is running",
        "err_no_customers": "No customers registered",
        "err_invalid_path": "Invalid path",
        "err_invalid_status": "Invalid status",
        "err_missing_title": "Missing title",
        "err_file_too_large": "File too large (max 5 MB)",
        "err_invalid_file_type": "Invalid file type",
        "err_bulk_running": "Bulk audit is already running",
        "err_missing_sections": "No sections selected",
        "err_preset_builtin": "Cannot overwrite built-in preset",
        "msg_settings_saved": "Settings saved",
        "msg_audit_cancelled": "Audit cancelled",
        "msg_customer_deleted": "Customer deleted",
        "msg_customer_wiped": "Customer data wiped",
        "msg_credentials_renewed": "Credentials renewed",
        "err_no_audit_data": "No audit data available",
        "err_no_audit_results": "No audit results available",
        "err_no_config_to_register": "No configuration to register",
        "err_no_data_files": "No data files found in directory",
        "err_no_recipient": "No recipient address specified",
        "email_test_subject": "Sybr HUB: test e-mail",
        "email_test_heading": "Test e-mail",
        "email_test_body": "The e-mail settings work.",
        "email_test_footer": "Sent from Sybr HUB",
        "err_no_webhook_url": "No webhook URL",
        "err_no_api_key": "No API key configured",
        "err_autotask_not_configured": "Autotask is not configured",
        "err_autotask_account_not_found": "No Autotask company with that id",
        "err_binding_taken": "That account is already linked to another customer",
        "err_no_orgs_selected": "No organizations selected",
        "err_no_report_files": "No report files found",
        "err_no_customer_config": "No customer configuration",
        "err_no_key_provided": "No key provided",
        "err_invalid_key": "Invalid key — must be 32 bytes base64url",
        "err_no_file_path": "No file path specified",
        "err_file_not_found": "File not found",
        "err_file_must_be_zip": "File must be a .zip file",
        "err_invalid_backup": "Invalid backup — manifest.json missing",
        "err_preset_not_found": "Preset not found",
        "err_no_logo": "No logo uploaded",
        "err_cannot_create_dir": "Cannot create directory",
        "err_cannot_create_cert_dir": "Cannot create certificate directory",
        "err_backup_failed": "Backup failed",
        "err_restore_failed": "Restore failed",
        "err_name_required": "Name is required",
        "err_customer_exists": "A customer with this name already exists",
        "err_write_denied": (
            "This action changes something and requires write access. Your account has read access."
        ),
        "err_insecure_transport": (
            "This connection is unencrypted. Signing in over plain HTTP is only "
            "allowed from this machine itself. Use HTTPS (for example "
            "'tailscale serve') to reach it from another machine."
        ),
        "err_mfa_verification_required": "MFA verification required; sign in again.",
        "err_mfa_enrolment_required": "Enable MFA from the user menu before continuing.",
    },
}


# Refusals the route modules raise, through refusal() below, and the errors and
# reasons they return in a JSON body instead, through keyed(). They were string
# literals in one language or the other, so an operator was refused in
# whichever language the route happened to be written in. Each pair sits side
# by side so the two cannot drift apart unnoticed; tests/test_route_messages.py
# holds the placeholders level.
_ROUTE_REFUSALS: dict[str, tuple[str, str]] = {
    # Refusals several route modules share.
    "err_customer_no_access": (
        "Ingen tilgang til denne kunden",
        "No access to this customer",
    ),
    "err_customer_not_found_id": (
        "Kunden '{customer}' finnes ikke",
        "No such customer: '{customer}'",
    ),
    "err_link_unknown_customer": (
        "Ukjent kunde i koblingen",
        "Unknown customer in the link",
    ),
    "err_customer_access_denied": (
        "Du har ikke tilgang til denne kunden",
        "You do not have access to this customer",
    ),
    "err_customer_no_access_id": (
        "Ingen tilgang til kunde {customer}",
        "No access to customer {customer}",
    ),
    "err_audit_run_access_denied": (
        "Ingen tilgang til denne auditkjøringen",
        "No access to this audit run",
    ),
    "err_host_required": (
        "Host er påkrevd",
        "Host is required",
    ),
    "err_host_ip_required": (
        "Host/IP er påkrevd",
        "Host/IP is required",
    ),
    "err_url_required": (
        "URL er påkrevd",
        "URL is required",
    ),
    "err_domain_required": (
        "Domene er påkrevd",
        "Domain is required",
    ),
    "err_username_password_required": (
        "Brukernavn og passord er påkrevd",
        "Username and password are required",
    ),
    "err_port_invalid": (
        "Ugyldig port: '{port}'",
        "Invalid port: '{port}'",
    ),
    "err_port_out_of_range": (
        "Port må være mellom 1 og 65535, ikke {port}",
        "Port must be between 1 and 65535, not {port}",
    ),
    "err_host_forbidden": (
        "Du har ikke tilgang til denne hosten",
        "You do not have access to this host",
    ),
    "err_host_choose_registered": (
        "Velg en registrert host",
        "Choose a registered host",
    ),
    "err_rdp_invalid_port": (
        "Ugyldig RDP-port",
        "Invalid RDP port",
    ),
    "err_host_not_found": (
        "Host ikke funnet",
        "Host not found",
    ),
    "err_guacamole_login_failed": (
        "Kunne ikke logge inn på Guacamole",
        "Could not sign in to Guacamole",
    ),
    # Sign-in, sessions and user administration (routes/auth.py).
    "err_auth_wrong_password": (
        "Feil passord",
        "Wrong password",
    ),
    "err_auth_mfa_setup_invalid": (
        "Ugyldig engangskode eller utløpt oppsett",
        "Invalid one-time code, or the setup has expired",
    ),
    "err_auth_invalid_otp": (
        "Ugyldig engangskode",
        "Invalid one-time code",
    ),
    "err_auth_session_unverifiable": (
        "Logg inn på nytt for å opprette en verifiserbar sesjon",
        "Sign in again to create a session that can be verified",
    ),
    "err_auth_bad_credentials": (
        "Feil brukernavn eller passord",
        "Wrong username or password",
    ),
    "err_auth_bad_mfa_code": (
        "Feil engangskode eller gjenopprettingskode",
        "Wrong one-time code or recovery code",
    ),
    "err_auth_invalid_refresh": (
        "Ugyldig refresh-token",
        "Invalid refresh token",
    ),
    "err_auth_account_disabled": (
        "Kontoen er deaktivert",
        "The account is disabled",
    ),
    "err_auth_session_expired": (
        "Sesjonen er utløpt. Logg inn på nytt.",
        "The session has expired. Sign in again.",
    ),
    "err_auth_current_password_wrong": (
        "Nåværende passord er feil",
        "The current password is wrong",
    ),
    "err_auth_username_taken": (
        "Brukernavnet '{username}' finnes allerede",
        "The username '{username}' already exists",
    ),
    "err_auth_user_not_found": (
        "Bruker ikke funnet",
        "User not found",
    ),
    "err_auth_cannot_delete_self": (
        "Kan ikke slette deg selv",
        "You cannot delete yourself",
    ),
    "err_auth_cannot_delete_system": (
        "Systemkontoen kan ikke slettes. Sybr HUB bruker den til planlagte jobber og tunneler.",
        "The system account cannot be deleted. Sybr HUB uses it for scheduled jobs and tunnels.",
    ),
    "err_auth_cannot_change_system": (
        "Rollen, tilgangene og statusen til systemkontoen kan ikke endres. Sybr HUB bruker "
        "den til planlagte jobber og tunneler.",
        "The system account's role, capabilities and status cannot be changed. Sybr HUB uses "
        "it for scheduled jobs and tunnels.",
    ),
    "err_auth_invalid_customer_id": (
        "Ugyldig kunde-ID",
        "Invalid customer ID",
    ),
    "err_auth_choose_access_mode": (
        "Velg alle kunder eller en avgrenset kundeliste",
        "Choose all customers or a limited list of customers",
    ),
    "err_auth_not_signed_in": (
        "Ikke innlogget. Logg inn på nytt.",
        "Not signed in. Sign in again.",
    ),
    "err_auth_last_admin_demote": (
        "Kan ikke nedgradere siste administrator",
        "Cannot demote the last administrator",
    ),
    "err_auth_last_admin_delete": (
        "Kan ikke slette siste administrator",
        "Cannot delete the last administrator",
    ),
    # Backup and restore (routes/backup.py).
    "err_backup_too_many_files": (
        "Backupen inneholder for mange filer.",
        "The backup contains too many files.",
    ),
    "err_backup_path_traversal": (
        "Ugyldig sti i backup (path traversal): {path}",
        "Invalid path in the backup (path traversal): {path}",
    ),
    "err_backup_file_location": (
        "Backup-filen må ligge i backup-mappen eller hjemmemappen",
        "The backup file must be in the backup folder or the home folder",
    ),
    "err_backup_file_too_large": (
        "En fil i backupen er for stor: {file}",
        "A file in the backup is too large: {file}",
    ),
    "err_backup_too_large": (
        "Backupen er for stor til å pakkes ut trygt.",
        "The backup is too large to unpack safely.",
    ),
    "err_backup_compression_ratio": (
        "Mistenkelig kompresjonsforhold på {file}. Avvist som mulig zip-bombe.",
        "Suspicious compression ratio on {file}. Rejected as a possible zip bomb.",
    ),
    "err_backup_entry_unreasonable": (
        "{name} i backupen er urimelig stor. Avvist.",
        "{name} in the backup is unreasonably large. Rejected.",
    ),
    "err_backup_entry_over_limit": (
        "Filen {file} overskrider størrelsesgrensen (mulig zip-bombe).",
        "The file {file} exceeds the size limit (possible zip bomb).",
    ),
    "err_backup_unauthenticated": (
        "Denne backupen er ikke autentisert (laget av en eldre versjon eller mangler signatur) og kan ikke gjenopprettes trygt. Lag en ny backup med denne versjonen.",
        "This backup is not authenticated (made by an older version, or missing its signature) and cannot be restored safely. Make a new backup with this version.",
    ),
    # Not err_invalid_backup: its English already says something else in
    # ui_i18n.json, which the front-end would show instead.
    "err_backup_manifest_missing": (
        "Ugyldig backup: manifest.json mangler",
        "Invalid backup: manifest.json is missing",
    ),
    "err_backup_manifest_no_files": (
        "Backupen mangler en gyldig fil-liste i manifestet.",
        "The backup's manifest has no valid file list.",
    ),
    "err_backup_signature_mismatch": (
        "Manifest-signaturen stemmer ikke. Backupen kan være endret. Avbrutt.",
        "The manifest signature does not match. The backup may have been altered. Aborted.",
    ),
    "err_backup_missing_file": (
        "Backupen mangler en fil den lover: {file}",
        "The backup is missing a file its manifest lists: {file}",
    ),
    "err_backup_file_corrupt": (
        "Filen {file} er skadet: hash stemmer ikke med manifestet.",
        "The file {file} is damaged: its hash does not match the manifest.",
    ),
    "err_backup_db_integrity": (
        "Databasen i backupen består ikke integritetssjekken: {result}",
        "The database in the backup fails the integrity check: {result}",
    ),
    "err_backup_password_required": (
        "Denne backupen inneholder en kryptert nøkkel. Oppgi backup-passordet for å gjenopprette.",
        "This backup contains an encrypted key. Enter the backup password to restore it.",
    ),
    "err_backup_wrong_password": (
        "Feil backup-passord. Kunne ikke dekryptere nøkkelen.",
        "Wrong backup password. Could not decrypt the key.",
    ),
    "err_backup_unknown_cipher": (
        "Backupen inneholder en ukjent krypteringsmetode",
        "The backup uses an unknown encryption method",
    ),
    "err_backup_key_adopt_failed": (
        "Kunne ikke ta i bruk nøkkelen fra backupen.",
        "Could not adopt the key from the backup.",
    ),
    "err_backup_decrypt_failed": (
        "Kunne ikke autentisere backupens krypterte innhold",
        "Could not authenticate the backup's encrypted content",
    ),
    # Customers, dashboards, history, reports, settings, the assistant and provisioning.
    "err_claude_conversation_not_found": (
        "Samtale ikke funnet",
        "Conversation not found",
    ),
    "err_claude_consent_required": (
        "Bekreft at meldinger og verktøydata kan behandles av Anthropic.",
        "Confirm that messages and tool data may be processed by Anthropic.",
    ),
    "err_claude_message_required": (
        "Melding er påkrevd",
        "A message is required",
    ),
    "err_claude_api_key_required": (
        "API-nøkkel er påkrevd for API-modus",
        "An API key is required for API mode",
    ),
    "err_claude_cli_exit_code": (
        "Claude CLI returnerte en feilkode",
        "The Claude CLI returned an error code",
    ),
    "err_claude_cli_timeout": (
        "Claude CLI svarte ikke innen 5 sekunder",
        "The Claude CLI did not answer within 5 seconds",
    ),
    "err_setup_code_state_required": (
        "Kode eller state mangler",
        "Missing code or state",
    ),
    "err_history_folder_missing": (
        "{label}: mappen finnes ikke",
        "{label}: the folder does not exist",
    ),
    "err_history_no_metrics": (
        "{label}: ingen metrikk-data funnet",
        "{label}: no metrics data found",
    ),
    "err_history_run_access_denied": (
        "{label}: Ingen tilgang til denne auditkjøringen",
        "{label}: No access to this audit run",
    ),
    "err_history_invalid_path": (
        "{label}: Ugyldig sti",
        "{label}: Invalid path",
    ),
    "err_baselines_no_such_run": (
        "Kjøringen finnes ikke",
        "No such run",
    ),
    "err_baselines_run_not_found": (
        "Ingen auditkjøring '{run}' for '{customer}'",
        "No audit run '{run}' for '{customer}'",
    ),
    "err_reports_email_failed": (
        "Kunne ikke sende e-post",
        "Could not send the email",
    ),
    "err_reports_generation_failed": (
        "Rapportgenerering feilet",
        "Report generation failed",
    ),
    "err_reports_path_required": (
        "Sti er påkrevd",
        "Path required",
    ),
    "err_reports_run_not_found": (
        "Rapporten finnes ikke",
        "Report not found",
    ),
    "err_reports_no_audited_customers": (
        "Fant ingen auditerte kunder",
        "No audited customers found",
    ),
    "err_settings_not_number": (
        "{field} må være et tall",
        "{field} must be a number",
    ),
    "err_settings_dir_outside_allowed": (
        "Mappen må ligge under hjemmemappen eller datamappen",
        "Directory must be under home or data directory",
    ),
    "err_settings_key_export_failed": (
        "Kunne ikke eksportere krypteringsnøkkel",
        "Could not export the encryption key",
    ),
    "err_settings_webhook_test_failed": (
        "Webhook-test feilet",
        "Webhook test failed",
    ),
    "err_scheduler_customer_required": (
        "Velg kunden automatisk audit skal gjelde, eller velg alle kunder.",
        "Choose the customer the automatic audit is for, or choose all customers.",
    ),
    "err_scheduler_customer_unknown": (
        "Kunden du valgte for automatisk audit, finnes ikke.",
        "The customer you chose for the automatic audit does not exist.",
    ),
    "err_provisioning_session_not_found": (
        "Sesjon ikke funnet",
        "Session not found",
    ),
    "err_provisioning_write_denied": (
        "Deploy skriver til kundens enhet og krever skrivetilgang. Kontoen din har lesetilgang.",
        "Deploying writes to the customer's device and requires write access. Your account has read access.",
    ),
    "err_provisioning_customer_name_required": (
        "Kundenavn er påkrevd",
        "Customer name is required",
    ),
    "err_provisioning_deploy_crashed": (
        "Deploy krasjet: {kind}: {error}",
        "Deploy crashed: {kind}: {error}",
    ),
    # ALSO, the hub, IT Glue, myITprocess, Uniweb and Tailscale.
    "err_also_not_found": (
        "Ikke funnet",
        "Not found",
    ),
    "err_also_not_configured": (
        "ALSO er ikke konfigurert",
        "ALSO is not configured",
    ),
    "err_also_price_scan_running": (
        "En prisskanning kjører allerede",
        "A price scan is already running",
    ),
    "err_also_renewal_not_found": (
        "Fornyelse ikke funnet",
        "Renewal not found",
    ),
    "err_also_scan_running": (
        "En skanning kjører allerede",
        "A scan is already running",
    ),
    "err_also_no_matches": (
        "Ingen treff oppgitt",
        "No matches given",
    ),
    "err_hub_recommendation_not_found": (
        "Fant ikke anbefalingen '{recommendation}' i siste audit for denne kunden.",
        "Recommendation '{recommendation}' is not in this customer's latest audit.",
    ),
    "err_hub_autotask_not_linked": (
        "Denne kunden er ikke koblet til en Autotask-konto. Koble den først under Hub → kobling.",
        "This customer is not linked to an Autotask account. Link it first under Hub → linking.",
    ),
    "err_hub_myitprocess_not_linked": (
        "Denne kunden er ikke koblet til en myITprocess-konto. Koble den først under Hub → kobling.",
        "This customer is not linked to a myITprocess account. Link it first under Hub → linking.",
    ),
    "err_hub_autotask_rejected": (
        "Autotask avviste saken: {error}",
        "Autotask rejected the ticket: {error}",
    ),
    "err_hub_myitprocess_rejected": (
        "myITprocess avviste anbefalingen: {error}",
        "myITprocess rejected the recommendation: {error}",
    ),
    "err_hub_autotask_id_not_number": (
        "autotask_account_id må være et tall",
        "autotask_account_id must be a number",
    ),
    "err_hub_link_nothing_sent": (
        "Send autotask_account_id, itglue_org_id og/eller myitprocess_account_id for å endre en kobling.",
        "Send autotask_account_id, itglue_org_id and/or myitprocess_account_id to change a binding.",
    ),
    "err_itglue_org_not_linked": (
        "IT Glue-organisasjonen er ikke koblet til denne kunden",
        "The IT Glue organization is not linked to this customer",
    ),
    "err_itglue_org_id_required": (
        "org_id er påkrevd",
        "org_id is required",
    ),
    "err_itglue_no_mapped_customers": (
        "Ingen kunder er koblet til en IT Glue-organisasjon",
        "No customers have an IT Glue organization mapped",
    ),
    "err_itglue_customer_not_mapped": (
        "Kunden er ikke koblet til en IT Glue-organisasjon",
        "The customer has no IT Glue organization mapped",
    ),
    "err_itglue_org_id_invalid": (
        "Kunden er koblet til en ugyldig IT Glue-organisasjon ({org_id}). Koble kunden på nytt.",
        "The customer is mapped to an invalid IT Glue organization ({org_id}). Link the customer again.",
    ),
    "err_itglue_upload_failed": (
        "Opplasting til IT Glue feilet",
        "IT Glue upload failed",
    ),
    "err_itglue_document_upload_failed": (
        "Opplasting av dokumenter til IT Glue feilet",
        "IT Glue document upload failed",
    ),
    "err_itglue_credential_upload_failed": (
        "Opplasting av tilganger til IT Glue feilet",
        "IT Glue credential upload failed",
    ),
    "err_itglue_sync_failed": (
        "Synkronisering til IT Glue feilet: {error}",
        "IT Glue sync failed: {error}",
    ),
    "err_itglue_bulk_sync_failed": (
        "Massesynkronisering til IT Glue feilet: {error}",
        "IT Glue bulk sync failed: {error}",
    ),
    "err_myitprocess_not_configured": (
        "myITprocess er ikke konfigurert. Legg inn API-nøkkelen under Integrasjoner.",
        "myITprocess is not configured. Add the API key under Integrations.",
    ),
    "err_myitprocess_not_configured_first": (
        "myITprocess er ikke konfigurert. Legg inn API-nøkkelen under Integrasjoner først.",
        "myITprocess is not configured. Add the API key under Integrations first.",
    ),
    "err_myitprocess_accounts_failed": (
        "Kunne ikke hente myITprocess-kontoer: {error}",
        "Could not fetch myITprocess accounts: {error}",
    ),
    "err_uniweb_not_configured": (
        "Uniweb-legitimasjon er ikke konfigurert",
        "Uniweb credentials are not configured",
    ),
    "err_uniweb_account_missing": (
        "Konto ikke funnet",
        "Account not found",
    ),
    "err_uniweb_account_not_found": (
        "Uniweb-konto ikke funnet",
        "Uniweb account not found",
    ),
    "err_uniweb_account_id_required": (
        "uniweb_account_id er påkrevd",
        "uniweb_account_id is required",
    ),
    "err_uniweb_no_accounts_selected": (
        "Ingen kontoer valgt",
        "No accounts selected",
    ),
    "err_uniweb_email_password_required": (
        "E-post og passord er påkrevd",
        "Email and password are required",
    ),
    "err_uniweb_sync_running": (
        "Synkronisering kjører allerede",
        "A sync is already running",
    ),
    "err_uniweb_account_already_linked": (
        "Allerede koblet til en kunde",
        "Already linked to a customer",
    ),
    "err_uniweb_account_name_missing": (
        "Kontonavnet mangler",
        "The account name is missing",
    ),
    "err_tailscale_not_configured": (
        "Tailscale API-nøkkel er ikke konfigurert",
        "No Tailscale API key is configured",
    ),
    "err_tailscale_remove_failed": (
        "Kunne ikke fjerne enhet",
        "Could not remove the device",
    ),
    "err_tailscale_revoke_failed": (
        "Kunne ikke tilbakekalle nøkkel",
        "Could not revoke the key",
    ),
    "err_tailscale_api_status": (
        "Tailscale API returnerte {status}",
        "The Tailscale API returned {status}",
    ),
    "err_tailscale_unreachable": (
        "Tailscale svarte ikke, så nodene kunne ikke hentes",
        "Tailscale did not answer, so the nodes could not be read",
    ),
    # FortiGate and UniFi.
    "err_fortigate_host_token_required": (
        "Host og API-token er påkrevd",
        "Host and API token are required",
    ),
    "err_fortigate_host_missing": (
        "FortiGate-host er ikke konfigurert for denne kunden",
        "No FortiGate host is configured for this customer",
    ),
    "err_fortigate_token_missing": (
        "FortiGate API-token er ikke konfigurert for denne kunden",
        "No FortiGate API token is configured for this customer",
    ),
    "err_fortigate_backup_not_found": (
        "Sikkerhetskopi ikke funnet",
        "Backup not found",
    ),
    "err_fortigate_admin_key_required": (
        "admin_user og public_key er påkrevd",
        "admin_user and public_key are required",
    ),
    "err_fortigate_ssh_required": (
        "ssh_host og ssh_password er påkrevd",
        "ssh_host and ssh_password are required",
    ),
    "err_fortigate_host_ip_required": (
        "host (IP-adresse) er påkrevd",
        "host (IP address) is required",
    ),
    "err_fortigate_customer_forbidden": (
        "Du har ikke tilgang til kunden FortiGaten skulle lagres på",
        "You do not have access to the customer this FortiGate was to be saved for",
    ),
    "err_fortigate_no_credentials": (
        "Ingen lagret påloggingsinformasjon for denne FortiGaten",
        "No saved credentials for this FortiGate",
    ),
    "err_fortigate_address_admin_only": (
        "Denne FortiGaten har et lagret admin-passord. Bare en administrator kan endre adressen.",
        "This FortiGate has a saved admin password. Only an administrator can change its address.",
    ),
    "err_fortigate_remove_admin_only": (
        "Denne FortiGaten har et lagret admin-passord. Bare en administrator kan fjerne den.",
        "This FortiGate has a saved admin password. Only an administrator can remove it.",
    ),
    "err_fortigate_invalid_ssh_port": (
        "Ugyldig ssh_port: '{port}'",
        "Invalid ssh_port: '{port}'",
    ),
    "err_unifi_credentials_required": (
        "Host, brukernavn og passord er påkrevd",
        "Host, username and password are required",
    ),
    "err_unifi_address_scheme": (
        "Kontrolleradressen må bruke http eller https",
        "The controller address must use http or https",
    ),
    "err_unifi_address_bad_port": (
        "Ugyldig port i kontrolleradressen",
        "Invalid port in the controller address",
    ),
    "err_unifi_address_no_host": (
        "Kontrolleradressen mangler vertsnavn",
        "The controller address has no hostname",
    ),
    "err_unifi_address_host_port_only": (
        "Kontrolleradressen kan bare inneholde vertsnavn og port",
        "The controller address can only contain a hostname and a port",
    ),
    "err_unifi_inform_required": (
        "Controller URL er påkrevd",
        "Controller URL is required",
    ),
    "err_unifi_inform_scheme": (
        "Controller URL må bruke http eller https",
        "The controller URL must use http or https",
    ),
    "err_unifi_inform_bad_port": (
        "Ugyldig port i controller URL: {error}",
        "Invalid port in the controller URL: {error}",
    ),
    "err_unifi_inform_no_host": (
        "Controller URL mangler vertsnavn",
        "The controller URL has no hostname",
    ),
    "err_unifi_inform_query": (
        "Controller URL kan ikke inneholde query eller fragment",
        "The controller URL cannot contain a query or a fragment",
    ),
    "err_unifi_inform_path": (
        "Controller URL må peke på /inform",
        "The controller URL must point to /inform",
    ),
    "err_unifi_subnet_required": (
        "Subnet er påkrevd (f.eks. 192.168.1.0/24)",
        "A subnet is required (for example 192.168.1.0/24)",
    ),
    "err_unifi_host_config_required": (
        "Host og konfigurasjon er påkrevd",
        "Host and configuration are required",
    ),
    "err_unifi_no_devices": (
        "Ingen nettverksenheter konfigurert for denne kunden",
        "No network devices are configured for this customer",
    ),
    "err_unifi_cloud_credentials_required": (
        "API-nøkkel eller brukernavn/passord er påkrevd",
        "An API key, or a username and password, is required",
    ),
    "err_unifi_2fa_required": (
        "Session-token og 2FA-kode er påkrevd",
        "Session token and 2FA code are required",
    ),
    "err_unifi_no_links": (
        "Ingen koblinger oppgitt",
        "No links given",
    ),
    "err_unifi_link_missing_id": (
        "Kunde-id eller host-id mangler",
        "The customer id or the host id is missing",
    ),
    "err_unifi_devices_failed": (
        "Kunne ikke hente enheter",
        "Failed to fetch devices",
    ),
    "err_unifi_isp_metrics_failed": (
        "Kunne ikke hente ISP-målinger",
        "Failed to fetch ISP metrics",
    ),
    "err_unifi_hosts_failed": (
        "Kunne ikke hente hoster",
        "Failed to fetch hosts",
    ),
    "err_unifi_site_overview_failed": (
        "Kunne ikke hente oversikten over sites",
        "Failed to fetch site overview",
    ),
    "err_unifi_diagnostics_unavailable": (
        "Diagnostikk er ikke tilgjengelig",
        "Diagnostics unavailable",
    ),
    "err_unifi_wan_details_failed": (
        "Kunne ikke hente WAN-detaljer",
        "Failed to fetch WAN details",
    ),
    "err_unknown": (
        "Ukjent feil",
        "Unknown error",
    ),
    "err_unifi_msp_wide": (
        "Denne visningen dekker alle kunder og krever tilgang til alle kunder",
        "This view covers every customer and requires access to all customers",
    ),
    # SSH, the remote browser and RDP, and VPN.
    "err_ssh_key_not_found": (
        "Nøkkel ikke funnet",
        "Key not found",
    ),
    "err_ssh_key_forbidden": (
        "Du har ikke tilgang til denne SSH-nøkkelen",
        "You do not have access to this SSH key",
    ),
    "err_ssh_key_missing": (
        "SSH-nøkkelen finnes ikke",
        "The SSH key does not exist",
    ),
    "err_ssh_password_line_breaks": (
        "Passordet kan ikke inneholde linjeskift",
        "The password cannot contain line breaks",
    ),
    "err_ssh_hosts_forbidden": (
        "Du har ikke tilgang til en eller flere av disse hostene",
        "You do not have access to one or more of these hosts",
    ),
    "err_ssh_key_choose_customer": (
        "Velg kunden nøkkelen hører til",
        "Choose the customer the key belongs to",
    ),
    "err_ssh_key_invalid": (
        "Ugyldig SSH-nøkkel. Sjekk at den er i PEM- eller OpenSSH-format og uten passord.",
        "Invalid SSH key. Check that it is in PEM or OpenSSH format and has no passphrase.",
    ),
    "err_ssh_key_unreadable": (
        "Nøkkelen kunne ikke leses. Sjekk at den er i PEM- eller OpenSSH-format.",
        "The key could not be read. Check that it is in PEM or OpenSSH format.",
    ),
    "err_ssh_key_import_failed": (
        "Importering av nøkkel feilet",
        "Importing the key failed",
    ),
    "err_ssh_host_key_forbidden": (
        "Verten bruker en SSH-nøkkel du ikke har tilgang til, så adressen kan ikke endres",
        "The host uses an SSH key you do not have access to, so its address cannot be changed",
    ),
    "err_ssh_test_failed": (
        "Tilkoblingstesten feilet",
        "The connection test failed",
    ),
    "err_rdp_no_client": (
        "Fant ingen RDP-klient. Installer FreeRDP (xfreerdp).",
        "No RDP client found. Install FreeRDP (xfreerdp).",
    ),
    "err_rdp_no_session": (
        "Ingen aktiv RDP-sesjon",
        "No active RDP session",
    ),
    "err_rdp_clipboard_empty": (
        "Ingen tekst å sende",
        "No text to send",
    ),
    "err_proxy_url_scheme": (
        "Nettleseren tillater bare fullstendige http/https-URL-er",
        "The browser only allows full http/https URLs",
    ),
    "err_proxy_url_userinfo": (
        "Brukerinformasjon i URL er ikke tillatt",
        "User information in the URL is not allowed",
    ),
    "err_proxy_session_other_user": (
        "Nettleserøkten tilhører en annen bruker",
        "The browser session belongs to another user",
    ),
    "err_proxy_host_missing": (
        "Host finnes ikke",
        "The host does not exist",
    ),
    "err_proxy_no_session": (
        "Ingen nettleser-sesjon kjører",
        "No browser session is running",
    ),
    "err_proxy_stopped_cleanup_pending": (
        "Nettleseren ble stoppet, men Guacamole-tilkoblingen kunne ikke slettes; opprydding vil prøves på nytt",
        "The browser was stopped, but the Guacamole connection could not be deleted; cleanup will be retried",
    ),
    "err_proxy_xvfb_failed": (
        "Xvfb startet ikke (exit code {code})",
        "Xvfb did not start (exit code {code})",
    ),
    "err_proxy_chromium_crashed": (
        "Chromium krasjet ved oppstart: {output}",
        "Chromium crashed on start: {output}",
    ),
    "err_proxy_x11vnc_failed": (
        "x11vnc startet ikke",
        "x11vnc did not start",
    ),
    "err_proxy_binary_missing": (
        "Binær ikke funnet: {binary}",
        "Binary not found: {binary}",
    ),
    "err_guacamole_vnc_failed": (
        "Kunne ikke opprette VNC-tilkobling i Guacamole",
        "Could not create a VNC connection in Guacamole",
    ),
    "err_guacamole_rdp_failed": (
        "Kunne ikke opprette RDP-tilkobling i Guacamole",
        "Could not create an RDP connection in Guacamole",
    ),
    "err_guacamole_cleanup_pending": (
        "Guacamole-tilkoblingen kunne ikke slettes; opprydding vil prøves på nytt",
        "The Guacamole connection could not be deleted; cleanup will be retried",
    ),
    "err_guacamole_stale_connection": (
        "En tidligere Guacamole-tilkobling kunne ikke ryddes; nekter å opprette en ny",
        "An earlier Guacamole connection could not be cleaned up; refusing to create a new one",
    ),
    "err_vpn_profile_not_found": (
        "Profil ikke funnet",
        "Profile not found",
    ),
    "err_vpn_profile_forbidden": (
        "Du har ikke tilgang til denne VPN-profilen",
        "You do not have access to this VPN profile",
    ),
    "err_vpn_share_admin_only": (
        "Bare administrator kan gjøre en VPN-profil delt",
        "Only an administrator can make a VPN profile shared",
    ),
    "err_vpn_create_shared_admin_only": (
        "Bare administrator kan opprette delte VPN-profiler",
        "Only an administrator can create shared VPN profiles",
    ),
    "err_vpn_no_auth_code": (
        "Kunne ikke finne auth-kode i URLen",
        "Could not find an auth code in the URL",
    ),
    "err_vpn_device_code_required": (
        "device_code er påkrevd",
        "device_code is required",
    ),
    "err_vpn_unknown_device_code": (
        "Ukjent enhetskode",
        "Unknown device code",
    ),
    "err_vpn_no_access_token": (
        "Ingen access token",
        "No access token",
    ),
    "err_vpn_not_azure": (
        "Profilen er ikke en Azure VPN-profil",
        "The profile is not an Azure VPN profile",
    ),
    "err_vpn_held_names": (
        "Systemkontoen holder VPN-tunneler åpne for statistikkinnhenting: {names}. Vent til innhentingen er ferdig, eller stopp den planlagte jobben først.",
        "The system account is holding VPN tunnels open to collect statistics: {names}. Wait for the collection to finish, or stop the scheduled job first.",
    ),
    "err_vpn_held_names_and_one": (
        "Systemkontoen holder VPN-tunneler åpne for statistikkinnhenting: {names} og 1 tunnel for andre kunder. Vent til innhentingen er ferdig, eller stopp den planlagte jobben først.",
        "The system account is holding VPN tunnels open to collect statistics: {names} and 1 tunnel for other customers. Wait for the collection to finish, or stop the scheduled job first.",
    ),
    "err_vpn_held_names_and_many": (
        "Systemkontoen holder VPN-tunneler åpne for statistikkinnhenting: {names} og {count} tunneler for andre kunder. Vent til innhentingen er ferdig, eller stopp den planlagte jobben først.",
        "The system account is holding VPN tunnels open to collect statistics: {names} and {count} tunnels for other customers. Wait for the collection to finish, or stop the scheduled job first.",
    ),
    "err_vpn_held_one": (
        "Systemkontoen holder VPN-tunneler åpne for statistikkinnhenting: 1 tunnel for andre kunder. Vent til innhentingen er ferdig, eller stopp den planlagte jobben først.",
        "The system account is holding VPN tunnels open to collect statistics: 1 tunnel for other customers. Wait for the collection to finish, or stop the scheduled job first.",
    ),
    "err_vpn_held_many": (
        "Systemkontoen holder VPN-tunneler åpne for statistikkinnhenting: {count} tunneler for andre kunder. Vent til innhentingen er ferdig, eller stopp den planlagte jobben først.",
        "The system account is holding VPN tunnels open to collect statistics: {count} tunnels for other customers. Wait for the collection to finish, or stop the scheduled job first.",
    ),
    # Security tests and TLS checks.
    "err_pentest_target_required_hint": (
        "Target er påkrevd (IP, hostname eller CIDR)",
        "A target is required (IP, hostname or CIDR)",
    ),
    "err_pentest_target_required": (
        "Target er påkrevd",
        "A target is required",
    ),
    "err_pentest_no_findings": (
        "Ingen funn å rapportere",
        "No findings to report",
    ),
    "err_pentest_subdomains_or_domain": (
        "Oppgi 'subdomains' eller 'domain'",
        "Give 'subdomains' or 'domain'",
    ),
    "err_pentest_scan_not_found": (
        "Scan ikke funnet",
        "Scan not found",
    ),
    "err_pentest_customer_or_targets": (
        "Oppgi customer_id for auto-test eller targets for manuell test",
        "Give customer_id for an automatic test, or targets for a manual test",
    ),
    "err_tls_no_endpoints": (
        "Ingen endepunkter oppgitt",
        "No endpoints given",
    ),
    "err_tls_no_domains": (
        "Ingen domener oppgitt",
        "No domains given",
    ),
    "err_tls_endpoint_not_found": (
        "Endepunktet finnes ikke i listen",
        "That endpoint is not in the list",
    ),
    # The docs viewer, GDAP, and Conditional Access deploy, restore and backup.
    # These were English literals, so the Norwegian interface was the one
    # refused in the wrong language here.
    "err_docs_path_required": (
        "path er påkrevd",
        "path is required",
    ),
    "err_docs_path_escapes": (
        "Stien peker utenfor docs-mappen",
        "path escapes docs root",
    ),
    "err_docs_only_markdown": (
        "Bare .md-filer kan hentes her",
        "only .md files are served",
    ),
    "err_docs_asset_type": (
        "Filtypen er ikke tillatt. Tillatt: {allowed}",
        "asset type not permitted; allowed: {allowed}",
    ),
    "err_docs_not_found": (
        "Fant ikke dokumentet: {path}",
        "doc not found: {path}",
    ),
    "err_docs_asset_not_found": (
        "Fant ikke filen: {path}",
        "asset not found: {path}",
    ),
    "err_gdap_tenant_client_required": (
        "partner_tenant_id og client_id er påkrevd",
        "partner_tenant_id and client_id are required",
    ),
    "err_gdap_secret_required": (
        "client_secret er påkrevd ved første oppsett",
        "client_secret is required for initial setup",
    ),
    "err_gdap_saved_not_validated": (
        "Legitimasjonen er lagret, men valideringen mot Partner Center feilet: {error}",
        "Credentials saved but Partner Center validation failed: {error}",
    ),
    "err_gdap_validation_failed": (
        "GDAP-validering feilet: {error}",
        "GDAP validation failed: {error}",
    ),
    "err_gdap_not_configured": (
        "GDAP er ikke konfigurert",
        "GDAP is not configured",
    ),
    "err_gdap_not_configured_setup": (
        "GDAP er ikke konfigurert. Legg inn partnerlegitimasjonen først.",
        "GDAP is not configured. Set up partner credentials first.",
    ),
    "err_gdap_partner_center_error": (
        "Feil fra Partner Center API: {error}",
        "Partner Center API error: {error}",
    ),
    "err_gdap_no_tenant_ids": (
        "Ingen tenant_ids oppgitt",
        "No tenant_ids provided",
    ),
    "err_gdap_not_in_partner_center": (
        "Finnes ikke i Partner Center",
        "Not found in Partner Center",
    ),
    "err_gdap_customer_has_tenant": (
        "Kunden har allerede tenant {tenant}…",
        "The customer already has tenant {tenant}…",
    ),
    "err_policy_no_template": (
        "Ingen mal oppgitt",
        "No template named",
    ),
    "err_policy_template_fingerprint_required": (
        "Både en mal og fingeravtrykket til planen er påkrevd",
        "Both a template and the fingerprint of its plan are required",
    ),
    "err_policy_which_policy": (
        "Hvilken policy? Oppgi den med id.",
        "Which policy? Name it by id.",
    ),
    "err_policy_no_consent": (
        "Denne tenanten har ikke samtykket til {permission}. Ingenting ble sendt.",
        "This tenant has not consented to {permission}. Nothing was sent.",
    ),
    "err_policy_not_in_tenant": (
        "Policyen '{policy}' finnes ikke i denne tenanten.",
        "No policy '{policy}' in this tenant.",
    ),
    "err_policy_not_report_only": (
        "Bare en policy i rapporteringsmodus kan håndheves herfra. Denne er '{state}', og det er en annen beslutning.",
        "Only a report-only policy can be enabled from here. This one is '{state}', which is a different decision.",
    ),
    "err_policy_no_tenant_id": (
        "'{customer}' har ingen tenant-id",
        "'{customer}' has no tenant id",
    ),
    "err_policy_no_client_id": (
        "'{customer}' har ingen klient-id",
        "'{customer}' has no client id",
    ),
    "err_policy_no_pending_sign_in": (
        "Ingen innlogging venter for denne kunden. Start en først.",
        "No sign-in is pending for this customer. Start one first.",
    ),
    "err_policy_restore_source_required": (
        "Både typen gjenopprettingskilde og referansen til den er påkrevd",
        "Both a restore source kind and its reference are required",
    ),
    "err_policy_fingerprint_required": (
        "Fingeravtrykket til planen som ble gjennomgått, er påkrevd",
        "The fingerprint of the reviewed plan is required",
    ),
    "err_policy_backup_no_such_snapshot": (
        "Øyeblikksbildet finnes ikke",
        "No such snapshot",
    ),
    "err_policy_backup_snapshot_not_in_run": (
        "Øyeblikksbildet '{name}' finnes ikke i kjøringen '{run}'",
        "No snapshot '{name}' in run '{run}'",
    ),
}


for _table in (CORE_MESSAGES, _ROUTE_REFUSALS):
    for _key, (_no, _en) in _table.items():
        _UI_STRINGS["no"].setdefault(_key, _no)
        _UI_STRINGS["en"].setdefault(_key, _en)


def refusal(cls: type[_E], key: str, **params: object) -> _E:
    """An exception for a route to raise, answered in the reader's language.

    The exception's own message is the Norwegian text, so the log reads as it
    always has. The error handler in server.py replaces it in the response
    with the reader's translation of *key*, filled from *params*.
    """
    return cls(_UI_STRINGS["no"][key].format(**params), message_key=key, params=params or None)


def keyed(field: str, key: str, request: Request | None, /, **params: object) -> dict[str, str]:
    """A message a route returns in its JSON body, in the reader's language.

    refusal() is for an error a route raises. Some routes answer with a 200
    instead: a connection test that failed, an import that skipped a row and
    says why. Those carried a literal in one language. This gives
    ``{field: text, field + "_key": key}``, the pair the error handler gives a
    raised refusal as ``error`` and ``error_key``, so the SPA can show
    ``t(key, text)`` and the text is already in the reader's language.
    """
    return {field: ui_t(key, request, params or None), f"{field}_key": key}


def get_ui_lang(request: Request = None) -> str:
    """Get UI language from query param, header, or default."""
    if request:
        lang = request.query_params.get("lang", "")
        if lang in ("no", "en"):
            return lang
        accept = request.headers.get("accept-language", "")
        if "en" in accept.lower():
            return "en"
    return "no"


@lru_cache(maxsize=1)
def _web_strings() -> dict[str, dict[str, str]]:
    """The front-end's language file, as a fallback for this module's table.

    There are two translation tables for one application, and they had already
    drifted: eight keys the routes ask for are only in the JSON, so ``ui_t``
    handed back the key name and the activity log on the home view read
    "log_history_deleted" to whoever deleted a run.

    They are not merged here. Six Norwegian and ten English strings say
    different things in the two tables, several with a ``{placeholder}`` on one
    side only, so a wholesale merge would silently reword messages that work
    today. This only covers keys the table below does not define at all.
    """
    path = Path(__file__).parent / "static" / "ui_i18n.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"no": {}, "en": {}}


class _KeepMissing(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def ui_t(key: str, request: Request = None, params: dict | None = None) -> str:
    """Translate a UI string, filling its {placeholders} from *params*."""
    text = _lookup(key, get_ui_lang(request))
    return text.format_map(_KeepMissing(params)) if params else text


def _lookup(key: str, lang: str) -> str:
    for table in (_UI_STRINGS.get(lang, {}), _UI_STRINGS["no"]):
        if key in table:
            return table[key]
    web = _web_strings()
    for table in (web.get(lang, {}), web.get("no", {})):
        if key in table:
            return table[key]
    return key
