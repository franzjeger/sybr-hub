# Oppfølging av revisjonen 8. september 2026

Revisjonsendringene på `fix/review-reliability` er basert på
`6fd9e5f2466e5996439b88898b8c7705870815cd`. Denne rapporten dokumenterer den
første lokale implementerings- og testfasen. Etterfølgende container-/CI-resultater
finnes i PR-en og eventuell release-verifikasjon. Ingen produksjonsutrulling er
utført; den eldre homelab-containeren er ikke endret.

De påviste kodefeilene i XSS, tilgang, sesjoner, backup, migrasjoner og
jobbkjøring er rettet og regresjonstestet. Nye kontroller dekker lokal MFA,
AI-handlinger, arkivering og installasjon av pakket programvare. Dette er
ikke en erklæring om at produksjonsmiljøet eller alle eksterne integrasjoner
nå er godkjent. F10 og F34 krever ekstern oppfølging; F28, F31 og F37 har
uttrykkelig restarbeid nedenfor.

## Status for hvert funn

«Rettet» gjelder den konkrete kodeflyten i revisjonen og de beskrevne
regresjonene. «Forbedret» betyr at vesentlig arbeid er levert, men at hele
arkitekturmålet eller driftskravet ikke er ferdig verifisert.

| ID | Status | Implementering og verifikasjon | Rest / avgrensning |
|---|---|---|---|
| F01 | Rettet | `escJs` beskytter både JavaScript-strenger og HTML-attributter. Dynamiske hendelser i fem JS-filer er gjennomgått; kundenavn i health-tabellen bindes med DOM og event listeners. Chromium tester lagret angrepsverdi mellom to brukere, backslash, sitater og linjeskift. Se [browser-testene](../tests/browser/security.spec.cjs). | Ingen inline-hendelser igjen (oktober 2026). CSP er `script-src-attr 'none'`, og `scripts/check-inline-handlers.cjs` stopper nye. `escJs` er fjernet fordi ingenting trenger den lenger. |
| F02 | Rettet | Ny bruker får avgrenset tilgang som standard. API/UI skiller uttrykkelig mellom alle kunder og valgte kunder; null valgte gir ingen kundetilgang. Flagg og tildelinger oppdateres atomisk. Effektiv admin-tilgang vises særskilt. [RBAC](../app/core/rbac.py), [tilgangstester](../tests/test_shared_customer_pool.py). | Administratorrollen har fortsatt den dokumenterte globale administratortilgangen. |
| F03 | Rettet fremover | Migrasjon 19 utvider ikke lenger tilganger. Migrasjon 14 bevarer eksplisitte avgrensninger. Regresjoner dekker gamle avgrensede brukere og tomt utvalg. | **Hvis gammel migrasjon 19 allerede er kjørt, må driftsansvarlig gjennomgå kontoenes tilganger. Tidligere intensjon kan ikke utledes sikkert og tilbakeføres automatisk.** |
| F04 | Rettet | Logout dekoder sesjonen før tokenet svartelistes og sletter sesjonen. Kopiert access- og refresh-token avvises etterpå. Testet gjennom HTTP og ekte nettlesercookies. | — |
| F05 | Rettet | Felles [skrivetillatelse](../app/core/capabilities.py) brukes også av WebSocket-handlinger. Audit/setup/bulk startes med POST; GET kan bare koble til en kjøring. Tenant-oppsett krever særskilt tenant-skriverettighet. | Gamle klienter som startet jobber via GET må oppdateres. |
| F06 | Rettet | [WebSocket-middleware](../app/web/middleware/websocket_security.py) følger sesjon og tillatelser hele forbindelsens levetid. Endringer via appen varsles straks; DB og utløp kontrolleres også periodisk. Åpne forbindelser stenges med 1008 ved tilbakekalling. [Levende socket-tester](../tests/test_websocket_revocation.py). | Støttet deployment er én worker. Endringer utenfor prosessen fanges ved periodisk kontroll, normalt innen 15 sekunder. |
| F07 | Rettet | [CustomerManager](../app/core/customer.py) har stabil `CustomerId`, eksplisitt create/update, kollisjonsavvisning, tenant-kontroll og låst filendring. Opprettelsesflytene bruker create-only. [Test](../tests/test_retention.py) viser at `A/B` og `A?B` ikke kan overskrive hverandre, og at navneendring bevarer ID. | Gamle ID-er og historikk beholdes. Eldre navnebaserte auditmapper er ikke masseflyttet; gamle navn inngår i retention-gjennomgangen. |
| F08 | Rettet | Backupformat 3 krypterer alle payload-filer, inkludert SQLite, aktivitetslogg og sertifikater, med autentisert AES-GCM. [ZIP-regresjon](../tests/test_backup_restore.py) kontrollerer at DB/logg ikke ligger i klartekst, og at passordrestore virker. | Manifest, filnavn og metadata er synlige. Gamle format-2-arkiver må fortsatt behandles som sensitive klartekstkopier. |
| F09 | Rettet | Nye nøkkelbackuper krever uavhengig wrapping-secret på minst 32 byte. Ingen ny maskin-ID-basert beskyttelse skrives. Nøkkelen caches først etter vellykket lagring; manglende beskyttet lagringssted gir feil. [Krypteringskode](../app/core/encryption.py), eksisterende og utvidede nøkkeltester. | Eldre formater kan leses for migrasjon. Uavhengig secret må konfigureres og sikres før oppgradering. |
| F10 | Ekstern blokkering | [CI](../.github/workflows/ci.yml) har obligatorisk lintbudsjett, dependency-skanning og nye browser-, type-, pakke-, installasjons- og image-kontroller. Actions er fortsatt SHA-pinnet. | GitHub-kontoens billing/spending-blokkering og tilgjengelige merge-regler kan ikke løses i kildekoden. Hosted kjøring og håndheving er **ikke verifisert**. |
| F11 | Rettet lokalt | Migrasjon 20 gir varige, unike operasjonsreservasjoner før eksternt POST. Parallelle forsøk får én vinner; pending/unknown hindrer ny innsending også etter omstart. [Test](../tests/test_revision_security.py), [avstemming](../scripts/reconcile_finding.py). | En timeout beviser ikke at leverandøren avviste handlingen. Ukjent resultat må avstemmes manuelt mot leverandøren før reservasjonen frigis. F34 gjenstår. |
| F12 | Rettet | Hver migrasjon utføres med `BEGIN IMMEDIATE`, SQL-setninger uten `executescript` sin implisitte commit og atomisk versjonsoppdatering. Feil ruller hele migrasjonen tilbake. [Feilinjeksjon](../tests/test_migrations.py) kontrollerer DDL, data og skjema-versjon. | Før oppgradering av faktisk eldre installasjon kreves test på kopi og kald backup. |
| F13 | Rettet ved å fjerne usikker flyt | Live git/pip/reexec-oppdatering er fjernet helt, både endepunktet og koden. [Deployment-prosedyren](DEPLOYMENT.md) beskriver bygg først, kontrollert bytte og sammenhørende datarollback. | Dette erstatter funksjonen med kontrollert utrulling; det innfører ikke en automatisk produksjonsdeploy. |
| F14 | Rettet | Logg- og task-opprettelsesfeil etter at auditlåsen er satt frigir både kjøringens og den globale running-tilstanden. [Regresjon](../tests/test_operational_guards.py) simulerer full loggdisk og viser at også neste start slipper til. | — |
| F15 | Rettet | Auditmapper får sekund, mikrosekund og tilfeldig suffiks med eksklusiv opprettelse. Restore-valideringen aksepterer nye og eldre navn. 20 raske opprettelser gir 20 forskjellige mapper. [Kontrakt](../app/core/audit_results.py). | Dette gjelder de reviderte M365-auditmappene, ikke en full navneendring av alle eksportformater. |
| F16 | Rettet | Credential-varsler bruker en forankret parser for collectorens faktiske sammendrag og antall utløpte credentials. Overskrift eller appnavn med «Expired» kan ikke alene utløse varsel. [Regresjoner](../tests/test_revision_security.py). | Tekstkontrakten er isolert og testet; full overgang til strukturerte collector-resultater gjenstår som arkitekturarbeid. |
| F17 | Rettet, tidligere endring bevart | Bare 2xx regnes som levert webhook; 3xx rapporteres som mislykket levering. [Statuskodetester](../tests/test_webhook_delivery.py). | — |
| F18 | Rettet, tidligere endring bevart | Identifier- og hostvalidering bruker fullmatch. Avsluttende linjeskift avvises av [regresjonstest](../tests/test_validation.py). | — |
| F19 | Rettet | Ikke-blokkerende PTY-I/O venter på fd-readiness ved EAGAIN, håndterer delvise writes og faktisk EOF/EIO. Input og resize er avgrenset; barn termineres og reapes. [Rørtesten](../tests/test_revision_security.py) verifiserer at output etter tom buffer fortsatt mottas. | Full interaktiv terminal-/SSH-aksept i målcontaineren gjenstår. |
| F20 | Rettet | Arch-installer bruker `pacman -Syu` og avviser eksisterende checkout/venv før systemendringer. Hard reset av eksisterende installasjon er fjernet. [Installertester](../tests/test_install_script.py), bash-syntakskontroll. | Selve installasjonen og systemoppgraderingen er ikke kjørt på homelabben. |
| F21 | Rettet | Argon2-kall kjøres i [avgrenset executor](../app/core/password_work.py): to worker-tråder, åtte innslupne operasjoner, 503 ved metning. Avbrutt request frigir ikke kapasiteten til arbeid som fortsatt kjører. [Regresjon](../tests/test_operational_guards.py) kontrollerer event loop, kansellering og metning. | Ingen generell last-/kapasitetstest er utført. |
| F22 | Rettet | API-chat har bruker-/globalgrense for samtaler og samtidige turer, utløp, begrenset input/historikk, seks verktøyrunder og tidsgrenser. SDK-klienten lukkes også ved feil. [AI-tester](../tests/test_ai_limits.py). | Samtaler er prosesslokale og forsvinner ved omstart; multi-worker støttes ikke. |
| F23 | Rettet for påvist manifestfeil | [Backup-tjenesten](../app/services/backups.py) beregner hash av nøyaktig kryptert strøm skrevet til arkivet, bruker samme fangede nøkkel til payload, wrapping og MAC, og publiserer atomisk med unikt navn. Manipulasjon, feil nøkkel og filnavnbinding testes. | Et online-arkiv er ikke ett globalt transaksjonelt øyeblikksbilde av DB, keyring og alle filskrivere. Bruk kald backup ved versjonsbytte og nøkkelendring. |
| F24 | Rettet | DOMPurify er oppdatert til låst 3.4.15. Seks vendorede pakker har versjon/hash-manifest, kontroll mot npm-låsen og OSV-skanning i CI. Lokal npm audit og OSV fant ingen kjente advisories for de undersøkte versjonene. | Ingen kjent advisory er ikke bevis på fravær av sårbarheter. Fremtidige advisories krever nye skanninger. |
| F25 | Implementert mekanisme, policy må bestemmes | UI/API kaller handlingen arkivering og beskriver beholdte data. Registreringen flyttes kryptert, aktive tenant-secrets fjernes og ID reserveres. [Offline purge](../scripts/purge_customer.py) har dry-run, eksplisitt bekreftelse, scoped DB-sletting og rollback før commit. [Tester](../tests/test_retention.py) bevarer nabokunde og gjenoppretter filer ved FK-feil. | Organisasjonens retention-frister er ikke valgt. Backups, delte logger, eksport, gamle navn, delte nøkler og leverandørdata må behandles særskilt etter [prosedyren](RETENTION.md). |
| F26 | Rettet kontrollflyt, databruk krever bevisst valg | AI krever uttrykkelig bekreftelse av ekstern behandling. Kundetilgang sjekkes før kontekstbygging; secret-felter filtreres og resultater avgrenses. Skriveverktøy krever engangsgodkjenning bundet til faktisk bruker, verktøy og uforanderlige parametere, med ny tilgangskontroll ved utføring. [AI actions](../app/services/ai_actions.py). Gammel CLI-modus med ubegrenset shell og delt tokenfil er deaktivert og fjernet. | Fritekst kan fortsatt inneholde person-/kundedata; filtrering er ikke full DLP. Meldinger og leseresultater sendes til Anthropic. Avtale og tillatt databruk må være avklart. |
| F27 | Rettet i appen | WebSocket tillater samme origin eller eksplisitt oppgitte `SYBR_WS_ALLOWED_ORIGINS`; avviser søsken-/opaque origins. Faktisk socket-handshake er testet. | Ikke-nettleserklient uten Origin må fortsatt ha gyldig token. TLS-proxyens faktiske headers og nettverksgrense må testes ved deployment. |
| F28 | Forbedret, videre refaktorering gjenstår | Jobbtilstand ligger i core, audit- og Uniweb-planlegging samt backup-opprettelse i services, og anbefalingslokalisering i reports. Core/services importerer ikke HTTP-handlere; [AST-kontrollen](../scripts/check_architecture.py) håndhever dette i CI. Gamle scheduler/state-importer er kompatibilitetsaliaser til samme modulobjekt. | Store HTTP-/JS-filer, dynamiske dictionaries og øvrige tekstkontrakter er ikke fullstendig ombygget. Neste trinn er modulvis frontend og strukturerte collector-resultater, med eksisterende regresjoner som vern. |
| F29 | Forbedret | Nye reelle HTTP-, WebSocket-, samtidighets-, feilinjeksjons-, backup- og Chromium-tester dekker de sentrale revisjonsfeilene. Installert wheel testes utenfor checkout med låste runtime-versjoner og native PDF. Mypy strict dekker tre nye domenemoduler. | Ingen påstand om full branch coverage, alle nettlesere, lasttest eller full typesikkerhet i prosjektet. Leverandøraksept er særskilt F34. |
| F30 | Rettet for jobb-bortfall | `/api/ready` sjekker DB og faktiske handles for aktiverte schedulere. Feiltellere kan degradere readiness; `/api/system/health` gir admin siste kjøring, siste suksess og neste kjøring. [Test](../tests/test_operational_guards.py) fanger død/failende aktiv jobb. | Readiness er ikke en transaksjonell test av hver leverandør. Metrics-eksport, tracing og eksterne alarmer må videreutvikles ut fra driftens behov. |
| F31 | Kode og wheel verifisert; image gjenstår | Hashlåste runtime-avhengigheter for Python 3.14, separat dev/TUI, Dockerfile med pinnet base/PowerShell, Compose med begrensede rettigheter, wheel-assetkontroll og installasjonstest er lagt til. [Deployment](DEPLOYMENT.md) krever artefakt/digest og sammenhørende datarollback. | Docker/Podman/Buildah finnes ikke i lokalmiljøet: **containeren er ikke bygget eller kjørt**. Debian-pakker løses ved build; lagre ferdig image for identisk rollback. Hosted Python 3.11–3.13-matrise og faktisk gammel→ny restore er ikke kjørt. |
| F32 | Rettet i berørte instrukser | README, SECURITY, CONTRIBUTING, ARCHITECTURE og UPGRADING er samordnet med at DB lokalt er klartekst, eksportbackup er kryptert, MFA finnes, AI kan sende data eksternt, og live updater er deaktivert. Personlige nettverks-/browserantakelser er fjernet fra design-review-instruksen. | Nye runbooks er normerende for denne endringen; eldre changelog beskriver historiske versjoner. |
| F33 | Rettet | API-chat leser valgt modell fra konfigurasjonen. [Mock-SDK-test](../tests/test_ai_limits.py) kontrollerer modellnavnet i faktisk request og at klienten lukkes. | Ingen betalt AI-request ble sendt. |
| F34 | Ekstern verifikasjon gjenstår | [Akseptanseprosedyre](INTEGRATION_ACCEPTANCE.md) beskriver testtenant, permissions, felter, pagination, samtidighet, timeout, avstemming og syntetiske fixtures. Lokale kontrakt-/feiltester kjører. | Ingen reell ticket eller annen leverandørobjekt ble opprettet. Mangler godkjente testkontoer og dokumentert operatøraksept. Dette kan ikke erstattes av mocks. |
| F35 | Lokal MFA implementert | [TOTP](../app/core/mfa.py) følger RFC 6238, med atomisk replayvern, forsøksgrense, kryptert secret og engangskoder. Enrollment/disable krever passord og OTP. Enrollment-kravet håndheves sentralt også for eldre endepunkter uten brukeravhengighet. Ny sesjon må ha sin egen MFA-bekreftelse; enrollment-race kan ikke gi passord-only tilgang. Fem minutters opptrinn brukes for nøkler, backup, brukerendringer, AI-skriving og terminalstart. HTTP, RFC-vektorer og enrollment/recovery gjennom faktisk Chromium-UI er testet. | Entra/OIDC/SSO er ikke implementert. `SYBR_REQUIRE_MFA=1` håndhever enrollment for teknikere/admin; er på i Compose. Recovery må øves før utrulling. |
| F36 | Rettet | Health-tabellens kundenavn er native knapp med eksplisitt handler. Chromium tester fokus og Enter på faktisk rendret kundedata. Grid tilpasser bredden og tabellen kan rulles vannrett. | Ingen full WCAG-/skjermleserrevisjon av alle skjermer er utført. |
| F37 | Forbedret, restgjeld beholdt | Ruff-funn er redusert fra 903 til 849 uten masseformatering. Rene og nye filer beskyttes nå av per-fil-tak i tillegg til totalbudsjettet. [Regresjon](../tests/test_lint_budget.py) viser at opprydding i gammel fil ikke kan finansiere feil i en ny. | 849 eksisterende funn gjenstår. Helprosjektets formatteringskontroll er fortsatt informativ; det er ikke rapportert et rent globalt Ruff-resultat. |
| F38 | Rettet produktavgrensning | Textual er flyttet til valgfri `.[tui]`, med eksplisitt `sybr-hub-tui`-inngang og forståelig melding hvis ekstraet mangler. Ubrukt, ufullført seksjonskatalog er fjernet. Pakking/entrypoint er testet. | TUI er eksperimentell og ikke ende-til-ende-testet som støttet produksjonsgrensesnitt. |
| F39 | Rettet | Security report viser unknown/stale med kilde og tid, skiller historisk MFA fra aktuell vurdering og lar manglende målinger gi ukjent score. Alle relevante domener må ha observerte DNS-data før positiv samlet indikasjon. Ukjente scorer utelates fra snittet. [Regresjon](../tests/test_revision_security.py). | Ferskhetsgrenser er 30 dager for audit og 7 for DNS. Det er ikke en sanntidssikkerhetsattest. |
| F40 | Rettet falsk godkjenning | Firmware kan parses som metadata, men alle versjoner vises som ukjent sikkerhetsstatus uten vedlikeholdt, modellspesifikt leverandørgrunnlag. Tester dekker ugyldig streng og flere 7.x/8.x-varianter. | En Fortinet-policy/feed må etableres før en versjon kan få positiv sikkerhets-/støttevurdering. Ingen slik vendor-feed er funnet opp. |

