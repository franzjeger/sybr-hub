# Endringslogg

Sybr HUB versjoneres etter semver fra og med `v1.0.0` (august 2026).
Oppføringene under `v1.0.0` — `v10.x`, `v9.x` … ned til `v0.1.0` (mars–juli
2026) — dokumenterer den importerte MSP-Toolkit-auditmotorens historikk og er
ikke Sybr HUB-pakkeversjoner. De deler versjonsnummer med Sybr HUBs `v1.0.0`–
`v1.1.1`, men er en annen historikk: skill dem på dato (august 2026 for Sybr
HUB, mars–juli 2026 for motoren).

## Ikke utgitt
### Auditen henter nå installerte apper fra Intune-enhetene

Intune-seksjonen leste app-*katalogen* (`mobileApps` — hva Intune er satt til å
distribuere), men aldri hva som faktisk er *installert* på enhetene, så en
Motavo-audit manglet programvareoversikten. Nå leses `deviceManagement/detectedApps`
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

## v10.11.0 (2026-07-31)
### Rapporten svarer for tallene sine

**Bakgrunn:** En gjennomgang av datagrunnlaget mot anbefalingene avdekket at flere vurderinger var bygget på felt som aldri ble samlet inn, og at rapporten ikke kunne spores tilbake til rådataene. Feilene delte én form: Graph protesterer ikke på en egenskap du staver feil, den utelater den, og "N/A" leses som "ikke konfigurert".

**Bugfix — vurderinger uten grunnlag:**
- **Kunderapporten viste «0 sensitivitetsmerker» der sannheten var «ikke målt».** Fonnaflys kjøringer får 404 fra Purview-endepunktet. Leseren blanker en feilet seksjon før noen parser ser den, som er riktig og hindrer at feilen tolkes som data, men det etterlot en merkefarget 0 under overskriften uten forbehold. Den tekniske rapporten lister feilede seksjoner rett ut, kunderapporten hadde ingenting. Nå vises en strek og «Ikke målt» i stedet for et tall. Flagget settes fra `error_files` og ikke i parseren, for på det tidspunktet er beviset for at hentingen feilet allerede borte.

- **CIS 7.2.3 (SharePoint legacy-protokoller)** besto på enhver tenant uansett innstilling. Parseren leste `legacy auth` fra en fil samleren aldri skrev. Feltet hentes nå (`isLegacyAuthProtocolsEnabled`), og fravær er en tredje tilstand i stedet for `false`.
- **"Uadministrerte enheter"** i den tekniske rapporten meldte alltid "Blokkert/Begrenset" uten at noe hadde sett etter. Hos Fonnafly var sannheten det motsatte.
- **Kryssleie-tilgang** viste `N/A` på begge feltene siden dagen de ble skrevet. `default` er en relasjon på `crossTenantAccessPolicy`, ikke en egenskap, så samleren leste et objekt som aldri fantes i svaret.
- **Tre egenskapsnavn i SharePoint-samleren** sto ikke på v1.0-ressursen. To fantes ikke, én manglet suffikset `Enabled`.
- **CIS 5.1.1** het "legacy authentication is blocked" og målte SharePoints protokollflagg, ikke Entras. Den leser nå Conditional Access, avgjort fra policyens klientapp-omfang og grant-kontroll, aldri fra visningsnavnet. SharePoint-flagget lever videre som 7.2.3.
- **CIS 5.2.1 og 5.2.2** gjorde et feilet DNS-oppslag om til "konfigurer SPF". DNS-laget skiller allerede ERROR fra MISSING; 5.2.3 hadde vakten fra før, disse to ble glemt.
- **Report-only CA-policyer** ble talt som håndhevet. Graph staver tilstanden `enabledForReportingButNotEnforced`, og prefikstesten på `[enabled` lå foran report-only-grenen.
- **Innbokssregler med ekstern videresending** ble rapportert som null nøyaktig når de fantes. Samleren signaliserer funnet ved å døpe om filen, og rapporten leste bare friskmeldingsnavnet.
- **Konnektorer** ble talt til tre der tenanten hadde én. Én post over tre linjer, og flerlinjedetektoren krevde stor forbokstav i feltnavnet.
- **Radtelleren** talte oppsummeringshaler og mellomtitler som poster. En tabell er nå det en `---`-strek understreker.

**Nye kontroller:**
- **1.1.7** Grunnleggende påloggingsbeskyttelse (Security Defaults sett mot CA-policyer)
- **1.1.8** Tilgangsgjennomganger, portet på tildelt Entra ID P2
- **1.1.9** Kryssleie-tilgang. Tillatt B2B-samarbeid graderes bevisst ikke som stryk; direct connect inn og ubesluttet systemstandard gjør det
- **7.2.4** Anonyme delingslenker
- **8.1.2** Teams gjestetilgang gikk fra en kontroll som aldri kunne gi pass eller fail til en reell vurdering

**Sporbarhet:**
- Hver CIS-kontroll navngir filen vurderingen er formet fra, lenket til vedlegget. Bare filer kjøringen faktisk samlet blir lenket.
- Anbefalingene har samme proveniens.
- Etterlevelsesprosenten viser hva den er en prosent av. `compliance_assessed` og `compliance_info` ble beregnet og aldri vist, så leseren så ikke at ikke-vurderbare kontroller var trukket ut av nevneren.

**Tester:**
- Sømtester som kjører den ekte samleren og mater utdataene til den ekte parseren, for ti seksjoner. Fixtures kan ikke fange drift mellom de to sidene, fordi fixturen *er* antagelsen. Den første av dem fant report-only-feilen på minutter.
- Golden-fil over den syntetiske auditen: nesten hver feil funnet her flyttet et tall uten å flytte en test.
- En test sjekker at hver Graph-egenskap SharePoint-seksjonen ber om faktisk publiseres på v1.0-ressursen.

**i18n:**
- **`app.js` er ferdig: 196 → 0.** All tekst som bygges inn i markup går nå gjennom `t()`. Rundt 2100 nøkler totalt, full paritet.
- **`app.js` påbegynt: 196 → 69 strenger.** 70 nøkler for tekst som bygges inn i markup fra JS. Detektoren måler posisjon i stedet for stavemåte — alt mellom `>` og `<` i en generert streng leses av et menneske, uansett språk — så den ser engelsk like godt som norsk.
- **`index.html` er ferdig.** Både tekstnoder og attributter står på null, og begge er mutasjonstestet. Rundt 1940 nøkler, full paritet mellom språkene.
- To elementer hadde `data-i18n` på en beholder med `<code>` inni. Oversetting satte `textContent` og slettet kodeelementet — teksten overlevde, formateringen ikke.
- **Alle attributter er ute av markupen.** 65 nøkler for `title`, `placeholder`, `aria-label` og `alt`. Budsjettet 74 → 0.
- Verktøyet håndterer nå attributter, og genererer ASCII-nøkler. Fem nøkler med `ø` i navnet ble omdøpt.
- Mobilnavigasjon, kontomeny og de siste API-overskriftene: 24 nøkler. Budsjettet 121 → 90.
- **`scripts/i18n_extract.py`** henter norsk tekst ut av filen, skriver den til språkfila byte for byte og merker elementet på plass. Den bruker samme definisjon av «oversettbart» som sperren, importert i stedet for gjentatt.
- Claude AI-seksjonen og resten av FortiGate/UniFi-skjemaene: 24 nøkler. Budsjettet 143 → 121.
- FortiGate- og UniFi-panelene hentet inn: 15 nøkler, skjemaetiketter og hjelpetekst. Budsjettet 158 → 143.
- API-referansepanelet hentet inn: 9 nye nøkler. Målingen ble samtidig rettet — 82 av strengene den talte var endepunktsignaturer og leverandørnavn, altså kode, ikke språk. Budsjettet 251 → 158, hvorav bare 11 er reelt hentet inn.
- Navigasjonsmenyen, innloggingsskjemaet og rapportvisningen hentet inn: 29 nye nøkler, 32 strenger. Tekstnodebudsjettet ned fra 283 til 251.
- **Tre elementer viste nøkkelnavnet sitt til brukeren.** `data-i18n="btn_export"` uten oppføring i språkfila gir bokstavelig «btn_export» på skjermen, siden `translatePage` kaller `t()` uten fallback. En test fanger det nå.
- Skjermleser-etikettene i innloggingsskjemaet var hardkodet, og var de eneste `sr-only`-etikettene i appen.
- **Hardkodet tekst er nå en testfeil, ikke en vane.** Rundt 400 strenger står fortsatt i markupen og skriptene, samlet opp over lang tid og lagt til av hvert redesign. `tests/test_i18n_coverage.py` teller dem og feiler hvis tallet vokser, så en batch om gangen kan hentes inn uten at grunnen gis tilbake.
- **`translatePage` håndterte aldri `aria-label` og `alt`.** Å merke dem gjorde ingenting, så norsk der var permanent uoversettelig — usynlig for seende og fastlåst for alle som bruker skjermleser.
- 22 nye nøkler for det nye dashbord-kortet fra redesignet, som kom med hardkodet norsk: «Krever handling», «Ikke konfigurert», «Se audit», «Ingen utløper snart» og flere.
- **Aktivitetsloggen på hjem-visningen skrev «log_history_deleted»** til den som hadde slettet en kjøring, i stedet for «Slettet 3 kjøring(er)». Appen har to oversettelsestabeller for én app: rutene bruker en hardkodet dict i `app/web/i18n.py`, front-enden bruker `ui_i18n.json`, og `ui_t()` returnerer nøkkelnavnet når den ikke finner noe. Åtte nøkler rutene ber om lå bare i JSON-fila. `ui_t` faller nå tilbake dit. Tabellene er ikke slått sammen: seks norske og ti engelske strenger sier forskjellige ting i de to, flere med en `{plassholder}` bare på den ene siden, så en sammenslåing ville omformulert meldinger som virker i dag. Det er flagget, ikke gjort.

- **Seks oversettelser ble malt på skjermen som tegn.** Kunde-lista viste `' + t('audit_2') + '` der «Audit»-knappen skulle stått, og det samme skjedde med Secure Score, Tags, Intune og IT Glue-velgeren. Verktøyet skriver `>' + t('nøkkel') + '<`, altså lukk strengen, kall `t()`, åpne igjen, og det lukker bare noe hvis strengen rundt har enkeltfnutt. Inne i en template-literal er fnuttene vanlige tegn. Docstringen i verktøyet lovte at alt annet ble «reported and left alone»; ingen kode sjekket det. Nå avgjør en skanner hvilken streng posisjonen står i og velger form deretter, med `${t()}` i template-literaler.
- **Suiten var grønn hele tiden mens dette sto på skjermen.** Alle detektorene lette etter tekst som manglet et `t()`-kall, ingen etter et `t()`-kall lagt et sted det ikke kan kjøre. Den sperren finnes nå, og den er verifisert mot selve filen som ble deployet, ikke mot en konstruert mutasjon.
- **Ett bilde bar tre `data-i18n-alt`-attributter.** Å kjøre samme attributt-plan to ganger la på en ny markør i stedet for å se den forrige, fordi markøren settes foran attributtet og sjekken lette bakover. En nettleser bruker den første og kaster resten, så de ekstra nøklene var døde og markupen ugyldig. Verktøyet er nå idempotent, verifisert ved å kjøre en plan to ganger mot en kopi av repoet.
- **IT Glue-modalen hadde to nøkler for samme tekst** på samme element, én i `data-i18n` og én i et `t()`-kall. `translatePage` vinner alltid, så den andre var død.

- **Null hardkodet tekst igjen i markupen og i alle tre skript.** De rundt 400 er hentet inn; sperren står nå på null for tekstnoder, attributter og generert markup, så tallet kan ikke vokse igjen.
- **Sperren målte feil sted.** Den så bare etter tekst mellom `>` og `<`, og var blind for strenger som sendes til `showToast`, `confirm` og `alert`. Alle fire filene målte rent mens 34 slike sto igjen. De tre funksjonene finnes for å vise ord til et menneske, så et strengargument til dem er brukervendt per konstruksjon, uten noen heuristikk. 14 av dem var engelske, som den norske detektoren aldri kunne se.
- **To fantomer i selve målingen.** Regexen for norske literaler leste over linjeskift og matchet et anførselstegn mot en kommentar to linjer ned, som holdt liv i et budsjett på 1 som ingen kunne tolke. Og detektoren kuttet treffet til 60 tegn før det ble returnert, slik at enhver streng lengre enn det ikke kunne spores tilbake til kilden sin. Avkortingen hører hjemme i feilmeldingen, ikke i verdien.
- **Fire arbeidsmøte-titler bar en norsk fallback ved siden av nøkkelen sin,** altså en andre kopi av teksten i kildekoden. Nøklene finnes, så fallbacken er fjernet og erstattet med en test som beviser at de finnes — en sterkere garanti enn en fallback.

- **«Kjør Audit» viste to avspillingsikoner.** Ikonet lå både i markupen og i selve oversettelsesverdien. 86 nøkler har fortsatt ikon bakt inn i verdien, som er presentasjon på feil sted, men bare denne ble faktisk doblet.

**Grensesnitt:**
- **Auditvisningen sa alt to ganger.** Funnlista bærer hele settet, mens tabellen under gjenga de samme funnene i en tapsbehandlet form: tre første som piller, resten bak «+n til», og alle sammen en tredje gang i en utvider. De to synlige gjengivelsene var de ufullstendige. Tabellen er nå redusert til det bare den kan svare på, nemlig om hver seksjon kjørte. Feil og hopp-begrunnelser blir stående, siden de hører til seksjonen og ikke til funnlista.
- **Radene tilbød en utvidelse tolv av dem ikke hadde noe å vise.** `cursor:pointer` og klikkhåndtereren lå på hver rad uansett innhold.
- **KPI-tallene på dashbordet** kunne vise feil verdi. Flisene ble tegnet med en literal `0` og sannheten i `data-count`, så tallet en leser så var avhengig av at en animasjon fullførte. Den startet alltid fra null og hadde ingen sperre mot overlappende løkker, så en gjenrendering dro tallet tilbake til null. Målt: «KUNDER 0» over en tabell med én kunde, risiko 23 der sannheten var 52, MFA 42 % der den var 97. Markupen bærer nå verdien, og animasjonen er pynt oppå.
- Auditresultatet ledes nå av hva kjøringen fant. Tabellen svarte "kjørte alle seksjonene", som er riktig spørsmål mens den kjører, ikke etterpå.
- Varsler har alvorlighetsgrad, satt av samleren som fant tingen. Fem aktive eksponeringer er merket kritiske.
- Fremdriftsbaren tok nevneren fra sitt eget teller og sto på 100 % gjennom hele kjøringen.
- En hoppet over seksjon meldes ikke lenger som feilet.
- Temaet settes før stilarket lastes, så siden ikke lenger blinker mørkt før den bytter.
- Autofylte felter beholder appens farger. Chrome maler over uten å vite om temaet.

**Drift:**
- Service worker-cachen evicter nå på utrulling, ikke bare på release. Nøkkelen var appversjonen, og et titalls frontend-fikser på samme versjon nådde aldri en nettleser som hadde lastet appen én gang.

---

## v10.10.1 (2026-05-05)
### Audit-integritet steg 2: data-mangler kaskaderer gjennom hele rapporten

**Bakgrunn:** v10.10.0 fikset hovedscoren ("?" i stedet for falsk B/70), men resten av rapporten viste fortsatt fabrikerte tall fra det samme tomme datasettet. "0 brukere totalt", "0% MFA-dekning" og særlig "Alle brukere har tofaktorautentisering aktivert ✅ OK" — sistnevnte direkte villedende fordi 0-av-0 evaluerte til "alle dekket". Radarchart viste defaultverdier (Identitet=16, Enheter=50 osv.) som så ut som målinger. Lisensoptimalisering blamet manglende P1-lisens når den faktiske årsaken var at PowerShell-auditen ikke samlet inn signInActivity-feltet.

**Bugfix — Python report-generator:**
- **`_parse_user_counts`** returnerer nå `has_data: False` når `03_users_count.txt` er tom. Brukerkort-, sammendrag- og statistikk-seksjoner viser "—" / "Ikke tilgjengelig" i stedet for "0".
- **MFA-card og MFA-funn-blokk** i kunderapporten gates nå på `mfa.has_data`. Den farlige "alle brukere har MFA ✅ OK"-fallthroughen er fjernet — uten data vises i stedet et eksplisitt warning-funn ("MFA-status kunne ikke verifiseres") med peker til Graph-tillatelser.
- **`_build_risk_radar`** returnerer tom dict når `risk.blocking_data_gaps` er satt, slik at hele radarchart-seksjonen skjules i stedet for å plotte fallback-verdier (Identitet=16, Enheter=50, Azure=80) som ser ut som målinger.
- **`_build_recommendations`** emitterer ikke MFA-anbefaling med mindre `mfa.has_data` er sann. Tidligere logikk antok `no_mfa: 0` betydde "alle har MFA" — nå skiller den korrekt mellom "ingen mangler" og "vi vet ikke".
- **Lisensoptimalisering** skiller nå mellom to årsaker til manglende stale-detection: `not_collected` (auditen kjørte ikke checken — vis ærlig "kjør auditen på nytt med riktig consent") og `license_p1_missing` (tenant mangler faktisk P1). Tidligere meldte alltid sistnevnte, selv når P1 var til stede via Business Premium.

**Bugfix — PowerShell (`Full_M365_Audit.ps1`):**
- **`signInActivity` hentes nå** sammen med øvrige bruker-properties. Tidligere hentet ikke PS1-auditen dette feltet i det hele tatt, så `03b_stale_accounts.txt` ble aldri produsert og rapporten konkluderte feilaktig "krever P1". Inkluderer fallback uten `signInActivity` hvis Graph-kallet feiler (i sjeldne tilfeller på eldre Graph-versjoner).
- **`03b_stale_accounts.txt` emitteres nå fra PowerShell** med samme struktur som Python-collectoren bruker, slik at lisens-optimalisering, unused-license-deteksjon og waste-estimate fungerer fra begge audit-paths. Hvis tenant mangler P1, skrives "NOTE:"-prefiks som rapport-generatoren tolker korrekt.

**i18n:**
- 5 nye nøkler (NO + EN): `data_unavailable`, `data_unavailable_short`, `mfa_data_missing_finding`, `mfa_data_missing_desc`, `lo_not_collected`.

**CSS:**
- `.metric-card-invalid` og `.posture-card-invalid` (stiplet kant, dempet bakgrunn) som visuell indikator når data ikke er tilgjengelig — i stedet for at "—" ser ut som en målt verdi.

