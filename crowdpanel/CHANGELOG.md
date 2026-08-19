# Changelog

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