## Viktige endringer før drift

- Opprett og ta vare på et uavhengig wrapping-secret og en separat recovery-kopi
  av master key. Eksisterende nøkkel og data må bevares sammen. Ikke generer en
  erstatningsnøkkel over eksisterende krypterte data.
- Migrasjonene går nå til 21. Gammel migrasjon 19 kan allerede ha endret
  tilganger; gjennomgå dem eksplisitt. Test oppgraderingen på en frakoblet kopi
  av den faktisk kjørende installasjonen først.
- Nye brukere er avgrenset til eksplisitte kunder. API-klienter må bruke
  `mode=all/scoped` for kundetilgang og POST for jobbstart.
- Aktiver og øv lokal MFA/recovery. Privilegerte handlinger kan svare
  `step_up_required`; bruk avatarens MFA-bekreftelse før nytt forsøk.
- Gammel live updater og AI CLI-modus er deaktivert. API-basert AI krever
  databehandlingsbekreftelse og separat godkjenning av hver skrivehandling.
- Kundearkivering er ikke full sletting. Velg retention-policy og følg
  [RETENTION](RETENTION.md). Uavklarte eksterne writes må avstemmes etter
  [INTEGRATION_ACCEPTANCE](INTEGRATION_ACCEPTANCE.md).
- Behold én worker. Sett opp TLS-proxy og verifiser origin/cookies i faktisk
  miljø. Containerens interne HTTP-port må ikke eksponeres direkte.

