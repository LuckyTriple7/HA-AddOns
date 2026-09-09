# Changelog

## [0.1.2] - 2026-09-05

### Neu
- Option `allow_monitoring_services` (Standard an): nimmt UptimeRobot und
  updown.io per `ALLOW`-Regel aus (User-Agent UND offizielle IP-Adresse
  gemeinsam), damit ein externer HTTP-Monitor nicht dauerhaft "down" meldet.
  Selbstgehostetes Uptime Kuma bleibt außen vor — keine feste IP, dafür einen
  internen Monitor direkt auf den Dienst legen.
- Option `ai_bot_policy` (Standard `off`): steuert den Umgang mit bekannten
  KI/LLM-Clients unabhängig von der catch-all-Regel, vier Stufen 1:1 aus
  Anubis' eigenen Voreinstellungen übernommen — `off`, `aggressive` (DENY
  für alles, auch On-Demand-Abrufe durch einen Menschen), `moderate` (DENY
  für Trainings-Crawler, ALLOW für dokumentierte Suchindexierung +
  On-Demand-Abrufe), `permissive` (ALLOW für alle dokumentierten KI-Clients
  inklusive GPTBot-Training).
- Option `trusted_ip_ranges` (Standard leer): eigene IP-Adressen/CIDR-
  Bereiche komplett von der Challenge ausnehmen, ohne User-Agent-Prüfung —
  gedacht für eigene Infrastruktur, keine Drittanbieter-Verifikation.
- run.sh umgebaut: generalisierte `apply_managed_block`-Funktion verwaltet
  jetzt vier unabhängige Marker-Blöcke in `/data/policy.yaml` (Suchmaschinen,
  Monitoring, KI-Bot-Stufe, vertrauenswürdige IPs) statt nur einem — jeder
  Block landet beim Einfügen automatisch hinter dem zuletzt verwalteten
  Block, dadurch stellt sich nach jedem Neustart unabhängig vom Vorzustand
  dieselbe Reihenfolge ein.
- Simuliert: sechs aufeinanderfolgende "Neustarts" mit wechselnden
  Options-Kombinationen (alle vier Schalter einzeln und gemeinsam getoggelt,
  inklusive Rückkehr zu den Standardwerten) gegen die tatsächliche
  run.sh-Funktion — jedes Mal gültiges YAML, korrekte Bot-Liste, keine
  Duplikate.

## [0.1.1] - 2026-09-05

### Neu
- Suchmaschinen-/Archiv-Allowlist (Option `allow_search_engines`) um DuckDuckGo,
  Qwant, Internet Archive, Kagi, Marginalia, Mojeek, Common Crawl, Wikimedia
  (Citoid/Zotero Translation Server) und Arquivo.pt erweitert — bisher waren
  nur Google und Bing enthalten. Alle geprüft per User-Agent **und** offizieller
  IP-Adresse gemeinsam, wie schon bei Google/Bing (Ausnahme: Internet Archive
  und Arquivo.pt haben laut Anubis-Vorlage bewusst keinen User-Agent-Check,
  dafür eine besonders enge IP-Liste).
- Absichtlich **nicht** enthalten: Yandex.

### Hinweis
- Der verwaltete Marker-Block in `/data/policy.yaml` wächst dadurch deutlich
  (v.a. durch DuckDuckGos ~480 Einzel-IPs) — rein zusätzliche Daten, keine
  Verhaltensänderung an Struktur oder Toggle-Logik.

## [0.1.0] - 2026-09-05

chore(deps): Bump alpine from 3.20 to 3.24 in /anubis


## [0.0.3] - 2026-09-05

### Behoben
- **Google Search Console meldete geschützte Domains als „nicht indexierbar".**
  Am Add-on-Log nachgewiesen: die IP passte (`66.249.79.x`, Googles echter
  Crawl-Bereich), aber der User-Agent war `Google-InspectionTool/1.0` — das
  eigene Werkzeug hinter „URL-Prüfung"/„Live-Test" in Search Console, mit
  anderem User-Agent als der reguläre Googlebot-Crawler
  (`+http://www.google.com/bot.html`). Die googlebot-Regel erkennt jetzt
  beide User-Agents; Anubis' eigene Vorlage im Techaro-Projekt kennt das
  Inspection-Tool bisher gar nicht.

## [0.0.2] - 2026-09-05

### Behoben
- **Echte Suchmaschinen wie Googlebot und Bingbot wurden von der mitgelieferten
  Policy ebenfalls challenged.** Sie lösen keine JavaScript-Proof-of-Work — eine
  aktivierte Domain wäre damit schleichend aus der Suche verschwunden.

### Neu
- Neue Option `allow_search_engines` (Standard an): nimmt Googlebot und Bingbot
  per `ALLOW`-Regel aus, geprüft anhand User-Agent **und** offizieller
  IP-Bereiche gemeinsam (kein bloßer User-Agent-Check, der sich fälschen
  ließe). Aus = wirklich jeder Client wird challenged, auch Suchmaschinen —
  für rein private Dienste, die in keiner Suche auftauchen sollen.
- Die Regeln stehen in einem eigenen, vom Add-on verwalteten Marker-Block in
  `/data/policy.yaml` (wie schon von der Ländersperre in NPMplus bekannt):
  bei jedem Start passend zur Option neu geschrieben, alles außerhalb der
  Marker bleibt unangetastet.
- Bewusst weiterhin **kein** `(data)/...`-Import für diese Freigabe, auch nicht
  für den offiziellen `(data)/crawlers/_allow-good.yaml`-Mechanismus: genau
  dieser Import ist beim praktischen Testen schon einmal mit
  `invalid source file: (data)/common/domain-fronting.yaml` gescheitert. Die
  Google-/Bing-Regeln liegen deshalb wörtlich in `policy.search-engines.yaml`
  im Image.
- Eigenes Icon/Logo.

## [0.0.1] - 2026-09-05

### Neu
- Erste Veröffentlichung. Kopiert das statische Binary aus dem offiziellen
  `ghcr.io/techarohq/anubis`-Image und startet es über `run.sh` mit
  einer eigenständigen, importfreien Policy (keine `(data)/...`-Abhängigkeit
  auf eingebettete Anubis-Assets).
- Läuft im reinen Auth-Request-Modus (`TARGET=" "`) für nginx' auth_request-
  Modul — gedacht für NPMplus' `AUTH_REQUEST_ANUBIS_UPSTREAM` (Auth-Request-
  Dropdown je Proxy Host), funktioniert aber mit jedem Reverse Proxy, der
  auth_request/forward-auth beherrscht.
- Kein Ingress, kein veröffentlichter Port — nur über den Add-on-Hostnamen
  auf Port 8923 aus anderen Containern erreichbar.
- Mitgelieferte Standard-Policy: Catch-all-Regel challenged jeden Client ohne
  gültiges Auth-Cookie (kein impliziter ALLOW-Zweig für unbekannte Clients).
