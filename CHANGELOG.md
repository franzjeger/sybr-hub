# Endringslogg

Sybr HUB versjoneres etter semver fra og med `v1.0.0` (august 2026). Historikken
til den importerte MSP-Toolkit-auditmotoren (`v0.1.0` til `v10.11.0`, mars til
juli 2026) ligger i [docs/HISTORY.md](docs/HISTORY.md).

## Ikke utgitt

Ingenting ennå.

## v1.2.0 (2026-10-03)

Hovedflyten virker i grensesnittet: kunden åpnes med funnene først, og et
funn blir en sak eller et planpunkt derfra. Deler som ikke hører til kjernen
er moduler du slår av og på. Sikkerhetsgrensene er strammet inn, ingen
JavaScript kjører fra markup, og norsk tekst er skrevet om. Les
[docs/UPGRADING.md](docs/UPGRADING.md) før oppgraderingen: noen innstillinger
bør sjekkes etterpå.

### Ett språk, én ordliste

- Norsk tekst i grensesnittet, i rapportene og i e-posten har ingen
  tankestreker. Setningene er skrevet om, ikke bare tegnet byttet.
- Scoren fra 0 til 100, der 100 er best, heter Sikkerhetsscore og bokstaven
  Karakter. «Risikoscore» fikk en sterk tenant til å se risikabel ut.
- Varsler betyr varsler, Varslinger er varselklokka, Advarsler er advarsler.
  Remediering heter Utbedring, Fjernaksess heter Fjerntilgang, Azure AD heter
  Entra ID.
- En merknad i rapporten sa at manglende nettverksfunn gjorde scoren «for
  lav». Nettverksfunn trekker bare fra, så den kan være for høy. Teksten sier
  det nå.
- Feilmeldinger kommer på språket du har valgt, fra hele API-et: rundt 260
  meldinger som var skrevet fast på norsk, og rundt 70 som var skrevet fast
  på engelsk, er oversatt. Det gjelder også svar som melder fra om noe uten
  å være en feil, som en tilkoblingstest som ikke fikk kontakt eller en
  import som hoppet over en konto.
- Opplasting og synkronisering til IT Glue svarte «IT Glue upload failed»
  når det var vi som avviste forespørselen, for eksempel fordi kunden ikke
  hadde auditdata. Nå får du vite hva som mangler.
- Mangler du tilgang til en kunde på dashbordet, får du beskjed om det i
  stedet for å bli logget ut.

### Innstillinger som ikke sletter hverandre

- Å lagre ett integrasjonskort nullstilte innstillinger andre kort eier:
  audit-mappen, sertifikatmappen, SMTP-oppsettet og automatisk e-post.
  Nå endres bare feltene kortet faktisk sender.
- Å lagre webhook-kortet slo av planlagte auditer. Det gjør det ikke lenger.
- Fanen «Terskler» er fjernet. Verdiene der ble aldri lagret eller brukt.
- Planleggeren kan lagres fra Innstillinger igjen. Hver lagring derfra ble
  avvist.
- Bytter du raskt mellom to kunder, åpnes den siste, og den blir aktiv.
  Notatet fra den første kunne tidligere havne på den andres side og bli
  lagret der.

### Strengere grensesnitt

- Ingen inline JavaScript i grensesnittet. CSP-en kjører ingen
  hendelseshandlere fra markup, så injisert HTML kan ikke starte skript.
- Alle API-kall tar imot en definert modell. Feil type, ukjente felt og
  ødelagt JSON gir en tydelig feilmelding i stedet for en serverfeil, og
  passord ekkoes aldri tilbake i feilsvaret.
- Tilkoblingstestene for IT Glue, Autotask og myITprocess krever administrator.
- En sti utenfor tillatt mappe gir en feilmelding i stedet for å logge deg ut.
- Ti feil funnet av den nye lint-kontrollen er rettet, blant dem at «Kopier
  tabell» alltid meldte feil, at notat på en fornyelse merket den som
  håndtert, og at importerte GDAP-kunder først dukket opp etter oppdatering.

### Provisjonering forteller hva enheten faktisk gjorde

- En utrulling rapporterer hvert steg som utført, hoppet over, feilet med
  grunn eller ikke kjørt. Før svarte den «ok» uansett utfall.
- REST-utrullingen stopper ved første steg som feiler. LAN-adressen endres
  derfor bare på en enhet som tok imot alt før den, og kundens adresse
  oppdateres bare når endringen er bekreftet, på kunden økten gjelder.
- En regel som finnes fra før gjenkjennes på FortiOS-feilkoden, ikke på at
  svaret var 500. Andre feil oppdaterer ikke lenger noe i blinde.
- SSH-utrullingen sender hver `config`-blokk som én kommando og leser svaret
  for feil. Denne veien er ikke prøvd mot en fysisk FortiGate ennå.

### Rapporter

- NIST-kolonnen bruker ID-ene i CSF 2.0. Den viste ID-er fra CSF 1.1, blant
  dem to som ikke finnes i 2.0.
- Kontroll 4.1 (postboksrevisjon) står alltid i rapporten. Den forsvant når
  Exchange-oppsettet ikke var samlet inn.
- Tilgangsgjennomganger uten Entra ID P2 merkes «Ikke lisensiert», som PIM.
- CIS-kartet er skrevet om fra én funksjon på 1 787 linjer til en tabell med
  35 kontroller. Utdataene er de samme, kontrollert mot 8 210 lagrede tilfeller.

### Drift og ytelse

- En ny versjon laster ikke lenger alle åpne faner på nytt. Terminal- og
  RDP-økter overlever en oppdatering; bare fanen der du godtar den lastes på nytt.
- PDF for fornyelser og pentest lages ved siden av serveren. Én PDF holdt
  tidligere igjen alle andre forespørsler mens den ble laget.
- Dashboard, varsler og lisensvisning henter siste audit per kunde med én
  spørring i stedet for å lese hele tabellen.
- Dashboardet passer på en mobilskjerm, og søkefelt bruker vanlig skrift.
- Nettleseren spør om varsler når du starter en audit, ikke når siden lastes.
- En ubrukt ikonfont (600 kB) og en RMM-stubb uten innhold er fjernet. README
  lover ikke lenger RMM-data.

### Moduler du kan slå av og på

Fjerntilgang, Tailscale, pentest, provisjonering, lisenser og hosting (ALSO og
Uniweb) og Sybrt AI er moduler. En administrator slår dem av eller på under
Innstillinger og Moduler. En avslått modul er borte for alle: menyer og kort
skjules, rutene svarer 404, og jobbene i planleggeren kjører ikke. Kjernen er
alltid på: kunder, audit, funn, rapporter, nettverksaudit og VPN.

Første oppstart etter oppgraderingen slår på modulene installasjonen bruker
(lagrede verter, en konfigurert nøkkel, skannehistorikk), og provisjonering
på installasjoner som allerede har brukere. En ny installasjon starter med alle av.

### Kundesiden svarer på hva som er galt, og hva som skal gjøres

- Kundesiden viser funnene fra siste audit først, sortert etter alvorlighet,
  med status og notat per funn. Tidligere viste den bare funn som allerede
  hadde fått status, så en nyauditert kunde så ut til å ikke ha noen.
- «Opprett sak» og «Til planlegging» vises bare når Autotask eller
  myITprocess er satt opp og kunden er koblet. Er en integrasjon satt opp
  men ikke koblet, sier én linje over listen det, med en knapp.
- Kunden kobles til Autotask, myITprocess og IT Glue fra kundesiden. Valget
  foreslår konto etter navn. Før fantes det ingen måte å koble i grensesnittet.
- «Kjør audit» på kundesiden starter auditen. Mangler kunden M365-tilgang,
  er knappen deaktivert, og siden tilbyr oppsett i stedet.
- Toppfeltet viser den aktive kunden. Det viste alltid «Velg kunde».
- Adressen følger visningen (`#/customer/<id>`), så Tilbake, oppdatering og
  delte lenker havner riktig. Innlogging lander på Dashboard.
- Dashboardet regner kunder som aldri er auditert eller har en audit eldre
  enn 30 dager som «trenger oppfølging», og viser ikke grønt når noe mangler.
- Velkomstturen vises én gang per bruker etter innlogging, ikke over
  innloggingen.
- Integrasjonssiden starter med M365, Autotask, myITprocess og IT Glue.
  «Kommer snart»-kortene, «Oppdater nå» og «Åpne mappe» er fjernet.
- En ny versjon når nettleseren ved neste innlasting. Filene får
  innholdshash i adressen i stedet for nummer som måtte økes for hånd.

### Sikkerhetsgrenser

En kritisk og flere alvorlige svakheter er rettet. Se `docs/UPGRADING.md` for
endringer som påvirker drift.

- WireGuard-profiler valideres felt for felt før de når `wg-quick`. Et
  linjeskift i et felt kunne tidligere legge til en kommando som kjørte på serveren.
- Data fra enheter, integrasjoner og andre teknikere vises som tekst i alle
  infrastrukturvisninger. Navn på enheter, hoster og nøkler kunne tidligere
  kjøre skript i teknikerens økt. En ny sjekk i `npm run check` stopper uescapet HTML.
- Lagrede passord, tokens og nøkler følger ikke lenger med når en enhet får ny
  adresse. De slettes og må legges inn på nytt.
- VPN-hemmeligheter ligger bare i det krypterte hemmelighetslageret og sendes
  aldri til lesere. OpenVPN-profiler som leser eller skriver filer på serveren avvises.
- Kunder med begrenset tilgang ser bare egne data i kostnader, domener,
  Uniweb, Autotask, IT Glue, aktivitetslogg og varselhistorikk.
- Lesere når ikke lenger VPN, fjerntilgang, Tailscale, pentest, TLS eller
  AI-konsollen via direkte lenke.
- AI-konsollen kan bare åpne tunneler og liste nøkler og hoster for kunder
  brukeren har tilgang til.
- SSH-nøkler hører til en kunde. Eksisterende nøkler kan bare brukes av
  administratorer og brukere med tilgang til alle kunder.
- En kunde kan ikke kobles til en Autotask-, IT Glue- eller myITprocess-konto
  som allerede er koblet til en annen kunde.
- Passordbytte logger ut andre økter, og refresh-tokens roteres ved hver bruk.
- Den fjernstyrte nettleseren starter med tom profil og kjører i en sandkasse
  når bubblewrap er installert. Guacamole-proxyen slipper bare gjennom statiske filer.
- Varselet «Mistet kontakt med server» vises ikke lenger ved hver innlasting.
- Testsuiten skriver ikke lenger til den ekte datakatalogen.

### Planlagte jobber kjører igjen

Planleggeren var flyttet ut i en egen prosess som verken containeren eller
installasjonsskriptet startet. Varsler, opprydding, sertifikatsjekk og
backup kjørte dermed aldri, og `/api/ready` svarte 503 i en standard
container. Web-prosessen kjører nå jobbene selv. En fillås i datakatalogen
bestemmer hvem som eier planen, så jobber aldri kjører dobbelt, heller ikke
når den valgfrie reserveprosessen (`sybr-hub-scheduler.service`) også kjører.
Reserven tar over bare mens web-tjenesten er nede.