## Verifikasjon som faktisk er kjørt

Sluttkontroller i Python 3.14 på Linux. Pakken er installert i en separat venv
utenfor checkout; samtlige runtime-versjoner der ble sammenlignet med
pytest-miljøet og var identiske. Ingen operatør-keyring eller kundedata brukes
av de nye fixture-/installasjonstestene.

| Kommando / kontroll | Faktisk resultat |
|---|---|
| `.venv/bin/pytest -q --tb=short --timeout=90 --session-timeout=600` | **2 730 passed**, 4 warnings, 130,80 sekunder. |
| `.venv/bin/pytest -q tests/test_lint_budget.py --tb=short` etter siste lint-forbedring | **11 passed**; inkluderer én ny test etter fullkjøringen. |
| `npm run check` | JavaScript-syntaks godkjent. |
| `npm run vendor` | Vendorede filhashes og låst DOMPurify samsvarer. |
| `SYBR_TEST_CHROMIUM=/usr/bin/chromium npm test` | **4 passed**, 3,6 sekunder: lagret XSS, escaping gjennom HTML-parser, logout og MFA-enrollment/recovery mot isolert faktisk app. |
| `.venv/bin/python scripts/lint_budget.py` | Godkjent: 849 funn innen per-fil- og totalbudsjett. Nye Python-filer er lint-rene. |
| `mypy` fra separat verktøy-venv | Ingen feil i de tre angitte domenemodulene. Ikke helprosjekt-typekontroll. |
| `.venv/bin/python scripts/check_architecture.py` | Ingen `app.web`-importer i core/services. |
| `python -m build --wheel --outdir /tmp/sybr-wheel-final` fra verktøy-venv | Wheel bygget. |
| `python scripts/check_wheel.py /tmp/sybr-wheel-final/*.whl` | Statiske filer, rapportmaler, versjon og entrypoint finnes i wheel. |
| Ren venv: `pip install --require-hashes -r requirements.lock`, deretter `pip install --no-deps WHEEL` | Begge installasjoner fullført. Ingen ødelagte avhengigheter ved `pip check`. |
| Ren venv fra `/tmp`: `python /ABSOLUTT/REPO/scripts/smoke_installed.py` | Installert pakke bestod DB, readiness, opprettelse/innlogging, statiske filer og native WeasyPrint-PDF. |
| `pip-audit -r requirements.lock --require-hashes --disable-pip --strict` | Ingen kjente sårbarheter rapportert for låste Python-avhengigheter. |
| `npm audit --audit-level=moderate` | Ingen kjente sårbarheter rapportert. |
| `python scripts/audit_vendor.py` | Seks vendorede npm-pakker undersøkt mot OSV; ingen kjente advisories. |
| `.venv/bin/pip check` og ren venvs `pip check` | Ingen ødelagte avhengigheter. |
| `git diff --check` | Godkjent etter fjerning av en ekstra blank sluttlinje. |
| `bash -n` for alle repositoryets shell-filer; JSON-parsing av alle JSON-filer | **1 shell-fil og 14 JSON-filer godkjent.** |
| `ruff check` på alle nye Python-filer | **30 filer godkjent.** |
| Målrettet siste UI-/lint-kjøring | **87 passed**: i18n coverage, CSP-budsjett, frontend/API-samsvar, statiske element-ID-er og lintbudsjett. |
| Målrettet siste sikkerhets-/driftskjøring | **26 passed**: ferskhet, MFA, backup-krypto, reservasjoner, PTY, retention, passordarbeid, readiness og loggfeil. |
| `command -v docker podman buildah chromium` | Bare Chromium tilgjengelig. Docker/Compose-build og runtime ble **ikke kjørt**. |