**Tests:**
- 5 nye tester: `TestUserCountsHasData` (2) verifiserer empty/populated → has_data; `TestLicenseOptimizationNoDataReason` (3) låser inn at "missing file" og "P1 NOTE" gir to forskjellige reasons.

---

## v10.10.0 (2026-05-05)
### Audit-integritet: refuserer å levere rapporter bygget på ufullstendige data

**Bakgrunn:** En audit mot askk.no produserte selvmotsigende tall — "0 brukere, 0% MFA-dekning" sammen med "Sikkerhetspostur B – Tilfredsstillende (70/100)". Root cause: `Get-MgUser -All` returnerte tom liste fordi admin consent for `User.Read.All` aldri ble fullført, men scriptet kjørte videre og rapport-generatoren behandlet manglende MFA-data som "ingen straff" i stedet for "kan ikke evalueres". Resultatet ville blitt sendt til kunden hvis vi ikke hadde plukket det opp manuelt.

**Bugfix — PowerShell (`Full_M365_Audit.ps1`):**
- **Sanity-check etter `Get-MgUser -All`:** hvis brukerlisten er tom *og* tenanten har lisenser i bruk, aborterer auditen med en tydelig diagnose (sannsynlig årsak: manglende Graph-tillatelser, hvor man verifiserer i Entra-portalen, hvordan man fikser). Lager `00_AUDIT_ABORTED.txt` og frakobler alle sesjoner pent. Forhindrer at tomme/feilaktige rapporter genereres.
- **Verifisering av admin consent under setup:** etter `New-MgServicePrincipalAppRoleAssignment` leses faktiske tilordninger tilbake fra Graph og kryss-sjekkes mot kritiske tillatelser (`User.Read.All`, `Directory.Read.All`, `Organization.Read.All`). Hvis noen mangler, blokkeres setup med en pekepinne til admin-consent-URL'en — i stedet for å rapportere "Admin consent gitt" og produsere ødelagte audits etterpå.
- **Permission-feil kobles til navn:** tidligere viste loggen kun rolle-GUID når en consent feilet. Nå mappes GUID → permission-navn (`User.Read.All` etc.) slik at man umiddelbart ser hvilke tillatelser som er problematiske.

**Bugfix — Python report-generator (`generator.py`):**
- **`_compute_risk` returnerer nå grade `?` / level "Ufullstendige data" når MFA-data mangler.** MFA er den største enkelt-vekten (35/100), så uten den var "B/70" fiksjon. Tidligere logikk hoppet bare over straffen; ny logikk markerer hele scoren som ugyldig og returnerer `score: None`. Andre datakildemangler (Secure Score) loggføres som data-quality-issue uten å invalidere grade-en.
- **Template `report_customer.html.j2`** håndterer `?`-grade med eksplisitt advarsel og lister opp blokkerende data-mangler. Score viser "—" i stedet for et tall når den ikke er beregnet.
- **2 nye i18n-nøkler** (NO + EN): `risk_level_invalid`, `posture_grade_invalid`, `posture_blocking_gaps_label`.

**Tests:**
- 3 nye tester i `test_parsers.py::TestComputeRiskDataGaps` som låser inn regresjonen: tom MFA-data → grade `?`, komplette data → numerisk grade, manglende Secure Score alene invaliderer ikke grade-en.

---

## v10.9.4 (2026-04-21)
### Workshop-plan engelsk oversettelse + språk-fallback

**Bugfix:**
- **Workshop-visning blandet språk:** UI-chrome (Wishlist, Discussion notes, Follow-up items, "Saved HH:MM:SS") fulgte UI-språket via i18n, men workshop-planen rendret alltid den norske `docs/workshop-plan.md`. Resultat: engelsk UI + norsk markdown-body = mix. Samme type feil som tidligere med GDAP-kortet — jeg glemte språk-fallback-mønsteret da jeg bygget Workshop-visningen.
- **`workshopLoad()` probing lagt til:** prøver nå `docs/workshop-plan.<lang>.md` (f.eks. `.en.md` på engelsk UI) før den faller tilbake til den kanoniske norske `workshop-plan.md`. Samme pattern som `wikiLoadAllCards()`.
- **Ny fil `docs/workshop-plan.en.md`** — fullstendig engelsk oversettelse (193 linjer, struktur 1:1 med norsk kilde). Dato lagt inn som "Tuesday, 21 April 2026" slik at dato-informasjonen er synkronisert på begge språk.

---

## v10.9.3 (2026-04-21)
### Fjernet duplisert 3-prikk integrasjonsstatus-widget i header

**Opprydding:**
- **3-prikk-indikatoren øverst til høyre** (FortiGate / UniFi / E-post) fjernet sammen med tilhørende popover og poll-kall til `/api/settings`. Widgetet ga kun delvis dekning (3 av 8 integrasjoner) og duplisert UI-flate — `Dashboard → Kundeoversikt → INTEGRASJONSSTATUS` viser alle 8 integrasjoner med mye rikere kontekst (sist skannet, konfigurasjonsstatus, klikkbare kort). Fjernet fra `index.html`, tilhørende `toggleIntegrationPopover()` og `_checkIntegrationStatus()` i `app.js`, samt `#integration-popover`-CSS i `app.css`. `_checkVpnHeaderBadge()` kalles nå direkte fra `_postAuthInit()` — det er samme løsning uten mellomleddet.

---

## v10.9.2 (2026-04-21)
### Rettet KPI-label på Kundeoversikt + VPN-kundetelling

**Bugfix:**
- **"258 Kunder med VPN"** på Kundeoversikt-dashboardet var feilmerket — tallet var totalt antall kunder, labelen sa "Kunder med VPN". I18n-nøkkelen `lbl_total_customers` ble brukt på to ulike steder med forskjellig semantikk: som total-KPI (app.js:6064) og som VPN-kundetelling (app-dashboard.js:266). Splittet i to nøkler:
  - `lbl_total_customers` → "Kunder" / "Customers" (total-KPI, dashboard-kort)
  - `lbl_customers_with_vpn` → "kunder med VPN" / "customers with VPN" (ny nøkkel, VPN-seksjon i dashboard)
- **VPN-seksjonen i dashboardet** talte alle skannede FortiGate-kunder, ikke bare de som faktisk hadde minst én tunnel. `dashboard_infra.py` returnerer nå `customers_with_vpn` = kunder med ≥1 tunnel (originalt `total_customers` beholdt for bakover-kompatibilitet, men UI-et bruker den nye nøkkelen). Frontend har fallback-logikk hvis man skulle kjøre eldre API-versjon.

---

## v10.9.1 (2026-04-21)
### Arkitekturdiagram inline i Workshop-visningen

**Nytt:**
- **Arkitekturdiagrammet** fra `docs/msp-toolkit-architecture.svg` rendres nå som et eget kort øverst i Workshop-visningen, over to-kolonne-layouten. Visuell referanse for seksjon 3 ("Oversikt — hva MSP Toolkit kobler til") i workshop-planen.
- **Nytt endpoint `GET /api/docs/asset`** serverer rå bilde-assets (svg/png/jpg/jpeg/webp/gif) fra `docs/`-treet med korrekt `Content-Type`. Samme path-traversal-guard som `/api/docs/file` (resolve + `relative_to`-sjekk); whitelist av filendelser slik at endepunktet ikke blir en generisk static-file-server. Auth-middlewaren aksepterer både Bearer-header og `access_token`-cookie, så `<img src>` fungerer uten ekstra headere.
- **2 nye i18n-nøkler** (NO + EN): `hdr_workshop_architecture`, `err_architecture_missing` med graceful fallback i UI hvis SVG-en skulle mangle på disk.

**Samtidig:**
- Fjernet dupliserte `btn_remove`-oppføringer i `ui_i18n.json` som ble introdusert i v10.9.0 — nøkkelen fantes allerede fra tidligere (~linje 1191 NO / 2894 EN).

---

## v10.9.0 (2026-04-21)
### Workshop-arbeidsrom — delte innspill, notater og oppfølgingspunkter

**Nytt:**
- **Workshop-visning** (`nav → Workshop`) for live arbeids-sesjoner. To-kolonne-layout: workshop-plan (rendret fra `docs/workshop-plan.md`) til venstre; interaktive felt til høyre.
- **Tre delte seksjoner** med auto-save (debounce 600 ms):
  - **Ønskeliste** — fritekst-ønsker deltakere legger til. Enter eller "Legg til"-knapp for å poste; ✕ for å fjerne.
  - **Diskusjonsnotater** — en textarea per diskusjonspunkt (§6 Veien til produksjon, §7 Rolle, §8 Funksjoner, §9 Rettigheter). Seksjonstitler er i18n-drevet.
  - **Oppfølgingspunkter** — handling + eier + frist + avkryssingsboks for "ferdig". Teller viser åpne/totalt.
- **Delt tilstand**: alle autentiserte brukere leser og skriver samme `data/workshop_notes.json`. Atomisk skriving (`.tmp` → `replace`) så avbrutte lagringer ikke korrumperer filen. Oppdater-knapp for å hente andres input uten page-reload.
- **Backend**: nytt `app/web/routes/workshop.py` med `GET/POST /api/workshop/notes`. Normaliserer innkommende data (type-sjekk, strip, monotonisk id-tildeling for nye oppfølgingspunkter). Logger hver lagring med brukernavn + teller.
- **20 nye i18n-nøkler** (NO + EN) — nav, headers, placeholders, seksjonstitler, save-status. Nettstedet språklinjen styrer også Workshop-visningen.

**Begrensninger (ikke-blokkerende):**
- Ingen sanntids-push — samtidige redigeringer kan overskrive hverandre hvis to personer endrer samme felt uten å oppdatere. For workshop-bruk i dag er det akseptabelt; WebSocket-broadcast kan komme i senere release.
- Eksport av workshop-notater (markdown/CSV) ikke implementert — hent rå JSON via `/api/workshop/notes` om nødvendig.

---

## v10.8.0 (2026-04-21)
### Full migrasjon av Wiki / Integrasjonsguide til markdown-drevet mønster

**Rot-årsaken til at norsk og engelsk har blitt blandet i Wiki-fanen:** de 14+ integrasjonskortene i `integ-wiki` var hardkodet norsk HTML i `index.html`. GDAP-kortet jeg la til i v10.6.2 var det eneste språkbevisste, og fem påfølgende micro-releaser på det kortet kunne ikke adressere helheten. Denne releasen migrerer **alle 19 kort** til samme markdown-drevne mønster.

**Nytt:**
- **19 Wiki-kort, én kilde per kort.** Hvert kort henter innholdet fra `docs/api/{slug}/WIKI.md` (engelsk, kanonisk) med `WIKI.<lang>.md`-varianter for språkspesifikke versjoner. GDAP beholder sin eksisterende `INTEGRATION.md` for konsistens med Docs-fanen.
- **36 nye markdown-filer**: `WIKI.md` + `WIKI.no.md` for 18 integrasjoner (itglue, vpn, guacamole, unifi, fortigate, tailscale, also-cloud, uniweb, tls-monitor, microsoft-graph, claude, autotask-datto, connectwise, halo-psa, teams-webhook, smtp, power-bi, rest-api). Norsk-versjonene er trofaste ekstrakter av den opprinnelige hardkodede HTML-prosa; engelske versjoner er fullstendige oversettelser.
- **Generalisert frontend-loader** i `app-integrations.js`: `wikiLoadAllCards()` erstatter den GDAP-spesifikke `wikiLoadGdap()`. Én `WIKI_CARDS`-katalog definerer alle 19 kort. Lazy-load på første åpning av Wiki-fanen, parallell fetch av alle markdown-filer, språkprobing med stille fallback.
- **HTML integ-wiki-seksjonen går fra 1089 linjer hardkodet HTML til 151 linjer shell-kort.** Hvert shell har `data-i18n` for status-badge + tittel, og en `wiki-<slug>-body`-div som markdown-loaderen rendrer inn i.
- **20 nye i18n-nøkler**: `wiki_title_{slug}` × 19 + `err_could_not_load_doc` (NO + EN). Eksisterende `status_implemented`/`status_planned`/`status_partial`/`status_advanced` gjenbrukt for badge-tekster.

**Resultat:**
- UI-språk styrer nå hele Wiki-fanen konsistent, ikke bare GDAP-kortet.
- Innhold oppdateres ett sted per integrasjon (markdown-fila). Ingen HTML-duplisering mellom Wiki-fanen og Docs-fanen for integrasjoner som deler innhold.
- Mønsteret er åpenbart utvidbart — nye integrasjoner krever bare `docs/api/{slug}/WIKI.md` + en linje i `WIKI_CARDS`-katalogen.

**Merknader / vedlikehold:**
- Docs-fanen (som auto-skanner `docs/**/*.md`) vil nå også liste `WIKI.md` og `WIKI.no.md` under hver integrasjon. Dette er noe støy i filtreet, men ingen funksjonell feil. Filtrering av `.no.md` i Docs-viewer når UI er engelsk kan komme som oppfølging.
- Noen integrasjonskortene hadde eksisterende `INTEGRATION.md` med mer teknisk API-fokus; det nye `WIKI.md`-innholdet er operativt/oversiktlig prosa. Begge sameksisterer — to dokumenter per integrasjon med ulik målgruppe (operator vs. utvikler).

---

## v10.7.4 (2026-04-21)
### Norsk oversettelse av GDAP-dokumentasjonen

**Dok:**
- **Ny fil `docs/api/partner-center/INTEGRATION.no.md`** — fullstendig norsk oversettelse av Partner Center / GDAP-integrasjonsguiden. Den kanoniske `INTEGRATION.md` er på engelsk; norske UI-brukere fikk engelsk innhold rendret i Wiki-kortet (miks med norsk chrome-tekst). Language-switch-mekanismen fra v10.6.2 plukker nå opp `.no.md`-varianten når `_lang === 'no'` og viser norsk innhold konsistent. Engelsk UI faller fortsatt tilbake til den kanoniske engelske `INTEGRATION.md`.
- Oversettelsen beholder tekniske termer i engelsk hvor det er etablert praksis (API, OAuth 2.0, client credentials, `AuthMode`, `client_id`, osv.) og oversetter prosa og operatørsteg til norsk. Strukturen speiler 1:1 den engelske kilden.

---

## v10.7.3 (2026-04-21)
### GDAP-kort i Wiki-fanen: stille fallback fra språkvariant til kanonisk doc

**Bugfix:**
- **"doc not found: api/partner-center/INTEGRATION.en.md"-toast ved åpning av Wiki/Integrasjonsguide.** I v10.6.2 ble `wikiLoadGdap()` gjort språkbevisst — den prøver først `INTEGRATION.<lang>.md` og faller tilbake til `INTEGRATION.md`. Probe-kallet gikk via `apiFetch()` som viser en feil-toast på alle 4xx-responser _før_ fallback-logikken rekker å kjøre, så en manglende oversettelse lekket som en synlig feil. Rettet ved å bytte probe-kallet til rå `fetch()` — 404 på språkvariant er nå stille og fallbacken kjører uten støy. Det kanoniske fallback-kallet beholder `apiFetch()` så ekte feil (nettverk, 5xx) fortsatt surfacer normalt.
### Swagger / ReDoc render igjen (CSP-unntak for `/api/docs`)

**Bugfix:**
- **`/api/docs` og `/api/redoc` viste tom side.** FastAPIs Swagger UI og ReDoc bruker én inline `<script>`-blokk for å bootstrappe etter at CDN-bundle-et laster. App-wide CSP satte `script-src 'self' https://cdn.jsdelivr.net` uten `'unsafe-inline'`, så bootstrapen ble blokkert og siden forble blank. Lagt til et snevert CSP-unntak kun for disse to pathene som tillater `'unsafe-inline'` på `script-src` (Swagger UI / ReDoc er statiske upstream-verktøy uten user-generated content — XSS-overflaten er null). Resten av appen beholder stram script-src. `app/web/server.py` (_SecurityHeadersMiddleware).

---

## v10.7.1 (2026-04-21)
### JWT rotation grace period (lukker SECURITY.md §9 / #2)

**Sikkerhet:**
- **Gammel JWT-hemmelighet utløper nå 1 time etter rotasjon** (`_JWT_SECRET_GRACE_SECONDS = 3600` i `app/core/auth.py`). Før dette ble `jwt_secret_previous` beholdt på ubestemt tid — en lekket gammel hemmelighet kunne forfalske tokens til neste rotasjon. Nå er vinduet hardt begrenset: etter grace-perioden slettes både `jwt_secret_previous` og det nye `jwt_secret_previous_expires_at`-markeret automatisk ved neste dekode-forsøk, og tokens signert med den gamle hemmeligheten avvises.
- **In-flight-tokens får myk overgang**: grace-vinduet gir aktive brukere opptil 1 time til å få utstedt nye tokens naturlig (hver hitt på `/api/refresh`), uten at rotasjon tvinger øyeblikkelig re-login.
- **Backfill for eksisterende deployments**: hvis en deploy har et eldre `jwt_secret_previous` uten utløpsmarker (fra før denne endringen), backfiller første dekode-lesning et ferskt 1-times grace-vindu. Ingen tvungen re-login ved oppgradering.
- **Tre nye tester** i `tests/test_auth_sessions.py`: grace-valid, grace-expired-purge, legacy-backfill. Alle 11 auth-tester passerer.

**Dokumentasjon:**
- `docs/SECURITY.md §9` markerer issue #2 som Fixed med henvisning til implementasjon.

---

## v10.7.0 (2026-04-21)
### FortiGate-hardening, subnet-scan device-actions, backup-robusthet

**Nytt:**
- **FortiGate-provisioning hardet (CIS-aligned)** — `app/services/provisioning.py`: SSH/SCP/admin-sport hardening, DNS-over-TLS enforcement, NTP padding til 3-server CIS-krav, dedikert MGMT-port (fjernes fra hard-switch), og split UTM-policy (MGMT uten UTM for å bevare cloud-trafikk, non-MGMT med full UTM). Bootstrap-port 8443 + VDOM/SSL-felter persistes i kunde-config.
- **UniFi auto-discovery via DHCP Option 43** — FortiGate DHCP-scope konfigureres med inform-URL så UniFi-enheter adopteres automatisk mot partner-kontrolleren ved oppstart.
- **Inline device-actions i subnet-scan** — `app/web/static/app.js` runSubnetScan-tabellen har nå per-enhet-knapper for SSH-nåbare enheter: **Set-Inform** (preset `unifi.sybr.no` + custom URL-input), **Vis konfig** (henter running-config og lagrer auto-backup via `/api/network/save-config-backup`), og **Restart**. Kaller eksisterende ruter i `app/web/routes/unifi.py`.
- **Workshop-leveranser** — `docs/workshop-plan.md` (internt team-introduksjonsdokument) og `docs/msp-toolkit-architecture.svg` (visuelt kart over alle 13 integrasjoner). `docs/ARCHITECTURE.md` lenker til SVG-en.