Den planlagte auditen regner neste kjøring fra et lagret tidspunkt. Tidligere
skjøv hver omstart en ukentlig audit en ny uke frem. Endringer i innstillingene
virker innen et minutt, uten omstart. `/api/ready` viser hvilken prosess som eier
planen og om den lever.

### Drift

- Installasjonsskriptet installerer fra `requirements.lock` med hasher, det
  samme settet CI kontrollerer, og bare testkjøreren i tillegg.
- Kodekatalogen er skrivebeskyttet for tjenesten, og systemd-enhetene dropper
  alle capabilities. En kompromittert prosess kan ikke lenger skrive om sin egen kode.
- `SYBR_HUB_LOG_LEVEL` styrer også uvicorn sin logg.
- Byggekonteksten for Docker tar ikke lenger med lokale hemmeligheter og kladd.
- Ubrukte avhengigheter er fjernet (Alembic, nh3, six og to Azure-pakker), og
  databaseskjemaet har én kilde: migreringene i `app/core/database.py`.

## v1.1.9 (2026-09-21)

ALSO SimpleAPI sin avvisning av kontoer med MFA vises nå som en konkret
innloggingsfeil, med veiledning på valgt språk. Den ble tidligere vist som en
midlertidig serverfeil med beskjed om å prøve senere.

### Integrasjonsfeil, Uniweb-partnersesjon og visning

Avviste Tailscale-nøkler og utløpte UniFi-sesjoner logger ikke lenger brukeren
ut av Sybr HUB. Nettleseren kontrollerer egen sesjon før utlogging og deler
tokenfornyelsen mellom samtidige forespørsler. Tilkoblingstester bruker den lagrede
hemmeligheten når feltet inneholder maskeringsprikker. Feil-ID vises, og leverandørfeil
eller mislykkede skrivinger utløser ikke automatiske gjentakelser i nettleseren.
Manuell gjentakelse virker også etter at feilvarselet lukkes. WebSocket-opprydding
fullføres ved avbrudd, med tidsgrense for fastlåste forbindelser.

Uniweb velger partnerkontoen etter innlogging, bruker en isolert nettleserprofil
og begrenser gjentatte innloggingsforsøk. ALSO viser en avvist API-legitimasjon
som innloggingsfeil selv når leverandøren returnerer en XML-feil med HTTP 500.

Integrasjonsskjemaer åpnes i full bredde og kan lukkes igjen. Uniweb-fremdriften
bruker CSS som fungerer med sikkerhetspolicyen, og DNS-feil avslutter lastingen.
Hosting-visningen leser leverandørens aktuelle feltnavn. Norsk/engelsk tekst i
disse visningene, felles feilmeldinger og flere manglende norske bokstaver er rettet.

### Logoer følger med installerte pakker og containere

Logoene på innlogging, i toppmenyen og i bunnteksten lå utenfor Python-pakken og
manglet i containeren. Branding-filene pakkes nå sammen med frontend-ressursene;
de eksisterende `/branding/`-adressene beholdes. Pakkekontroll, installasjonstest
og nettlesertest kontrollerer at logoene finnes og kan lastes.

### Graph-paginering: en avkortet liste rendres ikke lenger som komplett

`get_all` stoppet på et sidetak (500 sider) og returnerte den delvise lista med
bare en `log.warning`. `signins`-seksjonen henter innloggingene siste 30 dager
med `$top=999`, så en travel 500+ brukers tenant overskrider taket — og siden
Graph gir innlogginger nyeste-først, er de tapte sidene de *eldste*. Per-bruker-
tellingen av mislykkede innlogginger regnes da fra et utsnitt, og en reell
password-spray kan falle under `>50`-terskelen og rendres som «ingen terskel
overskredet». `get_all` kaster nå `GraphIncompleteError` når det stopper på taket
med flere sider igjen (ikke når samlingen tilfeldigvis slutter på siste side), og
`signins` registrerer seksjonen som en ufullstendig lesning i stedet for å skrive
undertellingen som et faktum. `max_pages` er nå en parameter (testbarhet).

### TLS-skann: resultater holdt på linje med endepunktene etter en vertsløs rad

`scan_customer_endpoints` hoppet over rader uten `host`, så resultatlista ble
kortere enn endepunktlista — men etikettene ble lest med `endpoints[idx]` mot den
lengre lista. Én tom vert forskjøv dermed hvert påfølgende resultat til feil
endepunkt: en vellykket skann fikk et annet endepunkts etikett, og en
gather-feil rapporterte feil vert/port. Resultatene zippes nå mot den filtrerte
lista, og feilresultatet bærer også etiketten sin.

### Uniweb: en uleselig partner-modal dropper ikke lenger de ekte kundene

`_get_partner_sub_customers` returnerte `[partner]` ved feil — som lagret
forhandler-kontoen som om den var en kunde, droppet de ekte underkundene, og
rapporterte suksess med et plausibelt antall (vanskeligere å oppdage enn en tom
liste). Den kaster nå `UniwebScrapeError`, og `list_accounts` fanger det
per-partner: den partnerens undertre hoppes over (de forrige radene beholdes av
lagringslaget) og gapet telles i `last_partner_read_failures` — én dårlig modal
avbryter ikke lenger hele lista.

### Uniweb-synk er single-flight også fra den planlagte stien

Den planlagte 02:00-synken (`scheduler._do_uniweb_sync`) kalte `_run_sync` direkte
uten å sjekke `_sync_status['running']`, som HTTP-ruta gjør — så en manuell synk
som kjørte da klokka slo startet en *andre* samtidig skraping, med en andre
headless Chromium og kappløp på `uniweb_accounts`. Vakten ligger nå i `_run_sync`
selv, så ingen av inngangene kan omgå den.

### CIS 8.1.1: Teams ekstern tilgang graderes nå på de faktiske B2B-verdiene

Verdikten leste hele `16c_teams_external_access.txt` i småbokstaver og ga PASS så
snart ordet «blocked» dukket opp *hvor som helst*. Fila har to uavhengige
innstillinger — B2B Collaboration og B2B Direct Connect — og Microsofts standard
er Direct Connect = blocked mens Collaboration = allowed. Så «blocked» finnes i
nesten hver tenants fil, og en tenant med innkommende B2B-samarbeid vidåpent fikk
PASS bare fordi Direct Connect sto på sin standard-blokk. Nå graderes det på de
allerede parsede verdiene: begge begrenset → pass, Direct Connect innkommende
åpen → fail (den alvorlige — den gir delt-kanal-tillit), Collaboration åpen med
Direct Connect begrenset → warn. Eldre federation-format uten parsede B2B-verdier
faller tilbake på det gamle tekstsøket.

### Risiko-radar: «Enheter»-aksen leser nå samme verdikt som CIS 6.1.1

Enheter-aksen var rå `compliance_pct`, kun betinget av `has_data` og `total>0`.
Men Intune markerer en uadministrert enhet «compliant» som standard, så en tenant
med enheter enrollert og *null* compliance-policyer fikk ~100 grønt på aksen mens
CIS 6.1.1 — som sjekker at policyer i det hele tatt finnes — FEILET samme tenant i
samme rapport. Aksen leses nå av compliance-kartet på nøyaktig samme måte som
E-post-aksen: pass = full, partial = halv, fail = null, «info» ekskludert. Ingen
vurderbar enhetskontroll → ingen akse. Radaren og tabellen kan ikke lenger vise
motstridende ting.

### `/api/logs` og `/api/logs/clear` er nå admin-only

`_BufferHandler` ligger på root-loggeren på DEBUG, så bufferen fanger uredigert
DEBUG fra alle subsystemer og kunder — navn, hostnavn/IP, integrasjonsdiagnostikk
på tvers av kunder. Begge rutene var kun `get_current_user` (viewer), så enhver
innlogget bruker kunne lese hele bufferen, og `/clear` lot dem tømme
diagnostikk-sporet (anti-forensikk). Begge er nå `require_role(admin)`, som
`/ssh/audit-log` og `/system/*`.

### FortiGate: `verify_ssl`-standard er nå lik i begge poll-stiene

`poll_all_fortigates` (flåtevisning) brukte standard `True` mens dashboard-polleren
brukte `False`. FortiGate-er presenterer nesten alltid et selvsignert sertifikat,
så `verify=True` feiler TLS-håndtrykket — en kunde uten nøkkelen satt viste samme
brannmur online i én visning og «error» i en annen, med falske offline-alarmer.
Begge går nå gjennom `_build_client` med samme `False`-standard.

### Uniweb-DNS: en sone er nå tilgangsstyrt til kunden som eier domenet

`GET /uniweb/dns/{domain}` var autentisert (viewer) men ikke autorisert: domenet
kom rett fra stien og hele sonen kom tilbake. Uniwebs clustered-zone-API svarer
for MSP-ens egne kunder, og et domene er offentlig og gjettbart — så en tekniker
med tilgang bare til kunde A kunne lese kunde Bs fulle sone (interne vertsnavn,
e-postruting, SPF/DKIM/tjenesteoppføringer) ved å oppgi Bs domene. Det slapp
forbi tilgangsdekningstesten fordi den bare introspiserer ruter skrevet med
`{customer_id}`/`{host_id}`, og denne er `{domain}`. Ruten slår nå domenet opp
mot eierkunden (via den synkroniserte `uniweb_accounts`-cachen) og serverer sonen
kun hvis en begrenset innlogget bruker har tilgang til den kunden — ellers samme
tomme sone som et domene Uniweb ikke er DNS for, så svaret kan verken lese en
annen kundes oppføringer eller brukes til å kartlegge hvilke domener som finnes.
Admin og all-customers er uendret.

### Rapport-tester rendrer nå med produksjonens autoescape (fester #166-fiksen)

XSS-fiksen i #166 satte `_jinja_env` til `autoescape=True` nettopp fordi malene
heter `*.html.j2`, og `select_autoescape(["html"])` matcher på `.html`-suffikset
— så `.j2` falt gjennom til False og hver `{{ verdi }}` ble rendret uescaped
(lagret XSS på tenant-visningsnavn, UPN-er, enhetsnavn). Men render-testene bygde
sitt *eget* miljø med akkurat den sårbare `select_autoescape`-konfigurasjonen, så
hele render-suiten kjørte med escaping AV — motsatt av produksjon — og å
reversere fiksen ville latt alle testene stå grønne. Testene renderer nå gjennom
produksjonens `_jinja_env()` (med `StrictUndefined` lagt på, så en omdøpt
context-nøkkel fortsatt feiler), og en ny regresjonstest injiserer et fiendtlig
tenant-navn og krever at det rendres escaped (`&lt;script&gt;`), ikke som en
levende tag.

### Uniweb-synk: én uleselig konto forkastet ikke lenger hele kjøringen

