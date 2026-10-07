"""User-facing error messages that core and service code raise, by key.

Code below the web layer cannot reach app/web/i18n.py, so the messages it
raises live here in both languages. app/web/i18n.py merges this table into
its own, and the error handler answers in the reader's language. The
Norwegian text is also the exception's own message, for logs and for callers
that never reach a person.
"""

from __future__ import annotations

from app.core.exceptions import ConflictError, ValidationError

MESSAGES: dict[str, tuple[str, str]] = {
    "err_setup_pkce_expired": (
        "Påloggingen er utløpt, brukt eller tilhører en annen økt. Velg Ny pålogging og lim inn den nye returadressen.",
        "This sign-in has expired, was used or belongs to another session. Choose New sign-in and paste the new return URL.",
    ),
    "err_setup_pkce_connect": (
        "Serveren kunne ikke koble til Microsoft. Kontroller DNS og nettverk, og prøv Fullfør oppsett igjen. Ved utløpt kode velger du Ny pålogging.",
        "The server could not connect to Microsoft. Check DNS and network, then retry Complete Setup. If the code expires, choose New sign-in.",
    ),
    "err_setup_pkce_delivery": (
        "Forbindelsen til Microsoft ble brutt. Koden kan allerede være brukt. Velg Ny pålogging før nytt forsøk.",
        "The connection to Microsoft was interrupted. The code may already be used. Choose New sign-in before retrying.",
    ),
    "err_setup_pkce_rejected": (
        "Microsoft avviste innloggingskoden ({code}). Velg Ny pålogging og lim inn den nye returadressen med en gang.",
        "Microsoft rejected the sign-in code ({code}). Choose New sign-in and paste the new return URL immediately.",
    ),
    "err_setup_pkce_busy": (
        "Innloggingen behandles allerede. Vent til forsøket er ferdig.",
        "This sign-in is already being processed. Wait for the attempt to finish.",
    ),
    "err_setup_pkce_registration": (
        "App-oppsettet feilet etter pålogging. Kontroller serverloggen og eventuell opprettet appregistrering før nytt forsøk.",
        "App setup failed after sign-in. Check the server log and any created app registration before retrying.",
    ),
    "err_setup_renew_tenant": (
        "Du logget inn på en annen tenant enn kunden som skal fornyes. Ingen app eller legitimasjon er endret. Velg Ny pålogging med kundens administrator.",
        "You signed in to a different tenant than the customer being renewed. No app or credentials were changed. Choose New sign-in with the customer's administrator.",
    ),
    "err_setup_customer_access": (
        "Denne tenanten er allerede lagret som en kunde du ikke har tilgang til. Oppsettet er stoppet før appen eller kundens legitimasjon endres.",
        "This tenant is already saved as a customer you cannot access. Setup stopped before changing the app or customer credentials.",
    ),
    "err_setup_grant": (
        "Microsoft avviste oppsettstrinnet {step} ({http_status}). Oppsettet er ikke ferdig. Velg Ny pålogging med en aktiv Global Administrator og prøv igjen; den lagrede appen gjenbrukes.",
        "Microsoft refused setup step {step} ({http_status}). Setup is incomplete. Choose New sign-in with an active Global Administrator and retry; the saved app will be reused.",
    ),
    "err_setup_permissions_pending": (
        "Microsoft har ikke gjort alle tilganger tilgjengelige ennå ({missing}). Appen er lagret for gjenopptakelse, men oppsettet er ikke ferdig. Vent noen minutter og velg Ny pålogging.",
        "Microsoft has not made all permissions available yet ({missing}). The app is saved for resuming, but setup is incomplete. Wait a few minutes and choose New sign-in.",
    ),
    "err_readonly_account": (
        "Kontoen din har lesetilgang. Endringer krever skrivetilgang.",
        "Your account has read access. Changes require write.",
    ),
    "err_policy_plan_unreadable": (
        "Kundens policyplan kunne ikke leses. Gjenopprett lagrede data før endringer.",
        "The customer policy plan could not be read. Restore the saved data before making changes.",
    ),
    "err_policy_plan_changed": (
        "Policyplanen er endret i en annen fane. Last inn på nytt før du lagrer.",
        "The policy plan changed in another tab. Reload before saving.",
    ),
    "err_policy_plan_selection": (
        "Velg en gyldig pakke og policyer fra biblioteket.",
        "Select a valid package and policies from the library.",
    ),
    "err_policy_review_evidence": (
        "Skriv kontrollgrunnlag eller begrunnelse for vurderingen.",
        "Enter verification evidence or a reason for the assessment.",
    ),
    "err_policy_review_date": (
        "Unntak krever en fremtidig utløpsdato. Kontrollnotatet kan ha maksimalt 2000 tegn.",
        "Exceptions require a future expiry date. Review notes may contain at most 2000 characters.",
    ),
    "err_field_required": (
        "{field} er påkrevd",
        "{field} is required",
    ),
    "err_field_not_text": (
        "{field} må være tekst",
        "{field} must be text",
    ),
    "err_field_too_long_n": (
        "{field} kan ikke være lengre enn {max_length} tegn",
        "{field} cannot be longer than {max_length} characters",
    ),
    "err_field_too_long": (
        "{field} er for lang",
        "{field} is too long",
    ),
    "err_field_line_breaks": (
        "{field} kan ikke inneholde linjeskift",
        "{field} cannot contain line breaks",
    ),
    "err_field_single_line": (
        "{field} må være én enkelt linje",
        "{field} must be a single line",
    ),
    "err_field_bad_chars": (
        "{field} inneholder ugyldige tegn",
        "{field} contains invalid characters",
    ),
    "err_field_range": (
        "{field} må være mellom {minimum} og {maximum}",
        "{field} must be between {minimum} and {maximum}",
    ),
    "err_field_not_integer": (
        "Ugyldig {field}: må være et heltall",
        "Invalid {field}: must be a whole number",
    ),
    "err_field_not_ip": (
        "Ugyldig {field}: '{text}' er ikke en gyldig IP-adresse",
        "Invalid {field}: '{text}' is not a valid IP address",
    ),
    "err_field_not_address": (
        "Ugyldig {field}: '{text}' er ikke en gyldig adresse",
        "Invalid {field}: '{text}' is not a valid address",
    ),
    "err_field_not_host": (
        "Ugyldig {field}: '{text}' er ikke et gyldig vertsnavn eller IP",
        "Invalid {field}: '{text}' is not a valid hostname or IP",
    ),
    "err_field_unparsable": (
        "Ugyldig {field}: {reason}",
        "Invalid {field}: {reason}",
    ),
    "err_field_identifier": (
        "Ugyldig {field}: kun bokstaver, tall, '.', '_' og '-' er tillatt",
        "Invalid {field}: only letters, digits, '.', '_' and '-' are allowed",
    ),
    "err_field_login_name": (
        "Ugyldig {field}: kun bokstaver, tall, mellomrom og . _ - @ \\ $ er tillatt",
        "Invalid {field}: only letters, digits, spaces and . _ - @ \\ $ are allowed",
    ),
    "err_field_ssh_key": (
        "Ugyldig {field}: forventet en OpenSSH public key",
        "Invalid {field}: expected an OpenSSH public key",
    ),
    "err_field_wg_key": (
        "Ugyldig {field}: forventet en WireGuard-nøkkel (44 tegn base64)",
        "Invalid {field}: expected a WireGuard key (44 characters of base64)",
    ),
    "err_field_endpoint_v6": (
        "Ugyldig {field}: forventet [IPv6]:port",
        "Invalid {field}: expected [IPv6]:port",
    ),
    "err_field_brackets": (
        "Ugyldig {field}: klammer brukes bare rundt IPv6",
        "Invalid {field}: brackets are only used around IPv6",
    ),
    "err_field_endpoint": (
        "Ugyldig {field}: forventet vert:port",
        "Invalid {field}: expected host:port",
    ),
    "err_field_nul": (
        "Ugyldig {field}: inneholder NUL",
        "Invalid {field}: contains NUL",
    ),
    "err_field_pem": (
        "Ugyldig {field}: forventet ett eller flere PEM-sertifikater",
        "Invalid {field}: expected one or more PEM certificates",
    ),
    "err_field_pem_base64": (
        "Ugyldig {field}: sertifikatet er ikke gyldig base64",
        "Invalid {field}: the certificate is not valid base64",
    ),
    "err_field_not_list": (
        "{field} må være en liste",
        "{field} must be a list",
    ),
    "err_field_not_object": (
        "{field} må være et objekt",
        "{field} must be an object",
    ),
    "err_unknown_fields": (
        "Ukjente felt i {field}: {names}",
        "Unknown fields in {field}: {names}",
    ),
    "err_wg_no_private_key": (
        "WireGuard-profilen mangler privat nøkkel",
        "The WireGuard profile has no private key",
    ),
    "err_field_not_hex_key": (
        "Ugyldig {field}: forventet en heksadesimal nøkkel",
        "Invalid {field}: expected a hexadecimal key",
    ),
    "err_vpn_config_file_unsupported": (
        "config_file støttes ikke. Lim inn innholdet i config_content.",
        "config_file is not supported. Paste the contents into config_content.",
    ),
    "err_vpn_placeholder_wrong_block": (
        "Plassholderen i <{tag}> hører til en annen blokk",
        "The placeholder in <{tag}> belongs to another block",
    ),
    "err_try_again_shortly": (
        "Prøv igjen om litt",
        "Try again in a moment",
    ),
    "err_setup_in_progress": (
        "Oppsett pågår",
        "Setup is in progress",
    ),
    "err_setup_already_done": (
        "Oppsett er allerede fullført",
        "Setup is already complete",
    ),
    "err_smtp_reenter_password": (
        "Skriv inn SMTP-passordet på nytt når du endrer konto eller server.",
        "Enter the SMTP password again after changing the account or server.",
    ),
    "err_smtp_settings_missing": (
        "SMTP-innstillingene mangler server, bruker eller passord",
        "The SMTP settings are missing the server, user or password",
    ),
    "err_smtp_no_recipient": (
        "Ingen mottakeradresse er angitt",
        "No recipient address is set",
    ),
    # Why sending the report after an audit failed (core.email_sender
    # .auto_send_after_audit). The audit screen words them from the key.
    "err_auto_send_no_recipient": (
        "Automatisk utsending er slått på, men ingen standardmottaker er satt",
        "Automatic sending is on, but no default recipient is set",
    ),
    "err_auto_send_no_smtp": (
        "Automatisk utsending er slått på, men ingen SMTP-server er satt",
        "Automatic sending is on, but no SMTP server is set",
    ),
    "err_auto_send_failed": (
        "Rapporten ble ikke sendt på e-post: {error}",
        "The report was not sent by e-mail: {error}",
    ),
}


def text(key: str, **params: object) -> str:
    """The Norwegian message for *key*, filled in."""
    return MESSAGES[key][0].format(**params)


def invalid(key: str, **params: object) -> ValidationError:
    """A 400 that the error handler translates for the reader."""
    return ValidationError(text(key, **params), message_key=key, params=params)


def conflict(key: str, **params: object) -> ConflictError:
    """A 409 that the error handler translates for the reader."""
    return ConflictError(text(key, **params), message_key=key, params=params)
