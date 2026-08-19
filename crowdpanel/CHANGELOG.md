# Changelog

## [0.2.3] - 2026-08-19

### Added
- **Das Panel nennt seine eigene Version.** In der Kopfzeile steht, welcher
  Stand tatsächlich läuft, unter Einstellungen zusätzlich, was der Supervisor
  als neueste Fassung führt. Weicht beides voneinander ab, färbt sich die
  Anzeige.

  Anlass: Heute widersprachen sich drei Quellen — der Add-on-Store, die
  Update-Entität und eine Portainer-Integration, die dieselbe Zahl aus dem
  Container-Digest ableitet. Zwei Stunden gingen dafür drauf, überhaupt
  festzustellen, welcher Code läuft. Die Versionszeile kommt jetzt aus der
  `config.yaml` im Image selbst und geht an jedem Zwischenspeicher vorbei; die
  Store-Zahl daneben holt sich das Panel über `/addons/self/info` direkt beim
  Supervisor.

## [0.2.2] - 2026-08-19

- Inhaltlich identisch mit 0.2.1. Home Assistant hatte 0.2.0 und 0.2.1 nicht
  als Aktualisierung angeboten, obwohl der Klon des Supervisors sie enthielt,
  die Validierung keine Warnung erzeugte und die Images für beide
  Architekturen vorlagen. Mit dem inhaltsgleichen Teststand 0.1.4 kam das
  Update sofort an — der Store arbeitet also. Die Funktionen kehren deshalb
  unter einer frischen Nummer zurück statt unter der bereits vergebenen 0.2.1,
  weil der Supervisor Versionen vergleicht und ein zweites Image unter
  derselben Nummer die Sache nur wieder unklar machen würde.

## [0.2.1] - 2026-08-19

### Security
- **Reitername aus der Adresszeile wurde ungeprüft als Schlüssel benutzt**
  (CodeQL, `js/unvalidated-dynamic-method-call`). `location.hash` landete direkt
  in `loaders[name]()`; ein Fragment wie `#toString` oder `#constructor` hätte
  über die Prototypenkette auf etwas dispatcht, das kein Loader ist. Der Name
  wird jetzt an einer Stelle gegen die feste Liste der Reiter geprüft, `loaders`
  und der Zwischenspeicher sind ohne Prototyp angelegt, und aufgerufen wird nur
  eine eigene Eigenschaft, die auch wirklich eine Funktion ist. Im Browser
  gegengeprüft: `#toString`, `#constructor`, `#__proto__` und `#hasOwnProperty`
  landen auf der Übersicht, `#alerts`, `#settings` und `#decisions` weiterhin
  auf ihrem Reiter.

## [0.2.0] - 2026-08-19

### Added
- **Alarme lassen sich verdichten.** Neben der Einzelansicht gibt es jetzt
  „nach Adresse" und „nach Szenario". Die Gruppierung zeigt Trefferzahl, alle
  dort gesehenen Szenarien beziehungsweise Adressen, Land, Netz und das letzte
  Auftreten. Aus hundert Einzelzeilen wird damit auf einen Blick sichtbar, dass
  achtundvierzig davon von derselben Adresse stammen und drei verschiedene
  Angriffsmuster auslösen — der Unterschied zwischen einem echten Angreifer und
  einem Fehlalarm, der stur dasselbe Szenario meldet.
- **Sperren direkt aus einem Alarm.** Jede Zeile mit einer Quelladresse hat einen
  Knopf, der nur noch nach Dauer und Grund fragt. Kein Abtippen der Adresse in
  den Reiter „Neue Sperre" mehr.
- **Sensoren in Home Assistant.** `sensor.crowdpanel_decisions`,
  `sensor.crowdpanel_decisions_local`, `sensor.crowdpanel_alerts_24h` und
  `binary_sensor.crowdpanel_lapi`. Der zweite ist der aussagekräftige: Die
  Gesamtzahl schwankt mit jeder Blocklisten-Aktualisierung um Tausende, die
  selbst erkannten Sperren sind eine kleine, verwertbare Zahl. Intervall über
  `ha_sensor_interval`, abschaltbar über `ha_sensors`.

### Changed
- Der Alarm-Reiter nennt jetzt wie die Sperren-Tabelle die Gesamtzahl neben den
  angezeigten Zeilen und weist auf eine Kürzung hin.
- Filteränderungen im Alarm-Reiter laden sofort neu, statt auf „Anwenden" zu
  warten.

### Notes
- Lehnt Home Assistant die Sensoren ab, steht das genau einmal im Protokoll —
  danach nicht mehr, damit eine Fehlkonfiguration das Log nicht flutet. Das
  Add-on deklariert dafür `homeassistant_api: true`.

## [0.1.4] - 2026-08-19