En konto scraperen ikke fikk åpnet markeres bevisst som `unavailable` *uten*
`data`-nøkkel — så «vi klarte ikke lese denne siden» aldri skrives som «denne
kunden har ingen domener». Men lagringssløyfa gjorde `dict(account["data"])`
for hver konto ubetinget, så den første utilgjengelige kontoen kastet
`KeyError('data')` inne i `get_db()`-blokka *før* commit, rullet tilbake alt som
var køet, og ble slukt av det brede `except`-et som en kryptisk
`last_error = "'data'"`. Resultat: én konto som ikke lot seg åpne i en kjøring
med mange kontoer kastet *alle* kontoene som faktisk var lest, og `last_sync`
sto stille. Den planlagte 02:00-synken traff det samme. Lagringen er nå skilt ut
i `_persist_sync_results`: en konto uten friske data hoppes over (den forrige,
gode raden beholdes i stedet for å overskrives med en tom sone), og hver skriving
er isolert, så én rad som ikke lar seg lagre kan ikke avbryte resten.

### ALSO-prisoppdatering roterer nå gjennom hele kundebasen

Den daglige planlagte oppdateringen skannet `linked[:25]` uten noen
ferskhetsfilter, så den re-skannet de samme første 25 kundene hver dag og nådde
aldri kunde 26+. Enhver MSP med mer enn 25 ALSO-koblede kunder fikk permanent
utdatert `contract_end` på halen, og fornyelsesvarsler gikk stille glipp av dem.
Den planlagte stien speiler nå det manuelle endepunktet: kunder som er oppdatert
siste 24 t hoppes over, så påfølgende kjøringer dekker resten av basen i rotasjon.

## v1.1.8 (2026-08-21)
### Uniweb: finn Chromium der den faktisk ligger, ikke bare /snap/bin/chromium

Rotårsaken bak «Innlogging til Uniweb feilet» i ett kundemiljø: scraperen prøvde
`chromium`/`chromium-browser`/`google-chrome` på PATH og falt så tilbake til en
hardkodet `/snap/bin/chromium` — som ikke fantes (`[Errno 2] No such file or
directory`), så oppstarten kastet. `_start_chromium` bruker nå en ordentlig
lokalisering (`_find_chromium`): en eksplisitt overstyring
(`SYBR_CHROMIUM_PATH`/`CHROMIUM_PATH`), så vanlige navn på PATH, så de faste
stedene pakker installerer til (`/usr/bin/chromium`, `/snap/bin/chromium`,
Google Chrome, m.fl.), og til slutt en Playwright-pakket build — den første som
finnes og er kjørbar vinner. Finnes ingen, kaster den med en handlingsrettet
melding som sier hva den prøvde og hvordan fikse det (installer Chromium eller
sett `SYBR_CHROMIUM_PATH`), i stedet for en rå Errno 2.

### Uniweb: en Chromium-oppstartsfeil har også en grunn nå