**Bugfix / herding:**
- **Backup/restore-feilstier logger nå** (`app/core/encryption.py`): `unwrap_master_key()` og `import_master_key()` snevret fra `except Exception: return False` til spesifikke unntak (`cryptography.exceptions.InvalidTag`, `ValueError`, `TypeError`, `keyring.errors.KeyringError`), hver med informativ `log.warning`/`log.exception`. Suksess-stien uendret; False-returverdier bevart for bakover-kompatibilitet. Rationale: backup-restore er en krise-operasjon; silent False fra unwrap skjulte om problemet var feil passord, korrupt bundle eller keyring-feil.
- **`pyproject.toml` version bumpet fra 9.0.0 → 10.7.0** — manifestet hadde driftet fra runtime (som leser fra git-tag / `app/core/version.py`), noe som ville gitt build-verktøy feil metadata.

**i18n:**
- To nye nøkler lagt til i `ui_i18n.json` (NO + EN): `btn_actions` (Handlinger / Actions), `msg_enter_url` (Skriv inn en URL / Enter a URL). Øvrige 12 nøkler brukt av subnet-scan-actions fantes allerede.

**Utsatt til v10.7.1:**
- Per-customer RBAC-rollout (~25 ruter), JWT rotation grace-period, systematisk sweep av 102 bare `except Exception`-blokker, `vpn_backends`-dedup.

---

## v10.6.2 (2026-04-21)
### GDAP / Partner Center synlig i Wiki / Integrasjonsguide

**Dok / UX:**
- **GDAP-kort i Wiki-fanen** lastes nå dynamisk fra `docs/api/partner-center/INTEGRATION[.<lang>].md` via `/api/docs/file` og rendres med `marked` + `DOMPurify` (samme pipeline som Docs-fanen). Kortet ble aldri lagt til i den hardkodede `integ-wiki`-blokken, så selv om operator-guiden fantes i repo og Docs-fanen, var den usynlig i Wiki/Integrasjonsguiden der brukere leter. `app/web/static/index.html`, ny `wikiLoadGdap()` i `app/web/static/app-integrations.js`, lazy-trigger i `switchIntegTab()` (`app/web/static/app.js:968`).
- **i18n gjennomført:** status-badge og integrasjonsnavn bruker `data-i18n` (`status_implemented`, `integ_gdap`), lastestatus bruker `msg_loading`, og feilmelding bruker ny nøkkel `err_could_not_load_gdap_doc` (NO + EN lagt til i `ui_i18n.json`). Markdown-hentingen prøver først `INTEGRATION.<lang>.md` (f.eks. `INTEGRATION.en.md` hvis `_lang==='en'`) og faller tilbake til kanonisk `INTEGRATION.md` når en oversettelse ikke finnes — slik at engelsk UI speiler engelsk doc så snart den finnes.
- **Single source of truth** for GDAP-innhold: markdown-fila oppdateres ett sted og blir speilet i Wiki-kortet. Mønster er gjenbrukbart for de 14 andre Wiki-kortene dersom vi vil migrere bort fra hardkodet HTML.

---

## v10.6.1 (2026-04-21)
### Bugfix-pass — stabilitet for bakgrunnstasks og logging

**Bugfix:**
- **Fire-and-forget-tasks bevares til de fullfører.** asyncio holder kun svak referanse til tasks opprettet via `create_task()`, så uten ekstern sterk ref kan de bli garbage-collected midtveis (RUF006). Ny `fire_and_forget()`-helper i `app/core/utils.py` holder et sett-basert sterkt ref fram til `done_callback` fjerner det. Tatt i bruk i token-blacklist-persisting (`app/core/auth.py`), MSAL device-code-polling (`app/services/vpn_backends/azure.py`), ALSO pricing/renewal-cache (`app/web/routes/also.py` × 3) og Uniweb-sync (`app/web/routes/uniweb.py`).
- **`NameError: 'log' is not defined`** i to varme feilstier: `app/integrations/also_cloud.py:175` (ALSO API-respons ≥400) og `app/modules/m365_audit/collector.py:108` (M365 tenant-info pre-collect feiler). Begge steder brukte `log.warning(...)` mens modulene kun har `logger`. `collector.py` manglet også `import logging` + `logger = logging.getLogger(__name__)` helt. Begge rettet.
- **Late-binding closures i lambdaer (B023)** som fikk alle iterasjoner til å referere siste løkkevariabel: `vm` i `azure_compute.py:141`, `bk_client` i `azure_governance.py:155`, `chrome` i `reports.py:54`, og `_cfg`/`_ro2`/`_cfg2`/`_results_objs` i `audit.py:386,428`. Alle bundet som default-argumenter.
- **`bulk_audit_stream()`** i `app/web/routes/audit.py` manglet `Request`-parameter som trengs for `request.is_disconnected()`-sjekken i SSE-løkken.

**Opprydning:**
- Fjernet ubrukt `import json` i `app/web/routes/dashboard_overview.py` og duplikat `import os` i `app/web/routes/ssh.py`.

---

## v10.6.0 (2026-04-20)
### Operativ herding — service-supervision, helseprobe, automatisert backup

**Nytt:**
- **systemd-unit** under `scripts/msp-toolkit.service` med `Restart=on-failure`, sandboxing (`ProtectSystem=strict`, `PrivateTmp=yes`, `NoNewPrivileges=yes`) og journalctl-logging. `INSTALL.md` har nå en produksjonsseksjon som beskriver installasjon og drift via systemd.
- **Singleton-lock ved oppstart:** `app/web/server.py` tar en eksklusiv `flock` på `DATA_DIR/.instance.lock` i lifespan og avslutter med klar feilmelding hvis en annen instans allerede kjører. Forhindrer duplikate scheduler-kjøringer (audits, backups, webhooks) ved uhell-dobbeltstart.
- **`/api/health`-endepunkt** (public, returnerer `{status, uptime_seconds, version, db_ok, db_exists}`, HTTP 503 hvis DB ikke nåbar). Egnet for cron-curl eller eksterne monitoreringsverktøy. Lagt til i middleware-allowlist.
- **Automatisk backup-task** (`app_backup`, ukentlig lør 02:30, default **av** — aktiveres i Settings). Kaller samme `create_backup_sync()` som UI-knappen og logger størrelse/sti.
- **TLS cert expiry-sjekk** (`cert_expiry_check`, daglig 06:00): parser `/etc/ssl/tailscale.crt`, logger WARN ved <7 dager, ERROR etter utløp.
- **CI-pipeline** (`.github/workflows/ci.yml`): pytest på Python 3.11+3.12 og `pip-audit` mot `requirements.txt`.