Den siste fullkjøringen inkluderer også lint-, ferskhets- og MFA-regresjonene.
I tillegg ble disse målrettede kontrollene kjørt:

```bash
.venv/bin/pytest -q tests/test_i18n_coverage.py tests/test_frontend_csp_budget.py \
  tests/test_frontend_api_calls.py tests/test_static_element_ids.py \
  tests/test_lint_budget.py --tb=short
.venv/bin/pytest -q tests/test_revision_security.py tests/test_retention.py \
  tests/test_operational_guards.py tests/test_mfa_routes.py --tb=short --timeout=90
```

Fullkjøringen har fire advarsler om de samme API-overgangene som tidligere:
Starlette/httpx-TestClient, AnyIO BlockingPortal-alias og to WeasyPrint URL-fetcher
advarsler. Testene feiler ikke, men API-migrasjonene bør tas ved neste målrettede
biblioteksoppgradering. Ingen påstand om en advarselsfri suite.

Tidlige delkjøringer fant kontrakttester som fortsatt forventet usikre gamle
standardvalg, en MFA-test som ikke sendte Secure-cookies over TestClient-HTTP,
en browser-test blokkert av onboarding-overlay, og en MFA-browser-selector som
valgte den skjulte generelle avbrytknappen fremfor modalens synlige lukkeknapp. Kontraktene og de isolerte
fixture-oppsettene ble rettet og testene kjørt igjen. Sluttresultatene ovenfor
er fra faktisk utføring; tidligere feilede forsøk regnes ikke som bestått.

## Anbefalt videre rekkefølge

1. Gjennomgå denne lokale diffen. Avklar retention, MFA-recovery og AI-databruk.
2. Gjenopprett GitHub Actions-tilgjengelighet, håndhev nødvendige checks og kjør
   alle jobber på den eksakte endringscommitten, inkludert containerbuild.
3. Bygg og lagre et immutable image; test oppstart, HTTP/TLS, terminal og restore
   med syntetiske data i målmiljøet. Test også kopi av eldre faktisk databaseskjema.
4. Kjør leverandøraksept mot utpekte testkontoer. Dokumenter avstemming av
   usikre ticket-resultater og slett syntetiske testobjekter.
5. Ta kald backup, gjennomgå eksisterende tilgangstildelinger og gjennomfør
   kontrollert cutover etter [DEPLOYMENT](DEPLOYMENT.md).
6. Fortsett modulvis frontend-/datakontrakt-refaktorering, typesikkerhet og
   nedbetaling av lintgjeld. Legg til observability og lasttester mot konkrete
   driftsmål før eventuell flerprosess-/flerinstansarkitektur.