`login()` hadde én gjenværende sti som feilet uten å si hvorfor: hvis den innebygde
nettleseren (Chromium) ikke startet, returnerte den `False` før `last_login_error`
ble satt, så kortet viste et bart «Innlogging til Uniweb feilet» — som leses som
feil passord, mens den egentlige årsaken er at Chromium mangler eller ikke kan
kjøre i miljøet. Nå settes en tydelig grunn på den stien også, så meldingen aldri
er blank. (Etter #186 var dette den siste stien som kunne gi en grunnløs feil.)

### Uniweb-innlogging: robust utfylling + en faktisk feilårsak

Innloggingen mot Uniwebs kontrollpanel feilet med kjente, korrekte
innloggingsdetaljer og sa bare «Innlogging til Uniweb feilet». Kontrollpanelet
er JSF/PrimeFaces, og skraperen satte `.value` på feltene uten å utløse
`input`/`change`-hendelsene komponentene lytter på — så skjemaet ble sannsynligvis
sendt *tomt*, som ser nøyaktig ut som «feil passord». Utfyllingen bruker nå en
nativ value-setter og utløser hendelsene, faller tilbake på flere selektorer i
tilfelle JSF-id-ene har endret seg, prøver flere måter å sende skjemaet på, og
venter på redirecten i stedet for en fast pause som kappløp med den.

Viktigst: en mislykket innlogging sier nå *hvorfor*. En ren
`_classify_login_outcome` leser landingssiden — Uniwebs egen feilmelding, at
skjemaet kom tilbake, eller at feltene ikke ble funnet — og årsaken vises i
grensesnittet («Innlogging til Uniweb feilet: …») i stedet for et blindt
«feilet». Suksess avgjøres nå av at man har forlatt innloggingssiden og skjemaet
er borte, så en uvanlig landings-URL ikke lenger feiltolkes som en feil.

### Uniweb fase 3a (frontend): e-postsikkerhet i kundekortet

Kryss-revisjonen fra fase 3a vises nå i kundens Uniweb-kort: en seksjon som
lister domenene med SPF/DMARC/DKIM-hull som fargede chip-er, og et «Kan fikses
her»-merke på de domenene der Uniweb er DNS-vert. Den holder seg stille når alt
er rent (ingen hull), gjenbruker `.uwar-*`-tabellen fra AR-visningen (ingen nye
inline-stiler), og en lastefeil gir en dempet merknad. Selve fiksen — knappen
som legger til posten — kommer i fase 3b.

### Uniweb fase 3a: kryss-revisjon av e-postsikkerhet mot Uniweb-hostede domener

M365-auditen graderer allerede SPF/DMARC/DKIM per domene; nå kobles den verdien
til Uniwebs DNS-kontroll. En ny kunde-skopet rute `GET /uniweb/partner/email-dns/{customer_id}`
tar domenene kunden holder hos Uniweb (`dns`-abonnementene), kjører den samme
e-postsikkerhetssjekken (`dns_checker.check_domain`) live per domene, og merker
hvilke hull Uniweb faktisk kan lukke — de domenene der Uniweb er DNS-vert (en
klynget sone svarer med poster). `fixable_here` settes bare når Uniweb hoster
sonen, så grensesnittet aldri tilbyr en fiks det ikke kan utføre. Et hull er en
`fail`/`warn` (aldri `unverifiable` — det betyr «kunne ikke sjekke», ikke
«mangler»). Domenene sjekkes samtidig (veggklokken er det tregeste domenet, ikke
summen) og listen kappes ved 25 med et `truncated`-flagg. Kun lesing; en
autentiseringsfeil kaster i stedet for å lese som «ingen domener hostet», og en
ukonfigurert Uniweb eller ubundet kunde er `matched: false`. Frontend-visning og
selve fiksen (fase 3b — den første skrivingen mot Uniweb) gjenstår.

### Uniweb AR per kunde: utestående fakturaer i kundekortet

Reskontroen finnes nå også der den brukes til daglig: inne i kundens Uniweb-kort
i huben. En ny kunde-skopet rute `GET /uniweb/partner/orders/{customer_id}`
(teknikertilgang via `require_customer_access`, i motsetning til den admin-brede
oversikten) resolver den bundne Uniweb-kontoen, henter `/orders/query` og filtrerer
til nettopp den kundens fakturaer (`orders_for_customer`). Her finnes ingen
tilbakefall til den enkle `/orders`-listen — den bærer ingen kunde å filtrere på —
så et kall som feiler kaster i stedet for å vise et falskt «ingenting skyldes»;
ukonfigurert Uniweb eller en kunde uten bundet konto er en tom reskontro
(`matched: false`), ikke en feil.

Kortet i huben viser AR-seksjonen bare når kunden faktisk skylder noe — en tom
reskontro holder seg stille i stedet for å legge et «ingen utestående»-felt på
hver eneste kunde — og en reell lastefeil gir en dempet merknad, aldri et stille
tomrom som leses som «ingenting skyldes». Seksjonen gjenbruker samme
`.uwar-*`-kropp (KPI-rad, aldersfordeling, fakturatabell) som partneroversikten,
så de to ser identiske ut, uten nye inline-stiler.

### Uniweb AR: pengevisningen i grensesnittet

AR-oversikten har nå et kort i ALSO-/fornyelsesvisningen: en KPI-rad (utestående,
forfalt, antall åpne og forfalte fakturaer), en aldersfordeling (ikke forfalt /
1–30 / 31–60 / 61–90 / 90+ dager) og en tabell over åpne fakturaer sortert med
mest forfalt øverst. Kortet er admin-gated (samme som ruten) og lastes ved siden
av Uniweb-fornyelsene.

For at kortet skal kunne vise *hvilken* kunde som skylder, foretrekker ruten nå
`POST /orders/query` (som bærer kundenavnet) og faller tilbake til den enkle
`GET /orders`-listen hvis spørringen feiler eller kommer tom tilbake — så et
feiltolket tomt filter aldri kan vise et falskt «ingenting skyldes». En
autentiseringsfeil kaster fortsatt i stedet for å falle tilbake til en
beroligende null.

### Uniweb fase 2: fakturaoversikt og forfalte krav (AR)

Partner-API-et bærer noe skraperen aldri så: fakturaene. Klienten kan nå lese
ordrer/fakturaer (`GET /orders`, `POST /orders/query`, `GET /orders/{id}/orderlines`),
og en ny admin-rute `GET /uniweb/partner/orders` gir en AR-oversikt over hele
partneren: utestående totalt, hvor mye som er forfalt, og en aldersfordeling
(ikke forfalt / 1–30 / 31–60 / 61–90 / 90+ dager) — pengevisningen som hører
hjemme ved siden av Autotask-kontrakten og M365-lisenskosten. Utestående regnes
som fakturert minus alt oppgjort (`invoiceSum` − `paid` − `credited` − `lost` −
`waived`), så en delvis kreditert eller ettergitt faktura teller riktig.

To felt på en faktura er hemmeligheter og prosjekteres bort før noe når UI-et:
`shareableRef` (en «betal denne fakturaen»-lenke som åpner fakturaen uten
innlogging) og den interne `invoiceId`-en — `open_invoice()` slipper bare gjennom
`invoiceNo` og beløpene, samme grense som `public_subscription()` trekker for en
`tsig`. Regnestykket og aldersfordelingen er rene funksjoner (`ar_aging`,
`order_outstanding`), enhetstestet uten innlogging. Ukonfigurert Uniweb gir en tom
oversikt (ingen reskontro å vise); et live-kall som feiler kaster — «vi fikk ikke
spurt» skal aldri se ut som «ingenting skyldes». Kun lesing; per-kunde-AR og en
frontend-visning gjenstår.

### Policy-oversikt: én side som svarer på hva kunden har, hva som har endret seg og hva som mangler

Tilbake til grunn: policy-informasjonen lå på fire separate steder —
kundefanget, drift-kjøring, drift-rapport og template-bibliotek — og en tekniker
måtte krysse-reference for å få svar på «hvordan står det til i realiteten».
Nå finnes en dedikert, read-only side under Kunder > Policy-oversikt som
samler alle tre i én sømløs leseflate: policyer i drift (med en kort kommentar pr. policy og handlingsforslag der det er forbedringsrom),
drift siden siste audit (med ærlig «Ikke målt» når sammenligning ikke er
mulig), og avstand til Sybr-standardene (navnematchet, så en kunde-spesifik
policy som standarden ikke kjenner til, ikke lurer lesaren). Kilden er
den samme som fangen, driften og rapporten — ingen ny datahenting, ingen
skrivemulighet, viewer-rett.

### Uniweb: strukturert Partner-API i stedet for skraping (fase 1)

Uniweb-integrasjonen leste kontrollpanelet ved å styre en hodeløs Chrome gjennom
DOM-en — den brøt når panelet «endret markup eller mistet økten» (dens egne
kommentarer). Nå finnes en `UniwebPartnerClient` som snakker det offisielle
Partner-API-et (`https://www.uniweb.no/api/partner`) og returnerer ren JSON for
lesningene aggregatoren trenger: abonnementer (med pris og kost, så margin er
utledbar), kunder, DNS, SSL, produkter, prislister og e-postantall.

Innloggingen gjenbrukes: klienten autentiserer med `session`- og `grant`-
informasjonskapslene fra en kontrollpanel-innlogging (`harvest_cookies()` henter
dem via CDP etter login), og de holdes og fornyes bare når API-et sier økten er
utløpt (401) — ingen ny Chrome-start per forespørsel. To felt bærer
hemmeligheter (`tsig` for domener, privat `key` for SSL); klienten logger aldri
svarkropper, og `public_subscription()` projiserer dem bort før noe når UI-et. Ny
rute `GET /uniweb/partner/subscriptions/{customer_id}` gir strukturerte
abonnementer med månedlig omsetning/kost/margin. Kun lesing i denne fasen; det
gjenstår å migrere de øvrige leserutene av skraperen og legge til fakturaer/AR.

### Uniweb: fornyelsesvarsler og DNS leses nå live, ikke fra skraper-cachen

To leseruter som fortsatt hvilte på den mellomlagrede skrapingen er flyttet til
Partner-API-et, så de ikke lenger avhenger av en fersk sync. `/uniweb/alerts`
utledes nå fra `/subscriptions`: `period.to` er den autoritative fornyelsesdatoen
(ekte datoer, ikke skrapede tekststrenger), og hvert element navngis etter Sybr-
kunden Uniweb-kontoen er koblet til — en tjeneste uten kobling forsvinner ikke,
men merkes med sitt eget navn. `/uniweb/dns/{domain}` henter sonen live og
projiserer hver post til den ene verdikolonnen Hub-en viser (`dns_record_view`),
uansett posttype (A/AAAA/CNAME/MX/SRV/TXT/…); projeksjonen er samtidig grensen
som gjør at en sones DNSSEC-signeringsnøkler aldri kan følge en post ut til UI-et.
Endepunktet dekker klyngedomener — et domene Uniweb ikke er DNS-vert for har
ingen poster å vise, akkurat som skraperens DNS-fane. Uniweb ukonfigurert er ikke
en feil (da finnes ingen fornyelser), men et live-kall som feiler kaster: «vi fikk
ikke spurt» skal aldri se ut som «ingenting utløper».

### Auditen henter nå installerte apper fra Intune-enhetene

Intune-seksjonen leste app-*katalogen* (`mobileApps` — hva Intune er satt til å
distribuere), men aldri hva som faktisk er *installert* på enhetene, så en
En kundeaudit manglet programvareoversikten. Nå leses `deviceManagement/detectedApps`
inn i `13c_intune_detected_apps.txt` (pluss et gjenopprettbart øyeblikksbilde):
den reelle beholdningen på tvers av administrerte enheter, aggregert per app og
versjon med et enhetstall, mest utbredte først (lang liste kappes i den lesbare
filen, hele settet ligger i øyeblikksbildet). Krever bare
`DeviceManagementManagedDevices.Read.All`, som app-registreringen alt har — ingen
ekstra samtykke. Additiv flate: en leietaker der enhetsbeholdningen ikke kan
leses feiler mykt — gapet skrives til sin egen fil, og seksjonen forblir DONE på
grunnlag av de øvrige lesningene.

## v1.1.7 (2026-08-19)
### Vurderingsbibliotek: en ærlig score i stedet for et villedende «100 %»

En kjøring som bare fikk lest ett av ti krav viste et stort grønt «100 %» ved
siden av «9 ikke vurdert» — tallet ropte suksess mens nesten ingenting faktisk
var målt. Nå dempes prosenten (grå, merket «Ikke nok data») så snart under
halvparten av kravene kunne vurderes, og en tydelig advarsel forklarer at
kjøringen mangler grunnlag: «Bare {assessed} av {total} krav kunne måles —
sjekk at siste audit fullførte alle seksjoner, eller kjør den på nytt.»
Resultatet viser også hvilken kjøring det ble målt mot, så et blankt resultat
avsløres som en ufullstendig siste audit — ikke som at kunden er perfekt.

Bakgrunn: vurderingen leser kundens **siste** audit. Er den siste kjøringen
delvis (throttling, en seksjon som feilet), leser hvert krav på den som «ikke
vurdert», mens dashboardets nøkkeltall fortsatt viser de lagrede tallene fra en
tidligere, komplett kjøring — derfor kunne de to være uenige.

## v1.1.6 (2026-08-19)
### Intune-innsamling dekker nå den moderne Endpoint Manager-flaten

Auditen leste bare de to gamle Intune-endepunktene (`deviceCompliancePolicies`
og den eldre `deviceConfigurations`), så en tenant der konfigurasjonen ligger i
Settings Catalog så nesten tom ut — selv med alle tillatelser på plass og en
fersk audit. Innsamleren henter nå også:

- **Settings Catalog** (`deviceManagement/configurationPolicies`) — der moderne
  konfigurasjon faktisk lever.
- **Administrative maler / ADMX** (`deviceManagement/groupPolicyConfigurations`).
- **Appbeskyttelse (MAM)** (`deviceAppManagement/managedAppPolicies`).
- **Endepunktsikkerhet / sikkerhetsgrunnlinjer** (`deviceManagement/intents`).

Hver skrives til sin egen bevisfil og som et gjenopprettbart øyeblikksbilde, og
dukker opp som egne rader under «Policies in production» på kundekortet ved
neste audit. De nye samlerne er additive og feiler mykt: en tenant som ikke
bruker en flate — eller beta-endepunktet som svarer 404 — gjør ikke en ellers
frisk Intune-seksjon rød; gapet noteres i bevisfilen, men seksjonen er fortsatt
`DONE` på styrke av de klassiske lesningene. Alle fire bruker de allerede
gitte `DeviceManagement*`-tillatelsene, så ingen ny samtykke trengs.

Merk: dette fylles på kundens **neste** audit — øyeblikksbildene fanges ved
innsamling og bakfylles ikke for tidligere kjøringer.

## v1.1.5 (2026-08-19)
### «Generate Report» rendret ustylet — kunderapport og batch-rapport fikk feil CSP

«Generate Report» åpnet kundesammendraget som en kolonne med ustylet tekst.
Årsaken var Content-Security-Policy: rapporten legger hele oppsettet sitt i ett
`<style>`-element, og applikasjonens CSP (`style-src-elem 'self'`) fjernet det —
akkurat samme feil som de nedlastede audit-rapportene hadde, ett lag over.
Audit-rapportene serveres av `serve_audit_data`, som allerede setter en egen
«artefakt»-CSP; kundesammendraget og batch-rapporten bygger sin egen HTML og
serveres rett fra `/api`, uten den headeren, så de arvet den strenge app-policyen.

CSP-en for et selvstendig, stylet rapportdokument er nå én delt konstant
(`ARTEFACT_CSP` i `security_headers.py`) som alle tre rutene bruker. Den tillater
inline `<style>`/`<script>` som rapporten trenger for å vises, og sandkasser
samtidig dokumentet — som er bygget av kundedata — inn i et opakt opphav uten
nettverk, så en åpnet rapport ikke røper hvem som leste den eller når.

### Vurderingsbibliotek — navngitte rammeverk, målt per kunde (Fase B)

Baselinemotoren målte til nå kunden mot én husstandard, og bare fra kundekortet.
Nå finnes et browsbart bibliotek av navngitte, scorede rammeverk under Kunder →
Vurderingsbibliotek: velg en kunde, kjør et rammeverk mot siste audit, og les
resultatet krav for krav med begrunnelse og hva som må rettes — navngitte
resultater, ikke check-id-er.

Tre nye rammeverk står ved siden av Sybr Standard, hver bygget **kun** på det
auditen faktisk måler:

- **Essential Eight — modenhetsnivå 1**: MFA, begrensning av administrator-
  rettigheter, styrte og etterlevende enheter, sikkerhetskopi. De fire
  strategiene som er rene endepunktkontroller (applikasjonskontroll, applikasjons-
  og OS-oppdatering, Office-makroer, applikasjonsherding) er utelatt heller enn
  gjettet på.
- **CIS Microsoft 365 Foundations (delmengde)**: MFA, Conditional Access, eldre
  autentisering, antall globale administratorer, Secure Score, ekstern deling og
  enhetsetterlevelse. Ærlig navngitt som en delmengde — kontroller som bare
  finnes som fritekst i innsamlingen dekkes fortsatt av samsvarskartet.
- **NIS2-herding (artikkel 21)**: de målbare tiltakene i artikkel 21(2) —
  herdingsveiledning, ikke en sertifisering; de organisatoriske tiltakene sier
  rammeverket selv at det ikke måler.

Regelen fra baselinemotoren holder: et krav uten innsamlet grunnlag rapporteres
`ikke vurdert`, aldri `ikke bestått`, og etterlevelsen quotes over det som faktisk
ble målt. En ny test (`test_baseline_paths_are_measurable`) kjører hvert rammeverk
mot en fullstendig audit og feiler hvis et krav peker på data auditen ikke
produserer, og en generert referanse (`docs/baseline-context-paths.md`, fra
`scripts/gen_baseline_paths.py`) lister hver målbare sti så nye krav forfattes mot
ekte felt. SharePoint-parseren fikk et `sharing_known`-flagg — samme tri-tilstand
som `legacy_auth_known` — så et rammeverk kan skille «lest, og for åpent» fra «vi
fikk ikke lest innstillingen».

### «Forny tilganger» fornyer nå faktisk — og rydder opp etter seg

Knappen slettet den lagrede legitimasjonen og stoppet der. Bekreftelsesdialogen
sa det til og med rett ut: «du må kjøre oppsett på nytt». Operatøren satt igjen
på en statusside uten legitimasjon og med en manuell jobb til. Nå gjør knappen
hele jobben: den fjerner den gamle legitimasjonen og starter *samme*
device-code-innlogging som førstegangsoppsettet, så du ender med et ferskt
sertifikat og en ny hemmelighet i én handling.

Samtidig ryddet ikke oppsettet opp etter seg i kundens leietaker.
`setup_helper.ps1` gjenbruker riktignok app-registreringen ved navn i stedet for
å lage en ny hver gang, men eldre versjoner gjorde det ikke — så en leietaker
som er auditert mange ganger sitter igjen med en haug identiske, privilegerte
«MSP Toolkit Audit»-bedriftsapper som ingen fjerner. Oppsettet beholder nå den
ene det gjenbruker og sletter dublettene (kun apper med akkurat det navnet, aldri
kundens egne, og aldri den som er i bruk). Å slette applikasjonen fjerner
tilhørende tjenestehovedstol — «Enterprise Application» — med den, og Entra
beholder en gjenopprettbar kopi i ca. 30 dager. Beste forsøk: en sletting den
innloggede administratoren ikke har lov til å gjøre, velter ikke oppsettet.

En ekspertgjennomgang av en generert kunderapport fant flere steder der tallet
eller ordlyden var misvisende. Alle er rettet i koden, ikke i den enkelte
rapporten:

- **E-post-aksen på risikoradaren kjørte sitt eget SPF/DMARC-stigebrett** som
  bare kjente «MISSING» og «WEAK». En DMARC `p=quarantine` (som samleren
  tokeniserer som «WARN») og en manglende DKIM — begge vurdert av CIS
  E-post-kontrollene — trakk ingenting fra, så aksen sto på 100 mens
  samsvarstabellen i samme rapport viste de samme kontrollene som ikke-bestått.
  Det er nettopp den motsetningen en leser mister tillit av. Aksen leser nå
  verdikten CIS-kontrollene alt har satt (bestått = full vekt, delvis = halv,
  ikke-bestått = null, «info»/ikke-verifiserbar utelatt akkurat som i
  samsvarsprosenten), så radaren og tabellen kan aldri være uenige igjen. Samme
  blindsone er tettet i den samlede risikoscoren.
- **«MFA registrert» sto hardkodet til «Nei»** i både kunde- og
  teknikertabellen, selv når brukeren faktisk hadde registrert MFA — cellen
  motsa metode-kolonnen ved siden av. Den leser nå `has_mfa`, og
  begrunnelseskolonnen skiller «registrert, men unntatt fra CA» fra «ingen MFA».
- **Innlogginger med mange feil OG mange suksesser** ble flagget som
  «brute-force» på lik linje med et reelt angrep. En byge av feil vekslet med
  vellykkede innlogginger fra samme konto er en enhet som prøver et utdatert
  bufret passord, ikke et gjettangrep. Slike kontoer rapporteres nå separat med
  lav alvorlighet — ute av det kritiske brute-force-funnet, og ute av «under
  aktivt passordangrep»-MFA-merket som leste den samme listen.
- **Lisensoptimaliseringen så en lisensiert delt postboks/rompostboks som en
  «inaktiv bruker»** å avvikle. En delt postboks logger aldri inn og skal aldri
  telles som en bruker. Delte/rom-postbokser skilles nå ut via
  Exchange-postboksdataene: en reell inaktiv bruker beholder «fjern lisens»-funnet,
  mens en lisensiert delt postboks får sitt eget, riktig rammede funn (en delt
  postboks under 50 GB trenger ingen lisens). Kr/mnd-estimatet blåses ikke lenger
  opp av funksjonspostbokser.
- **Lisens «nær kapasitet» sto som sikkerhetsanbefaling** i en liste over
  sikkerhetsfunn. Det er en kommersiell merknad, ikke en feilkonfigurasjon, og
  vises allerede via lisensmerket og lisensoptimaliseringsseksjonen — nå fjernet
  fra sikkerhetsanbefalingene.
- **CIS 1.1.6 (nødtilgangskonto) skilte ikke** «en adminkonto er unntatt fra CA,
  men er i aktiv bruk og fungerer derfor ikke som nødtilgang» fra «ingen admin er
  unntatt i det hele tatt». Ordlyden skiller nå de to tilfellene.
- **Handlingsplanens plassholderceller** viste en tankestrek som lett leses som
  «manglende data»; de er nå tomme, utfyllbare felter med status «Ikke startet».

### Kundeoppsettet mister ikke lenger legitimasjonen når fanen lukkes

Samme rot som auditen: førstegangs-oppsettet (`/setup/stream`) kjørte hele
PowerShell-flyten — device-code-innlogging og skrivingen av sertifikat +
legitimasjon — *inne i* SSE-strømmen. Restartet du maskinen midt i innloggingen,
ble flyten revet ned før `save_config`/`store_secret` kjørte, og «cachet
legitimasjon ble ikke lagret». Nå eier serveren jobben (`_run_setup_job`): den
kjører ferdig og lagrer uansett om nettleseren er der, og en nettleser som
kobler til igjen re-attacher og får **device-koden spilt av på nytt** så
operatøren kan fullføre innloggingen. `?attach=1` gjør at en gjenåpning bare kan
koble til, aldri starte et nytt oppsett. Samme mønster som audit-fiksen over.

### Auditen overlever at nettleseren mister forbindelsen

Auditen kjørte på verten, men *levetiden* hang på nettleserfanen din. Alt
etterarbeidet — lagre metrikker for dashboard-karakteren, resultatene, e-post,
webhook — lå inne i SSE-strømsløyfen, og `running`-flagget ble nullstilt når
strømmen ble revet ned. Restartet du en ekstern maskin midt i en audit, trodde
serveren den var «ferdig», nettleseren lastet på nytt — og rapporten var aldri
skrevet.

Nå eier serveren jobben. Collector-en kjører som en bakgrunnsoppgave som lagrer
resultatene sine uansett om noen ser på, og `running` nullstilles først når
**jobben** faktisk er ferdig — ikke når en fane lukkes. En nettleser som kobler
til igjen **re-attacher** til den kjørende jobben (`GET /audit/stream` kobler til
en pågående kjøring i stedet for å starte en ny; reconnect legger til `attach=1`
så en gjenåpning aldri kan starte en dublett) og får live-fremdrift tilbake, og
utfallet spilles av på nytt hvis kjøringen alt er ferdig. En tapt forbindelse er
en tapt *visning*, ikke en tapt audit.

Enhetskode-skjermen viste `login.microsoft.com/device` som en ren lenke uten
måte å kopiere den på. En nettleser kan ikke åpne operatørens standardnettleser
i et privat vindu — det er en bevisst sandkasse-grense, ingen webapp kan det —
så når popup-en blokkeres eller operatøren vil bruke en annen nettleser, er
kopier-og-lim inn den pålitelige veien. Lenken har nå en **Kopier**-knapp ved
siden av seg (samme mønster som koden allerede har), og vises som en tydelig
lenke i stedet for grå tekst.

### Appen ber om tillatelsene den faktisk trenger

Defender-seksjonen kaller `security/incidents` og har hele tiden dokumentert at
den krever `SecurityIncident.Read.All` — men tillatelsen sto aldri i den
deklarerte lista (`REQUIRED_GRAPH_PERMISSIONS`). Dermed spurte oppsettet aldri
om den, ingen tenant samtykket, og innhentingen fikk 403 ved hver kjøring mens
seksjonen stille degraderte. Nå er den med i lista (og i de to andre stedene
lista speiles: PowerShell-fallbacken og validatoren), som warn-only — auditen
fullfører fortsatt uten den, kun Defender-hendelser mangler til samtykke er gitt.

- **Eksisterende app-registreringer må re-samtykke én gang.** Trykk **Sjekk
  tillatelser** på kundekortet; den navngir det som mangler, og kjør så
  samtykke-flyten (eller `setup`) på nytt.
- **Ny vakt mot at dette gjentar seg.** En test leser seksjonenes egne
  «requires X.Read.All»-notater og krever at hver navngitt tillatelse står i den
  deklarerte lista — så en kalt-men-udeklarert tillatelse feiler i CI i stedet
  for å dukke opp som en 403 mot en ekte tenant måneder senere.
- PIM-400 og OneDrive-«tomt for budsjett» var *ikke* tillatelseshull:
  `RoleManagement.Read.Directory` er allerede gitt (400 = tenant uten Entra P2),
  og OneDrive-taket er en bevisst skannegrense som rapporterer delvis dekning.

## v1.1.4 (2026-08-15)
### Versjonsmerket følger med på en box som bare hentet grenen

En box som ble oppdatert med den gamle selvoppdatereren (som hentet grenen
uten tagger) samlet inn commits — og dermed den nye endringsloggen — men mottok
aldrig tagg-objektene. `git describe` kan bare navngi en tagg som finnes lokalt,
så versjonsmerket i menyen satt fast på den siste taggen boxen noen gang hadde
(v1.1.1) selv om endringsloggen allerede viste v1.1.3. De to panelene sa
dermed to ulike ting.

- **`app/core/version.py`**: versjonen løses nå opp til det høyeste av git-taggen
  og den nyeste `## vX.Y.Z`-rubrikken i `CHANGELOG.md`. En utdatert lokal tagg
  skjuler ikke lenger en nyere utgave, og en checkout uten noen tagg henter
  fortsatt utgaven den bærer. En nyere lokal tagg vinner fortsatt — taggen er
  kilden når den er nyest.
- **`tests/test_version_consistency.py`**: fire nye tester som låser fast at en
  utdatert tagg ikke skjuler en nyere endringslogg, at en ny tagg vinner, at en
  taggløs checkout faller tilbake på endringsloggen, og at en manglende
  endringslogg ikke knuser versjonsoppløsningen.

## v1.1.3 (2026-08-15)
### Rapportpresisjon: tre tall som ikke lenger løy

Tre feil hvor rapporten viste et tall som ikke svarte på det den hevdet å
måle. Ingen av dem endrer hva som samles inn — de endrer hvordan det som
allerede er samlet inn, teller.

- **MFA-dekningsgrunnlag** (`users_mfa.py`): nedtente kontoer teller ikke
  lenger med i CA-dekningsgrunnlaget. De kan ikke logge seg inn, så de rapporteres
  på egen linje («Deactivated / guest (not in the base)») i stedet for å
  fortynne et ellers fullt deknings-tall. Generatorens fallback-regex leses
  fortsatt av de samme merkelinjene.
- **Break-glass-heuristikken** (`identity_security.py`): en Global Admin som
  er ekskludert fra CA *og* har logget seg inn innenfor 30 dager er en
  hverdagskonto som omgår MFA — en risiko, ikke den nødtilgangsstillingen CIS
  1.1.6 sjekker for. Den telles ikke lenger som break-glass-kandidat. En
  sjelden brukt ekskludert admin — eller en uten innsignaldata (P1/P2) —
  telles fortsatt, nøyaktig som før.
- **Enheter utenfor styring** (`generator.py`): ett tall, overalt. Tallet
  kommer nå fra registerets egen `isManaged`-flagg i stedet for
  `total − intune_total`, som ble en annen målestørrelse — og lot
  anbefalingen (11/16) avvike fra seksjonsstatusen og tellfilen (9/16) for
  samme leie.
- **Selvoppdatering henter tagger** (`self_update.py`): `git fetch` hentet bare
  grenen, ikke tagg-referansene, så en utgave som ble trukket ned viste likevel
  den gamle `git describe`-versjonen. `--tags` er lagt til, så versjonskortet
  og oppdateringsmenyen følger med på en ny utgave.

## v1.1.2 (2026-08-15)
### Sikkerhet, presisjon og at en nektelse er en nektelse

En serie rettinger (#141–#152) som lukker tilgangskontrollhull, stopper
rapporten fra å stille dommer på data den ikke har lest, og låser fast
klientens egen tråd slik at en feil i forespørselen ikke lenger går upåaktet
forbi.

- **Tilgangskontroll** (#142): kryss-kundepunktene `/dashboard/devices`,
  `/reports/batch-summary` og `/unifi/all` er nå begrenset til kallerens
  kunder; `/audit/compare` sjekker tilgang på begge kjøringene (stenger et
  IDOR-hull hvor noen logget inn kunne lese enhver kundes metrikker), og
  `/reports/archive/delete` er sikret. Pentest-modulen blokkerer ikke lenger
  eventløkka og lekket ikke sokker.
- **M365-presisjon** (#141, #143): 18 presisjonsfeil rettet på
  grad-/anbefalings-/sammendragsoverflaten, og en CRITICAL feil hvor en
  Graph 403 ble lest som «ingen MFA registrert» — en nektelse er nå ukjent,
  ikke et nullmål. `GraphClient.get()` kaster `GraphPermissionError` på
  401/403 i stedet for å returnere en feil-ordbok som kallerne leste som
  «ingen data».
- **Bulk-audit-race** (#148): `bulk_audit_stream` klarte flagsene
  atomisk under lås i håndtereren. Tidligere kunne to samtidige forespørsler
  begge passere sjekken før noen satt flagget, og kjøre bulk-auditten to
  ganger.
- **ALSO-lagdeling** (#149): `_cache_renewals` flyttet ut av web-laget til
  `app/services/also_renewals.py` — en service som kalte en rute var en
  lagdeling-inversjon i begge retninger.
- **Versjonskort** (#144): viser nå antall commits foran siste tag, slik at
  en utdatert utgave ikke lenger ser ut som en som er fast.
- **Dokumentasjon** (#145): utdaterte versjoner, seksjonsantall (28 = 24 M365
  + 4 Azure) og CHANGELOG-struktur rettet.
- **Testdekning** (#152): Graph-klientens *forespørsels*-side er nå låst —
  URL, Authorization-header, scope, Accept og at query-parametere bare reiser
  på første side. Tidligere testet kun responsen; en feil i forespørselen
  ville gått upåaktet forbi.

## v1.1.1 (2026-08-15)
### M365-rapporten svarer for dommene sine

En serie rettinger (#133–#140) som gjør at kundens rapport og den
tekniske gjennomgangen ikke lenger konkluderer fra data de ikke har
lest. Rapporten sier «kan ikke verifiseres» i stedet for å stille en
bestått-eller-strøkt-dom på en tom lesing.

- **OneDrive-delingsscan** (#133) går nå hele veien og feiler lukket på
  delvis dekning i stedet for å rapportere det den tilfeldigvis leste.
- **Teams- og PIM-dommer stiller ikke fra manglende data** (F4, F7, #134)
  — en seksjon som ikke kjørte gir «kan ikke verifiseres», ikke et pass.
- **MFA er én dom om håndhevelse, ikke to om registrering** (F1, F2, #135).
  En CA-ekskludert bruker teller som ikke-håndhevet uavhengig av om en
  metode er registrert, og en CA-ekskludert Global Admin eller en konto
  under aktivt angrep heves til et kritisk funn i stedet for å ligge i
  rådata.
- **Dataen som allerede er samlet korreleres** (F8, F3, #136) —
  break-glass-ekskluderinger og Exchange-status vises der de hører
  hjemme, ikke gjemt i rådata.
- **Scoringen reflekterer kritiske funn, uadministrerte enheter og
  MFA-låses-ut-risiko** (F9, F10b, F5, #137) — en kritisk dom setter tak
  på graden, og en tenant ingen har lest får ikke en oppdiktet B.
- **Gjentatte audit-logg-feil** (F12, #138) slås nå opp som et eget funn
  i stedet for å gå tapt i en seksjon som «kjørte».
- **Seks interaksjonsfeil** (#139) og **seks falske verdikter i
  CIS-kartet** (#140) rettet: dommer som sto på feil bevis, og tellere
  som telte feil, er nå bundet til den faktiske lesningen.

## v1.1.0 (2026-08-15)
### Appen kan oppdatere seg selv

En admin kan nå oppdatere installasjonen fra innsiden av appen —
**Innstillinger → Avansert → Oppdater nå** — som henter den kjørende greinen til
`origin` og re-exec-er prosessen på den nye koden. Bakgrunnen er praktisk:
verten står ofte bak et tailnet en nettleser når, men et byggemiljø ikke gjør,
så «ssh inn og `git pull`» er ikke alltid mulig.

- Mekanismen er bevisst liten og innsnevret: den kan bare spole gjeldende grein
  fram til dens `origin`-motpart — ingen ref, remote eller URL kommer fra
  forespørselen — og avviser et skittent arbeidstre eller en løsrevet HEAD i
  stedet for å gjette. Endepunktet er admin-only, `can_write`-vaktet av
  `WriteGuardMiddleware`, og er utilgjengelig fra planlagt kode.
- Omstarten er en `os.execv` på stedet: den kjørende Python-prosessen bytter ut
  sitt eget bilde med en frisk `python main.py` på ny kode. systemd overvåker
  samme PID videre, migrasjoner kjøres ved oppstart, og ingen privilegier trengs
  — prosessen kan ikke `systemctl restart` seg selv under `NoNewPrivileges`, og
  slipper å gjøre det.
- Fordi verten er vanskelig å nå for hånd, er hvert steg ordnet så en feil lar
  den kjørende versjonen stå: den avviser lokale commits foran `origin` (en
  hotfix på boksen) i stedet for å forkaste dem, installerer målets avhengigheter
  *før* `HEAD` flyttes, spoler bare fram (`merge --ff-only`), og
  import-røyktester den nye koden i en subprosess — klarer den ikke å importeres,
  rulles `HEAD` tilbake og oppdateringen avvises *før* re-exec. For en
  kjøretidsfeil som først viser seg ved oppstart parkerer enheten nå tjenesten i
  `failed` etter fem mislykkede starter på tre minutter (`StartLimitBurst`) i
  stedet for å restarte i evig løkke; manuell gjenoppretting står i
  `docs/UPGRADING.md`.
- Én bevisst oppmykning: den leverte systemd-enheten lister nå `/opt/sybr-hub`
  under `ReadWritePaths`, så tjenesten kan skrive over sitt eget utsjekk. Dette
  er det eneste stedet kodekatalogen er skrivbar for tjenesten, og er den
  iboende kostnaden av en app som kan oppdatere seg selv. `NoNewPrivileges`
  røres ikke. `scripts/install-cachyos.sh` legger dette inn automatisk; se
  `docs/UPGRADING.md`. Vil du beholde koden skrivebeskyttet, fjern
  `/opt/sybr-hub` fra linja og oppdater for hånd.
- Frontenden viser gjeldende versjon/commit/grein, en «Oppdater nå»-knapp
  (bare for admin på et git-utsjekk), og poller `/api/system/version` til den
  nye commit-en svarer før den laster siden på nytt for å hente nye assets.

### Oppsummeringen og rådataene sier nå det samme

En ekstern gjennomgang av en ekte kunderapport fant at oppsummeringskortene og
CIS-dommene motsa rådataene rett under seg. Strukturen og metodikken holdt mål —
sporbarhet per kontroll, CIS/NIST/ISO-mapping, skillet mellom «ikke bestått» og
«kan ikke verifiseres» — men der summeringen og rådataene ikke stemte overens,
kunne ingen bestått-status stoles på. Åtte feil, med rot i to klasser: et tall
utledet feil, og en dom stilt på feil bevis.

**Den farligste: MFA-dekning som skjulte det faktiske bruddet.**

- Dekningspredikatet var `covered = has_mfa or (has_ca and not is_excluded)`.
  `or`-en kortsluttet, så Conditional Access-ekskluderingen ble bare sjekket for
  brukere *uten* registrert metode. En Global Admin og en konto under aktivt
  passordangrep, begge unntatt fra MFA-policyen men med en registrert metode,
  telte som «dekket» — så tenanten leste 100 % og CIS 1.1.1 «bestått». En
  ekskludering betyr at MFA *ikke håndheves*; en registrert metode er ikke
  håndhevelse. Predikatet er nå `(has_mfa or has_ca) and not is_excluded`, som gir
  den ærlige håndhevede dekningen (6 av 8 på denne tenanten), snur 1.1.1 til
  «delvis», og slår på MFA-anbefalingen igjen.
- Et nytt kritisk funn krysser de CA-ekskluderte kontoene mot global-admin-lista
  og brute-force-mistenkte, så «Global Admin unntatt fra MFA-håndhevelse» og
  «angrepet konto unntatt fra MFA-håndhevelse» havner øverst i rapporten i stedet
  for gjemt i rådatafil 04b — den faktiske sikkerhetsbristen, løftet dit den hører
  hjemme. En ekskludert konto med ukjent metode-oppslag teller nå som
  kjent-ubeskyttet, ikke «ukjent», så kortet og navnelista under det ikke lenger
  motsier hverandre.

**Dommer stilt på feil bevis, og tellere som telte feil:**

- CIS 3.2.1 «sensitivitetsetiketter funnet» besto på null etiketter fordi
  betingelsen lette etter ordet «label» i en fil som *heter*
  `PURVIEW SENSITIVITY LABELS` med en `Label Name`-kolonne. Dommen står nå bare på
  det parsede antallet; null etiketter går til «ingen funnet». CIS 3.1.1 (DLP) og
  7.2.2 (oppbevaring) hadde samme svakhet via en `.strip()`-reserve — en tom
  `(none)`-seksjon er ikke-tom tekst — så de besto med null policyer mens kortet
  viste 0. Begge teller nå policyer, og en tom seksjon som kjørte blir «warn».
- DLP-, oppbevarings- og anti-phish-kortene telte `(none)`-plassholderen som én
  policy og hver feltlinje i en ekte policy som en til — én seks-felts
  anti-phish-policy ble til «7». Telleren leser nå `[i]`-blokkene i
  `_section_block`-formatet: tom → 0, én policy → 1.
- Safe Links / Safe Attachments ble rapportert «ikke funnet» selv med
  Built-In Protection Policy aktiv, fordi innsamleren skrev en nøstet dict som
  parseren ikke kunne lese. Den flates nå ut til én blokk per policy, og
  Built-In-policyen (Safe Attachments `Action=Block` uten `Enable`) telles som
  beskyttelse.
- Break-glass-sjekken hoppet over seg selv fordi `global_admin_ids or []`
  erstattet den delte, ennå-tomme admin-ID-lista med en ny tom en, og
  in-place-fyllingen senere ble usynlig. `is not None` bevarer referansen.
- Innloggingsfeil ble kollapset til «THRESHOLD EXCEEDED» uten feilkoder eller
  geografi, enda Graph returnerer dem som standard. Innsamleren aggregerer nå
  topp feilkoder (50126 vs 50053), kilde-land og kilde-IP-er, og rapporten viser
  dem — så en leser kan vurdere om Nordic-blokken faktisk stopper forsøkene.
- Lisensoptimalisering-seksjonen sto igjen tom i kunderapporten; den er nå
  vaktet på `has_data` som resten. «Compliance»-etiketten var uoversatt norsk og
  er nå «Samsvar».

### En avvist lesing er ikke en tom lesing — nå også i enhetsklientene

- FortiGate- og UniFi-klientene svarte på en mislykket lesing med en verdi
  kalleren ikke kunne skille fra et ekte tomt resultat: UniFi ga `[]`,
  FortiGate ga `{"error": ...}`. En kontroller som svarte 403 ble til «0
  enheter», en brannmur auditen ikke nådde ble «0 regler, score 100», og en
  CIS-kontroll hvis konfig ikke kunne leses ble stille hoppet over — eller verre,
  fikk en oppdiktet dom fra feil-dicten. Rapporten sa at nettverket var rent
  fordi ingen fikk sett etter. Dette er defekten arkitekturdokumentet navngir —
  «a refusal is not a zero» — som M365-pipelinen ble bygget om rundt; den levde
  videre her fordi disse klientene mater dusinvis av kall-steder.
- `app/modules/api_result.py` innfører `ApiList` og `ApiDict` — subklasser av
  `list`/`dict` som bærer `.error`. De *er* den tomme verdien de erstatter, så
  de ~30 stedene som itererer, `len()`-er eller indekserer et resultat virker
  uendret, mens de få stedene som publiserer et tall en kunde leser kan spørre
  `read_failed(x)` og si «utilgjengelig» i stedet for «0». En feilet container
  er alltid tom, aldri et delresultat — en halv-lesing som så hel ut ville vært
  en mer subtil versjon av samme løgn.
- Kundevendte aggregater sier nå «utilgjengelig» i stedet for en betryggende
  null: CIS-compliance scorer bare kontroller den faktisk leste (uleste teller
  som `unknown`, ikke som bestått eller strøket); brannmur-regelauditen,
  hurtigauditen, flåtepollingen og trussel-sammendraget rapporterer
  `unavailable` med `None`-tellere når lesingen ble avvist; UniFi
  firmware-sjekk, WiFi-helse, enhetsstatistikk og klientinventar likeså.
  Dashboard-pollerne skriver en feilrad, ikke en grønn «online»-rad, for utstyr
  som ikke svarte.
- En kunde med bare UniFi hvis kontroller ble avvist forsvinner ikke lenger fra
  nettverksoversikten som «ingen nettverk» — raden blir stående med varselet
  synlig. En uleselig FortiGate legges ikke lenger inn som en frisk-utseende
  rad. FortiGate live-dashboardet svarer `unavailable` i stedet for en tom, idle-
  aktig øyeblikksbilde. AI-konsollen får feilen, ikke en tom liste som `[]`.
- To nye testfiler pinner begge halvdeler: `tests/test_api_result.py` for
  containeren, `tests/test_device_reads_are_not_clean.py` for hvert kundevendt
  kall-sted — hver «feilet lesing → ikke ren» har en søster «ekte tom → fortsatt
  ren», fordi å flagge en frisk kunde som utilgjengelig ville vært samme defekt
  pekt andre veien. En mutasjonstest bekreftet at consumer-testene biter.

### En transportfeil er det tidspunktet gjør den til

- `send_with_retry` fanget `httpx.TimeoutException` og prøvde på nytt for alle
  metoder, med begrunnelsen at en tilkobling som aldri åpnet ikke kan ha utført
  en skriving. Begrunnelsen er riktig; koden gjorde ikke det den sa.
  `TimeoutException` dekker `ReadTimeout` like mye som `ConnectTimeout`, og en
  read timeout betyr at forespørselen *ble* sendt og at svaret forsvant.
- Transportfeil skilles nå på om forespørselen kan ha nådd fram.
  `ConnectTimeout`, `ConnectError` og `PoolTimeout` skjer før noe sendes og er
  fortsatt trygge for alle metoder. Alt annet behandles som en 5xx: gjentas for
  idempotente metoder, feiler én gang for resten.
- Det betyr mer nå enn da hjelperen ble skrevet, fordi FortiGate- og
  UniFi-klientene sender konfigurasjonsendringer gjennom den. «Svaret forsvant»
  og «gjør det en gang til» er ikke det samme på en brannmur.

### FortiGate og UniFi prøver ikke lenger bare én gang

- Begge klientene går nå gjennom `send_with_retry`. De snakker med utstyr i
  enden av en VPN-tunnel til et kundelokale, der en forbigående feil er
  normalen og ikke unntaket — en audit som ga opp på første forsøk rapporterte
  en brannmur som uleselig når et nytt forsøk to sekunder senere hadde virket.
- UniFi-innlogging spesielt: det er kallet en controller strupes hardest på, og
  det første hver audit gjør. En strupet innlogging kostet hele sitet.
  429 gjentas uansett metode, som er nettopp dette tilfellet.
- «Uleselig» og «feil passord» er nå to forskjellige meldinger.
- Site Manager-lesingene mot `api.ui.com` er også dekket.
- En ratchet-test krever at hver upstream-klient går gjennom laget. Graph er
  eksplisitt unntatt og navngitt som det, siden den har sin egen backoff.

### Den andre bøtta: noe som skal planlegges, ikke fikses denne uka

- «Til planlegging» ved siden av «Opprett sak» på hvert funn.
  `POST /hub/{id}/recommendations` med samme vakter som saks-endepunktet, og de
  deler `_push_finding` — de sju stegene rundt selve kallet er identiske, og
  kappløps-håndteringen er subtil nok til at en kopi nummer to ville vært en
  ny sjanse til å ta feil.
- Unikheten er per system, så ett funn kan bli både en sak og en anbefaling —
  et DKIM-hull kan fikses denne uka *og* planlegges ordentlig neste kvartal.
  To anbefalinger for samme funn kan det derimot ikke bli: de havner i kundens
  kvartalsgjennomgang som to punkter ingen klarer å skille.
- `list_tickets` er nå scopet på system. Én dict nøklet på `rec_id` på tvers av
  begge ville stille mistet den raden databasen returnerte sist.

**Verifikasjonen er svakere enn Autotasks, og forskjellen er verdt å vite.**
Autotask-klienten ble skrevet mot en publisert REST-referanse noen hadde lest.
Denne ble ikke det: `app.myitprocess.com` var ikke nåbar fra miljøet den ble
bygget i, så forespørselsformen kommer fra kontrakten den gamle stubben
erklærte. Koden er derfor skrevet for å være *diagnostiserbar* i stedet for
selvsikker — base-URL er en innstilling, ID-en leses fra en kort liste
kandidatnøkler i stedet for én gjetning, et svar den ikke kjenner igjen sier hva
den faktisk fikk, og kategori og prioritet er fritekst fordi en nedtrekksliste
med gjettet vokabular er verre enn et felt du kan skrive den ekte verdien i.
Kjør `/api/myitprocess/test` først; den rapporterer feltnavnene som kom tilbake.

### Ett funn blir én sak, og bare en operatør kan gjøre det

- «Opprett sak» på en anbefaling oppretter nå en Autotask-sak.
  `POST /hub/{id}/tickets` krever technician *og* `can_write`-tildelingen —
  stubben hadde `viewer` som gulv, som ville sluppet en lesekonto til å skrive
  inn i en kundes PSA i det øyeblikket den sluttet å være en stubb.
- Verkstedets regel om at ingenting automatisk oppretter saker holdes ikke av
  klienten — den lager en sak for hvem som helst som kaller den. Den holdes av
  endepunktet, og av en test som feiler hvis en uovervåket modul
  (scheduler, site collector, alert engine) importerer skrive-siden.
- Idempotens ligger i `UNIQUE(customer_id, rec_id, system)` (migrasjon 18), ikke
  i en sjekk i Python: to teknikere som klikker samtidig får begge tomt svar på
  et `SELECT` og setter begge inn. Taper man kappløpet, finnes saken likevel i
  Autotask — den rapporteres med ID i stedet for å skjules, for ellers er det
  kunden som finner den.
- Nøkkelen er `rec_id`, ikke `finding_id`. Flere anbefalinger deler
  `finding-email`, så en sak per `finding_id` ville blitt én sak for fire
  domener. `rec_id` ligger i request-body og ikke i URL-en: den bygges av
  meldingsnøkkel pluss parametere som bærer tenant-data, og et path-segment kan
  ikke trygt holde et domenenavn eller et app-registreringsnavn.
- Saken bærer hvilken kjøring funnet kom fra. En sak lever lenger enn rapporten,
  og uten det er det første teknikeren gjør å kjøre auditen på nytt for å finne
  ut hva saken betyr.
- En POST retries aldri på 5xx. Det er hele grunnen til at `send_with_retry`
  skiller på metode: en skriving som ble utført og så feilet på vei ut ville
  blitt sak nummer to.
- Autotask-kortet under Integrasjoner sto som «Kommer snart» bak en deaktivert
  knapp, så det fantes ingen steder i produktet å legge inn legitimasjonen
  endepunktet trenger. Kortet har nå et ekte skjema, og «Test tilkobling»
  lagrer før den tester — ellers tester man forrige legitimasjon og får vite at
  den virker.
- Kø, prioritet og status kan settes som standard, fordi status og prioritet er
  plukklister en tilpasset Autotask-instans nummererer annerledes. Ugyldige
  verdier avvises når de lagres, ikke som en 400 fra Autotask i det øyeblikket
  teknikeren klikker på en skjerm som ikke har noe med innstillinger å gjøre.
- `toggleIntegConfig` leste `el.style.display`, som er tom for et panel skjult
  av en stilarkklasse — første klikk lukket alt og åpnet ingenting. Den leser
  nå den beregnede verdien.

### Et passord skal ikke krysse en linje som ikke kan bære det

- Plain-HTTP-innlogging fra en annen maskin avvises nå med 403. README har
  lovet dette siden første utgivelse uten at noe håndhevet det: `_cookie_secure`
  bestemmer et cookie-flagg, og `/api/auth/login` returnerer begge tokenene i
  svarkroppen også — så en klient som aldri rører en cookie autentiserte over
  klartekst fra hvor som helst på nettet.
- Standard bind er nå `127.0.0.1`. Den var `0.0.0.0`, så hurtigstarten i README
  publiserte et klartekst-innloggingsskjema til hele LAN-et uten at den som
  kjørte den valgte det. Et rutbart bind uten sertifikat nekter å starte og
  sier hvilke fire ting man kan gjøre i stedet.
- `app/web/transport.py` holder predikatene. «Kan legitimasjon krysse denne
  linjen» ser bare på klientadressen — en forespørsel fra 127.0.0.1 med et
  offentlig Host-felt er en lokal TLS-terminator, altså oppsettet installeren
  lager med `tailscale serve`. «Skal denne cookien merkes Secure» krever begge
  ender lokale. To spørsmål, delte byggeklosser, så forskjellen forblir synlig.
- `SYBR_ALLOW_INSECURE_AUTH=1` åpner begge deler igjen for en terminator
  prosessen ikke kan se.

### Hemmeligheter maskeres der verdien går ut, ikke i den grenen noen husket

- `factory_bootstrap` maskerte FortiGate-API-nøkkelen den nettopp hadde parset,
  og returnerte så den samme terminal-outputen ordrett som `raw_output` i
  grenen der parsingen *feilet* — grenen som kjører når nøkkelen ikke så ut som
  parseren ventet, altså der en ugjenkjent nøkkel mest sannsynlig fortsatt står
  i teksten. Det nye admin-passordet hadde samme eksponering gjennom
  asyncssh-feiltekst.
- `app/core/redact.py` maskerer både på navngitt verdi og på form. `/` er
  bevisst utenfor mønsteret: med den inne er `/home/user/sybr-hub/app/web/` én
  28-tegns sekvens, og maskering som spiser tracebacks er maskering noen slår av.

### En uventet feil svarer med noe, og en request-body har en form

- `create_app()` har nå en handler for alt `ToolkitError` ikke dekker. Svaret
  bærer en feil-ID og ingenting annet; ID-en står i logglinjen ved siden av
  tracebacken, så en support-skjermdump kan finne hendelsen uten å inneholde den.
- Scheduler-endepunktet tok imot hva som helst og lagret det: en JSON-liste ga
  `AttributeError` og 500, og et hvilket som helst objekt havnet under en nøkkel
  scheduleren leser hver runde. `app/models/settings.py` beskriver formen, med
  `extra="forbid"` — en feilstavet nøkkel ble tidligere lagret for alltid og
  gjorde stille ingenting.
- Språk-, webhook-test- og oppgaveplanleggerendepunktene validerer på samme måte.

### En lesing som feilet er ikke en kunde uten funn

- `/customer/{id}/unified` svarte `except Exception: result["audit"] = None`.
  Konsekvensen var ikke et manglende kort: frontend bygger «Krever handling» av
  `a.users_no_mfa || 0`, så en feilet metrikklesing ga en kunde uten funn — samme
  side som en faktisk frisk kunde får. Den beroligende siden var den en
  databasehikke produserte.
- Hver blokk rapporterer nå feilen sin i `unavailable`, og grensesnittet viser
  en «Ufullstendige data»-stripe over handlingsbåndet pluss en feiltilstand på
  de berørte brikkene. ALSO-blokken hadde ingen vakt i det hele tatt og tok hele
  siden ned; den er nå degradert som de andre.

### Testsuiten skriver ikke lenger i operatørens egne kataloger

- `conftest.py` isolerer `CONFIG_DIR` og `DATA_DIR`, både per test og for hele
  økten. Master-nøkkelen mintes på nytt per test, mens `settings.json` lå i den
  ekte katalogen — så en test som lagret innstillinger etterlot en blob ingen
  nøkkel kunne åpne igjen, og hver senere test som leste innstillinger døde på
  `InvalidTag` langt unna den som forårsaket det. Det tok ut 269 tester i én
  kjøring av denne suiten.

### Grensesnittet heter Sybr HUB

- Sidetittel, overskriften på admin-kortet, PWA-manifestet, offline-siden og
  begge språkblokkene i i18n-laget sier nå Sybr HUB.
- IT Glue-identifikatorene er bevisst uendret: asset-typene og dokumentmappen
  «MSP Toolkit» navngir levende objekter i kundenes tenanter, og et navnebytte
  ville opprettet nye og forlatt alt som allerede ligger der. Meldingen om
  opplastede rapporter beholder derfor også det navnet, siden den beskriver
  nettopp den mappen.

### Versjonen kommer fra git-taggen

- setuptools-scm eier versjonen. En utgivelse er `git tag` og ingenting annet
  — ingen literal i treet gjentar den lenger.
- Service worker-ens `CACHE_VERSION` er nå en eksplisitt plassholder. Den ble
  aldri servert som skrevet; `frontend.py` skriver den om med levende versjon
  og en digest av de statiske filene før noen nettleser ser den.
- CI sjekker ut med `fetch-depth: 0`. Uten det leser setuptools-scm en
  historikk uten tagger og gir `0.1.devN+g<sha>` i stedet for utgivelsen.
- Installeren kloner med full historikk og utdyper eksisterende grunne
  checkouter. `git describe` krever at den taggede commiten er *nåbar*, ikke
  bare at tagg-refen er hentet, så en grunn checkout kunne bare beskrive en
  tagg som lå nøyaktig på HEAD. Første deploy etter enhver utgivelse falt
  derfor tilbake til fallback-versjonen.

## v1.0.0 (2026-08-08)
### Første stabile utgave under Sybr HUB-navnet

- Produktversjonen er satt til `1.0.0`. `0.1.0` var aldri en modenhetsvurdering,
  men startverdien fra navnebyttet, og den underkommuniserte en plattform som
  kjører i produksjon med hele regresjonssuiten grønn.
- `app/core/version.py` og service worker-ens `CACHE_VERSION` er bumpet i takt,
  slik `tests/test_version_consistency.py` krever.

### Installasjonen henter tagger, så den viste versjonen kan løses

- `scripts/install-cachyos.sh` henter nå tagger eksplisitt etter kloning og
  oppdatering. Både den grunne klonen (`--depth 1`) og enkeltgren-hentingen
  utelot tagg-referanser, så `git describe --tags` i `app/core/version.py`
  feilet på hver installasjon og alle flater rapporterte fallback-verdien
  uansett hvilken utgave som faktisk kjørte.
- Ingen andre endringer var nødvendige. Web-UI, API, rapporter, TUI,
  service worker-cachenøkkelen og oppstartsloggen leser allerede
  `get_version()`, og begynner å vise riktig utgave så snart en tagg finnes.
- `pyproject.toml` leser `__version__` på byggetidspunktet og kan ikke se git.
  Den verdien må fortsatt oppdateres per utgave.

### Audit-resultater, VPN-kontroll og vedlikehold er herdet

- Audit-fremdrift, avbrudd, resultatsett og valgt rapportmappe er isolert per
  bruker og kunde. Historikk, rapporteksport, e-post, IT Glue og status kan
  ikke lenger lese prosessens sist kjørte audit fra en annen innlogget bruker.
- Trendoversikten følger kundetilgang, bulk-audit krever administrator, og
  vertsoperasjonene mappeåpning og SMTP-test er flyttet bak admin-grensen.
- VPN-kontroll rapporterer nå en eksplisitt capability per protokoll. Under
  den herdede systemd-uniten vises `external`, Connect deaktiveres, og API-et
  stopper før profilhemmeligheter lastes. WireGuard forsøker ikke lenger
  `sudo` eller et ikke-levert hjelpeprogram.
- VPN-profiler, status, Azure-innlogging og frakobling filtreres etter
  kundetilgang. Force-disconnect og import av delte profiler krever admin.
- 102 flere statiske klikkhandlere er flyttet til den eksplisitte CSP-listen;
  handlerbudsjettet er redusert fra 808 til 706.
- GitHub Actions er oppdatert til immutable SHA-er for checkout 7.0.1 og
  setup-python 7.0.0. Testede øvre intervaller for WebSockets og fire Azure
  SDK-er er utvidet til de aktuelle hovedversjonene.
- Ruff-gjelden er redusert fra 1068 til 934 funn, og alle endrede Python-filer
  er rene.

### Aktiv kunde er isolert per bruker

- Autentiserte requests binder brukeridentitet og gjeldende kundetilganger i
  et `ContextVar`. Aktiv kunde lagres i en kryptert, brukerhash-basert fil og
  lekker ikke lenger mellom samtidige teknikere.
- Manglende brukervalg faller aldri tilbake til legacy `active.txt`. Tilgang
  som trekkes tilbake etter valg gjør konteksten ugyldig umiddelbart.
- Konfig- og sertifikatlesing følger samme request-kontekst. Bytte av kunde
  kopierer ikke lenger data inn i prosessglobale config-/sertifikatplasser.
- 26 statiske inline-klikkhandlere er flyttet til en eksplisitt delegert
  allowlist uten `eval`; CSP-handlerbudsjettet er redusert fra 834 til 808.

### Nettleser-, CI- og driftsgrensene håndheves

- CSP tillater ikke lenger inline `<script>`- eller `<style>`-elementer i
  applikasjonsskallet. Tema-bootstrap og offline-siden er flyttet til egne,
  cache-versjonerte filer. Eldre event- og style-attributter er isolert i
  egne CSP3-direktiver inntil den større markup-migreringen er ferdig.
- Swagger er fortsatt tilgjengelig for autentiserte brukere, men bruker nå en
  eksakt versjon av UI-bundle og en tilfeldig CSP-nonce per respons. ReDoc-ruten,
  `unsafe-inline` og FastAPIs mutable major-tag-standard er fjernet.
- GitHub Actions er pinnet til full commit-SHA, checkout lagrer ikke
  push-credential, og CI dekker merge queue, manuell kjøring og `pip check`.
- systemd-uniten krever nå en root-eid `LoadCredential` for innpakking av
  master-key-backup, setter `UMask=0077` og aktiverer flere kernel/host-sperrer.
  CachyOS-installasjonen oppretter hemmeligheten atomisk én gang.
- Det ikke-fungerende sudoers-rådet er fjernet: `NoNewPrivileges=yes` blokkerer
  slik elevasjon. Privilegerte VPN-operasjoner må leve utenfor webprosessen.

### Fargeemoji ut av grensesnittet

**Bakgrunn:** Fargeemoji rendres i fontens egne farger og sin egen vekt. Én 🔒 ved siden av en rad monokrome ikoner er det eneste på skjermen designspråket ikke rekker, og Filer-fanen hadde ni av dem rett under hverandre.

**Endret:**
- Kortoverskrifter og knapper i Filer-fanen, søkefeltet i kommandopaletten, overskriften i rapportvisningen og pentest-overskriften bruker nå SVG-linjeikoner i nøyaktig samme form som `icon()` produserer. Ikonene arver farge gjennom `currentColor` og virker derfor i begge temaene.
- Policy-utrulling i nav-nedtrekket fikk en monokrom geometrisk glyf (`&#8650;`) som passer søsknene sine. Den var den eneste ekte emojien i navigasjonen.
- Den skjulte tema-knappen i headeren bruker `◐` og `◑` i stedet for 🌙 og ☀️, samme glyf som den synlige veksleren i kontomenyen.

**Det som måtte til for at fiksen ble ekte:**
- Emojiene lå i `ui_i18n.json`, ikke bare i markupen. `translatePage()` setter `textContent` fra nøkkelen, så emojien ble skrevet inn igjen ved hver oversettelse. Å fjerne den fra `index.html` alene ville ikke endret noe på skjermen. Prefikset er strippet fra elleve nøkler i begge språk. Ordene er uendret.
- Den samme `textContent`-skrivingen sletter et ikon som ligger inne i et `data-i18n`-element. Ikonet ligger derfor utenfor, med nøkkelen på et `<span>` rundt bare teksten, slik `hdr_report` allerede var bygget.
- `uploadToITGlue()` skrev `btn.textContent` i åtte tilstandsskifter og ville spist ikonet ved første klikk. Nye `setButtonLabel()` skriver til etikett-spanet og lar ikonet stå.

**Nye navn i `icon()`:** `folder`, `key`, `unlock`.