**Sikkerhet:**
- Fjernet `verify=False` fra 6 httpx-klienter mot Guacamole (`app/web/server.py`, `app/web/routes/proxy.py` × 5). Backend er `http://localhost:8888` som default slik at verify-flagget var no-op, men fjerningen hindrer at en framtidig HTTPS-omkonfigurering stille aksepterer ethvert sertifikat.
- Dokumentert de resterende 6 legitime `verify=False`-bruksstedene med `SECURITY:`-kommentar: 4 pentest-scannere (scan'er misconfigurerte mål), UniFi device-discovery (self-signed fra fabrikk) og `scripts/migrate_fortigate_port.py` (FortiGate management-interface).
- **Plaintext-passord maskert i pentest-funn** (`app/modules/pentest/credential_tester.py`): SSH- og HTTP-default-credential-treff returnerer ikke lenger passordet i `title`/`detail`-feltene. Disse persisteres i audit-rapporter, PDFer og backups — tidligere lekkasje nå lukket.

**Bugfix:**
- `load_remediation_sync()` returnerte stille legacy-JSON-data hvis kalt fra en allerede kjørende event-loop. Nå kaster funksjonen `RuntimeError` med tydelig melding. Silent-stale-data-faren er borte.
- **DB-migreringer kjører nå i transaksjoner**: hvis en migration feiler halveis, rulles versjonsbumpen tilbake så databasen ikke blir værende i en delvis-migrert tilstand. Feilen re-reises slik at oppstart feiler tydelig.
- `time.sleep()` i async-handlere (`app/web/routes/proxy.py:477,518,542`) byttet til `await asyncio.sleep()`. Blokkering av event-loop under browser-start er borte; andre forespørsler serveres parallelt.

**Drift:**
- **Logg-rotasjon bumpet fra 5 MB × 3 → 100 MB × 20** (ca. 15 MB → 2 GB audit-trail). `app/web/server.py:244`.

**Dok:**
- In-app Docs → Overview viste hardkodet "v9.2.0"; nå lest dynamisk fra `/api/version`. Auditseksjons-teller rettet fra "23+" til "26" i tråd med README.
- Brukket lenke i `docs/api/README.md` (pekte til `it-glue/`, katalogen heter `itglue/`).

---

## v10.5.9 (2026-04-20)
### Sikkerhetsherding — TLS-verifisering + remediation-sync

**Sikkerhet:**
- Fjernet `verify=False` fra 6 httpx-klienter mot Guacamole (`app/web/server.py`, `app/web/routes/proxy.py` × 5). Backend er `http://localhost:8888` som default slik at verify-flagget var no-op, men fjerningen hindrer at en framtidig HTTPS-omkonfigurering stille aksepterer ethvert sertifikat.
- Dokumentert de resterende 6 legitime `verify=False`-bruksstedene med `SECURITY:`-kommentar slik at automatiske scannere og framtidige lesere ser at disse er bevisste: 4 pentest-scannere (scan'er misconfigurerte mål der TLS-verifisering vil skjule funn), UniFi device-discovery (self-signed er fabrikk-default) og `scripts/migrate_fortigate_port.py` (FortiGate management-interface).

**Bugfix:**
- `load_remediation_sync()` returnerte stille legacy-JSON-data hvis den ble kalt fra en allerede kjørende event-loop. Nå kaster funksjonen `RuntimeError` med tydelig melding om å bruke `await load_remediation()` i stedet. Kodestien brukes i praksis fra `run_in_executor`-tråder og utløser aldri feilen i normal drift, men silent-stale-data-faren er nå borte.

---

## v10.5.8 (2026-04-17)
### Brannmur-deny tilbake + admin-URL bruker port 8443

**Bugfix:**
- "Åpne brannmur på ny adresse"-knappen i deploy-resultatet brukte default port 443 (FortiOS lytter på 8443 etter bootstrap-hardening). Nå `https://<ip>:8443`.

**Sikkerhetsbaseline gjeninnført (zero-trust):**
- v10.5.4 fjernet alle inter-VLAN deny-policies da rolle-konseptet ble droppet — det var et feilgrep, baseline-isolasjon var et must.
- Hver VLAN får nå en `_<NAVN>-INTERNAL_DENY` som blokkerer trafikk til LAN, MGMT-port og alle andre VLAN.
- LAN får `_LAN-INTERNAL_DENY` mot alle ikke-MGMT VLANs.
- **MGMT-VLAN-detekt:** VLANs med navn som inneholder `mgmt` eller `management` (case-insensitive) får i stedet en `_<NAVN>-to-ALL` allow-policy med full tilgang til alle interne nett + WAN. MGMT VLAN får IKKE deny-rule.
- Detekteringen er navn-basert, ikke rolle-basert — Frank kan navngi VLANs fritt og fortsatt få MGMT-semantikk på ett av dem.

---

## v10.5.7 (2026-04-17)
### Provisjonering — fix `NameError: log` i deploy

**Bugfix:**
- `deploy_config()` brukte `log.info(...)` (innført i v10.5.5) men `provisioning.py` har modul-logger som heter `logger`, ikke `log` → `NameError: name 'log' is not defined` på hver deploy. Returnerte 502 etter 3ms — rot-årsak nå synlig i Feilsøking-fanen takket være v10.5.6-loggingen.
- Oppdaget to pre-eksisterende identiske bugs samme sted: `log.warning("Rejected CLI line: ...")` (SSH-deploy guard) og `log.warning("Site Manager lookup failed: ...")` (UniFi). Begge ville krasjet hvis de noen gang ble nådd. Alle 3 endret til `logger.`.

---

## v10.5.6 (2026-04-17)
### Provisjonering — deploy-feil logges til Aktivitetslogg

**Bugfix:**
- Deploy-feil ble bare vist som "Deploy feilet" i UI-en uten detaljer, og generiske exceptions ble ikke fanget i `provisioning.py`-routen → endte som 500 fra FastAPI uten kontekst. Nå fanges alle exceptions, og hvert utfall (start/success/partial/failed/crashed) skrives som strukturert entry i `activity_log`.

**Synlig i Settings → Aktivitetslogg:**
- `provisioning_deploy_started` — method, target_host, kunde
- `provisioning_deploy_completed` — N/M steg OK
- `provisioning_deploy_partial` — N/M OK, K feilet, første 10 feilende steg med feilmelding
- `provisioning_deploy_failed` — top-level eller FortiGate-branch feil med full feilmelding
- `provisioning_deploy_crashed` — type, melding, og siste 4 linjer av traceback

Crashes returneres nå som `IntegrationError` (502) i stedet for å lekke som generisk 500.

---

## v10.5.5 (2026-04-17)
### FortiGate deploy — sentralisert variabel-resolusjon

**Bugfix (kritisk):**
- `_deploy_via_rest` brukte `customer.get("port", 443)` fra wizard step 1, som ikke inneholder porten. Hver REST-kall gikk til `192.168.1.99:443` (intet lyttende) → 30s timeout per kall × ~50 kall = ~25 min å feile. Nå løses porten fra `_resolve_fortigate_conn` med korrekt presedens.

**Nytt:**
- `_resolve_fortigate_conn(steps, target_host)` — én sannhetskilde for alle FortiGate-tilkoblingsvariabler (`host`, `port`, `vdom`, `verify_ssl`, `api_token`, `admin_user`, `admin_password`). Presedens:
  1. Wizard step 1 (eksplisitt input)
  2. Aktiv kundes `config.json` (`FortiGateHost/Port/VDOM/VerifySSL/AdminUser`)
  3. Keyring (`fortigate_api_token`, `fortigate_admin_password`, `fortigate_admin_user`)
  4. Hardkodede defaults (port `8443` post-bootstrap, vdom `root`, verify `False`, user `admin`)
- `deploy_config` logger nå start-info: `Deploy via rest to 192.168.1.99:8443 (vdom=root, customer=Ferro..., has_token=True, has_pw=True)` — synlig i `msp_toolkit.log`.
- Tidlig fail med tydelig feilmelding hvis host/token/passord mangler (i stedet for å henge i 25 min).

---

## v10.5.4 (2026-04-17)
### FortiGate-provisjonering — fjernet rolle-systemet

**Bryter med tidligere atferd:**
- VLAN-rolle (`corporate`/`guest`/`iot`/`server`/`mgmt`) er fjernet helt fra wizard og backend. VLAN-navnet driver alt nå (address-objekter, policy-navn, alias).
- Hver VLAN får én standard policy: `VLAN → WAN, accept all, NAT, full UTM`. Spesialcase (web-only for gjest, no-UTM for mgmt, etc.) konfigureres manuelt i FortiGate-GUI etter generering.
- MGMT_ZONE (gruppering av VLAN99 + port10) fjernet. Den fysiske MGMT-porten (`port10`) får sin egen policy `MGMT-ACCESS-to-ALL` som tillater tech-laptop full tilgang til alle interne nett + WAN.
- Inter-VLAN deny-matrisen, `LAN-to-MGMT`, `LAN-to-SRV`, `MGMT-to-ALL`, `INTER-VLAN_DENY-ALL` osv. fjernet — FortiOS implicit deny dekker det som ikke er eksplisitt tillatt.

**UI:**
- "Rolle"-kolonnen fjernet fra `Steg 2: Nettverk`-VLAN-tabellen. Brukeren kan navngi VLANs fritt (DMZ, Lab, Backup, hva som helst) uten å være låst til 5 forhåndsdefinerte oppførsler.
- Kort hjelpetekst under tabellen forklarer at avansert policy-konfigurasjon gjøres i FortiGate etterpå.

**Internt:**
- Magic VLAN ID-sjekker (`if vid == 20`, `if vid == 30` osv.) i REST-deploy-pathet er fjernet. VPN-pool default = LAN-subnett `.240–.254`, override via `network["vpn_pool_subnet"]`.
- Default-suggested VLAN-template (`Servere/Gjest/IoT/Management`) sender ikke lenger `role`-felt.
- `mgmt_phys_subnet` for fysisk MGMT-port: default = LAN-subnett med tredje oktett +100 (f.eks. `10.25.0.0/24` → `10.25.100.0/24`). Override via `network["mgmt_phys_subnet"]`.

---

## v10.5.3 (2026-04-17)
### FortiGate provisjonering — kritiske template-feil rettet

**Bugfix:**
1. **Tidssone:** `set timezone 27` (Namibia/Belgrade) → **26** (Brussels/Copenhagen/Madrid/Paris). Gjelder både CLI-template og REST-pathet i `harden_security`. Override via `services["fortigate_timezone_id"]`.
2. **IP-konflikt på MGMT:** Fysisk MGMT-port (`port10`) hadde samme `/24` som VLAN99 (to FortiGate-IPer i samme subnet → ARP/ruting-kaos). MGMT-port er nå i eget `/24` (default = MGMT-VLAN-subnet med tredje oktett +1, f.eks. `.99` → `.100`). Override via `network["mgmt_phys_subnet"]`.
3. **DNS-domene:** Default `"local"` (reservert for mDNS, bryter Apple/Linux-discovery) → kunde-domene hvis satt, ellers `<hostname>.lan`.
4. **FortiGuard tunneling:** `autoupdate tunneling set status enable` → **disable** (forrige tvang updates via tunnel-proxy som ikke fantes → updates feilet).
5. **DHCP for MGMT:** Manglet før (header-kommentaren lovet "DHCP on MGMT subnet"). Lagt til DHCP-server på `port10` med kort lease (1t, range `.100–.150`).

**Andre forbedringer:**
- NTP-default fra 1 → 3 servere (`0/1/2.pool.ntp.org`) — CIS krever ≥2.
- Fjernet eksplisitt `DENY-ALL`-policy med ugyldig `srcintf any`/`dstintf any` (FortiOS < 7.4 avviser, og implicit deny finnes uansett).
- MGMT_ZONE: `set intrazone allow` så VLAN99 ↔ port10 kan kommunisere innenfor sonen.

---

## v10.5.2 (2026-04-17)
### FortiGate bootstrap — fjernet automatisk trust-host

**Bugfix:**
- `factory_bootstrap` satte trust-host til `0.0.0.0/0` (allow-all) på den nye API-brukeren — usikkert, og syntaksen var dessuten ugyldig (FortiOS forventer `IP MASK`, ikke CIDR). Hele trust-host-blokken fjernet. Trust-host konfigureres nå manuelt per miljø via FortiGate GUI/CLI etter bootstrap.

---

## v10.5.1 (2026-04-17)
### FortiGate bootstrap — credentials persistering og recovery

**Bugfix (kritisk):**
- `factory_bootstrap` returnerte admin-passord og API-token kun til browseren — ved PC-krasj/lukket fane var credentials uopprettelige. Nå lagres begge automatisk i keyring under aktiv kunde (`fortigate_admin_password`, `fortigate_admin_user`, `fortigate_api_token`).
- `FortiGatePort` ble ikke oppdatert til 8443 etter bootstrap (CIS hardening flytter admin-GUI fra 443 → 8443) — kunden ble uleselig fra toolkitet etterpå. Nå settes porten korrekt automatisk.
- API-token ble logget i plaintext til `msp_toolkit.log` via `log.info("API key output: %s", output[:400])`. Tokenet maskes nå før logging.

**Nytt:**
- `GET /api/fortigate/credentials/{customer_id}` — henter lagrede credentials (technician-rolle).
- "Last ned credentials"-knapp i FortiGate-konfigurasjonskortet — laster ned credentials som `.txt` for aktiv kunde.
- Activity-log entry `fortigate_bootstrapped` og `fortigate_credentials_viewed` for revisjon.
- `scripts/migrate_fortigate_port.py` — engangs-migrering for eksisterende kunder med `FortiGatePort=443`; prober 8443 med lagret token og oppdaterer config.
- `FortiGateBootstrappedAt` og `FortiGateApiUser` lagres i kundens config.

**Auto-fill:**
- `fgBootstrapAutoFill` setter nå port til **8443** (ikke 443) etter bootstrap.

---

## v10.5.0 (2026-04-16)
### GDAP Partner Center — delegert admin for alle kundetenanter

**Ny funksjonalitet:**
- GDAP (Granular Delegated Admin Privileges) integrasjon med Microsoft Partner Center
- Én multi-tenant app-registrering i partner-tenant erstatter per-kunde app-registreringer
- Partner Center API-klient: kundeoppdagelse, GDAP-relasjoner, abonnementer
- Hybrid auth-modus: GDAP og legacy per-kunde auth kjører side om side
- `AuthManager.from_gdap()` — opprett auth med partner-credentials for enhver kundetenant
- `get_auth_for_customer()` — automatisk velger riktig auth-modus per kunde
- GDAP-tilgangsvalidering via endpoint-probing (users, secureScores, conditionalAccess, Intune)

**API-endepunkter (6 nye):**
- `POST /api/gdap/setup` — lagre partner-credentials med validering
- `GET /api/gdap/status` — GDAP-konfigurasjonsstatus
- `POST /api/gdap/validate/{tenant_id}` — test Graph-tilgang for én kunde
- `GET /api/gdap/customers` — oppdag kunder fra Partner Center
- `POST /api/gdap/import` — importer valgte GDAP-kunder til lokal registry
- `POST /api/gdap/refresh` — synkroniser kundeliste med Partner Center

**Frontend:**
- GDAP-integrasjonskort i Settings med credentials-oppsett og tilkoblingstest
- Kundeoppdagelse-dialog med GDAP-status, roller og import
- GDAP-badge på kundelisten, credential-expiry skjult for GDAP-kunder
- i18n-støtte (norsk + engelsk) for alle GDAP UI-elementer

**Database:**
- Migrasjon 12: `gdap_customers` tabell for Partner Center synkronisering
- `AuthMode` felt på CustomerContext (`"legacy"` / `"gdap"`)

**Teknisk:**
- `HttpxClientSecretCredential` uendret — GDAP bruker samme OAuth2-flow
- EXO-seksjoner markeres som utilgjengelig for GDAP-kunder (krever per-kunde cert)
- Audit-stream og bulk-audit dispatcher automatisk basert på AuthMode
- 163 tester bestått, ingen regresjoner

---

## v10.4.0 (2026-04-10)
### Sikkerhetsherding, UniFi Site Manager, kodequalitet

**Sikkerhet (kritisk):**
- Route-level auth på alle ~60 endepunkter (settings, tailscale, uniweb, backup, history, fortigate, vpn)
- Krypteringsnøkkel-eksport krever nå admin-rolle
- Nmap input-validering: kun gyldig IP/hostname/CIDR (maks /24), blokkerer flag-injection
- RDP-passord skrives aldri til disk, temp-profil slettes etter 5 sekunder
- SSRF blokkert: proxy validerer mot RFC1918, link-local, cloud metadata, IPv6 private
- `/audit_data/`, `/guacamole/`, `/api/logs` fjernet fra offentlige stier

**Sikkerhet (høy/medium):**
- CLI allowlist for FortiGate SSH-deploy (kun config/edit/set/next/end)
- `unsafe-eval` fjernet fra CSP, `object-src:none` og `base-uri:self` lagt til
- Lokal terminal krever admin-rolle
- Activity log: append-only per-linje kryptering (O(1) skriving)
- Master key backups kryptert med PBKDF2+AES-256-GCM (maskin-spesifikk passphrase)
- Backup restore begrenset til backup-dir eller hjemmemappe
- Admin-passord maskert i generert FortiGate CLI-config og API-respons
- SSH host key fingerprint logges for audit trail
- AES-GCM v2 med Associated Authenticated Data (AAD)
- Full SHA-256 token hash, passord-policy styrket (min 10 tegn, spesialtegn, common-check)
- Token blacklist økt til 10 000, provisioning sessions auto-utløper etter 1t

**UniFi Site Manager — maksimal datautnyttelse:**
- UniFi-fanen faller tilbake til Site Manager API når ingen per-kunde config finnes
- Klikkbare UniFi-kort med inline detaljpanel
- Detaljpanel: console-info, KPI-kort, tidsstempler, sub-site tabell med
  WAN uptime, varsler, gateway uptime, ISP org/ASN, internet issues
- Async-lastet per-enhet tabell (modell, IP, firmware, oppdateringer, notat)
- ISP-ytelseskort (download/upload, latency, pakketap — siste + 7d snitt)
- WAN & gateway-sikkerhet per site (IDS-modus, IPS-regler, per-WAN issues)
- Alle tilgjengelige felt fra v1/hosts, v1/sites, v1/devices, v1/isp-metrics hentet
- «Oppdater nå» henter alltid fersk data (10k req/min rate limit)
- Auth lagt til på 6 uautentiserte device-endepunkter

**Provisioning:**
- UniFi deployment via controller REST API (nettverk/VLAN)
- Credential-oppløsning: per-kunde → app settings → Site Manager API
- WireGuard: ValueError ved manglende privatnøkkel i stedet for PLACEHOLDER

**Kodequalitet:**
- Delt `format_uptime()` utility erstatter 5 dupliserte implementasjoner
- 47 nye tester (163 totalt): provisioning, scanner-validering, passord-policy, SSRF, uptime
- i18n: 8 hardkodede norske strenger flyttet til ui_i18n.json (NO+EN)
- TUI: FortiGate/UniFi moduler aktivert, åpner web UI
- Fjernet død kode: `UniFiClient` alias, `adopt_device()`, `UniFiSiteManagerHost`

## v10.3.0 (2026-04-09)
### Pentest v2, provisioning wizard, webhook-varsler

**Pentest — nye moduler:**
- `tls_auditor.py` — probe per TLS-versjon (1.0/1.1/1.2/1.3), full sertifikat-inspeksjon
  (utløpsdato, SAN-coverage, selvsignert, svake signatur-algoritmer), cipher-styrke
- `subdomain_takeover.py` — fingerprint-basert deteksjon av dangling-CNAME takeover
  for 20+ tjenester (S3, GitHub Pages, Heroku, Azure, Shopify, Fastly osv.)
- CMS-scanner, SMB-enumerering, segmenteringstest, skannehistorikk

**Pentest — UX og i18n:**
- Verktøy gruppert i faser: recon → service → exploit
- «Hvorfor + hvordan fikse»-forklaring per funn
- Alle hardkodede strenger erstattet med i18n-nøkler

**Pentest — nye endepunkter:**
- `POST /api/pentest/tls-audit` — krever `host`, valgfri `port` (default 443)
- `POST /api/pentest/takeover-check` — tar enten `subdomains[]` eller `domain`
  (auto-enumererer via `dns_tester` hvis kun domene oppgis)

**Provisioning wizard v2:**
- FortiGate REST API-deployment (`PUT /api/v2/cmdb/`)
- Deterministisk subnet-autogenerering fra kundenavn
- Manuell kundeopprettelse uten M365 (`POST /api/customers/add-manual`)
- Subnet-forslag-endepunkt (`POST /api/provisioning/suggest-subnets`)
- UI: felt-labels, auto-fill fra aktiv kunde, forbedret layout

**Webhook-varsler:**
- `webhook_sender.py` — rike webhook-notifikasjoner med pentest-alert-integrasjon

**Feilrettinger:**
- `loadRemediation` kalte `.json()` på allerede parset `apiFetch`-resultat
- UniFi-rute importerte poller fra feil modul
- Pentest: subdomain-strenger fra `dns_tester` dict-er
- Pentest: TLS-sertifikat parsing via `cryptography` (CERT_NONE workaround)
- HSTS, CSP, X-XSS-Protection sikkerhetsheadere lagt til

## v10.2.0 (2026-04-09)
### Integrert pentest-modul, compliance-dashboard, asset-inventar

**Pentest-modul (ny):**
- Port-skanning via nmap med SYN/versjon/stealth-modus
- Sårbarhetsjekk med innebygd CVE-database for vanlige tjenester
- Web-applikasjonssikkerhet: OWASP-headers, cookies, SSL, sensitive stier
- Standard-passord testing: SSH, FTP, SNMP community, HTTP basic auth
- DNS-sikkerhet: zone transfer (AXFR), DNSSEC, subdomain-oppdagelse
- Profesjonell pentest-rapport (HTML/PDF) med severity-gradering og remediation
- Alt krever admin-rolle og logges til aktivitetslogg
- UI: Pentest-fane under Nettverk med scan-form, KPI-kort, funn-tabell

**Compliance-dashboard (ny):**
- GET /dashboard/compliance — samlet CIS/NIST/ISO-status per kunde
- Gjennomsnittlig compliance-prosent og kategori-breakdown

**Asset-inventar (ny):**
- GET /dashboard/assets — alle assets: nettverksenheter, SSH, VPN, domener, abonnement

**Bulk FortiGate-backup:**
- POST /fortigate/backup-all — parallell backup på alle brannmurer

**Per-kunde varslingsterskler:**
- Backend for per-kunde alert overrides klar

---

## v10.1.0 (2026-04-08)
### Compliance dashboard, asset inventar, bulk backup, per-kunde terskler

**Compliance-dashboard (ny):**
- GET /dashboard/compliance — samlet CIS/NIST/ISO-status på tvers av kunder
- Pass/fail/partial-telling fra audit metrics per kunde
- Gjennomsnittlig compliance-prosent og kategori-breakdown
- RBAC-filtrert

**Unified asset-inventar (ny):**
- GET /dashboard/assets — alle assets samlet: nettverksenheter, SSH, VPN, domener, abonnement
- Nettverksenheter fra FortiGate + UniFi live-poller
- SSH-verter med nåbarhetsstatus
- Domener fra Uniweb med utløpsdatoer
- ALSO-abonnement med priser og fornyelsesdatoer

**Bulk FortiGate-backup:**
- POST /fortigate/backup-all — kjører backup parallelt på alle FortiGates
- "Backup alle"-knapp i FortiGate-taben (krever admin)

**Per-kunde varslingsterskler:**
- get_effective_threshold() sjekker per-kunde overrides først, fallback til global
- Klar for frontend-konfigurasjon per kunde

---

## v10.0.0 (2026-04-08)
### Multi-VPN, UniFi samlet visning, bruker-RBAC UI, FastAPI lifespan, FortiGate forbedringer

**Multi-VPN støtte:**
- Flere samtidige VPN-tilkoblinger (var begrenset til én)
- Connection registry erstatter global singleton-state
- Per-profil disconnect, status viser alle aktive tilkoblinger
- OpenVPN: separate prosesser og logger per tilkobling
- WireGuard/FortiGate: dynamiske interface/conn-navn

**UniFi samlet visning (ny):**
- GET /api/unifi/all — alle UniFi-enheter på tvers av kunder
- KPI-kort: enheter, online/offline, klienter, kunder
- Enhetskort med modell, firmware, klienter, oppgraderingsvarsel
- RBAC-filtrert

**Bruker-RBAC UI (ny):**
- 🔑-knapp per bruker åpner kundetilgangspanel
- Avkrysningsliste over alle kunder med nåværende tilgang markert
- Lagre/fjern/avbryt handlinger
- API: GET/PUT /api/auth/users/{id}/customers

**FastAPI lifespan:**
- Migrert fra deprecated @app.on_event("startup") til lifespan context manager
- Fjerner DeprecationWarning, legger til shutdown-logging
- Fikset test_routes.py import-krasj (guac config lest ved import-tid)
- Alle 116 tester passerer inkl. test_routes.py

**FortiGate forbedringer:**
- Deny-regler markert som positiv segmentering (grønn + 🛡)
- Accept-regler uten UTM-profiler markert i oransje
- FortiGate REST API: robust mot list-responser (rotårsak for 'list has no attribute get')
- Nettleser-verktøy: snap Chromium cgroup-fix, fullskjerm, isolert profil

---

## v9.9.0 (2026-04-07)
### FortiGate-overhaul, utvidet brannmurdata, nettleser-fix

**FortiGate samlet visning:**
- Fjernet "Enheter (Live)"-tab — alt samlet i FortiGate-taben
- Alle FortiGates på tvers av kunder med live-polling og intervallkontroll
- Utvidet detaljvisning med klikk på kort:
  - SSL VPN aktive brukere (bruker, IP, varighet)
  - Alle brannmurregler (fjernet 15-grense) med sikkerhetsprofiler per regel
  - any/any/any-regler markert i rødt, regler uten UTM-profil i oransje
  - Statiske ruter, SD-WAN helsestatus (latency/jitter/pakketap)
  - FortiGuard-lisensutløp med fargekoding
  - Admin-kontoer med advarsel på manglende 2FA/trusthost
  - Logg-diskbruk i prosent
  - VLAN-detaljer (type, alias, rolle) fra CMDB
- Fikset bug der detaljpanel forsvant ved første klikk

**Nettleser-verktøy fikset:**
- Snap Chromium cgroup-problem løst — bruker binær direkte fra snap-mount
- Chromium-vindu fyller hele 1920×1080 Xvfb-skjermen
- Isolert profil per sesjon (--user-data-dir)
- Feilmelding med detaljer ved Chromium-krasj i stedet for svart skjerm

---

## v9.8.0 (2026-04-07)
### Performance, UI-forbedringer, ALSO-matching

**Performance:**
- VPN stats: subprocess/file I/O kjøres i thread pool (blokkerte event loop)
- Proxy: delt httpx-klient med connection pooling (ny TCP per request → gjenbruk)
- Kundetags: 60s TTL-cache med invalidering (dekrypterte JSON per forespørsel)
- DB-queries: samlet i én tilkobling der mulig
- Frontend: defer på CDN-scripts, cached DOM-queries i tabellsortering,
  én DOM-scan for i18n i stedet for tre

**ALSO ↔ Uniweb matching:**
- Normalisert fuzzy-matching (A/S vs AS)
- M365-sjekk bruker service_display (lesbare navn)
- Fjernet falsk "M365 not tracked in ALSO"-alarm — MX→Exchange = M365 bekreftet
- Domene-E-post-Lisens forenklet: kun ekte dobbeltbetalinger flagges

**UI:**
- Responsiv nav: kollapser til hamburger ved 1100px (var 767px)
- Dropdown-menyer fungerer korrekt i hamburger-meny
- Større hamburger-ikon
- Integrasjonsstatus-prikker klikkbare med popover-forklaring
- FortiGate-indikator sjekker faktiske kundedata (ikke tom innstilling)

---

## v9.7.0 (2026-04-07)
### Datakvalitets-overhaul, live DNS-sjekker, falskt-negativ eliminering

**Dataproveniensystem (ny arkitektur):**
- Alle _parse_*-funksjoner returnerer nå has_data: True/False
- Manglende data er None, ikke 0 — nedstrøms kode vet forskjellen
- Risk-score: manglende MFA/SecureScore inflerer/deflerer ikke lenger
- Compliance-mapping: manglende audit-fil = "info" (ikke "fail")
- Helsescore: kunder uten data får "?" (ikke "F")

**Live DNS e-postsikkerhet (ny):**
- Innebygd MXToolbox-lignende sjekker (SPF/DKIM/DMARC/MX)
- 16+ DKIM-selektorer probes + Uniweb-baserte custom selectors
- DMARC via CNAME (hosted DMARC) følges automatisk
- DNS timeout = "kan ikke verifiseres" (ikke "feil")
- API: POST /api/dns/check og /api/dns/check-bulk
- ALSO↔Uniweb normalisert fuzzy-matching (A/S vs AS)

**Alerts forbedret:**
- Utløpte sertifikater/domener: "UTLØPT for X dager siden" (ikke "-X dager")
- Alle tre utløps-alarmer (SSL, domene, lisens) fikset konsekvent
- audit_age_days og is_stale på alle metrikk-oppslag

---

## v9.6.0 (2026-04-07)
### Per-kunde RBAC, API-dokumentasjon, DOM-cache, integrasjonstester

**Per-kunde tilgangsstyring (ny):**
- Ny modul app/core/rbac.py med komplett RBAC-system
- Bruker eksisterende customer_access-tabell i databasen
- Admin-rolle har alltid full tilgang (bypass)
- Bakoverkompatibel: ingen RBAC-rader = full tilgang (gradvis utrulling)
- 15 dashboard-endepunkter filtrert per brukerens kundetilgang
- Kundeliste og kunde-bytte validerer tilgang
- Tilgangsnekt returnerer 403

**API-dokumentasjon (ny):**
- Swagger UI tilgjengelig på /api/docs
- ReDoc tilgjengelig på /api/redoc

**Frontend-optimalisering:**
- DOM-element cache ($()-hjelper) for hyppig brukte elementer
- Reduserer gjentatte getElementById-oppslag

**Nye tester (18 stk):**
- test_auth_sessions.py: token-oppretting, blacklisting, sesjons-CRUD
- test_rbac.py: tilgangskontroll, filtrering, admin-bypass, bakoverkompatibilitet
- Totalt 116 tester (opp fra 98)

---

## v9.5.0 (2026-04-07)
### Sikkerhetshardening, token-revokasjon, persistent logging, kodekvalitet

**Sikkerhet:**
- SQL injection-beskyttelse: frozenset-whitelister for dynamiske UPDATE-feltnavn
- JS-injeksjon fikset i Uniweb CDP-scraper: all brukerinput via json.dumps()
- Path traversal blokkert i open-folder — kun audit-mappen er tilgjengelig
- SSL-verifisering i proxy konfigurerbart via MSP_PROXY_VERIFY_SSL env-var
- Chromium auto-discovery via shutil.which() i stedet for hardkodet sti

**Token-revokasjon (ny):**
- Server-side sesjoner via sessions-tabellen (eksisterte, nå aktiv)
- Login oppretter sesjon, logout sletter sesjon + blacklister access-token
- Refresh validerer at sesjonen finnes før nye tokens utstedes
- In-memory token-blacklist for umiddelbar invalidering ved logout

**Persistent logging (ny):**
- RotatingFileHandler skriver til DATA_DIR/msp_toolkit.log (5 MB × 3 filer)
- Logger beholdes på tvers av server-restart

**Kodekvalitet:**
- Nye DB-indekser: ssh_hosts(customer_id), vpn_profiles(customer_id) (migration 11)
- 15+ stille except/pass erstattet med logging (encryption, activity_log, scheduler m.fl.)
- Frontend: _cleanupViewTimers() rydder alle intervaller ved view-bytte
- Fikset versjon-flash: fjernet hardkodet v3.5.0 fra HTML

**Bugfiks:**
- _parse_licenses: rsplit(None,3) for flerords lisensnavn
- _parse_spf_dmarc: støtter DKIM sel1/sel2-format i tillegg til DKIM (M365)

---

## v9.4.0 (2026-04-07)
### Kundeoversikt-filtre, rapportarkiv, QBR batch-rapport, trenddiagrammer og offline-indikator

**Kundeoversikt-forbedringer:**
- Nye filtre: Har M365 / Har FortiGate / Trenger oppsett / Utdatert audit
- Integrasjonsbadger per kunde: M365 (blå), FG (oransje), UF (cyan), ? (trenger oppsett)
- Stale audit-indikator: viser dager siden siste audit eller "Aldri auditert"
- API returnerer has_m365, has_fortigate, has_unifi flagg per kunde

**Rapportarkiv (ny dashboard-fane):**
- Oversikt over alle lagrede rapporter gruppert per kunde
- Kollapsbar detaljvisning med filantall, størrelse, PDF/HTML-status
- Slett enkeltrapporter (krever admin)
- Massesletting: slett eldre enn 3/6/12 måneder med frigjort-størrelse rapport

**QBR Batch-rapport:**
- Ny "QBR"-knapp i kundeoversikt
- Genererer samlet HTML-rapport over alle auditerte kunder
- KPI-oppsummering: snitt risikoscore, snitt MFA, karakter-fordeling
- Skriv ut til PDF via nettleseren (Ctrl+P)

**Trenddiagrammer:**
- Ny SQLite-tabell health_snapshots (schema v10)
- Ny scheduler-oppgave: ukentlig snapshot av helsescorer (søndag 23:00)
- Dashboard-API /api/dashboard/trends returnerer historiske data
- Sparkline-grafer i kundeoversikten bruker nå ekte trenddata

**Offline-indikator:**
- Rød banner vises når nettleseren mister tilkobling
- Auto-dismiss med suksessmelding når tilkoblingen gjenopprettes

---

## v9.3.0 (2026-04-07)
### Sikkerhet, planlagte rapporter, dashboard-forbedringer og konfigurerbare terskler

**Sikkerhetsforbedringer:**
- RBAC på alle kunde-endepunkter: delete krever admin, øvrige krever innlogget bruker
- Auth-sjekk (Depends) på alle audit, TLS og kunde-routes
- WebSocket-autentisering via cookie (foretrukket) + first-message auth, query-param som fallback
- Aktivitetslogg bruker nå ekte brukernavn fra JWT i stedet for getattr-fallback

**Planlagte rapporter:**
- Ny scheduler-oppgave: ukentlig rapport (mandag 07:00) — sender PDF til konfigurert mottaker
- Teams-webhook-varsling med sammendrag (antall sendt, feil)
- Rapport-e-post med HTML-body og PDF-vedlegg

**Dashboard-forbedringer:**
- Auto-refresh (2 min intervall) med toggle-knapp
- CSV-eksport for alle dashboard-faner (varsler, helse, kostnader, domener, fornyelser, kunder)
- Klikk-navigasjon: varsler, helse-tabell og fornyelser navigerer til kundedetaljer
- VPN-status returnerer warnings-felt for utilgjengelige enheter

**Konfigurerbare terskler (ny innstillings-fane):**
- MFA-dekningsterskel (standard 80%)
- Secure Score-terskel (standard 75%)
- Credential-varsel dager (standard 30)
- Varselintervall (standard 6 timer)
- Minimum passordlengde (standard 8)
- Trenger audit (standard 30 dager)

**Scheduler-forbedringer:**
- Crash recovery: maks 5 konsekutive feil, deretter auto-deaktivering med logg
- Eksponentiell backoff ved gjentatte feil (1m, 2m, 4m, 8m, 16m)
- Task-status persisteres til disk — overlever restart
- consecutive_failures synlig i scheduler-status API

**Feilhåndtering:**
- 15+ stille catch-blokker i app.js erstattet med console.warn/showToast
- Remediation-oppdatering viser feilmelding til bruker
- Periodiske polls (VPN badge, notifikasjoner, sesjon) dokumentert som forventet

---

## v9.2.0 (2026-04-06)
### Kryssintegrasjon-intelligens, FortiGate/UniFi deep integration og sikkerhetshardening

**Kryssintegrasjon-intelligens:**
- Lisensoptimalisering: ALSO betalt vs M365 faktisk bruk, flagg over/under-lisensiert
- Nettverksinventar per kunde: UniFi APs/switcher + FortiGate brannmurer
- Sikkerhetsrapport: MFA%, SPF/DKIM/DMARC, firmware, trusler, karakter A-D
- Kostnadsoversikt: ALSO MRR + Uniweb månedlig per kunde
- Domene-Email-Lisens-kjede: detekterer dobbelbetaling
- Unified Domain Dashboard: Uniweb + TLS + SPF/DKIM/DMARC

**FortiGate Deep Integration:**
- Trusseloversikt: IPS/virus/botnet/webfilter siste 7 dager
- Brannmurregel-audit: score 0-100, flagg any-any og no-logging
- Config backup: POST for FortiOS 7.6+, backup-historikk med nedlasting
- FortiGate detail-panel i nettverksfanen

**UniFi Deep Integration:**
- Klientliste: alle enheter med signal, båndbredde, tilkoblet AP
- WiFi-helse: per-AP satisfaction, interferens, rogue AP-deteksjon
- Live data i nettverks sub-site visning
- 2FA-støtte for UniFi SSO-innlogging

**Infrastruktur-kobling:**
- SSH-verter og VPN-profiler koblet til kunder
- Kunde-dropdown i SSH/VPN-skjemaer
- Kundenavn-kolonne i SSH/VPN-lister
- Infrastruktur-kort på kundedetalj

**Sikkerhet:**
- CSRF-beskyttelse middleware
- Request body size limit (10MB)
- JWT secret rotation support
- asyncio.Lock på global state
- Passordpolicy: min 8 tegn
- Audit-logging for sensitive operasjoner
- Standardisert error response format

**UI/UX:**
- Sorterbare tabellkolonner
- SVG-ikonsystem
- Tailscale flyttet til Nettverk-meny
- Uniweb-fornyelser utvidet til 365 dager med 4 hastegrader
- Full i18n for Fornyelser-fane

**Dokumentasjon:**
- 6 nye API INTEGRATION.md-filer
- docs/api/README.md med 15 integrasjoner

---

## v9.1.0 (2026-04-06)
### Uniweb-integrasjon, kundekort-redesign og UI/UX-forbedringer

**Uniweb Integrasjon:**
- Kundeimport fra Uniweb — modal med søk, "Velg alle", bekreftelsesdialog
- DNS-scraping fra Uniweb domeneredigering (A, AAAA, CNAME, MX, TXT, NS, SRV, CAA)
- Uniweb konto-ID vises på kundekortet
- Partner sub-kunde-håndtering (65+ kunder fra SYBR AS partnerkonto)
- Forbedret sync-fremdrift: pulserende animasjon, forløpt/gjenstående tid, kontonavn
- Oppsummering ved fullført synk (kontoer, domener, feil)
- Fornyelser-fane i dashboard med tre hastegrader (Kritisk <7d, Snart 7-14d, Kommende 14-30d)

**Kundekort:**
- Seksjonsikoner og visuell hierarki for Hosting-kortet
- DNS-antall badge per domene
- Utløpsdatoer fargekodet (oransje <30d, rød <7d)
- E-post som full tabell
- "Sist oppdatert" med relativ tid på norsk
- Loading-spinner ved DNS-ekspandering

**Import-modal:**
- Bekreftelsesdialog og feilvisning per konto
- Overordnet konto-kolonne for sub-kunder
- Escape-tast, responsiv layout, "X av Y valgt" teller

**UI/UX:**
- Hardkodede farger erstattet med CSS-variabler
- Card hover med lift-effekt
- Staggered fade-in animasjon
- Input focus-glow
- Forbedret nav aktiv-tilstand
- Smooth accordion-transitions

---

## v9.0.0 (2026-04-05)
### Web browser, Web RDP, HTTPS, and clipboard support via Guacamole

**Web browser via Guacamole VNC:**
- In-app remote browser using Xvfb + Chromium + guacamole-common-js
- Launches headless Chromium inside an Xvfb virtual display
- VNC server exposes the display; guacamole-common-js connects directly from the browser
- No external VNC client needed — fully embedded in the web UI

**Web RDP via Guacamole:**
- Apache Guacamole integration for native RDP connections to Windows hosts
- guacamole-common-js direct embed (no guacamole-client WAR needed)
- Connect to any host with RDP credentials stored in the host database

**HTTPS via Tailscale certificates:**
- Automatic TLS using Tailscale-issued certificates
- Secure access over Tailscale network without manual certificate management

**Host password field:**
- New password field in host edit form for storing RDP/VNC credentials
- Used by Guacamole RDP and VNC connections

**Full clipboard support:**
- Bidirectional clipboard between local machine and remote session
- Powered by guacamole-common-js clipboard API
- Copy/paste works seamlessly in both browser and RDP sessions

**Auto-scale display:**
- Remote desktop display automatically scales to fit the container
- Responsive sizing on window resize

**Fullscreen support:**
- Toggle fullscreen mode for remote browser and RDP sessions
- Clean, distraction-free remote access experience

**Changelog server-side rendering:**
- Changelog page rendered server-side with tabs (Siste / Alle)
- "Siste" tab shows the latest release; "Alle" tab shows full history

---

## v8.9.0 (2026-04-06)
### Quality, security & UX improvements

**Security hardening:**
- Fix XSS vulnerability in user management UI (escape user IDs in onclick handlers)
- Add SQL field name whitelists in auth, VPN, and SSH update queries
- Escape breadcrumb onclick handler values
- Add quote escaping to esc() function (&quot; and &#39;)
- Add try/catch to raw fetch() calls without error handling

**New features:**
- SSH key import validation — verify key format, show SHA256 fingerprint
- Settings dirty-flag — warn on unsaved changes before navigating away
- Audit progress bar — floating indicator with section name and percentage
- TLS certificate auto-discovery from configured SSH/FortiGate/UniFi hosts
- ALSO subscription pricing auto-cache (top 10 on renewals page load)

**Data layer:**
- Remediation tracking migrated from JSON files to SQLite (schema v8)
- Auto-migrate existing JSON data on first access, preserves files for rollback
- SSH key push/revoke logged to global activity log

**Error handling & i18n:**
- ~50 English error messages translated to Norwegian across 16 route files
- 10 API endpoints stopped leaking internal errors to clients
- 11 bare except:pass blocks replaced with specific types + debug logging

**Performance:**
- UniFi Site Manager SSO token cached in memory (1h TTL)
- Rate limiting: 120 req/min general, 10 req/min for VPN/audit endpoints

## v8.8.0 (2026-04-06)
### Azure VPN — headless server support via OpenVPN 3

**Azure VPN connection via openvpn3-client:**
- Replaced pure-Python OpenVPN tunnel with `openvpn3` (apt package `openvpn3-client`)
- OpenVPN 3 handles large JWT tokens and EKM key derivation natively — no patching needed
- Credentials piped via stdin (`AzureAD` + JWT token)
- Session management via `openvpn3 sessions-list` / `session-manage --disconnect`

**PKCE paste-back auth flow (headless compatible):**
- Removed browser popup auth — unusable on remote/headless servers
- New flow: web UI shows PKCE link → user opens on any device → copies redirect URL back
- Silent refresh for subsequent connections using cached refresh token
- Token scope fixed: `{APP_ID}/.default` (was `openid profile` which gave wrong audience)

**Token management:**
- MSAL refresh tokens cached in encrypted app storage (`azure_vpn_tokens/`)
- Refresh token exported to `/etc/openvpn/msp/refresh_token.txt` for cron auto-refresh
- Cron job refreshes token every 45 minutes, restarts VPN with new token

**Key debugging findings documented:**
- `Connection reset` after TLS = JWT truncated (USER_PASS_LEN=128) or wrong audience
- `Key Method #2 write failed` = control channel buffer too small (TLS_CHANNEL_BUF_SIZE=2048)
- Token `aud` must be `c632b3df-fb67-4d84-bdcf-b95ad541b5c8`, NOT `00000003-...` (Graph)
- OpenVPN 2.x cannot handle Azure AD JWT tokens without source patching
- OpenVPN 3 is the correct solution — same library used by Microsoft's Azure VPN Client

## v8.7.0 (2026-04-03)
### MRR / pricing tracking for ALSO subscriptions

**Subscription pricing cache (schema v7):**
- New `also_subscription_details` table: subscription_id, quantity, unit_price, monthly_cost, currency, fields_json, priceable_items_json
- Auto-caches when user clicks to expand a subscription detail (GetSubscriptionWithAddons)
- Extracts quantity from Fields (seat count), price from PriceableItems (purchase price)
- Zero bulk API calls — pricing builds up gradually as users browse licenses

**MRR in renewals table:**
- Three new columns: Qty, Unit Price, Monthly — show "-" when not yet cached
- Per-customer MRR subtotal rows between customer groups
- KPI cards: "MRR (cached)" showing total monthly recurring revenue + "Priced" count
- LEFT JOIN from also_renewals → also_subscription_details for live pricing data
- CSV export includes qty, unit_price, monthly_cost columns

**MRR in unified customer dashboard:**
- ALSO integration card shows "18 subs · MRR 4,500 NOK" when pricing is cached

## v8.6.1 (2026-04-03)
### Refactor: app.js split, API fixes, comprehensive documentation

**app.js split into 7 modules (10.4k → 7 files):**
- `app.js` (6,680) — core: i18n, auth, nav, settings, customers, overview, charts, files, audit, theme, init
- `app-infra.js` (2,497) — hosts, SSH, VPN, live dashboard, AI console, provisioning, FortiGate, UniFi, terminal
- `app-dashboard.js` (135) — alerts dashboard, health scores
- `app-also.js` (242) — ALSO renewal action list, bulk actions, CSV export, PDF download
- `app-tailscale.js` (450) — Tailscale device management, detail panel, routes, keys
- `app-tls.js` (224) — TLS/certificate monitor
- `app-integrations.js` (189) — showView override, docs tabs, ALSO Cloud config
- No bundler — separate `<script>` tags, globals shared automatically

**Tailscale fix: online detection**
- API uses `connectedToControl` (bool), NOT `online` — field doesn't exist
- All devices were showing offline despite being connected
- Fixed in `_normalize_device()` to check `connectedToControl` first

**ALSO term detection fix:**
- BillingStartDate is original creation date, NOT current term start
- Date-math produced wrong terms (4mo, 5mo) for Annual NCE subscriptions
- Now uses service name patterns: `(NCE)` = Annual, `monthly` keyword = Monthly, `Azure Plan` = Pay-as-you-go, `Reserved` = Reserved, `Adobe` = Annual
- Same logic in license view, renewals table, and PDF report via shared `_detect_term()` helper

**PDF report auth fix:**
- Browser `<a href>` links don't send JWT token → 401 error
- Changed to `fetch()` with `Authorization: Bearer` header, downloads as blob

**API documentation (3,691 lines):**
- `docs/api/tailscale/API_REFERENCE.md` (1,829 lines) — full v2 API from OpenAPI spec: 70+ endpoints, all device fields, OAuth scopes, webhooks
- `docs/api/also-cloud/API_REFERENCE.md` (1,018 lines) — full SimpleAPI: 62 endpoints, all response models from PHP wrapper, 10 known gotchas
- `docs/api/tailscale/INTEGRATION.md` — our usage, connectedToControl fix, ?fields=all
- `docs/api/also-cloud/INTEGRATION.md` — parentAccountId gotcha, rate limiting, caching
- `docs/api/fortigate/INTEGRATION.md` — monitor/CMDB endpoints, CIS checks
- `docs/api/unifi/INTEGRATION.md` — controller + direct + Site Manager
- `docs/api/microsoft-graph/INTEGRATION.md` — 50+ Graph endpoints, permissions
- `docs/api/tls-monitor/INTEGRATION.md` — stdlib ssl/socket approach

## v8.6.0 (2026-04-03)
### Alerts dashboard, health scores, bulk renewals, PDF reports, audit in unified

**Alerts Dashboard (Dashboard → Alerts):**
- Morning overview: one tab showing everything that needs attention
- Aggregates credential expiry (<30d/expired) + ALSO renewal expiry (<30d/expired)
- KPI cards: Total / Critical / Warning / Info
- Sorted tables for credentials and renewals with severity badges
- Green "All clear" state when nothing needs action

**Customer Health Scores (Dashboard → Health):**
- Per-customer 0-100 health score with A-F grade
- Deductions: no M365 (-10), expired creds (-30), expiring creds (-15/-5), expired ALSO subs (-20), bad audit grade (-20/-10)
- KPI cards: Average score, Healthy (A/B), Warning (C/D), Critical (F)
- Full table sorted worst-first with colored grade badges and issues list
- Bulk DB queries (no N+1) — reads audit_metrics + also_renewals in one pass

**Bulk Actions in Renewals:**
- Select-all checkbox in table header
- "Mark selected handled" — bulk marks multiple renewals at once
- "Export CSV" — downloads all visible renewals as CSV file
- Vendor filter dropdown — filter table by Microsoft/Adobe/Letsignit/etc
- "PDF Report" button — generates downloadable PDF via WeasyPrint

**PDF Renewal Report:**
- `GET /api/also/renewals/report?days=365` — generates PDF
- Jinja2 HTML template (`app/reports/templates/renewal_report.html`)
- Grouped by customer, color-coded status (red/orange/green)
- Summary stats: total, expired, <30d, <60d
- WeasyPrint conversion, downloads as `renewal_report.pdf`

**Audit Results in Unified Dashboard:**
- Unified customer overview now shows latest audit metrics
- Risk grade (A-F with color), Risk score, Secure Score %, MFA coverage %
- Total users, users without MFA — all from `audit_metrics` table
- Audit date shown for context

## v8.5.0 (2026-04-03)
### Unified customer dashboard, scheduled ALSO renewal scan, renewal action list

**Unified Customer Dashboard:**
- New **"Overview"** button in customer sub-nav bar (next to M365/History/Report/Files/Licenses)
- Single-page view aggregating all integrations for the active customer — zero external API calls
- Integration status cards: M365 (cred expiry), FortiGate (host), UniFi (host), ALSO (subscription count + alerts), SSH hosts (count)
- ALSO renewal table: expired + expiring <90d shown prominently, rest collapsed
- SSH host grid with reachability status
- M365 credential expiry with color-coded warnings
- `GET /api/customer/{id}/unified` endpoint — aggregates config + DB cache

**Scheduled ALSO Renewal Scan:**
- Integrated into existing scheduler loop alongside audit cycle
- Scans 10 customers per cycle with 3s delay between calls
- Skips customers already scanned in last 24h
- Auto-stops on 403/429 rate limit detection
- Full customer base cached in ~10 scheduler cycles, zero manual intervention

**Renewal Action List (Dashboard → Renewals tab):**
- DB table `also_renewals` (schema v6) with UPSERT caching
- Auto-cache: viewing licenses for any customer automatically caches their renewal data
- KPI cards: Cached / Expired / <30d / 30-60d / 60-365d / >1 year
- Action table with: checkbox (handled), customer, product, vendor, **term** (Monthly/Annual/etc), renewal date, days left, status, notes
- Progress bar for batch scanning with live customer name display
- Batch scanning: 10 per click, 3s delays, skips recently cached, stops on rate limit
- Term column calculated from billing_start → contract_end date span

**ALSO API fixes:**
- `GetSubscriptions` now uses correct `parentAccountId` parameter (was `AccountId`)
- `GetSubscription` / `GetSubscriptionWithAddons` use correct `accountId` (camelCase)
- License table shows real ALSO fields: ServiceDisplayName, VendorDisplayName, AccountState
- Click-to-expand subscription detail: Fields (seats/config) + PriceableItems (pricing)
- Term column in license view (Monthly/Quarterly/Annual/Multi-year)
- Fixed naive datetime comparison bug that caused all renewals to show as 0

## v8.4.1 (2026-04-03)
### fix: Tailscale online detection + full device management

**Critical fix:**
- Added `?fields=all` to device list API call — `online` field was missing from default response, causing all devices to show as offline

**New device management features:**
- **Click any device card** → opens full detail panel with all device info
- **Rename device**: inline name field + save (sets `givenName` via API)
- **Authorize/deauthorize**: approve pending devices or revoke authorization
- **Key expiry toggle**: enable or disable key expiry per device
- **Remove device**: delete from tailnet with confirmation
- **Subnet route management**: view all advertised routes per device, approve or disable individual routes with one click
- **Exit node indicator**: badge on cards + detail panel shows exit node status
- **Tags editor**: comma-separated tag input with auto `tag:` prefixing, save to API
- Device cards now show: subnet router badge (🔀), exit node badge (🚪), unauthorized warning (⚠)

**New API endpoints:**
- `POST /api/tailscale/device/{id}/authorize` — authorize/deauthorize
- `POST /api/tailscale/device/{id}/name` — rename device
- `POST /api/tailscale/device/{id}/key` — toggle key expiry
- `GET /api/tailscale/device/{id}/routes` — get advertised + enabled routes
- `POST /api/tailscale/device/{id}/routes` — approve/set routes

**Service additions (`tailscale_api.py`):**
- `authorize_device()`, `rename_device()`, `set_key_expiry()`
- `get_device_routes()`, `set_device_routes()`
- Normalized device now includes `advertised_routes`, `enabled_routes`, `is_exit_node`, `client_connectivity`

## v8.4.0 (2026-04-03)
### Tailscale integration — device inventory, auth keys, VPN mesh monitoring

**Tailscale API service (`app/services/tailscale_api.py`):**
- Shared httpx client with bearer token auth, lazy initialization
- Device list with normalized fields: hostname, OS, Tailscale IP, online status, last seen, stale detection, key expiry
- Auth key CRUD: list, create (reusable/ephemeral/preauthorized), revoke
- Device management: remove, update tags
- Human-readable "ago" strings for Norwegian locale

**Tailscale routes (`app/web/routes/tailscale.py`):**
- `GET /api/tailscale/status` — config check + quick device count
- `GET /api/tailscale/devices` — full inventory with KPI aggregates (online/offline/stale/expiring keys)
- `DELETE /api/tailscale/device/{id}` — remove device from tailnet
- `POST /api/tailscale/device/{id}/tags` — update device tags
- `GET /api/tailscale/keys` — list auth keys with expiry
- `POST /api/tailscale/keys` — create auth key with options
- `DELETE /api/tailscale/keys/{id}` — revoke key
- `POST /api/tailscale/test` — test API key before saving

**Dashboard UI (Infrastruktur → Tailscale):**
- KPI summary row: total / online / offline / stale (>7d) / expiring keys
- Device cards with strict 3-row grid: name+OS icon / Tailscale IP+user / stats (OS, version, hostname, status, last seen, key expiry, tags)
- Sorted: online first, then alphabetical
- Update-available badge on devices
- Auth key management panel: create keys with reusable/ephemeral/preauthorized options, view/revoke existing keys
- Key creation shows one-time key value with copy-ready styling

**Settings (Integrations panel):**
- New Tailscale card with API token + tailnet config
- Test connection shows device count on success
- Saved via global app settings (same pattern as ALSO/UniFi/IT Glue)

**Tests: 39 → 49:**
- 6 route tests: unconfigured status, unconfigured devices/keys, missing API key, mocked device list with KPI assertions
- 4 service unit tests: device normalization (online/offline), human_ago strings, timestamp parsing

**i18n:** 17 new keys (NO + EN) for Tailscale UI

## v8.3.0 (2026-04-03)
### Structured errors, TLS monitoring, expanded tests, grid alignment fix

**Structured error handling:**
- New `app/core/exceptions.py` — typed exceptions: `ValidationError` (400), `NotFoundError` (404), `AuthError` (401), `IntegrationError` (502), `ConflictError` (409)
- Global `@app.exception_handler(ToolkitError)` in server.py — catches all subclasses, returns consistent `{"error", "error_type", "detail?"}` JSON
- Routes can now `raise ValidationError("...")` instead of manually building JSONResponse

**TLS/Certificate monitoring (new feature):**
- New service `app/services/tls_monitor.py` — scans endpoints for cert validity, expiry, protocol strength, cipher security
- `check_endpoint_tls()` — async single-endpoint check via `run_in_executor` (no new dependencies, stdlib ssl+socket)
- `scan_customer_endpoints()` — concurrent batch scan with aggregate summary (valid/expired/expiring_soon/weak_tls/errors)
- Detects: expired certs, expiring < 30 days, weak protocols (TLS < 1.2), weak ciphers (RC4/DES/NULL/EXPORT/MD5)
- New routes: `POST /api/tls/check` (single) and `POST /api/tls/scan` (batch)
- **Full dashboard UI**: new "TLS Monitor" tab under Infrastruktur dropdown
- Single endpoint check: host/port input with detailed cert card (subject, issuer, SAN, expiry, protocol, cipher)
- Batch scan: auto-collects endpoints from SSH hosts (network devices), FortiGate fleet; deduplicates by host:port
- KPI summary row (total/valid/expired/expiring/weak) + sortable results table (worst-first)
- 26 new i18n keys (NO + EN) for TLS UI

**Test coverage expanded (15 → 39 tests):**
- Error-path tests: ToolkitError serialization, exception handler integration
- Payload validation: empty body, null values, invalid params, custom limits
- TLS route tests: missing host 400, empty endpoints 400, mocked check/scan
- TLS service unit tests: unreachable host, empty list, blank hosts, weak cipher/protocol detection
- Static file tests: index serves HTML, 404 on missing files, path traversal blocked
- Dashboard edge cases: empty customer list, mocked customer data

**Grid alignment fix (v8.2.1):**

## v8.2.1 (2026-04-03)
### fix: strict 3-row grid alignment for all dashboard cards

- **FortiGate cards**: KPI row uses fixed 90px height, no justify-content centering; all fields always rendered with `-` fallback
- **SSH Host cards**: group badge always visible (shows `-` if none); action buttons always rendered (RDP/Web UI disabled with opacity when N/A); 2-col grid layout for actions
- **Site detail**: all 13 info rows always rendered (Registrert, Siste backup, Siste tilkobling show `-` instead of being hidden); sub-sites table always rendered with empty-state row; totals row includes WLAN column
- **CSS**: `.card-grid--kpi > .card` — removed `justify-content: center`, `align-items: center`, `min-height`; replaced with fixed `height: 90px` + `padding: 16px 8px`
- Cache bust: CSS/JS imports bumped to `v=831`

## v8.2.0 (2026-04-03)
### ALSO licenses, architecture refactor, i18n completion, API tests

**ALSO Cloud Marketplace — License viewing:**
- New "Licenses" tab in customer detail for ALSO-linked customers
- Shows subscription count, total seats, MRR summary cards
- Full table: product name, SKU, quantity, unit price, monthly cost, status
- Shared ALSO client with session reuse (prevents 403 rate-limit blocks)
- 19 new i18n keys for license UI (both NO + EN)

**Architecture refactor — thinner routes, services layer:**
- Extracted FortiGate fleet polling (130 lines) into `services/fortigate_api.py`
- Extracted network quick-audit (280 lines) into new `services/network_audit.py`
- Split `customers.py` (700 lines) into `customers.py` (161) + `dashboard.py` (542)
- Route file sizes: unifi 712→480, fortigate 382→258, customers 700→161
- All hardcoded Norwegian removed from extracted code

**i18n completion — dynamic JS strings:**
- 140+ remaining hardcoded Norwegian strings in app.js wrapped in t() calls
- Covers: VPN, FortiGate dashboard, provisioning, network scan, SSH, error messages
- Also: showToast messages, tooltips, placeholders, option labels, form labels, status text
- UniFi SM labels, firewall rules headers, AI assistant status, device lists
- All new keys (140+) added to both NO and EN sections in ui_i18n.json

**API smoke tests:**
- New `tests/test_routes.py` with pytest-asyncio smoke tests
- Covers settings, language, dashboard, activity log, scheduler, system info
- Auth dependency mocking for protected endpoints

**Bug fixes:**
- Fixed hardcoded "Laster kundedata..." in customer detail (now i18n)
- Fixed hardcoded "Ukjent" fallbacks in status/search endpoints
- Fixed "Sertifikat utløper" → English in status warnings

---

## v5.4.0 (2026-04-03)
### Massive i18n — 81 new keys, all views covered

**Complete i18n of all remaining hardcoded strings:**
- 81 new i18n keys added in both languages (NO + EN)
- Total: 765 keys with perfect match between languages
- Covers all 15+ views: nav menus, dashboard tabs, hosts, SSH, VPN, terminal, AI, provisioning, integrations, log, settings
- All buttons, labels, placeholders, select options, status texts
- Login/setup form fully translated
- No remaining hardcoded Norwegian strings in static HTML

---

## v5.3.0 (2026-04-03)
### i18n audit, customer detail meta, breadcrumb i18n

**Complete i18n audit:**
- Breadcrumbs: all hardcoded "Infrastruktur", "Verter & SSH" etc replaced with t()
- Cmd+K: "Innstillinger" → t('hdr_settings')
- Health cards: "Secure Score" → t('lbl_secure_score')
- 8 new i18n keys (bc_hosts_ssh, bc_network, bc_ssh_keys etc)
- 676 keys in both languages, perfect match

**Customer detail extended:**
- Shows "days since last audit" (e.g. "2025-03-12 (23d)")
- Shows total warning count with color coding
- Warnings row with orange color when >0

---

## v5.2.0 (2026-04-03)
### Remaining tasks completed — report button, login polish, file counter

**Latest report in customer detail:**
- "Report" button that finds and opens the latest HTML report for the customer
- Uses GET /api/latest-report endpoint
- Shows toast if no report exists

**Improved login page:**
- Rounded corners with shadow
- Version number displayed under "MSP Toolkit"
- Fetched dynamically from /api/version

**Audit statistics after completion:**
- Shows number of generated files in addition to sections and time
- Format: "26 sections (2m 34s · 48 files)"

**Improved error handling:**
- 5xx errors after auto-retry now show retry button
- i18n for "Server error"

---

## v5.1.0 (2026-04-03)
### Browser notifications, latest report API

**Browser push notifications:**
- Web Notification API — shows alert when audit completes and tab is in background
- Requests permission at startup
- Shows section count and time in notification

**Latest report API:**
- GET /api/latest-report — finds newest HTML report for active customer
- Returns URL, filename and run date
- Ready for use in customer detail

---

## v5.0.0 (2026-04-03)
### Filter badges, retry UX, template fix, 120+ features

**Active filter badges:**
- Search, dropdown filters and grade filters shown as removable pills above the table
- Click ✕ on a badge to remove that filter
- "Clear all" link to reset everything
- Only shown when at least one filter is active

**Improved error handling:**
- 5xx server errors now show retry button (showToastWithRetry) after 2 attempts
- Hardcoded error messages replaced with i18n keys
- Network errors already had retry from earlier

**Template literal fix:**
- All ${t(...)} in static HTML confirmed removed
- Zero remaining template errors in static HTML

---

## v4.9.0 (2026-04-03)
### Scroll-to-top, history with grade badge, premium polish

**Scroll-to-top button:**
- Floating ↑ button in bottom right that appears on scroll >300px
- Smooth animation in/out with opacity and transform
- Blue circular button with shadow

**History with grade badge:**
- Grade badge (A-F with color) shown inline in history table per audit run
- Hover tooltip with Grade, Score, MFA% per row
- Backend now returns metrics summary per run from history API
- Row hover effect in history

---

## v4.8.0 (2026-04-03)
### Keyboard nav, audit timer, info tooltip

**Keyboard navigation in dashboard table:**
- ↑/↓ arrow keys to move between customer rows
- Enter to open selected customer detail
- Blue outline on focused row
- Auto-scrolls to visible position

**Audit timer:**
- Records start time when audit begins
- Shows "Completed: 26 sections (2m 34s)" when finished
- Time formatted as Xm Ys or just Xs

**Customer info tooltip:**
- Hover over customer name in dashboard → tooltip with Grade, Score, MFA%, Secure Score, Users
- Multiline native tooltip

---

## v4.7.0 (2026-04-03)
### Tab title progress, sticky header, recent customers

**Audit progress in browser title:**
- Tab shows "Audit 45% — SYBR MSP Toolkit" during audit run
- Resets automatically when audit completes/fails/cancels

**Sticky table header:**
- Dashboard table column headers stick on scroll
- Max-height 70vh with internal scroll in table card

**Recent customers in Cmd+K:**
- Last 5 visited customers shown at top of command palette (⏱ icon)
- Shown when search field is empty — quick switch without typing
- Stored in localStorage

**Cleanup:**
- Removed duplicate i18n keys (btn_prev, btn_next)
- 668 i18n keys in both languages, perfect match

---

## v4.6.0 (2026-04-03)
### Pagination, grade border, i18n fix

**Pagination in dashboard table:**
- 25 customers per page with Previous/Next navigation
- Page counter: "1 / 10"
- Resets to page 1 on filter/search

**Grade color code on row border:**
- 3px left border on table rows with grade color (green/blue/orange/red)
- Subtle visual indicator for quick scanning

**Bugfix:**
- Removed duplicate i18n key msg_last_saved with {date} placeholder

---

## v4.5.0 (2026-04-03)
### Auto theme, improved search, Escape reset

**Automatic dark/light mode:**
- Respects OS prefers-color-scheme on first visit
- Stored preference in localStorage overrides OS preference

**Improved customer search:**
- Now also searches in Tenant ID
- Counter shows "X / Y customers" with i18n
- Improved placeholder text

**Escape resets grade filter:**
- Press Escape in dashboard to clear active grade filter

---

## v4.4.0 (2026-04-03)
### Shortcut hints, KPI tooltips, dashboard timestamp, sorting fix

**Shortcut hints in buttons:**
- Ctrl+Shift+A shown in Run Audit button with subtle kbd styling
- Ctrl+, shown in Settings button tooltip

**KPI health cards with tooltips:**
- Hover over health indicator → shows threshold values
- Border highlight on hover for visual feedback
- Explains what is critical/warning

**Dashboard "Last updated" timestamp:**
- Timestamp of last data load shown in top right

**Bugfix:**
- Sorting by grade crashed when customers lacked metrics (toLowerCase on number)

---

## v4.3.0 (2026-04-03)
### Grade filter, print CSS, confetti celebration

**Clickable grade badges:**
- Click A/B/C/D/F badge in dashboard table to filter
- Toggle — click again to remove filter
- Toast notification about active filter
- Scale-hover animation on badges

**Print-friendly styling:**
- @media print CSS hides nav, header, footer, modals
- Card shadows removed, borders simplified
- Tables compressed for A4

**Confetti celebration on A grade:**
- After completed audit with Grade A → CSS confetti animation
- 40 colored particles with fall-rotation
- Toast: "Grade A — excellent security posture!"
- Confetti removed automatically after 5 seconds

---

## v4.2.0 (2026-04-03)
### Relative times, double-click audit, grade distribution

**Relative timestamps:**
- "just now", "5 min ago", "2 hours ago" in notifications and activity log
- timeAgo() helper function with i18n support
- Replaces absolute dates in notifications and customer activity

**Double-click → audit:**
- Single click on customer row in dashboard = customer detail
- Double click = switches customer and starts audit directly
- Tooltip explains the interaction

**Grade distribution under donut:**
- Compact A:5 · B:8 · C:3 display under grade chart
- Color-coded letters with count

---

## v4.1.0 (2026-04-03)
### Theme shortcut, terminal font control, copy summary

**Ctrl+Shift+T — toggle theme:**
- Keyboard shortcut for quick toggle between dark/light mode
- Added to shortcuts modal

**Terminal font size:**
- A-/A+ buttons in terminal toolbar
- Size stored in localStorage (10-24px)
- Updates xterm.js in real time with auto-fit

**Copy customer summary:**
- "Copy to clipboard" button in customer detail
- Copies customer name, domain, grade and KPIs as text
- Useful for Teams/Slack sharing

---

## v4.0.0 (2026-04-03)
### Polished details, footer statistics, bugfix

**Last audit date in active customer bar:**
- Shows date of last audit run next to grade badge
- Fetched from /api/dashboard after status loads

**Footer statistics:**
- Subtle line: "X customers · Y audits · Z warns"
- Updates automatically when dashboard loads

**Customer detail bugfix:**
- Loads overview data automatically if cache is empty
- Fixes "Customer not found" when navigating from customer list

---

## v3.9.0 (2026-04-03)
### Animated KPIs, integration status

**Animated count-up KPI numbers:**
- Dashboard KPI numbers animate from 0 to value with ease-out cubic curve
- 900ms animation, smooth and professional
- Supports suffix (/100, %)

**Global integration status in header:**
- 3 colored dots: FortiGate, UniFi, Email
- Green = configured, gray = not configured
- Checked at startup from /api/settings
- Compact pill design with tooltip

---

## v3.8.0 (2026-04-03)
### Favorites, warnings preview, VPN redesign

**Favorite customers:**
- Click star on customer card to mark as favorite
- Favorites sorted to top of list
- Stored in localStorage (no backend change)
- Hover animation on star icon

**Warnings preview in dashboard:**
- Warning count shown under customer name in dashboard table
- Yellow ⚠ indicator with count

**VPN view redesigned:**
- Card-based layout with status dot (green glow on connection)
- Animated pulsing dot on connection
- Empty state with icon and description
- All texts i18n-ized (12 new keys)
- Improved buttons with btn-sm

---

## v3.7.0 (2026-04-03)
### Health indicators, bulk operations, customer activity

**M365 Health Indicators:**
- 6 color-coded cards in M365 status: Risk Score, MFA, Secure Score, Users, Without MFA, CA Policies
- Green/orange/red dot based on threshold values
- Loaded from /api/dashboard after status loads

**Bulk operations in customer list:**
- Checkbox per customer card for multi-select
- Action bar: bulk delete with confirmation
- Counter for selected customers
- Cancel/reset bulk selection

**Customer activity log:**
- Filtered activity view per customer in detail view
- GET /api/activity-log?customer=X for server-side filtering

---

## v3.6.0 (2026-04-03)
### Customer activity, scope picker, report fix

**Activity log in customer detail:**
- Filtered view of last 15 events for active customer
- Icon per event type, timestamp and user
- Backend: GET /api/activity-log?customer=X filters the log

**Improved audit scope picker:**
- Sections grouped in cards: M365, Azure with visual frame
- "All" checkbox per group for quick on/off
- Section count per category

**Report fix:**
- PDF: table-layout:fixed restored for WeasyPrint compatibility
- Badge white-space:nowrap prevents "CRITICAL" from wrapping
- Adjusted column widths in action plan
- Tech report: TOC activates correct tab before scrolling

---

## v3.5.0 (2026-04-03)
### Improved audit comparison

**Visual diff bar in comparison:**
- Colored horizontal bars show the magnitude of change per metric
- Green for improvement, red for deterioration
- Hover effect on rows
- More visually intuitive than just numbers

---

## v3.4.0 (2026-04-03)
### Customer notes in detail view

**Inline notes per customer:**
- Textarea in customer detail view for free-text notes
- Save button with visual confirmation (green "Saved ✓")
- "Last saved" timestamp
- Encrypted storage per customer (notes.md)
- Uses existing backend API (GET/POST /api/customer/notes)
- All texts i18n-ized (NO + EN)

---

## v3.3.0 (2026-04-03)
### i18n cleanup — all hardcoded strings removed

**23 new i18n keys (Norwegian + English):**
- Onboarding wizard: title, step titles, step descriptions
- Remediation: header, status labels, messages, tooltips
- Dashboard KPIs: MFA average, Outdated >30d
- Customer cards: Score/MFA/Last prefixes, status tooltips, button texts
- All strings now use t() function with fallback

---

## v3.2.0 (2026-04-03)
### Upgraded customer cards, onboarding step wizard

**Customer cards redesigned:**
- Grade badge (A-F) with color coding on left side of card
- Status dot: green (audit OK), gray (no audit), orange (not configured)
- Inline metrics: Score, MFA%, last audit date
- Entire card clickable → customer detail view
- More compact layout with btn-sm buttons

**Onboarding step wizard:**
- Empty customer list shows 3-step visual guide: Add → Set up M365 → Run audit
- Numbered circles with descriptions
- Large CTA button: "+ New customer"

---

## v3.1.0 (2026-04-03)
### Dashboard KPIs, clickable audit sections

**Dashboard extended to 5 KPI cards:**
- Total customers | Avg risk score | MFA average | Needs attention | Outdated >30d
- MFA average color-coded: red <80%, orange <95%, green 95%+
- Outdated counter shows customers without audit in last 30 days

**Clickable audit sections:**
- Click a row in audit table to expand all warnings
- Hover effect on rows for visual feedback
- Expandable detail panel with all warnings listed
- "+X more ▼" badge indicates additional warnings

---

## v3.0.0 (2026-04-03)
### Report viewer, remediation, and premium polish

**Inline Report Viewer:**
- Fullscreen modal with iframe to view reports directly in the app
- Header with report name + "New tab" and "Close" buttons
- Generated HTML reports show "View in app" button instead of auto-opening

**Remediation Tracking:**
- Click-based status toggle: Open → In Progress → Done → Ignored
- Progress bar with percentage display in customer detail
- Per-recommendation notes, user attribution and timestamp
- API: GET/POST /api/remediation + GET /api/remediation/summary
- Activity logging of status changes

**Backend:**
- Remediation endpoints with encrypted storage per customer
- Static file serving with path traversal protection

---

## v2.9.0 (2026-04-03)
### New audit sections, CSS polish, session handling, report font

**3 new M365 Audit sections (26 total):**
- **Defender for Office 365** — security alerts and incidents from Security Graph
- **OneDrive Sharing** — external sharing, anonymous links, sharing analysis
- **Compliance Score** — Microsoft Compliance Manager score and improvement actions
- All registered in collector.py for automatic execution

**CSS Polish:**
- Utility classes: flex, gap, margin, padding, text, grid (27 new classes)
- Improved table hover with smooth transitions
- Clickable card variant with blue border glow
- Toast notifications with colored left bar per type
- Confirm modal with red top border

**Session Timeout:**
- JWT expiry check every 30 seconds
- Warning toast 5 minutes before expiry with renewal link

**Multi-recipient Email:**
- Support for comma-separated email recipients
- Sends to all recipients in parallel
- Updated placeholder text in settings

**Report improvements:**
- Font changed from Cairo to Inter in all report templates
- Improved static file serving with path traversal check

---

## v2.8.0 (2026-04-03)
### Navigation redesign — streamlined menu structure

**New navigation structure:**
- Simplified from 7 top-level to 5: Dashboard, Customers, Infrastructure, AI, Integrations
- "Tools" renamed to **Infrastructure** with consolidated submenu:
  - "Hosts & SSH" (conceptually merged)
  - Network, VPN, Terminal, Provisioning
- "Customers" dropdown removed — single direct button leading to customer list
- "AI Console" shortened to "AI"
- "Log" hidden by default (accessible via settings)

**Customer detail with tabs:**
- Click customer in dashboard → tab-based profile page
- 4 tabs: Dashboard (gauges+trend), M365 Status, History, Files
- Run Audit button always visible in header
- Breadcrumb points to customer list

**Nav highlighting improved:**
- Infrastructure views highlight "Infrastructure" in menu
- Customer-related views highlight "Customers"
- Command palette updated with new section names

---

## v2.7.0 (2026-04-03)
### Scheduled report delivery, audit findings in search, shortcuts

**Scheduled Report Delivery:**
- Scheduler automatically generates HTML report after each audit
- Email sent automatically if auto-send is enabled in settings
- Works for both single-customer and all-customers mode
- Logging of email sending in activity log

**Audit findings in Command Palette:**
- Cmd+K now also searches warnings/findings from latest audit
- Shown as separate "Audit findings" section with ⚠ icon
- Activates at minimum 2 characters in search field

**Keyboard Shortcuts Updated:**
- Cmd+K (command palette) added to shortcuts modal
- Correct description for Escape (close modal/menu)

**Bug fixes:**
- Report tables with vertical/malformed text fixed (table-layout + max-width:0)

---

## v2.6.0 (2026-04-03)
### PWA, gauge charts in customer detail

**Progressive Web App (PWA):**
- manifest.json with app metadata, icons and standalone mode
- Service Worker with cache-first for static resources, network-first for API
- Meta tags for iOS (apple-mobile-web-app-capable) and Android (theme-color)
- App can now be installed as desktop/mobile app via browser

**Gauge charts in Customer Detail:**
- 3 circular doughnut gauges: Risk Score, MFA%, Secure Score
- 270° arc with color coding (green/blue/orange/red)
- Value text centered in middle of gauge
- Responsive with maintainAspectRatio
- Grade badge with glow shadow (box-shadow)

---

## v2.5.0 (2026-04-03)
### KPI deltas, active customer bar, polished footer

**KPI Delta Indicators (↑↓):**
- Green/red arrows in dashboard table showing change since previous audit
- Risk Score, MFA% and Secure Score% with tooltip showing exact difference
- Backend now returns `prev_metrics` from second-to-last audit run

**Active Customer Status Bar:**
- Compact bar under header showing active customer's name, domain and grade
- Quick buttons to M365 and History
- Cmd+K shortcut badge for quick access
- Updates automatically on customer switch

**Polished Footer:**
- Two-column layout with logo/product name on left
- Keyboard shortcuts (Cmd+K, ?) and version number on right
- Cleaner, more professional presentation

---

## v2.4.0 (2026-04-03)
### Dashboard polish, quick actions, settings redesign

**Auto-refresh Dashboard:**
- Toggle button with visual 60s countdown
- Green indicator when active
- Only updates when dashboard is visible

**Quick actions per customer (⋯ menu):**
- Three-dot menu in each customer row in dashboard table
- Actions: Details, Run Audit, History, Delete
- Dropdown with animation, closes on click outside
- Quick-switch: changes customer and navigates in one operation

**Tab-based Settings Modal:**
- 5 tabs: General, Branding, Email, Backup, Advanced
- Cleaner layout — settings grouped logically
- Tab switching with visual active indicator
- Scales better on smaller screens

---

## v2.3.0 (2026-04-03)
### Customer detail, notification bell, breadcrumbs

**Customer Detail View:**
- Click a customer in dashboard → dedicated profile page
- 4 KPI cards: Grade, Risk Score, MFA%, Secure Score
- Chart.js trend graph with 3 lines: risk score, MFA and Secure Score over time
- Detail panel with user data, CA policies, Intune, last audit
- Tags display and quick buttons to audit and history

**Notification Bell:**
- Bell icon in header with badge count for unread events
- Dropdown with last 20 events from activity log
- Icon per event type (audit, report, backup, email)
- Shows user and timestamp per event
- "Mark all as read" button with localStorage persistence
- Automatic badge check at startup

**Breadcrumb Navigation:**
- Dynamic path display under header (Dashboard / Customers / M365)
- Clickable parent elements for quick navigation
- Only shown at depth > 1 level
- Supports all 14 views including customer detail

---

## v2.2.0 (2026-04-03)
### Premium UX, data visualization and parallel audit

**Design System:**
- New font: Inter (replaces Cairo) with complete typography scale (11-34px)
- Design tokens: spacing (4-64px), border-radius, shadow system, transition easing
- Improved color contrast in dark mode (`--bg-card` upgraded)
- Cards with hover elevation and shadow transitions
- Buttons: sizes (sm/md/lg), lift effect on hover
- Modals: slide-in animation with backdrop blur
- Dropdown menus: fade-in animation + invisible bridge (no hover gap)
- View transitions: fade-in on navigation
- Lucide Icons CDN for professional icon library

**Data Visualization (Chart.js):**
- Risk score bar chart per customer in dashboard (color-coded)
- Grade distribution donut chart (A-F)
- SVG sparklines in customer table (risk score over time)
- Responsive, theme-aware rendering

**Command Palette (Cmd+K):**
- Global quick search: pages, actions and customers
- Arrow navigation + Enter to select
- Customer search with direct active customer switch
- Animated modal with sectioned results

**Trend Tracking:**
- New `audit_metrics` table in database (schema v5)
- Metrics stored automatically in DB after each audit
- API: `GET /api/trends` and `GET /api/trends/{customer_id}`
- Historical risk score graph per customer

**Parallel Bulk Audit:**
- 3 customers run simultaneously (asyncio.Semaphore)
- `AuthManager.from_customer()` — no global state mutation
- ~3x faster for MSPs with many customers
- Automatically filters to configured customers (TenantId + ClientId)
- Shows number of unconfigured customers that are skipped

**White-label Branding:**
- Color picker in settings for custom primary color
- Dynamic CSS injection at startup and after saving
- Company name in browser title
- Hex input with real-time sync to color picker

**Per-user Activity Log:**
- `user` parameter in all `log_activity()` calls
- Route handlers send username automatically
- Scheduler actions logged as `user="scheduler"`

**Bug fixes:**
- Audit metrics always saved after audit (grade/score shows in dashboard)
- Dropdown menus no longer disappear before cursor reaches them

---

## v2.1.0 (2026-04-03)
### Security hardening, complete backup and UI improvements

**Security:**
- Fixed XSS in VPN OAuth callback — all user input escaped with `html.escape()` + `json.dumps()`
- Fixed command injection in SSH manager — all shell paths sanitized with `shlex.quote()`
- Credentials masked in GET /settings API — SMTP password, ITGlue/UniFi API keys shown as `••••••`
- Removed `shell=True` in subprocess calls (Windows report opening)
- JWT secret encrypted with master key in database (auto-migrates from plaintext)
- CORS middleware restricted to localhost:8099
- Security headers: X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy
- PBKDF2 iterations increased from 600,000 to 1,000,000
- Dependencies pinned with upper version bounds

**Backup:**
- Complete backup: SQLite database, activity log and certificates now included
- Safe database backup via `sqlite3.backup()` API (not `shutil.copy2`)
- Safe database restore via `sqlite3.backup()` + cleanup of WAL/SHM files
- UI shows database, certificates and activity log in restore results
- `restart_required` flag returned on database restore
- Backward compatible with older backups

**Code Quality:**
- ~27 silent `except: pass` replaced with logging with context
- 12 blocking `subprocess.Popen` calls wrapped in `run_in_executor`
- VPN connect/disconnect protected with `asyncio.Lock()` against race conditions

**UI/UX:**
- New styled confirmation modal replaces all 16 native `confirm()` dialogs
- All 38 native `alert()` dialogs replaced with `showToast()` notifications
- `:focus-visible` styles for keyboard navigation
- Screen reader labels (`<label>`, `aria-modal`, `aria-label`, `role="dialog"`) on forms and modals
- `autocomplete` attributes on login form
- 18 new i18n keys (Norwegian + English)

---

## v2.0.0 (2026-04-02)
### MSP-Toolkit V2 — Multi-user web platform

**Platform:**
- Rewritten from single-user app to multi-user web platform
- Authentication with JWT (argon2 + refresh tokens) and role-based access (Admin/Technician/Reader)
- First login creates admin account
- Server.py split from 3564 to ~160 lines — 15 route modules
- SQLite database for users, SSH hosts, VPN profiles
- All API calls authenticated with Bearer token

**SSH Management:**
- Key generation (Ed25519/RSA) with complete form and dropdown
- Host management with device type, group, auth method, notes
- 3-strategy key deployment (SFTP/exec/sudo) from SuperManager
- Batch command execution across multiple hosts
- Health check for all hosts
- Edit/Delete/Terminal buttons per host

**VPN Management:**
- FortiGate IPsec via strongSwan (swanctl) with sudo — matches SuperManager config
- Azure P2S VPN with PKCE OAuth2 popup login and MFA
- Refresh token caching — automatic re-auth without popup
- WireGuard and OpenVPN backends
- Drag-and-drop file import (.conf/.ovpn/.xml) with multi-file Azure support
- Split tunnel as default for web server security
- Automatic route installation after connection
- Create/Edit/Delete profiles

**Web Terminal:**
- xterm.js-based terminal in browser
- Local shell (PTY) and SSH to managed hosts
- Full ANSI support with colors, cursor, resize

**FortiGate Integration:**
- Global FortiGate overview in Dashboard (all customers in parallel)
- Detail view: interfaces, VPN tunnels, firewall rules, DHCP, DNS, admin accounts
- CPU/memory/sessions with color coding
- Config backup and CIS compliance check with score bar
- REST API configuration per customer under Integrations

**UniFi Site Manager:**
- v1 API integration (10,000 req/min)
- Hosts + Sites + Devices endpoints
- Sub-sites expanded in overview with clickable detail views
- Device type breakdown, WiFi TX retry, offline alerts
- Unihosted cloud controller with 23 customer sites
- API key stored and auto-filled

**Live Dashboard:**
- FortiGate/UniFi device polling with configurable interval
- Clickable device cards with KPI number cards
- FortiGate, UniFi Sites, and Customer Overview as sub-tabs
- FortiGate tab: all firewalls across customers

**AI Console:**
- Claude integration with SSE streaming
- 10 tools: SSH, VPN, FortiGate, UniFi
- Conversation history

**Provisioning:**
- 5-step wizard for new customer networks
- FortiGate CLI + UniFi JSON generation
- CIS benchmark-based templates
- Optional AI-assisted configuration

**Integrations:**
- FortiGate REST API (per customer)
- UniFi Site Manager (API key + SSO)
- IT Glue, Email (SMTP), Teams/Slack Webhook (existing)

---

## v1.6.0 (2026-03-30)
### Network security in main report — full integration

**Report Integration:**
- New "Network Security" section in customer report (HTML/PDF) with FortiGate + UniFi data
- FortiGate: model, firmware, admin table (2FA/trusthost), firewall warnings, VPN tunnels, HA mode
- UniFi controller: devices, SSIDs, networks, firewall rules, alarms
- UniFi direct: device table with model, firmware, MAC, status, firmware check
- Table of contents updated with network section (between Azure and Compliance)

**Risk score integration (new weight budget: +15 pts):**
- FortiGate admin without 2FA: up to 5 pts deduction
- FortiGate allow-all rules: up to 5 pts
- FortiGate rules without logging: up to 3 pts
- UniFi default password: up to 10 pts (5 per device)
- UniFi EOL devices: up to 5 pts
- UniFi outdated firmware: up to 3 pts
- Open WiFi network: 5 pts

**New recommendations (9 network types):**
- FortiGate: admin without 2FA, allow-all rules, rules without logging, admin without IP restriction
- UniFi: default password, outdated firmware, EOL devices, factory settings, open WiFi
- All with severity, sub-items (affected devices/rules), and i18n (NO/EN)

**Data Storage:**
- Quick audit results now automatically saved as encrypted files (`60_fortigate_audit.txt`, `61_unifi_audit.txt`)
- Stored in customer's latest audit directory for report generation
- Network metrics included in `_audit_metrics.json` (device count, default passwords, outdated firmware)

**i18n:**
- 18 new translations (NO/EN) for network sections and recommendations

---

## v1.5.0 (2026-03-30)
### Network audit Phase 2 — firmware check, subnet scanner, config backup

**Firmware Version Database:**
- 80+ UniFi models with latest known stable firmware (APs, switches, gateways)
- End-of-life (EOL) flagging for discontinued models (UAP-LR, USG, etc.)
- Model normalization: board.info names, aliases, prefix matching
- Automatic version check during quick audit — findings marked as ok/warning/critical
- Quick audit summary shows count of outdated and EOL devices

**Network Scanner:**
- `POST /api/network/scan` — scan a CIDR subnet (max /22) for devices
- Ping sweep + SSH banner check + HTTPS probe
- Auto-detection of UniFi devices (dropbear SSH, UniFi HTTPS)
- "Add" button to import discovered devices to direct devices list
- UI: Scanner section under Network Audit with subnet field and result table

**Configuration Backup:**
- `POST /api/network/save-config-backup` — saves device config encrypted per customer
- `GET /api/network/config-backups` — shows saved backups with timestamp and size
- "View config" button automatically saves a backup on each view
- Backup files stored under `audit_data/{customer}/network_configs/` (AES encrypted)
- UI: Backup list under Network Audit

**Improved Quick Audit:**
- Firmware version checked against database and shown as finding (green ✓ / orange ⚠ / red ⚠)
- EOL devices flagged with critical finding
- Summary card shows: outdated firmware count, EOL count
- Orchestrator now also recognizes `UniFiDirectDevices` (not just `UniFiHost`)

---

## v1.4.1 (2026-03-30)
### UniFi direct device audit — full SSH data extraction + device actions

**Robust SSH data extraction (rewritten):**
- Runs 10+ SSH commands in single session: `board.info`, `/etc/version`, `mca-cli-op info`, `mca-status`, `hostname`, `ip addr`/`ifconfig`, `uptime`, `iwinfo`/`iwconfig`, `wlanconfig`/`iw station dump`, `system.cfg`
- Three-level model detection: board.info → mca-cli-op info → mca-status
- Three-level firmware detection: /etc/version → mca-cli-op info → mca-status
- MAC fallback from ifconfig/ip addr when not in mca-status
- IP fallback from ifconfig/ip addr
- Wireless: SSID(s), channel, security mode, WiFi mode from iwinfo/iwconfig + system.cfg
- Management: inform URL, adoption status (adopted/standalone/factory default)
- Client count from wlanconfig or iw station dump
- Uptime from /proc/uptime with human-readable formatting
- All parsing uses shlex.quote() for safe credential handling

**Security audit per device:**
- Default credentials (ubnt/ubnt) flagged as critical finding
- Factory default config detection
- Open/unencrypted WiFi flagged as critical
- Admin user list extracted from running config
- Adoption status: adopted (with inform URL) / standalone / factory default

**Device actions (new API endpoints):**
- `POST /api/unifi/set-inform` — adopt device to a controller (mca-cli-op set-inform)
- `POST /api/unifi/reboot-device` — restart device via SSH
- `POST /api/unifi/device-config` — dump running configuration (system.cfg)

**Quick audit UX:**
- Per-device cards with full info grid: model, firmware, serial, MAC, IP, hostname, uptime, clients, SSID(s), channel, WiFi security, inform URL
- Security findings inline with severity icons
- Action buttons: Set-Inform, View config, Restart
- Config dump shown inline with syntax-highlighted pre block
- Summary: device count, reachable, default-credentials count
- Fixed: direct mode no longer returns "No network devices configured"

---

## v1.4.0 (2026-03-30)
### FortiGate and UniFi audit — Phase 1 (foundation)

**New module structure:**
- FortiGate audit module (`app/modules/fortigate_audit/`) with async REST API client
- UniFi audit module (`app/modules/unifi_audit/`) with async cookie-based API client
- Audit orchestrator (`app/modules/orchestrator.py`) to coordinate M365 + FortiGate + UniFi
- 9 FortiGate sections and 8 UniFi sections defined

**FortiGate API Client:**
- Token-based authentication (Bearer token)
- Support for self-signed TLS, VDOM selection, timeout
- `get_cmdb()` for configuration, `get_monitor()` for runtime data
- Test connection with firmware/hostname/serial verification

**UniFi API Client:**
- Cookie-based authentication with auto-detection of Classic vs UniFi OS (UDM/Cloud Key)
- Methods for sites, devices, WLANs, networks, firewall, settings, clients, alarms
- Login/logout lifecycle management

**New API endpoints:**
- `POST /api/fortigate/test` — test FortiGate connection
- `POST /api/fortigate/save` — save FortiGate config per customer
- `POST /api/unifi/test` — test UniFi connection
- `POST /api/unifi/save` — save UniFi config per customer
- `GET /api/network-devices` — get configured network devices for active customer

**Customer model:**
- New optional fields: FortiGateHost, FortiGatePort, FortiGateVDOM, FortiGateVerifySSL
- New optional fields: UniFiHost, UniFiIsUniFiOS, UniFiSite
- Credentials (API token, username/password) stored in OS keyring

---

## v1.3.0 (2026-03-30)
### Report clickability, cross-references, and drilldowns

**Customer Report — Clickability:**
- Every finding card now links directly to its recommendation: "→ See recommendation #N"
- Every recommendation links back to its related finding: "↑ Related finding"
- All 13 section headers are clickable anchor links (hover shows § indicator)
- Section headers use `id` attributes instead of legacy `<a name>` anchors

**Customer Report — New Drilldowns:**
- Global Administrator finding: expandable list of all GA users with name + email
- Intune non-compliance finding: expandable table of non-compliant devices (name, OS, user, status)
- OAuth high-privilege apps finding: expandable list of app names
- All drilldowns use consistent ▶ toggle UI

**Data & Architecture:**
- `finding_to_recs` cross-reference map passed to template context
- Each recommendation carries `finding_id` and `rec_index` for bidirectional linking
- `_parse_admin_roles()` now returns `global_admin_users` list
- `_parse_intune_devices()` now returns `noncompliant_devices` list
- "See details below" replaced with actual anchor links

---

## v1.2.4 (2026-03-30)
### Security hardening and error logging

**Security:**
- Path traversal fix in `/api/itglue/upload/reports` — filenames validated to stay within audit directory
- Path traversal fix in backup restore — each entry validated against its target directory

**Error logging:**
- Dashboard/search metrics loading now logs warnings instead of silently failing
- Tenant info pre-collection failure logged with context
- Email report metrics loading failure logged
- IT Glue import/upload activity log failures logged
- Graph API pagination limit warning improved with "results may be incomplete" note

---

## v1.2.3 (2026-03-29)
### IT Glue document content fix

**IT Glue:**
- Document sections now actually contain content — fixed attribute from `body` to `content` in `POST /documents/:id/relationships/sections`
- Documents uploaded to IT Glue now display the full audit report HTML (stripped of CSS/scripts)

---

## v1.2.2 (2026-03-29)
### DMARC filter, report fix, IT Glue field inspection

**DNS / Email Security:**
- Filter out `.onmicrosoft.com`, `.inkyphishfence.com`, `.mimecast.com` etc. from DNS checks
- No more false DMARC/SPF warnings on non-production domains

**Reports:**
- Prevent text/element dragging in HTML reports (`-webkit-user-drag: none`)

**IT Glue:**
- New `GET /api/itglue/inspect` — shows all Flexible Asset Types and fields in IT Glue
- `inspect_asset_type()` and `inspect_all_types()` methods to check existing field structure
- Upload now matches fields that actually exist in IT Glue — only sends traits for existing fields

---

## v1.2.1 (2026-03-29)
### Full Norwegian/English language switching

**Language:**
- Language selector in Settings (Norsk/English) — switches the entire UI
- 574 translations per language (navigation, buttons, labels, error messages, dialogs, tooltips)
- Preference stored in localStorage and server settings
- Backend API error messages translated via `ui_t()` (respects Accept-Language header)
- Static `/static/` file serving for i18n JSON

---

## v1.2.0 (2026-03-29)
### Security hardening, performance, reports, accessibility

**Security:**
- Path traversal vulnerability fixed in `/api/history/load` — validates paths are within audit directory
- Tracebacks no longer sent to browser — logged server-side only
- XSS vulnerability in toast messages fixed — messages are now properly escaped
- Audit lock (`asyncio.Lock`) prevents race conditions on concurrent requests
- Cancel endpoint: `POST /api/audit/cancel` stops a running audit

**Performance:**
- Identity Security: 10 sequential Graph calls now run in parallel via `asyncio.gather()`
- SharePoint: Per-site API calls parallelized with semaphore (5 concurrent)
- Graph API: Exponential backoff (1s → 2s → 4s → ... max 30s) replaces fixed 5s delay
- Pagination: Max 500 pages to prevent infinite loop on invalid `@odata.nextLink`
- EXO PowerShell: 5-minute timeout prevents audit from hanging

**Reports:**
- Missing i18n keys added: `tab_compliance`, `search_placeholder`, `signin_analysis`, `brute_force_warning`, `cover_tech_subtitle`, etc.
- Microsoft Learn links updated in customer report
- Logo: Dark variant (`Sybr Dark.png`) now used in dark mode reports

**UX / Accessibility:**
- ARIA labels on all icon-only buttons (theme, settings, shortcuts, close)
- Sortable columns: Visual hover effect and sort indicators (↑/↓/⇅)
- Mobile: Minimum touch target 44×44px (WCAG 2.5.5)

**Stability:**
- Azure Governance: Failure in one data source no longer blocks the entire section
- Each `_collect_*()` has individual error handling with warning

---

## v1.1.1 (2026-03-29)
### Bug fixes and data path migration

**Config/cert moved to platformdirs:**
- `audit_config.json` and `audit_cert.pfx` now stored in `~/.local/share/MSPToolkit/` (Linux) / `~/Library/Application Support/MSPToolkit/` (macOS) instead of relative to CWD
- Automatic migration from legacy location on first startup
- Hardcoded `Path("audit_cert.pfx")` replaced with `cert_path()` in server, scheduler, and customer switching

**Credential cache:**
- `get_secret()` no longer caches `None` values — after "Renew Credentials", secrets are correctly fetched from keyring without restart
- `clear_secret_cache()` called explicitly on renewal to prevent stale cache

**Version:**
- Hardcoded version in HTML header updated to match actual version

---

## v1.1.0 (2026-03-26)
### Webhook alerts, history management, integration docs

**Webhook / Teams alerts:**
- Rich audit notifications to Teams: risk grade, score, MFA coverage, Secure Score, warning count
- Bulk audit sends per-customer alerts + summary card with all results
- Failed audits send error message to Teams
- Adaptive Card format with structured TextBlock rows (heading + details)
- Webhook type auto-detection extended with `flow.microsoft.com` URLs

**History and report comparison:**
- Delete individual audit runs (checkboxes + confirmation dialog)
- Delete all runs for a customer (with confirmation dialog)
- Incomplete runs (without metric data) marked as "incomplete" — cannot be compared but can be deleted
- Comparison results now shown above history list (not below the fold) with auto-scroll
- Run count shown per customer card

**Files and folder view:**
- "Open folder" now works — sends actual path from `/api/files` to backend
- Backend `/api/open-folder` accepts optional path parameter, falls back to audit directory
- Null checks on all DOM elements in Files tab (prevents crash on missing elements)

**IT Glue integration:**
- "Upload to IT Glue" without configured API key now navigates to Integrations tab (not Settings)
- Opens IT Glue configuration panel automatically
- Import customers from IT Glue
- Upload audit reports (HTML+PDF) to IT Glue Documents folder "MSP Toolkit" (auto-created)
- Report names date-stamped: "2026-03-26 — Tech-report.pdf"
- New "Import from IT Glue" button on Customers page
- Shows all IT Glue organizations with search, select all, and marking of already imported
- Imports customer name and IT Glue org ID — ready for setup afterwards
- Flexible Asset Type name changed to "MSP Toolkit" (matches existing config)
- All fields set to show-in-list = True with 0 decimals
- Better error handling on upload — clear message on missing access

**Compliance mapping (CIS/NIST/ISO):**
- Expanded from 10 to 30+ CIS M365 Benchmark controls
- New controls: PIM, break-glass accounts, password policies, DLP, sensitivity labels, DKIM, Safe Links/Attachments, audit logging, forwarding, Teams, retention policies, Defender alerts, risky users
- NIST CSF 2.0 and ISO 27001:2022 now show control names (not just IDs)
- Compliance summary with pass percentage and per-category overview
- Separate categories: Identity, Email, Applications, Data, Devices, Teams, Logging

**Integration wiki:**
- Complete technical documentation for IT Glue: data flow, Flexible Asset fields, API architecture, limitations vs. capabilities (table)
- Complete technical documentation for Autotask/Datto PSA: authentication, endpoints, planned features (table), API limitations
- ConnectWise PSA: three-way auth, endpoints, clientId requirements
- Halo PSA: OAuth2 flow, webhook capabilities
- MSP Toolkit REST API: complete endpoint list (25+), curl examples
- Clear distinction between "not yet implemented" and "actual API limitations"

**Audit:**
- Admin roles now show last sign-in time per user (fetched from signInActivity)

**Documentation:**
- New section: "How SYBR MSP Toolkit works" — complete architecture, data flow, and authentication explanation
- First-time setup documented step by step (what the PowerShell script does)
- All 21 Graph permissions listed with their purpose
- All 23 audit sections documented with API endpoints and data source
- Authentication flow explained: Graph (httpx OAuth2), Azure SDK, Exchange Online (certificate + PowerShell)
- Secret storage documented (Keychain, AES-256-GCM)
- Tools and dependencies (Python, PowerShell, httpx, Azure SDK, WeasyPrint)
- Report generation and scoring explained

**Troubleshooting and logging:**
- Webhook context building now logs errors (ERROR level) instead of silent `pass`
- Fallback to simple notification if context building fails
- Timestamp in log view cleaned up (removes microseconds and timezone suffix)

---

## v1.0.1 (2026-03-23)
### UX improvements and cleanup

**UI:**
- Dark logo switched to "Sybr Dark.png" for dark mode header
- Integration configuration (IT Glue, Email, Webhook) removed from Settings modal
- All integration configuration consolidated exclusively under Integrations tab
- No duplicate input IDs — settings modal is simpler and cleaner

**Integrations:**
- Teams Webhook wiki expanded with complete step-by-step setup guide
- Information about newer Teams versions (connector migration) and Power Automate alternative
- IT Glue wiki updated to point to Integrations tab instead of Settings

---

## v1.0.0 (2026-03-23)
### Full platform release

**Dashboard and customer management:**
- Multi-customer dashboard with search, filtering, and sortable columns
- Customer tags/groups (Premium, Standard, etc.)
- Customer notes with auto-save
- Expiring credential warnings with webhook alerts
- Bulk audit for all customers

**Audit:**
- 23+ audit sections (M365, Azure, Teams, PIM, Password Protection)
- Audit scope selector with presets (Full/Quick/Identity)
- Graph API permission validation (pre-flight check)
- Dynamic group member resolution (transitiveMembers)
- Domain filtering (onmicrosoft, anti-spam gateways)

**Reports:**
- Norwegian/English language toggle (600+ translations)
- CIS + NIST CSF + ISO 27001 compliance mapping
- Dark mode PDF option
- MFA/forwarding/risky users with clickable drill-down tables
- License optimization analysis
- Trend charts (SVG, up to 6 data points)
- Microsoft Docs links on recommendations
- Custom logo upload
- Risk score recalculated with proportional penalties

**Security:**
- AES-256-GCM encryption at rest for all customer data
- Master encryption key backup and restore
- Encrypted backup/export (ZIP with manifest)
- Private/incognito browser for device code authentication

**Integrations:**
- IT Glue (Flexible Assets, credentials, PDF upload)
- Automatic email report (SMTP)
- Webhook customization (7 event types with thresholds)
- Integration wiki with PSA roadmap

**Platform:**
- Mobile-responsive UI
- Keyboard shortcuts
- Activity log
- Remediation tracking
- Audit comparison (side by side)
- Excel/Power BI export
- Built-in help and onboarding guide
- Per-customer scheduling

---

## v0.1.0 (2026-03-20)
### Initial release
- Core audit engine with 20 M365/Azure sections
- Customer and technician reports in HTML and PDF
- Multi-tenant customer management
- Basic web UI with dark/light mode