- Diagnose-Stand, inhaltlich identisch mit 0.1.3 und zeitlich nach 0.2.1
  veröffentlicht. Dient nur der Eingrenzung, warum Home Assistant 0.2.x nicht
  als Aktualisierung angeboten hat.

## [0.1.3] - 2026-08-19

### Added
- **Whitelists werden angezeigt.** CrowdSec kennt zwei Arten von Ausnahme, die
  sich leicht verwechseln lassen: Allowlists liegen in der Datenbank und
  verhindern die Sperre, Whitelists sind Parser-Dateien und greifen schon beim
  Lesen der Logzeile — die LAPI sieht sie nie. Der Reiter zeigt jetzt beide,
  mit einer Erklärung des Unterschieds. Die YAML-Dateien werden aus
  `/homeassistant/.storage/crowdsec/config/parsers/s02-enrich` gelesen; liegen
  sie woanders, hilft die neue Option `whitelist_dir`.

### Changed
- Neues Mapping `homeassistant_config:ro` — **nur lesend**, ausschließlich für
  diese Anzeige. Symbolische Verweise aus dem Verzeichnis heraus werden
  übersprungen, Dateien über 256 KB nicht angezeigt. Home Assistant stuft das
  Add-on wegen des Mappings sicherheitstechnisch herunter.

- **Blocklisten-Updates zählen nicht mehr als Erkennung.** CrowdSec meldet jede
  Aktualisierung einer abonnierten Blockliste als Alarm — „update : +15000/-0
  IPs", ohne Ereignisse, mit 15.000 Entscheidungen daran. In der Auslöser-Liste
  stand das gleichberechtigt neben echten Angriffen. Die Übersicht zählt sie
  jetzt getrennt in einer eigenen Kachel, und der Alarm-Reiter hat einen Filter
  „nur Erkennungen" (Vorgabe), „nur Blocklisten-Updates" oder „alles"; in der
  Tabelle sind sie zusätzlich als solche gekennzeichnet.
- Der Alarm-Reiter nennt jetzt wie die Sperren-Tabelle die Gesamtzahl neben den
  angezeigten Zeilen.

### Notes
- Ändern lassen sich Whitelists weiterhin nur mit einem Editor, Allowlists nur
  mit `cscli allowlists` — die LAPI bietet für beides keine Schreibschnittstelle.

## [0.1.2] - 2026-08-19

### Fixed
- **„Details" bei den Alarmen schien nichts zu tun.** Die Detailansicht wurde
  unter die Tabelle gehängt und lag bei einer vollen Alarmliste weit außerhalb
  des sichtbaren Bereichs. Sie öffnet sich jetzt als Fenster über der Seite,
  schließbar über die Schaltfläche, Esc oder einen Klick daneben.

### Changed
- Das Detailfenster zeigt zusätzlich die Entscheidungen des Alarms und stellt
  jedem Ereignis die eigentliche Anfrage voran (Methode, Pfad, Ziel-Hostname);
  die vollständige Feldliste steht weiterhin darunter.
- Der Service Worker wird nur noch außerhalb von Ingress registriert. Der
  Ingress-Pfad enthält ein Sitzungsmerkmal und ändert sich, ein darunter
  registrierter Worker läuft beim nächsten Aufruf ins Leere — in der Konsole
  stand dafür eine 404-Meldung.

## [0.1.1] - 2026-08-19

### Fixed
- **Allowlists blieben leer** und meldeten „Maschinen-Zugangsdaten werden
  abgelehnt". Die offizielle Swagger-Datei weist `/v1/allowlists` und
  `/v1/allowlists/check` als offen aus, eine laufende CrowdSec-Instanz antwortet
  darauf aber mit 401. Beide Aufrufe schicken jetzt das Maschinen-Token mit.
- **Filter wirkten teils gar nicht.** Gegen eine echte LAPI geprüft: `GET
  /v1/alerts` beachtet `scope`+`value` und `origin`, ignoriert `ip` und `range`
  aber stillschweigend und liefert dann alles zurück. Umgekehrt beantwortet
  `DELETE /v1/decisions` genau `ip` und `range`, während `scope`+`value` mit
  HTTP 500 quittiert wird. Lesen läuft jetzt über `scope`+`value`, Löschen über
  `ip`/`range` oder die Entscheidungs-Kennung.
- **IP prüfen** fand einen abdeckenden Bereich nicht. Da die LAPI nur exakt
  vergleicht, sucht CrowdPanel Bereiche jetzt selbst — dasselbe Ergebnis wie
  `cscli decisions list --ip`.
- **Allowlist-Auskunft war ohne Aussage.** `/v1/allowlists/check` liefert je nach
  Version ein leeres Objekt; dann werden die Listen direkt durchsucht, sodass die
  Antwort immer ein echtes Ja oder Nein ist und die Liste benennt.

