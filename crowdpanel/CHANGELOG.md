# Changelog

## [0.4.3] - 2026-08-20

### Added
- **Die Bouncer gibt es jetzt auch als Sensoren in Home Assistant.** Bisher stand
  in der Übersicht, welcher Bouncer wann zuletzt abgeholt hat — sehen konnte man
  es nur, wenn man hinschaut. Neu sind `sensor.crowdpanel_bouncer_<name>` je
  Bouncer (Zustand ist der letzte Abruf, `device_class: timestamp`),
  `sensor.crowdpanel_bouncers` mit der Anzahl der echten Bouncer und
  `sensor.crowdpanel_bouncers_stale` mit denen, die seit über 10 Minuten nichts
  mehr abholen.

  Damit lässt sich das Ausbleiben eines Abrufs automatisieren: Ein Bouncer, der
  nicht mehr abholt, setzt keine Sperre mehr durch, meldet das aber von sich aus
  nirgends. Abgeleitete Kindeinträge bekommen eine eigene Entität, gelten aber nie
  als gefallen. Verschwindet ein Bouncer aus CrowdSec, wird seine Entität beim
  nächsten Durchlauf entfernt.

### Fixed
- **Der Sprachwechsel im Ingress lud Home Assistant ein zweites Mal in den Tab.**
  Die Schaltflächen DE/EN sprangen nach dem Umstellen auf `/` — also auf die
  Startseite von Home Assistant statt zurück ins Add-on, das hinter dem
  Ingress-Pfad liegt. Sichtbar wurde ein komplettes zweites Home Assistant im
  Rahmen; erst Zurück und erneut Öffnen zeigte CrowdPanel in der neuen Sprache.
  Das Weiterleitungsziel behält den Ingress-Pfad jetzt bei.

## [0.4.2] - 2026-08-19

### Fixed
- **Die Sperren-Tabelle zeigte nicht die neuesten Einträge.** Die Deckelung auf
  `page_size` griff, bevor sortiert wurde — und weil eine einzelne
  Blocklisten-Aktualisierung 15.000 Entscheidungen an einem Alarm mitbringt,
  bestand die ganze erste Seite aus genau diesem einen Alarm. Alle Zeilen
  `CAPI`, alle `http:scan`, und die selbst angelegten oder erkannten Sperren
  waren nie zu sehen.

  Jetzt wird nach Alter sortiert und danach gedeckelt: Oben stehen die
  neuesten. Die Spalte **Angelegt** ist dazugekommen, sortierbar wie die
  übrigen; auf schmalen Bildschirmen fällt sie weg.

  Sortieren allein reichte allerdings nicht — die neuesten Einträge *sind* die
  Blockliste. Der neue Filter **Art** trennt deshalb wie im Alarm-Reiter
  zwischen „eigene Sperren" (Herkunft `crowdsec` und `cscli`, Vorgabe), „nur
  Blocklisten" und „alle".
- **„Letztes Lebenszeichen: noch nie" sah bei CrowdPanel nach einem Ausfall
  aus.** Lebenszeichen schicken nur Agenten — der Teil von CrowdSec, der Logs
  auswertet. Ein Maschinen-Zugang, der die API bloß benutzt, hat dort
  dauerhaft nichts stehen. Statt einer Altersangabe steht jetzt „kein Agent" in
  Grau, mit Erklärung im Tooltip, und der eigene Zugang ist als *dieses Panel*
  gekennzeichnet.
- Die Spalte „Läuft ab" sortiert nach der Restlaufzeit statt nach einem Feld,
  das die LAPI leer lässt.

## [0.4.1] - 2026-08-19

### Fixed
- **Abgeleitete Bouncer wurden fälschlich als tot markiert.** CrowdSec legt
  automatisch einen Kindeintrag `<name>@<adresse>` an, wenn derselbe
  API-Schlüssel von einer anderen Adresse benutzt wird — etwa bei einem
  `curl`-Test während der Fehlersuche. Solche Einträge holen selbst nichts ab,
  ihr letzter Abruf liegt also naturgemäß weit zurück, und CrowdPanel färbte
  sie rot wie einen ausgefallenen Bouncer.

  Sie sind jetzt als *abgeleitet* gekennzeichnet und von der Alterswarnung
  ausgenommen. Der Tooltip erklärt, dass sie sich nur zusammen mit dem
  übergeordneten Bouncer löschen lassen — was man nicht tun sollte, weil das
  den Schlüssel des funktionierenden Bouncers entwertet.

