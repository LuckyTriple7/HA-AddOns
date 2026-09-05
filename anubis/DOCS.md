# Anubis

🇬🇧 [English version](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/anubis/DOCS.en.md)

[Anubis](https://github.com/TecharoHQ/anubis) stellt Besuchern eine Proof-of-Work-Rechenaufgabe, bevor eine Anfrage den eigentlichen Dienst erreicht. Ein normaler Browser löst sie unbemerkt per JavaScript im Hintergrund; einfache Bots, Scanner und CLI-Clients ohne JavaScript kommen nicht durch. Gedacht als zusätzliche Schutzschicht **vor** einem Reverse Proxy — ersetzt kein Login, erhöht nur die Kosten automatisierter Zugriffe.

```text
Internet
   ↓
Reverse Proxy (z.B. NPMplus)
   ↓
Anubis-Challenge (Proof of Work)
   ↓
eigentliche Anwendung
```

Dieses Add-on ist reine Engine ohne eigene Oberfläche und ohne Ingress — es wird ausschließlich intern von einem Reverse Proxy angesprochen, der `auth_request`/forward-auth beherrscht. Am einfachsten in Kombination mit dem [NPMplus-Add-on](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/npmplus/DOCS.md) dieses Repos, das Anubis bereits fest als Auth-Request-Anbieter kennt.

## Warum eine eigene Policy statt der Standard-Policy von Anubis

Die mitgelieferte Standard-Policy von Anubis bindet zusätzliche Snippets ein (`(data)/common/domain-fronting.yaml`, `(data)/bots/...` usw.), die nur im Original-Image eingebettet liegen. Eine einzelne, gemountete Policy-Datei ohne diese Importe scheitert damit:

```text
invalid source file: (data)/common/domain-fronting.yaml
```

Dieses Add-on liefert deshalb eine **eigenständige, importfreie Policy** mit (`policy.default.yaml`), die beim ersten Start nach `/data/policy.yaml` kopiert wird. Sie enthält bewusst **keinen impliziten ALLOW-Zweig**: jeder Client, der von keiner Regel erfasst wird, landet in einer catch-all-Regel und wird ebenfalls challenged — das schließt curl, wget, Scanner und unbekannte Clients mit ein, die sonst mit `weight <= 0` durch eine Standard-Freigabe fallen könnten.

## Suchmaschinen (Google, Bing & Co.)

Die catch-all-Regel challenged auch echte Suchmaschinen-Crawler — die lösen keine JavaScript-Proof-of-Work. Ohne Ausnahme verschwindet eine aktivierte Domain deshalb schleichend aus der Suche, weil Google & Co. beim erneuten Crawlen nicht mehr durchkommen.

Die Option `allow_search_engines` (Standard **an**) nimmt deshalb echte Suchmaschinen-, Web-Archiv- und Zitier-Crawler per `ALLOW`-Regel aus — geprüft wird dabei immer User-Agent **und** die jeweils offizielle IP-Adresse gemeinsam (`remote_addresses`), ein bloßer User-Agent-String ließe sich sonst von jedem Client fälschen. Ausschalten (`false`), wenn wirklich jeder Client challenged werden soll, auch Suchmaschinen — etwa bei einem rein privaten Dienst, der in keiner Suche auftauchen soll.

Enthalten: **Google** (inklusive Search-Console-„Live-Test"/Google-InspectionTool), **Bing**, **DuckDuckGo**, **Qwant**, **Internet Archive**, **Kagi**, **Marginalia**, **Mojeek**, **Common Crawl**, **Wikimedia** (Citoid/Zotero Translation Server) und **Arquivo.pt**. Absichtlich **nicht** enthalten: **Yandex**.

Die Regeln stehen zwischen zwei Markern in `/data/policy.yaml`:

```yaml
bots:
  # >>> anubis-addon search-engines >>>
  # <<< anubis-addon search-engines <<<
```

Das Add-on schreibt **nur diesen Block** bei jedem Start neu, passend zur aktuellen Einstellung von `allow_search_engines` — eigene Regeln dort gehen beim nächsten Neustart verloren. Alles außerhalb der Marker (z.B. eigene Regeln unterhalb der `catch-all`-Regel) bleibt unangetastet, genau wie beim Rest der Datei.

Bewusst **kein** `(data)/crawlers/_allow-good.yaml`-Import für diese Freigabe: genau ein Import dieser Art ist beim praktischen Testen schon einmal mit `invalid source file: (data)/common/domain-fronting.yaml` gescheitert. Die Google-/Bing-Regeln liegen deshalb wörtlich in `policy.search-engines.yaml` im Image, als Kopie der offiziellen Anubis-Quellen.

Weitere Crawler (z.B. Yandex) lassen sich nach demselben Muster **unterhalb** der Marker in `/data/policy.yaml` ergänzen (außerhalb des verwalteten Blocks, sonst gehen sie beim nächsten Start wieder verloren) — die passende Regel liegt fertig unter `https://github.com/TecharoHQ/anubis/blob/main/data/crawlers/<name>.yaml`.

**Grenzen:** Die Anbieter veröffentlichen ihre Crawler-IP-Bereiche gelegentlich neu. Ändert sich ein Bereich, bevor die Liste hier aktualisiert wird, würde der betroffene Teilbereich kurzzeitig wieder challenged — kein Datenverlust, nur ein vorübergehend nicht gecrawlter Ausschnitt.

## Monitoring-Dienste

Externe HTTP-Monitore lösen ebenfalls keine JavaScript-Proof-of-Work — ohne Ausnahme meldet ein Monitor auf eine geschützte Domain dauerhaft „down", obwohl der Dienst dahinter läuft.

Die Option `allow_monitoring_services` (Standard **an**) nimmt **UptimeRobot** und **updown.io** per `ALLOW`-Regel aus, wieder per User-Agent **und** offizieller IP-Adresse gemeinsam geprüft. Landet im selben Mechanismus wie die Suchmaschinen-Freigabe, eigener Marker-Block `monitoring` in `/data/policy.yaml`.

**Selbstgehostetes Uptime Kuma ist davon nicht abgedeckt** — es hat keine feste, veröffentlichte IP-Adresse, eine sichere Verifikation ist damit nicht möglich. Dafür stattdessen einen zweiten, internen Monitor direkt auf den Dienst legen, an Anubis vorbei:

```text
Extern:  https://dienst.domain.tld     → Reverse Proxy + Anubis
Intern:  http://<interne-adresse>:port → Dienst selbst
```

## KI-Bot-Stufe

`ai_bot_policy` steuert, wie Anubis mit bekannten KI/LLM-Clients umgeht — unabhängig von der catch-all-Regel, die sie ohnehin schon challenged. Vier Stufen, identisch zu den offiziellen Anubis-Voreinstellungen übernommen:

| Stufe | Wirkung |
|---|---|
| `off` (Standard) | Keine eigene Regel — die allgemeine Challenge trifft KI-Bots wie jeden anderen unbekannten Client |
| `aggressive` | **DENY** für jeden bekannten KI/LLM-Client vollständig, auch dokumentierte On-Demand-Abrufe (z.B. „ChatGPT, fass diese Seite zusammen" schlägt dann ebenfalls fehl) |
| `moderate` | **DENY** für Trainings-Crawler (GPTBot, ClaudeBot) und die breite Sammel-Regel unbekannter KI-Bots, **ALLOW** für dokumentierte Suchindexierung (OAI-SearchBot, PerplexityBot) und On-Demand-Abrufe durch einen Menschen |
| `permissive` | **ALLOW** für alle gut dokumentierten KI-Clients mit veröffentlichter IP-Liste, **inklusive** OpenAIs GPTBot-Trainings-Crawler — nur die breite Sammel-Regel bleibt `DENY` |

Alle `ALLOW`-Regeln prüfen User-Agent **und** offizielle IP-Adresse gemeinsam. `DENY` heißt: sofortige Ablehnung ohne Challenge-Seite (spart dem Bot wie dem Server den Proof-of-Work-Umweg) — anders als bei catch-all, das auf `CHALLENGE` steht.

`off` ändert am aktuellen Verhalten nichts: unbekannte KI-Bots landen weiter in catch-all und werden challenged (in der Praxis meist gleichbedeutend mit „kommt nicht durch", da sie kein JavaScript ausführen).

## Vertrauenswürdige IP-Bereiche

`trusted_ip_ranges` (Liste von IP-Adressen oder CIDR-Bereichen, z.B. `203.0.113.0/24`) nimmt eigene, selbst gewählte Adressen komplett von der Challenge aus — **ohne** User-Agent-Prüfung. Anders als bei Suchmaschinen/Monitoring/KI-Bots oben ist das keine Drittanbieter-Verifikation, sondern eine reine Vertrauensentscheidung des Betreibers, gedacht für eigene Infrastruktur (z.B. ein eigener Server, das Büro-Netz, ein Partnerdienst mit fester IP).

```yaml
trusted_ip_ranges:
  - 203.0.113.0/24
  - 198.51.100.5/32
```

Leer (Standard) = keine Ausnahme, keine Regel wird geschrieben.

## Einrichtung mit NPMplus

1. Anubis-Add-on installieren und starten.
2. Hostnamen des Anubis-Containers ermitteln (im Terminal-Add-on mit Docker-Zugriff):

   ```sh
   docker inspect -f '{{.Config.Hostname}}' $(docker ps --format '{{.Names}}' | grep -i anubis)
   ```

   Das Ergebnis sieht aus wie `424ccef4-anubis`. Der vordere Teil ist die Kennung des Add-on-Repositorys und unterscheidet sich je nach Installation — den eigenen Wert auslesen, nicht diesen abschreiben. Eine Container-IP (`172.30.33.x`) hier einzutragen wäre ein Fehler: Docker vergibt sie bei jedem Neustart neu, der Hostname bleibt gleich.

3. In den NPMplus-Add-on-Optionen unter `extra_env` ergänzen:

   ```yaml
   extra_env:
     - "AUTH_REQUEST_ANUBIS_UPSTREAM=http://424ccef4-anubis:8923"
   ```

4. NPMplus neu starten.
5. Im gewünschten Proxy Host: Reiter „Optionen" → Feld **Auth Request** → `anubis` auswählen → Speichern.

   Keine zusätzlichen Advanced-Nginx-Regeln oder Custom Locations nötig — die Integration steckt bereits in NPMplus. Am besten zuerst mit einer weniger kritischen Domain testen.

Mit anderen Reverse Proxys funktioniert dasselbe Prinzip, sofern sie `auth_request` (nginx) oder eine vergleichbare forward-auth-Funktion mitbringen — Anubis muss dann von Hand als Auth-Backend auf `http://<anubis-hostname>:8923/.within.website/x/cmd/anubis/api/check` eingebunden werden.

## Auth-Request von Hand testen

```sh
curl -s -o /dev/null -w '%{http_code}\n' \
  -A 'Mozilla/5.0' \
  -H 'Host: test.example' \
  -H 'X-Real-IP: 127.0.0.1' \
  -H 'X-Forwarded-For: 127.0.0.1' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: test.example' \
  -H 'X-Original-URI: /' \
  -H 'X-Http-Version: HTTP/1.1' \
  http://424ccef4-anubis:8923/.within.website/x/cmd/anubis/api/check
```

Erwartete Ausgabe: `401` — das bedeutet „Challenge erforderlich" und ist mit der mitgelieferten catch-all-Policy korrekt, auch für diesen nackten Testaufruf.

## Challenge erneut erzwingen

Nach bestandener Challenge setzt Anubis ein Cookie (Name beginnt etwa mit `techaro.lol-anubis-auth-`). Die Prüfung erscheint danach nicht bei jedem Seitenaufruf erneut.

- **Einfachster Test**: die geschützte Domain in einem Inkognito-/Privatfenster öffnen.
- **Alternativ**: Cookie im Browser löschen (F12 → Application/Storage → Cookies → betreffende Domain) und neu laden.

## Policy anpassen

`/data/policy.yaml` ist nach dem ersten Start frei editierbar — das Add-on schreibt sie nie wieder darüber. Nach jeder Änderung das Add-on neu starten.

Schwierigkeit testweise erhöhen, um die Proof-of-Work-Berechnung sichtbar zu machen:

```yaml
challenge:
  algorithm: fast
  difficulty: 5
```

Nicht dauerhaft hoch lassen — auch legitime Besucher brauchen dann spürbar Rechenzeit. Zum Alltagsgebrauch zurück auf `difficulty: 2` (mitgelieferter Standard) oder niedriger.

Gültige Werte für `algorithm`: `fast` (schnelle JavaScript-Berechnung), `slow` (bewusst aufwendiger) und `metarefresh` (Seiten-Neuladen statt Proof of Work, kein echter Rechenaufwand).

## Was ein Bot dabei erlebt

```text
Besucher
   ↓
Anubis erzeugt Rechenaufgabe
   ↓
Browser führt JavaScript aus
   ↓
Proof of Work wird berechnet
   ↓
Lösung wird geprüft
   ↓
korrekt → Auth-Cookie → Zugriff
```

Ein einfacher Bot ohne JavaScript kann die Challenge normalerweise nicht lösen. Ein moderner Bot, der einen vollständigen Browser wie Chromium automatisiert, kann Proof of Work grundsätzlich ebenfalls berechnen — Anubis ist deshalb keine klassische „Beweise, dass du ein Mensch bist"-Prüfung, sondern erhöht vor allem Kosten und Aufwand automatisierter Zugriffe.

## Monitoring-Tools wie Uptime Kuma

Uptime Kuma, Healthchecks und ähnliche Monitore können eine JavaScript-/Proof-of-Work-Challenge normalerweise nicht lösen und werden mit der mitgelieferten catch-all-Policy ebenfalls challenged. Ein HTTP-Monitor auf eine per Anubis geschützte Domain zeigt dann bestenfalls, dass **Reverse Proxy + Anubis** antworten — nicht, dass die dahinterliegende Anwendung funktioniert.

Für vollständige Überwachung zusätzlich einen internen Monitor direkt auf den Dienst legen, an Anubis vorbei:

```text
Extern:  https://dienst.domain.tld     → Reverse Proxy + Anubis
Intern:  http://<interne-adresse>:port → Dienst selbst
```

Es gibt bewusst keinen eingebauten Bypass für Monitoring-Tools — das würde die catch-all-Regel aufweichen. Wer einzelne Clients ausnehmen will, trägt eine eigene Regel mit `action: ALLOW` und passendem `user_agent_regex` oberhalb der catch-all-Regel in `/data/policy.yaml` ein.

## Daten und Backup

| Was | Pfad |
|---|---|
| Policy (editierbar) | `/data/policy.yaml` |

Ein Home-Assistant-Backup des Add-ons enthält `/data` vollständig. Da die Policy keine Geheimnisse enthält, ist auch eine Kopie in `/share` unbedenklich.

## Problembehandlung

**`invalid source file: (data)/...` im Protokoll** — es wurde eine Policy mit externen Importen eingetragen (z.B. aus der Anubis-Dokumentation kopiert). Zur eigenständigen Policy aus `policy.default.yaml` zurückkehren oder eigene Importe entfernen.

**Auth-Request liefert 500 statt 401/403** — meist fehlende Header. Ein nacktes `curl http://<anubis-hostname>:8923` ohne die in „Auth-Request von Hand testen" genannten Header ist kein vollständiger Auth-Request und liefert deshalb keinen sinnvollen Code.

**Anubis-Seite erscheint nicht, Proxy Host liefert direkt aus** — `AUTH_REQUEST_ANUBIS_UPSTREAM` in `extra_env` prüfen (Hostname korrekt? NPMplus danach neu gestartet?) und ob im Proxy Host unter „Auth Request" tatsächlich `anubis` ausgewählt ist.

**Monitoring-Tool zeigt rot** — siehe Abschnitt „Monitoring-Tools wie Uptime Kuma": normal bei einer per Auth-Request geschützten Domain, kein Fehler des Add-ons.

## Lizenz

Anubis steht unter der [MIT-Lizenz](https://github.com/TecharoHQ/anubis/blob/main/LICENSE). Dieses Add-on kopiert nur das statische Binary aus dem offiziellen Image; Einzelheiten in [LICENSE.md](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/anubis/LICENSE.md).