### Changed
- **Deutlich schnellere Oberfläche.** Ein einzelner Alarm kann tausende
  Entscheidungen tragen — eine Community-Blockliste kommt als ein Alarm mit
  15.000 davon. Auf einer Instanz mit 29.000 aktiven Sperren dauerte jeder
  Reiterwechsel über eine Sekunde. Jetzt:
  - Übersicht und Sperren teilen sich dieselbe Abfrage, deren Antwort 15 Sekunden
    vorgehalten wird; jede Änderung verwirft sie sofort.
  - Die Übersicht zählt direkt über die Alarme, statt für jede Entscheidung ein
    Objekt zu bauen.
  - Die Sperren-Tabelle liefert höchstens `page_size` Zeilen und nennt die
    Gesamtzahl daneben, mit Hinweis auf einen engeren Filter.
  - Der Browser zeichnet beim Reiterwechsel sofort die zuletzt geladenen Daten
    und lädt erst danach nach.
  Gemessen: Übersicht 1,15 s → 0,02 s, Alarme 0,37 s → 0,002 s, Antwort der
  Sperren-Tabelle 27 KB statt mehrerer Megabyte.
- **Herkunft ist jetzt eine Auswahlliste** statt eines Textfelds, gefüllt aus den
  Herkünften, die die Instanz tatsächlich meldet.
- Sammel-Entsperren ist auf 200 Einträge begrenzt; darüber weist CrowdPanel auf
  einen engeren Filter hin, statt hunderte Anfragen loszuschicken.
- `page_size` begrenzt die angezeigten Zeilen, nicht mehr die abgefragten Alarme.

### Notes
- Land und Netz lassen sich nicht über einen Sammel-Filter aufheben — die LAPI
  bietet dafür keinen. Über die Zeile in der Tabelle geht es, dort steht die
  Entscheidungs-Kennung.
- Ein Entsperren per IP hebt auch einen abdeckenden Bereich mit auf. Das ist
  CrowdSec-Verhalten, identisch zu `cscli decisions delete --ip`. Die Schaltfläche
  in der Tabelle nutzt die Kennung und trifft deshalb genau einen Eintrag.

## [0.1.0] - 2026-08-19

### Added
- Erste Fassung: Weboberfläche für eine bestehende CrowdSec-Installation.
- **Übersicht** mit aktiven Sperren, Alarmen der letzten 24 Stunden sowie
  Verteilung nach Art, Herkunft, Land und Szenario.
- **Sperren** — Tabelle aller aktiven Entscheidungen mit Wert, Bereich, Art,
  Szenario, Herkunft, Land, Netz und Restlaufzeit. Filter nach Bereich, Art und
  Herkunft werden an die LAPI durchgereicht, die Volltextsuche wirkt auf die
  angezeigten Zeilen. Einzelne Sperren und die gesamte angezeigte Auswahl lassen
  sich aufheben — nie mehr als auf dem Bildschirm steht.
- **Neue Sperre** für die Bereiche `Ip`, `Range`, `Country` und `AS`, Art `ban`
  oder `captcha`, Dauer aus Vorschlägen oder frei im Go-Format, dazu ein Grund.
- **Alarme** mit Detailansicht samt Ereignissen und Quelle.
- **IP prüfen** — aktive Sperren, Alarmverlauf und Allowlist-Treffer zu einer
  Adresse oder einem Bereich.
- **Allowlists** zum Ansehen.
- **Zwei-Faktor-Anmeldung** (TOTP) für den direkten Port: QR-Code wird lokal
  erzeugt, zehn Backup-Codes zur einmaligen Nutzung, Gerätevertrauen für 30 Tage
  über einen signierten Cookie.
- Über HA-Ingress ohne eigene Anmeldung, über Port 17797 mit Benutzer, Passwort
  und optional TOTP; Sperre nach fünf Fehlversuchen für 15 Minuten.
- Oberfläche und Dokumentation vollständig auf Deutsch und Englisch,
  Dark- und Light-Modus, als PWA installierbar.

### Security
- Zustandsändernde Anfragen brauchen ein signiertes CSRF-Merkmal und einen
  Absender derselben Herkunft.
- Jede Eingabe wird geprüft, bevor sie die LAPI erreicht: Adressen und Bereiche
  über `ipaddress`, Länderkürzel und Netznummern über feste Muster, Dauer über das
  Go-Zeitformat.
- Fehler der LAPI werden auf feste Kennungen abgebildet; Antworttexte des Servers
  erscheinen nie in einer HTTP-Antwort.
- Zustandsdaten liegen in `/data`, 2FA-Datei und Signaturschlüssel mit Rechten 600.

### Notes
- CrowdPanel benötigt einen **Maschinen-Zugang** (`cscli machines add`), keinen
  Bouncer-Schlüssel: Bouncer dürfen Entscheidungen nur lesen.
- Sperren werden mit der Herkunft `cscli` angelegt, damit jeder Bouncer sie
  annimmt; CrowdPanel steht im Szenariotext.