## [0.4.0] - 2026-08-19

### Added
- **Bouncer-Übersicht.** Wer holt die Entscheidungen ab, und wann zuletzt — die
  wichtigste Betriebsfrage, denn ein Bouncer, der seit Minuten nichts geholt
  hat, setzt auch nichts mehr durch. Liegt der letzte Abruf über zehn Minuten
  zurück oder ist der Zugang gesperrt, färbt sich die Zeile rot. Maschinen
  stehen unter Einstellungen.

  Das hatte ich zweimal als unmöglich abgetan, weil die LAPI beides nicht
  hergibt. Seit das Konfigurationsverzeichnis ohnehin lesend eingehängt ist,
  liegt die SQLite-Datei von CrowdSec daneben. Sie wird schreibgeschützt
  geöffnet, und es werden ausschließlich Name, Art, Version, Adresse und
  Zeitstempel ausgelesen — die Spalten mit Schlüsseln und Passwörtern rührt
  CrowdPanel nicht an, gegen eine nachgebaute Datenbank überprüft.
- **Verlauf über mehrere Tage** in der Übersicht, Zeitraum über `history_days`.
  Erkennungen und Blocklisten-Updates getrennt, Tageswerte im Tooltip.
- **Sortierbare Spalten** in Sperren, Alarmen und der gruppierten Ansicht.
  Erster Klick aufsteigend, zweiter absteigend.

### Changed
- **Schmale Bildschirme** zeigen nur noch die tragenden Spalten; Bereich,
  Szenario, Herkunft und Netz fallen unter 820 Pixel weg. Aus neun Spalten
  werden fünf, ohne seitliches Scrollen.
- **Ohne eigene Wahl folgt das Thema dem System** statt stur dunkel zu starten.
  Der Umschalter überschreibt das weiterhin dauerhaft.

### Notes
- Benachrichtigungen bleiben bewusst außen vor: Das kann CrowdSec über
  `cscli notifications` und `profiles.yaml` selbst, und zwar dort, wo die
  Entscheidung entsteht — auch dann, wenn CrowdPanel gar nicht läuft.

## [0.3.1] - 2026-08-19

### Added
- **Ländercodes zeigen beim Überfahren den vollen Namen** — in der Übersicht
  unter „Häufigste Länder", in der Sperren-Tabelle und im Alarm-Reiter, auch in
  der gruppierten Ansicht. `PL` wird zu Polen, und zwar in der Sprache der
  Oberfläche.

  Die Namen kommen über `Intl.DisplayNames` aus dem Browser. Sie in die
  Sprachdateien zu schreiben hätte rund 250 Einträge je Sprache bedeutet, die
  gepflegt werden wollen und bei denen die Oberfläche trotzdem nur die zwei
  Sprachen könnte, die dort stehen. Kennt ein Browser die Funktion nicht,
  bleibt es beim Code wie bisher.

## [0.3.0] - 2026-08-19

### Added
- **Reiter „Hub".** Zeigt, was CrowdSec geladen hat — Collections, Parser,
  Postoverflows, Szenarien, AppSec-Konfigurationen und -Regeln, jeweils getrennt
  danach, ob das Element aus dem Hub stammt oder selbst angelegt wurde. Parser
  und Postoverflows nach Stufe aufgeschlüsselt. Gelesen aus dem
  Konfigurationsverzeichnis von CrowdSec, das seit 0.1.3 ohnehin nur lesend
  eingehängt ist; abweichende Pfade über die neue Option `crowdsec_dir`.

  Hub-Elemente liegen dort als symbolische Verweise in ein Verzeichnis
  innerhalb des CrowdSec-Containers. CrowdPanel kommt an das Ziel nicht heran
  und liest den Namen deshalb aus dem Verweis — `crowdsecurity/appsec-crs`
  bleibt so lesbar, obwohl die Datei selbst nicht geöffnet werden kann.

### Notes
- Versionen und `update-available` fehlen bewusst. `cscli` ermittelt sie über
  den Hub-Index, und der liegt ebenfalls im Container — das Supervisor-Protokoll
  sagt es ausdrücklich: `Skipping hub update, index file is not in a volume`.
  Dafür bleibt `cscli hub list` das richtige Werkzeug.
- Die Whitelist-Ansicht findet ihr Verzeichnis jetzt über dieselbe Wurzel;
  `whitelist_dir` wirkt weiterhin, wird aber nur noch gebraucht, wenn die
  Struktur von der üblichen abweicht.

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
