# Changelog

## 0.7.21

- 🔐 **Zwei-Faktor-Authentifizierung (2FA) für den Admin** — Der direkte Login (Port 17761) lässt sich optional mit einem zeitbasierten Einmalcode (TOTP, RFC 6238) absichern. Einrichtung im Tab **System → 2FA**: QR-Code scannen (Google Authenticator, Aegis, 1Password …) oder Geheimnis manuell eintragen, mit einem Code bestätigen — danach verlangt der Login nach Benutzername/Passwort zusätzlich den Code. Es gibt **10 einmalige Backup-Codes** (für den Fall eines verlorenen Geräts), neu erzeugbar. **Über Home Assistant (Ingress) ist 2FA bewusst nicht erforderlich**, da HA die Authentifizierung dort bereits übernimmt. Das TOTP-Verfahren ist mit der Standardbibliothek umgesetzt; Secret und (gehashte) Backup-Codes liegen in `admin_2fa.json` und werden vom Backup mitgesichert.

## 0.7.20

- 🗑 **Nachrichten löschen** — Mitglieder können einzelne Nachrichten (✕ an der Sprechblase) oder eine ganze Unterhaltung (🗑 in der Kopfzeile) löschen. Das Löschen wirkt **nur für einen selbst** — die Gegenseite behält ihre Sicht; erst wenn beide gelöscht haben (oder ein Konto entfernt wurde), wird der Eintrag endgültig aus `dm.json` entfernt.
- ⏰ **Erinnerungs-Mail bei ungelesenen Nachrichten** — Bleibt eine neue Nachricht **3 Stunden ungelesen**, bekommt der Empfänger eine **E-Mail** (sofern Mailserver + öffentliche URL gesetzt). Die Mail enthält **bewusst keinen Inhalt und keinen Absender** — nur einen Hinweis und den **Link zum Postfach**. Pro ungelesener Nachricht wird höchstens **einmal** erinnert; ein Hintergrund-Dienst prüft das alle 15 Minuten.

## 0.7.19

- ✉️ **Mitglieder-Nachrichten (verschlüsselt)** — Eingeloggte Mitglieder können sich im geschützten Bereich gegenseitig private Nachrichten schreiben: neues **Postfach** mit Unterhaltungen, Ungelesen-Zähler und Empfänger-Auswahl per **durchsuchbarem Dropdown** (zeigt nur Mitglieder, die Nachrichten empfangen). Die **Nachrichtentexte werden verschlüsselt** auf der Platte gespeichert (Fernet/AES, Schlüssel in `dm.key`) — Metadaten wie Zeitstempel bleiben für die Listenansicht im Klartext. **Pro Mitglied abschaltbar**: jedes Mitglied kann den Empfang im eigenen Profil deaktivieren, der Admin kann es zusätzlich pro Mitglied erzwingen. Global im Design-Tab ein-/ausschaltbar. **Backup/Restore** sichern `dm.json` und `dm.key` mit, sodass verschlüsselte Nachrichten nach einer Wiederherstellung lesbar bleiben.

## 0.7.18

- 🔒 **CodeQL: Open-Redirect-Warnungen behoben** — Beim Absenden eines Blog-Kommentars wird das Redirect-Ziel jetzt aus dem **validierten Beitrag** (`post['id']`) statt direkt aus dem URL-Parameter gebildet. Funktional identisch, aber ohne Taint-Fluss von der Anfrage in `redirect()` (2 MEDIUM-Findings).

## 0.7.17

- ✏️ **Markdown-Editor an weiteren Feldern** — Der Editor-Button (Werkzeugleiste + Live-Vorschau) ist jetzt überall verfügbar, wo Text als Markdown gerendert wird: **Wartungsmodus-Text**, **Formular-Danke-Text**, **Login-Nachricht je Benutzer** und **Standort-Öffnungszeiten** (zusätzlich zu Blog, Seiten, Projekten, Bio, Newsletter, Formular-Einleitung, Tipps und FAQ-Antworten).

## 0.7.16

- 💅 **Design-Vorlagen einzeilig & scrollbar** — Die Vorlagen-Galerie im Design-Tab bricht nicht mehr auf mehrere Zeilen um, sondern bleibt eine Zeile mit horizontalem Scrollen und denselben Rand-Pfeilen wie die Admin-Tableiste (zeigen an, dass links/rechts weitere Vorlagen sind).

## 0.7.15

- ⏳ **Countdown auch im Wartungsmodus** — Ist ein Countdown eingerichtet, erscheint er jetzt zusätzlich auf der „Seite im Aufbau"-Vollbildseite (Wartungsmodus) — fertige Coming-Soon-Seite inkl. „Benachrichtige mich"-Newsletter-Button, der dort auch während des Wartungsmodus funktioniert. (Countdown-Markup intern in ein wiederverwendbares Partial ausgelagert.)
- ◀▶ **Admin-Tableiste: Scroll-Pfeile** — Passt die Tab-Navigation nicht in die Breite, erscheinen an den Rändern dezente Pfeile mit Verlauf, die anzeigen, dass links/rechts weitere Tabs sind (klickbar zum Scrollen). Der aktive Tab wird beim Wechsel automatisch in den sichtbaren Bereich gerückt.

## 0.7.14

- ⏳ **Countdown-Sektion** — Neuer Startseiten-Abschnitt, der sichtbar auf ein Zieldatum/-zeit herunterzählt (Eröffnung, Launch, Veranstaltung …). Kacheln für Tage/Stunden/Minuten/Sekunden im Karten-Stil mit Akzentfarbe, theme-bewusst — passt sich automatisch ans gewählte Design an. Konfigurierbar: Überschrift, Untertitel und optionales Bild darüber (alle DE/EN), frei wählbarer „Es ist soweit!"-Text bei Ablauf, und ein **optionaler „Benachrichtige mich"-Button**, über den Besucher ihre E-Mail fürs Newsletter-Abo hinterlegen (mit Bestätigung direkt auf der Startseite). Wie jede Sektion: per Drag sortierbar, ein-/ausblendbar, sogar „nur für Mitglieder". Leeres Zieldatum = Abschnitt aus.

## 0.7.13

- 🐳 **Standalone-Betrieb dokumentiert** — MyPage lässt sich auch ohne Home Assistant als reiner Docker-Container betreiben. Neu im Repo: `docker-compose.yml`, `options.example.json` und eine Schritt-für-Schritt-Anleitung **[STANDALONE.md](STANDALONE.md)** / **[STANDALONE.en.md](STANDALONE.en.md)** (inkl. Konfigurations-Tabelle, HTTPS via Caddy, Updates/Backup, Sicherheitshinweise). Keine Code-Änderung — die HA-Funktionen (Sensoren/Notifications/Ingress) waren schon immer optional und werden ohne `SUPERVISOR_TOKEN` übersprungen.

## 0.7.12

- 🔗 **Teilen-Buttons auch auf Projekt-Detailseiten** — Die im Design-Tab aktivierbaren Teilen-Buttons erscheinen jetzt nicht nur unter Blog-Beiträgen, sondern auch am Ende von Projekt-Detailseiten (`/p/<id>`).

## 0.7.11

- ↪️ **Weiterleitungen (301/302)** — Neuer Bereich im System-Tab: alte/geänderte Adressen dauerhaft (301) oder temporär (302) auf eine neue Adresse umleiten (interner Pfad oder vollständige URL). Greift bewusst nur für nicht (mehr) existierende Pfade, sodass echte Seiten nie überschrieben werden. Ideal nach Slug-Änderungen, damit alte Links/Lesezeichen weiter funktionieren. Regeln liegen in `site.json` (im Backup).

## 0.7.10

- 🔗 **Teilen-Buttons unter Blog-Beiträgen** — Im Design-Tab aktivierbar (Standard aus). Zeigt unter jedem Beitrag Buttons für **WhatsApp, X, Facebook, LinkedIn, E-Mail** und **Link kopieren** sowie auf Mobilgeräten den nativen Teilen-Dialog. Datenschutzfreundlich: reine Share-Links, kein Tracking-Skript, es wird nichts von Drittanbietern nachgeladen.

## 0.7.9

- 🔎 **Search-Console-Verifizierung** — Im Design-Tab zwei neue (optionale) Felder für den **Google-Search-Console-** und **Bing-Webmaster-Code**. MyPage setzt daraus das passende Meta-Tag in den Kopf der Startseite (HTML-Tag-Methode). Man kann auch das ganze Meta-Tag einfügen — der Code wird herausgelesen und auf unbedenkliche Zeichen gefiltert. Leer = nichts passiert.

## 0.7.8

- 🔒 **Fotoalben nur für Mitglieder** — Wie bei Blog/Seiten gibt es jetzt je Album einen Schalter „🔒 Nur für Mitglieder". Gäste sehen statt der Fotos eine Schloss-Karte (Titel + Anzahl + Login-Link); die Bild-Adressen des Albums werden für sie nicht ausgeliefert. Eingeloggte Mitglieder sehen das Album normal. Im statischen Export bleiben gesperrte Alben außen vor.

## 0.7.7

- 💅 **Admin-Tableiste einzeilig** — Durch die neuen Tabs (Seiten, Formulare) brach die Navigationsleiste im Admin-Panel auf zwei Zeilen um. Sie bleibt jetzt auf einer Linie und wird bei Platzmangel horizontal scrollbar.

## 0.7.6

- 🔒 **Mitglieder-only-Inhalte** — Blog-Beiträge, eigene Seiten und ganze Startseiten-Sektionen lassen sich auf **angemeldete Mitglieder** beschränken. Beiträge/Seiten: Schalter „🔒 Nur für Mitglieder" im Editor; Gäste sehen in der Liste ein Schloss und auf der Seite nur Titel + kurzen Anriss + „Zum Mitglieder-Login" (Kommentare/Galerie/Video verborgen), Mitglieder sehen alles. Sektionen: neues Schloss-Symbol je Abschnitt im Tab „Inhalt" — für Gäste komplett ausgeblendet (inkl. Navigation), für Mitglieder sichtbar. Der Anriss zeigt höchstens die Hälfte des Textes, sodass auch kurze Inhalte geschützt bleiben; Export/Suchmaschinen sehen nichts Geschütztes.

## 0.7.5

- 📢 **Ankündigungs-Banner** — Eine schmale Hinweisleiste ganz oben auf allen öffentlichen Seiten (z. B. „Sommerfest am 12.7.!"). Text in DE/EN, optionaler Link (URL oder interner Pfad) mit eigenem Link-Text, in Akzentfarbe. Wahlweise **schließbar** (Besucher kann es ausblenden; bei geändertem Text erscheint es erneut). Einstellbar im Design-Tab.

## 0.7.4

- 🧾 **Formular-Baukasten** — Neben dem einen Kontaktformular lassen sich jetzt **beliebige Formulare** anlegen (Veranstaltungs-Anmeldung, Umfrage, Anfrage …). Neuer Admin-Tab **„Formulare"** mit Feld-Editor: Feldtypen **Text, mehrzeilig, E-Mail, Telefon, Zahl, Datum, Auswahl (Dropdown), Auswahl (Radio), Kontrollkästchen**, je Feld DE/EN-Bezeichnung, Platzhalter, Pflicht-Schalter und Optionen; Felder per Drag sortierbar. Einleitung & Danke-Text in Markdown (DE/EN). Jedes Formular ist unter `/formular/<slug>` erreichbar (optionaler Navi-Eintrag, Entwurf/Veröffentlicht, Vorschau). **Einsendungen** erscheinen im Tab „Nachrichten" (mit 📋-Markierung und allen Feldern) und lösen — je Formular abschaltbar — dieselbe Benachrichtigung wie das Kontaktformular aus (E-Mail/Telegram/HA). Spam-Schutz wie gehabt: Honeypot, Rechen-Captcha und Rate-Limit.

## 0.7.3

- 🎨 **Design-Vorlagen (1-Klick-Stile)** — Oben im Design-Tab gibt es jetzt eine Galerie fertiger Vorlagen: **Elegant Dunkel, Hell & Clean, Verspielt, Tech Neon, Magazin, Natur Warm** und **Standard**. Jede Kachel zeigt eine Mini-Vorschau ihres Looks; ein Klick setzt **Modus, Akzentfarbe, Schrift und Layout** auf einmal. Die Felder werden nur gefüllt — erst „Speichern" wendet die Vorlage an, sodass man gefahrlos durchprobieren kann. Eigenes CSS bleibt unangetastet.

## 0.7.2

- 🧹 **Speicher aufräumen** — Neuer Knopf im System-Tab entfernt hochgeladene Bilder, die in keinem Beitrag, keiner Seite, keinem Projekt und keinem Album mehr verwendet werden (z. B. nach dem Löschen einer Seite). Vor dem Löschen werden Anzahl und freigegebener Speicher angezeigt; **geteilte Bilder bleiben erhalten** (es wird über alle Verweise geprüft). Die Aktion landet im Audit-Log.
- ✍️ **Markdown-Editor auch im Newsletter** — Das Newsletter-Textfeld hat jetzt denselben Editor mit Werkzeugleiste und Live-Vorschau wie Blog und Seiten.

## 0.7.1

- 🖼️ **Markdown-Editor: Bilder, Tabellen & mehr** — Die Werkzeugleiste hat drei neue Knöpfe: **Bild** (URL eingeben **oder** leer lassen und eine Datei direkt hochladen → wird optimiert und um Metadaten/GPS bereinigt), **Tabelle** (fügt eine Vorlage ein) und **Trennlinie**. Die Live-Vorschau zeigt Bilder, Tabellen und Trennlinien jetzt mit an. Damit Tabellen und Codeblöcke auch auf der öffentlichen Seite korrekt erscheinen, sind die Markdown-Erweiterungen `tables` und `fenced_code` aktiviert (gilt für Blog, eigene Seiten, Projekt-Details und Bio).

## 0.7.0

- 📄 **Eigene Seiten** — Neben Startseite und Blog lassen sich jetzt **eigenständige Unterseiten** anlegen (z. B. „Über uns", „Anfahrt", „Vereinsordnung"). Jede Seite hat eine eigene Adresse unter `/seite/<slug>` und Inhalt in **Markdown** (DE/EN, gleicher Editor mit Live-Vorschau wie beim Blog). Pro Seite: frei wählbare Adresse (oder automatisch aus dem Titel; reservierte/doppelte werden umgangen), Schalter **„In der Navigation zeigen"** und **Veröffentlicht/Entwurf** (Entwürfe nur über die Admin-Vorschau sichtbar). Reihenfolge per Drag & Drop. Sichtbare Seiten landen automatisch in `sitemap.xml` und im statischen Export; die Daten liegen in `site.json` (im Backup). Neuer Admin-Tab **„Seiten"**.

## 0.6.161

- 🔐 **Bild-Uploads: EXIF-Orientierung + Metadaten entfernt** — Hochgeladene Bilder werden jetzt vor dem Speichern korrekt nach ihrer EXIF-Orientierung gedreht (Handy-Hochkant-Fotos erscheinen richtig herum), und beim WebP-Re-Encode werden sämtliche Metadaten verworfen — inklusive eines evtl. eingebetteten **GPS-Standorts**. (GIFs bleiben für die Animation unverändert.)

## 0.6.160

- 👁 **Aufrufe je Blog-Beitrag** — Jeder Beitrag zählt jetzt seine Aufrufe (ohne Bots). Die Zahl steht im Admin in der Beitragsliste und erscheint dezent neben dem Datum auf der Beitragsseite. Zähler in `stats.json` (im Backup).
- 💅 **Reaktions-Buttons: Emoji zentriert** — Ohne Zähler (0 Reaktionen) saßen die Emojis durch das leere Zähler-Feld leicht links; jetzt sind sie sauber mittig, das Zähler-Feld erscheint erst ab der ersten Reaktion.

## 0.6.159

- 💬 **Kommentar-Antworten & Autor-Benachrichtigung** — Mitglieder können jetzt auf Blog-Kommentare antworten (Antwort-Threads, eine Ebene eingerückt). Antwortet jemand auf einen Kommentar, erhält dessen Autor – sofern ein Mailserver konfiguriert ist – eine E-Mail mit Vorschau und Link zur Diskussion (nicht bei Antwort auf den eigenen Kommentar).

## 0.6.158

- 📰 **Newsletter / Blog-Abo** — Besucher können den Newsletter auf der Blog-Seite abonnieren (Double-Opt-in: Eintrag → Bestätigungs-Mail → bestätigt). Im Blog-Tab schreibst du eine Nachricht (Betreff + Markdown) und sendest sie an alle bestätigten Abonnenten; jede Mail enthält einen Abmelde-Link. Abonnentenliste mit Anzahl und Einzel-Löschen. Schutz: Honeypot, Rate-Limit, keine E-Mail-Enumeration. Aktivierbar im Design-Tab (Standard aus); benötigt SMTP + öffentliche URL. Liste in `subscribers.json` (im Backup).

## 0.6.157

- 🛡️ **Admin-Protokoll (Audit-Log)** — Im System-Tab werden jetzt sicherheitsrelevante Admin-Aktionen mit Zeitpunkt und IP protokolliert: erfolgreiche und fehlgeschlagene Logins, Benutzer angelegt/gelöscht/freigegeben, Passwort/Quota/Spiele geändert, Einstellungen gespeichert und Backup eingespielt. Die letzten 500 Einträge liegen in `audit.json` und werden im Backup mitgesichert.

## 0.6.156

- 🔔 **„Offene Freigaben" in Home Assistant** — Neuer Sensor `sensor.mypage_pending_approvals` zeigt, wie viele selbst-registrierte (E-Mail-bestätigte) Konten auf deine Freigabe warten. Solange welche offen sind, bleibt zusätzlich eine **stehende HA-Benachrichtigung** sichtbar; sie verschwindet automatisch, sobald alles freigegeben ist. Aktualisiert sofort bei Bestätigung/Freigabe (sonst alle 2 Min).

## 0.6.155

- 👤 **Mitglieder: eigenes Profil** — Eingeloggte Mitglieder können im Bereich jetzt einen **Anzeigenamen** setzen (wird z. B. bei Blog-Kommentaren verwendet) und ihr **Passwort selbst ändern** (mit Eingabe des aktuellen Passworts). Beim Passwortwechsel bleibt die aktuelle Sitzung bestehen, andere Geräte werden abgemeldet.
- ℹ️ Hinweis: Die volle Breite des „Anzeigename"-Felds im Registrierungsformular ist seit 0.6.154 behoben — dafür muss das Add-on auf ≥ 0.6.154 aktualisiert sein.

## 0.6.154

- 💅 **Registrierung & Benutzerliste — kleine UI-Korrekturen** — Das Feld „Anzeigename" im Registrierungsformular ist jetzt so breit wie die übrigen Felder (das Captcha-Feld bleibt bewusst kompakt). In der Admin-Benutzerliste steht der Status selbst-registrierter Konten nicht mehr als langer Text in der Info-Zeile, sondern als kompaktes Badge direkt beim Namen (🆕 unbestätigt / ⏳ wartet auf Freigabe) — spart Platz und ist klarer.

## 0.6.153

- 📖 **Doku: eigener Abschnitt „Selbst-Registrierung"** — In DOCS.md ist die Selbst-Registrierung jetzt als ausführlicher, eigener Abschnitt beschrieben (Aktivieren, zweistufiger Ablauf, Vorgaben für neue Konten, Schutzmaßnahmen) statt nur als kurze Notiz.

## 0.6.152

- 🆕 **Selbst-Registrierung für Mitglieder** — Besucher können sich (wenn aktiviert) über „Konto erstellen" auf der Login-Seite selbst anmelden. Zweistufig: erst **E-Mail-Bestätigung** (Link, 24 h gültig), dann **Admin-Freigabe** (Button „Freigeben" in der Benutzerliste). Selbst-registrierte Konten starten ohne Spielezugang und mit einstellbarer Standard-Quota. Schutz: Captcha, Honeypot, Rate-Limit, keine E-Mail-Enumeration; HA-Benachrichtigung bei jeder Registrierung. Aktivierbar im Design-Tab (Standard aus); benötigt SMTP + öffentliche URL.

## 0.6.151

- 📖 **Dokumentation erweitert (DE/EN)** — DOCS.md und beide READMEs (DE/EN) dokumentieren jetzt die neuen Funktionen: Blog-Suche & Tags, Kommentare/Reaktionen, Self-Service-Passwort-Reset, abschaltbare Spiele pro Mitglied, Top-Seiten-Statistik, Spiel-Sensoren und Home-Assistant-Benachrichtigungen (inkl. neuer Option `ha_notify`).

## 0.6.150

- 🎮 **Spiele pro Mitglied abschaltbar** — In der Benutzerverwaltung gibt es jetzt pro Mitglied einen Schalter (🕹️/🚫), mit dem sich die Spiele für dieses Konto sperren lassen. Gesperrte Mitglieder sehen im Bereich keine Spiel-Kacheln mehr, und Spiel-Seiten/-APIs sind serverseitig blockiert (der Dateibereich bleibt normal nutzbar).
- 🧹 **Benutzerverwaltung aufgeräumt** — Die Buttons „Dateien" und „Login-Nachricht" sind jetzt platzsparend nur noch als Symbol mit Tooltip dargestellt.

## 0.6.149

- 💬 **Blog: Kommentare & Reaktionen für Mitglieder** — Angemeldete Mitglieder können Blog-Beiträge kommentieren und mit Emoji reagieren (👍 ❤️ 😄 🎉 👏, eine Reaktion pro Person, umschaltbar). Aktivierbar über einen neuen Schalter in den Design-Einstellungen (Standard: aus). Im Admin gibt es unter „Nachrichten" eine Moderationsliste, in der sich einzelne Kommentare löschen lassen; bei neuen Kommentaren kommt zusätzlich eine HA-Benachrichtigung. Kommentare werden im Backup mitgesichert.

## 0.6.148

- 📊 **Statistik: Top-Seiten** — Das Statistik-Dashboard zeigt jetzt zusätzlich die meistbesuchten Seiten (aus den letzten Aufrufen, ohne Bots). Für Blog-Beiträge und Projekt-Detailseiten wird der Titel angezeigt statt nur der Pfad.
- 🏷️ **Add-on-Option `ha_notify` beschriftet** — Die in 0.6.146 ergänzte Option zeigte im HA-Konfigurations-UI nur den Schlüssel; jetzt mit Name und Beschreibung (DE/EN).

## 0.6.147

- 🔎 **Blog: Suche & Schlagwörter (Tags)** — Beiträge können jetzt im Admin mit Schlagwörtern versehen werden (komma-getrennt, max. 8). Auf der Blog-Seite gibt es ein **Suchfeld** (durchsucht Titel, Text und Tags in DE+EN) und **Tag-Filter-Chips**; Suche und Tag lassen sich kombinieren. Auf jeder Beitragsseite werden die Tags angezeigt und verlinken auf die gefilterte Blog-Ansicht. Geplante/Entwurfs-Beiträge tauchen weder in der Suche noch in der Tag-Liste auf.

## 0.6.146

- 🔔 **Home-Assistant-Benachrichtigungen** — MyPage meldet sich jetzt aktiv in HA (persistente Benachrichtigung): bei **neuer Kontaktnachricht** (mit Absender + Vorschau) und bei **verdächtigen Anmeldeversuchen** (wenn eine IP wegen zu vieler Fehllogins gesperrt wird). Wiederholungen derselben IP überschreiben dieselbe Meldung statt zu spammen. Abschaltbar über die neue Add-on-Option `ha_notify` (Standard: an). Ergänzt die bestehenden Telegram-/E-Mail-Hinweise und die HA-Sensoren.

## 0.6.145

- 🔑 **Mitglieder: Passwort selbst zurücksetzen** — Auf der Login-Seite gibt es jetzt „Passwort vergessen?". Das Mitglied gibt seine E-Mail ein und bekommt einen zeitlich begrenzten Link (1 Stunde gültig), über den es ein neues Passwort setzen kann — ganz ohne Admin. Aus Sicherheitsgründen: immer dieselbe neutrale Rückmeldung (keine Rückschlüsse, ob eine E-Mail existiert), Token nur einmal verwendbar, Rate-Limit pro IP, und nach dem Zurücksetzen werden alle bestehenden Sitzungen beendet. Der Link erscheint nur, wenn E-Mail-Versand (SMTP) und die öffentliche URL konfiguriert sind.

## 0.6.144

- ⏱️ **Glücksrad-Finale: Zeitablauf wird sauber aufgelöst** — Läuft im Finale die Zeit ab, ohne dass gelöst wurde, passierte bisher nichts (die leere Eingabe wurde verschluckt, der Timeout nie festgeschrieben). Jetzt ertönt ein negativer Sound, anschließend deckt sich die Lösung langsam auf, und das Spiel wird beendet.
- 🔁 **Glücksrad-Finale: Countdown läuft serverautoritativ weiter** — Verlässt man das Spiel im Finale und kommt zurück, startet der Countdown nicht mehr von vorn, sondern macht mit der verbleibenden Zeit weiter (war die Zeit schon abgelaufen, wird sofort aufgelöst).

## 0.6.143

- 🎯 **Glücksrad: Start-Auslosung bleibt stehen** — Beim „Wer fängt an?" zu Spielbeginn drehen alle drei (Spieler, Lisa, Max) reihum. Bisher verschwand der erdrehte Betrag, sobald der nächste dran war. Jetzt zeigt eine feste Tafel die Beträge **aller** Spieler und füllt sich, bis alle drei gedreht haben. Erst wenn der Startspieler feststeht (kurz hervorgehoben) oder bei Gleichstand verschwindet die Tafel wieder. Wird nur zur Start-Auslosung angezeigt.

## 0.6.142

- 🖥️ **Glücksrad: neue Kategorie „Computer & IT"** — 20 neue Begriffe rund um Computer und IT (z. B. FESTPLATTE, ARBEITSSPEICHER, ZWISCHENABLAGE, HAUPTPLATINE, EINGABEAUFFORDERUNG). Bewusst echte deutsche Wörter, die sich vom englischen Begriff unterscheiden — nicht einfach das englische Wort.

## 0.6.141

- 🔒 **Sicherheit: CodeQL-Pfadwarnungen behoben** — Alle Spielstand-Dateipfade (66, 20 AB, Schwimmen, Mau-Mau, Präsident, Jeopardy, Glücksrad, Sitzungs-Log) werden jetzt über `safe_under`/`safe_join` zusammengesetzt statt direkt per f-String. Funktional unverändert (die UID war bereits regex-validiert), beseitigt aber die als „uncontrolled data in path expression" geflaggten Stellen.

## 0.6.140

- ⏸️ **Glücksrad: echte Pause (friert sofort ein)** — Bisher lief der gerade laufende Zug (Rad drehen, Buchstaben aufdecken) noch komplett zu Ende, bevor die Pause griff. Jetzt wird **sofort an Ort und Stelle eingefroren**: Das Rad hält mitten im Dreh an, die Buchstaben-Aufdeckung stoppt, Wartezeiten merken sich ihre Restzeit. Beim Fortsetzen läuft alles **genau dort** weiter (kein Springen zum Ergebnis). Gilt für Pause-Button, Leertaste und Auto-Pause beim Tab-Wechsel; auch Münzwurf und Finale-Countdown pausieren mit.

## 0.6.139

- ⏸️ **Glücksrad: Auto-Pause im Hintergrund** — Verlässt man den Tab/das Fenster, geht das Spiel jetzt automatisch in die normale Pause (Overlay) und ist stumm. Fortgesetzt wird **nur manuell** über den Pause-Button bzw. die Leertaste — kein automatisches Weiterlaufen mehr. Ein ReSync ist dabei nicht nötig, weil im Pausenzustand serverseitig nichts passiert.
- 💬 **Glücksrad: Hinweis beim Vokalkauf der KI** — Kauft Lisa oder Max einen Vokal, erscheint jetzt der Hinweis „… kauft einen Vokal (−250 €)" (vorher wurde er vom Treffer/Fehlversuch sofort überschrieben).
- 🔁 **Glücksrad: Rundensieger fängt die nächste Runde an** — Bisher rotierte der Startspieler stur. Jetzt beginnt die nächste Runde immer der, der die letzte gewonnen hat.

## 0.6.138

- ↩️ **Glücksrad: „neutrale Geldzahl"-Rad zurückgenommen** — Das in 0.6.137 eingeführte Verhalten, das Rad zwischen Aktionen auf eine Geldzahl springen zu lassen, war Murks und ist wieder raus. Das Rad verhält sich wie zuvor. (Der Ton-/Hintergrund-Fix aus 0.6.137 bleibt erhalten.)

## 0.6.137

- 🐛 **Glücksrad: Rad zeigt kein irreführendes Sonderfeld mehr** — Das Rad blieb nach einem RISIKO-/BANKROTT-/AUSSETZEN-Dreh auf diesem Sonderfeld stehen. Löste danach ein Spieler das Rätsel (ohne zu drehen!), sah es aus wie „dreht RISK/Bankrott → löst → gewinnt". Jetzt wird das Dreh-Ergebnis nur noch angezeigt, **solange der Spieler darauf reagiert** (Konsonant/Vokal wählen, Risiko, Extraleben); danach ruht das Rad auf einer neutralen Geldzahl. Ein altes Sonderfeld kann nie mehr so wirken, als hätte es den Zug oder das Lösen entschieden.
- 🔇 **Glücksrad: kein Ton im Hintergrund-Tab** — Wechselt man in einen anderen Tab/Fenster, ist das Spiel jetzt wirklich pausiert und **komplett stumm** (vorher liefen Sounds weiter). Beim Zurückkehren geht es synchron weiter.

## 0.6.136

- 🐛 **Glücksrad: Desync im Hintergrund-Tab behoben** — Lief das Spielfenster im Hintergrund (anderes Fenster/Tab im Vordergrund), drosselte der Browser die Animations-Timer so stark, dass das Rad auf einem alten Frame hängenblieb (z. B. BANKROTT), während Tafel und Punkte schon weiter waren — es sah aus, als würde die KI „auf Bankrott drehen und trotzdem gewinnen". Jetzt **pausiert die KI, solange der Tab verborgen ist** (man verpasst nichts), und beim Zurückkehren wird der Zustand **hart vom Server synchronisiert** und das Rad auf die echte Position gesetzt. Das Rad spiegelt zudem immer den tatsächlichen Spielzustand und kann nicht mehr auf einem Geister-Frame hängen.

## 0.6.135

- 🎭 **Glücksrad: Spannung beim KI-Lösen wirklich überall** — Der Hinweis „🧠 {Name} versucht zu lösen …" erscheint jetzt zuverlässig, egal wie ein KI-Gegner (Lisa/Max) die Runde gewinnt (geraten oder durch Komplettieren), inkl. langsamem Aufdecken. Die KI rät außerdem etwas früher, sodass mehrere Buchstaben spannend nacheinander aufgehen. Auch das **Finale der KI** wird jetzt mit Einblendung und langsamem Aufdecken gezeigt (vorher sprang es sofort zum Ergebnis).
- 🎉 **Konfetti nur noch beim eigenen Sieg** — Gewinnt ein KI-Gegner eine Runde, das Finale oder das Spiel, gibt es kein Konfetti/Jubel mehr — das bleibt jetzt dem Spieler vorbehalten.

## 0.6.134

- 🎭 **Glücksrad: Spannung beim Lösen** — Versucht ein KI-Gegner (Lisa/Max) zu lösen, blendet sich jetzt „🧠 {Name} versucht zu lösen …" ein; bei richtiger Lösung gehen anschließend **alle Buchstaben langsam nacheinander auf** (statt sofort), dann Jubel/Konfetti. Bei falschem Versuch erscheint die Einblendung mit der Auflösung. Löst der Mensch korrekt, wird die Lösung ebenfalls Buchstabe für Buchstabe aufgedeckt.

## 0.6.133

- 🐛 **Glücksrad: Hänger, wenn die KI eine Runde gewinnt** — Der „Weiter"-Button erschien nur, wenn der Mensch am Zug war; gewann die KI die Runde, blieb das Spiel stehen. Der Button wird jetzt bei jedem Rundenende angezeigt, sodass es immer weitergeht.

## 0.6.132

- 🎭 **Glücksrad: Spannung beim Aufdecken** — Bei mehreren Treffern (z. B. 5× derselbe Buchstabe) erschien der Gewinn (5×5000 = 25000 €) sofort im Spielerpanel, noch bevor die Buchstaben nacheinander auf der Tafel auftauchten. Jetzt wird das Rundenkonto **erst nach dem Aufdecken** aktualisiert — für Spieler und KI gleichermaßen.

## 0.6.131

- 🎲 **Jeopardy: frische Spiele statt Wiederholungen** — Aufeinanderfolgende Partien meiden jetzt die zuletzt gesehenen Inhalte (pro Mitglied gespeichert): **keine Kategorie kommt zwei Spiele in Folge** vor, und zuletzt gezeigte **Fragen werden ~5 Spiele lang nicht wiederholt** (auch das Final-Jeopardy meidet sie). Ist der Pool erschöpft, wird sauber zurückgefallen. Je mehr Kategorien der Pool hat (aktuell 12), desto abwechslungsreicher wird zusätzlich die Auswahl.

## 0.6.130

- 🐛 **Glücksrad: gewonnene Spiele wurden als Niederlage gezählt** — Der Sieger wurde im Verlauf falsch gespeichert (`'p'`/`'a'` statt des numerischen Index), wodurch die Statistik trotz Sieg „0 Siege" und im Verlauf „💀 ? (0 €)" zeigte. Der Sieger wird nun korrekt als Index abgelegt; Sieg-/Niederlagezählung und Verlauf (🏆/💀 + Name/Betrag) stimmen wieder. Bereits gespeicherte Alt-Einträge werden dank Abwärtskompatibilität ebenfalls richtig angezeigt.
- 🎯 **Glücksrad: keine Kategorie doppelt pro Spiel** — War eine Kategorie (z. B. „Essen & Trinken") schon dran, kommt sie im selben Spiel nicht noch einmal — auch die Finalrunde zieht eine eigene, neue Kategorie.

## 0.6.129

- 📖 **Glücksrad: Regeln-Button im Spiel** — Die Spielregeln lassen sich jetzt direkt aus dem Spiel öffnen: über einen 📖-Button in der Lobby (neben Statistik/Einstellungen) und ein 📖-Symbol oben im Spielbereich. Sie erscheinen in einem Modal (DE/EN, per Esc/✕ schließbar).
- 🔤 **Glücksrad: Buchstabenleiste in 2 gleichmäßigen Zeilen** — Statt A–Y in einer Zeile mit einsam umbrechendem „Z" liegt das Alphabet nun sauber als 13 + 13 (A–M / N–Z) vor.

## 0.6.128

- 🎡 **Neues Mitglieder-Spiel: Glücksrad** — Dreh das Rad, rate Buchstaben und löse das Wort-Rätsel gegen zwei KI-Gegner (Lisa & Max). Mit Qualifikationsdrehung, Spezialfeldern (Bankrott, Aussetzen, Risiko 50:50, Extraleben), Vokal-Kauf, 3 Runden und großem Finale (R S T L N E gratis, Bonus verdoppelt das Konto). 300 zweisprachige Rätsel (DE/EN) in 10 Kategorien, drei Schwierigkeitsgrade, Statistik/Verlauf, Cross-Device-Schutz und Handy-Querformat wie die übrigen Spiele.
- 🎯 **Jeopardy: Fragen-Pool stark erweitert** — von 87 auf **359 zweisprachige Clues** und von 6 auf **12 Kategorien** (neu: Musik, Serien & TV, Tierwelt, Mythologie, Computer & IT, Kunst), jeweils sauber über easy/medium/hard verteilt. Dank des Zufalls-Boards (v0.6.127) sorgt das für deutlich mehr Abwechslung pro Partie.

## 0.6.127

- 🎲 **Jeopardy: beliebig viele Kategorien möglich** — Das Board zieht jetzt pro Spiel **6 zufällige** Kategorien aus allen im Fragen-Pool vorhandenen (statt aus einer fest verdrahteten 6er-Liste). Neue Kategorien lassen sich damit **rein über `data/quiz_pool.json`** ergänzen, ganz ohne Code-Änderung — mehr Kategorien = mehr Abwechslung pro Partie. Dazu eine Pflege-Anleitung unter `data/QUIZ_POOL_GUIDE.md`.

## 0.6.126

- 🔔 **Jeopardy: Buzzer-Hinweis größer & für beide gleich** — Der „wer hat gebuzzert"-Hinweis ist jetzt ein großer, gut sichtbarer Banner (deutlich größere Schrift, breiter) — und gilt nun auch für den **Spieler** („🔔 Du warst zuerst dran!", grün), nicht nur für die KI (gold). Anzeigedauer einheitlich **2 Sekunden** (zentrale Konstante `BUZZ_BANNER_MS`). Der Spieler-Banner ist klick-durchlässig, du kannst also sofort antworten.

## 0.6.125

- 🤖 **Jeopardy: KI-Buzzer mit eigenem Sound & deutlichem Hinweis** — Buzzert die KI schneller (oder schnappt sich einen verstrichenen Clue), ertönt jetzt ein tiefer Game-Show-Doppel-Honk (statt des Spieler-Sounds), und ein gut sichtbarer Hinweis „🤖 Die KI war schneller!" blendet sich für 2 Sekunden ein, **bevor** die KI antwortet — vorher ging das zu schnell vorbei. Der Spieler-Buzzer (heller „Lock-in"-Sound) bleibt unverändert.

## 0.6.124

- 🎵 **Jeopardy: Musik nur auf dem Board + kräftigerer Buzzer-Sound** — Die Hintergrundmusik spielt jetzt nur noch auf dem Auswahl-Board (und Startbildschirm) und **pausiert automatisch, sobald ein Clue offen ist**, damit Buzzer-Ticker und Antwort-Sounds nicht übertönt werden; danach läuft sie weiter. Der Buzzer hat einen neuen, deutlich hörbaren „Lock-in"-Sound (aufsteigender Sweep + heller Bestätigungs-Ping) statt des bisher zu leisen Zweitons.

## 0.6.123

- 🐛 **Jeopardy: Reveal zeigt jetzt die echte Punkteänderung** — Bei einer falschen Antwort, die sonst niemand übernahm, stand fälschlich „Niemand bekommt Punkte", obwohl der Punktwert sehr wohl abgezogen wurde. Das Reveal zeigt nun pro Clue die tatsächliche Differenz (z. B. „❌ Du −400" bzw. „🤖 KI −600"); „Niemand bekommt Punkte" erscheint nur noch, wenn sich wirklich nichts ändert (alle haben verstreichen lassen).

## 0.6.122

- 🎵 **Jeopardy: Buzzer-Ticker & optionale Theme-Musik** — Beim Erscheinen eines Clues läuft jetzt ein **Ticker, der mit dem Countdown immer schneller (und höher) wird** (rein per Web-Audio, kein Asset) und beim Buzzern/Verstreichen stoppt. Außerdem kann eine **Hintergrundmelodie** abgespielt werden, umschaltbar über den 🔊-Button (gemerkt). Aus urheberrechtlichen Gründen wird **keine** Musik mitgeliefert: Wer mag, legt eine eigene Datei `jeopardy_theme.m4a` in den Add-on-Konfigurationsordner (Details in der Doku) – fehlt sie, läuft das Spiel ohne Musik weiter.

## 0.6.121

- 🎯 **Neues Mitglieder-Spiel „Jeopardy"** — ein Wissens-Quiz-Duell gegen die KI auf einem klassischen Board (6 Kategorien × 5 Werte 200–1000). Highlights: **Buzzer-Rennen** (schneller drücken als die KI, deren Reaktionszeit & Trefferquote vom Schwierigkeitsgrad abhängt), **Daily Double** (verstecktes Feld mit Einsatz) und **Final Jeopardy** (beide setzen geheim auf den letzten Clue). Server-autoritativ: der Server kennt die Antworten, der Client nie. Inklusive Statistik, HA-Sensor (Live „wer spielt"), Fortsetzen über Geräte hinweg und DE/EN. Erreichbar als Kachel im Mitgliederbereich. Der Fragen-Pool (zweisprachig) basiert teilweise auf der Open Trivia Database (CC BY-SA 4.0), übersetzt und kuratiert.

## 0.6.120

- 🃏 **20 AB: Animation beim KI-Kartentausch** — tauscht eine KI Karten, blenden die getauschten Karten jetzt langsam aus und neue blenden langsam wieder ein (mit Sound), statt nur einer Textmeldung. Berücksichtigt „Reduzierte Bewegung".

## 0.6.119

- 🤔 **Fangfragen: 20 weitere Fragen (jetzt 50) + bessere Lesbarkeit** — der Fragenpool ist von 30 auf 50 Scherz- und Fangfragen gewachsen (u. a. „Was hat ein Auge, kann aber nicht sehen?", „Was ist voller Löcher, hält aber trotzdem Wasser?"), alle DE/EN. Außerdem behoben: Die Antwort-Buttons waren im Dark Mode kaum lesbar (heller Text auf hellem Grund), weil nicht vorhandene CSS-Variablen genutzt wurden. Sie verwenden jetzt die echten Theme-Farben (`--surf2`/`--border`/`--text`); richtige Antwort wird grün, falsche rot hervorgehoben — bei gut lesbarem Text in beiden Themes.

## 0.6.118

- 🤔 **Neues Mini-Game „Fangfragen"** — ein Quiz mit 30 klassischen Scherz- und Fangfragen (Welche Monate haben 28 Tage? Welche Enten laufen auf zwei Beinen? …) als Multiple Choice mit 4 Antworten. Richtige Antwort = ein Punkt, Bestwert wird lokal gespeichert. Fragen und Antworten sind komplett DE/EN lokalisiert, Reihenfolge der Fragen und Antwortoptionen werden bei jedem Durchgang neu gemischt. Erreichbar über den Footer-Link „🎮 Mini Games" (muss in den Design-Optionen aktiviert sein).
- 🃏 **20 AB: mehr Pause nach KI-Reizentscheidung** — nach „KI Links/Rechts spielt/passt" kommt jetzt — wie schon bei Trumpfansage und Kartentausch — die eingestellte Liegezeit als Extra-Pause, damit man die Entscheidung in Ruhe sieht.

## 0.6.117

- 🔊 **20 AB: ergebnisabhängiger Rundensound** — beim Rundenergebnis (Zwischenrunden) klingt es jetzt je nach deinem Ausgang unterschiedlich: gewonnen (Stiche geholt, Punkte runter) = aufsteigend positiv, „Überschuss prallt zurück" = „Boing"-Abpraller, verloren (0 Stiche, +5) = Sad Trombone, gepasst = dezenter neutraler Ton. Am Spielende übernimmt weiterhin der Sieg-/Niederlage-Sound.

## 0.6.116

- 🐛 **20 AB: Fortsetzen hängt bei „KI überlegt…"** — verließ man eine Partie, während die KI am Zug war, blieb sie nach dem Wiedereinstieg stehen, weil die KI-Schleife nicht neu gestartet wurde. `resumeGame()` stößt jetzt `advanceAI()` an (bzw. zeigt das Rundenergebnis / die Auslosung, falls man dort fortsetzt) — wie bei Schwimmen, Mau Mau und Präsident.

## 0.6.115

- 🃏 **20 AB: Verbesserungen** — (1) Kein Sound mehr beim Rundenergebnis. (2) Mehr Pause nach KI-Trumpfansage und (3) nach KI-Kartentausch — jeweils mit der eingestellten Liegezeit aus den Optionen, damit man die Ansage/den Tausch in Ruhe sieht. (4) Handsortierung wie bei 66: zuerst nach Farbe, dann nach Wert, und der Trumpf liegt immer ganz rechts an.

## 0.6.114

- 🐛 **Schwimmen: weitere „Du"-Grammatikfehler korrigiert** — „Du schwimmt!" → „Du schwimmst!", „Du ausgeschieden!" → „Du bist ausgeschieden!" und im Log „Du Klopft!" → „Du Klopfst!". Schwimmt/ausgeschieden jetzt korrekt für Spieler, KI (Einzahl) und Mehrzahl, zudem lokalisiert (vorher fest deutsch). Komplette „Du"-Durchsicht: alle übrigen Stellen (Sieg, Turnier, KI-Anzeigen, Klopf-Status aus v0.6.113) waren bereits korrekt.

## 0.6.113

- 🐛 **Schwimmen: Grammatikfehler „Du hat geklopft!" korrigiert** — wenn der Spieler selbst klopfte, zeigte die Status-Anzeige „Du hat geklopft!". Jetzt korrekt „Du hast geklopft!" (eigene `_you`-Variante; KI bleibt „… hat geklopft!"). Alle übrigen „Du"-Stellen geprüft — Sieg-/Turnier-Texte und KI-Anzeigen waren bereits korrekt.

## 0.6.112

- 🐛 **Mau Mau & Präsident: „Spiel fortsetzen" nach Spielende ausblenden** — war eine Partie beendet (und es wurde keine neue gestartet), erschien auf dem Startbildschirm fälschlich noch der „Spiel fortsetzen"-Button. Jetzt wird er bei beendetem Spiel ausgeblendet — wie bereits bei 66, 20 AB und Schwimmen.

## 0.6.111

- 🧠 **66: stärkere KI, dreht jetzt sinnvoll zu** — die KI drehte den Talon praktisch nie zu (alte Bedingung zu streng). Neu: bei „Schwer" dreht sie zu, sobald sie den Partie-Sieg **erzwingen** kann (Suche mit perfekter Information, nutzt ihre starke Endspiel-Logik); bei „Mittel" eine verbesserte Heuristik. Zusätzlich schont die KI jetzt König/Dame einer noch nicht angesagten Hochzeit, und „Mittel" spielt etwas weniger zufällig. Gilt für beide Varianten (Standard & Andys Oma). In Simulationen (je 150–200 Matches, neue vs. alte KI) gewinnt die neue KI deutlich: Schwer 58 %/66 % (Standard/Oma), Mittel 55 %/53 % — und dreht ~3× häufiger zu.

## 0.6.110

- 📱 **66: Handy-Optimierung (Querformat)** — als letztes der fünf Kartenspiele auch 66 fürs Smartphone optimiert: „Bitte Gerät drehen"-Hinweis im Hochformat, kompaktes Querformat-Layout (Karten an die Höhe gekoppelt, schlanke Top-Leiste, kompaktes Auslosen-Modal), Startbildschirm oben ausgerichtet + scrollbar, angetippte Karten ohne Hochklappen (Ring statt Anheben). Damit sind alle fünf Spiele (66, 20 AB, Schwimmen, Mau Mau, Präsident) im Querformat handytauglich.

## 0.6.109

- 📱 **Schwimmen & 20 AB: Handy-Optimierung (Querformat)** — wie Mau Mau/Präsident: „Bitte Gerät drehen"-Hinweis im Hochformat, kompaktes Querformat-Layout (Karten an die Höhe gekoppelt, schlanke Top-/Scorebar, Gegner-/Tischkarten verkleinert), Startbildschirm oben ausgerichtet + scrollbar (nichts mehr abgeschnitten), und ausgewählte/angetippte Karten werden nicht mehr angehoben (kein Abschneiden), sondern mit Ring markiert. Damit sind alle fünf Kartenspiele fürs Smartphone optimiert.

## 0.6.108

- 📱 **Handy (Mau Mau & Präsident): Startbildschirm & Kartenauswahl gefixt** — im Querformat wurde der Startbildschirm oben/unten abgeschnitten; er ist jetzt oben ausgerichtet und bei Bedarf scrollbar (nichts mehr abgeschnitten). Außerdem klappten ausgewählte/angetippte Karten nach oben und wurden im niedrigen Hand-Streifen abgeschnitten — auf dem Handy werden sie jetzt nicht mehr angehoben, sondern mit einem goldenen Ring markiert.

## 0.6.107

- 📱 **Präsident: Handy-Optimierung (Querformat)** — wie Mau Mau: „Bitte Gerät drehen"-Hinweis im Hochformat, kompaktes Querformat-Layout (kleinere Karten an die Höhe gekoppelt, schlanke Top-/Scorebar mit Rollen, Stich-Bereich verkleinert, Hand und Tausch-Ansicht als einreihiger scrollbarer Streifen) — passt ohne Überlappen auch mit 10 Handkarten aufs Display.

## 0.6.106

- 📱 **Mau Mau: Handy-Optimierung (Pilot)** — auf dem Smartphone wird das Spiel jetzt im Querformat gespielt: Im Hochformat erscheint ein „Bitte Gerät drehen"-Hinweis (DE/EN), im Querformat ist das Layout kompakt und passt ohne Überlappen aufs Display (kleinere Karten, Top-Leiste/Stapel an die Höhe gekoppelt, große Hand bleibt in einer scrollbaren Reihe). Die anderen vier Spiele folgen nach Freigabe.

## 0.6.105

- 🐛 **Mau Mau: Grammatik im Runden-/Spielende-Dialog** — „Du gewinnt die Runde!" war falsch; für den Spieler heißt es jetzt korrekt „Du gewinnst die Runde!" (2. Person), für die KI weiterhin „KI 1 gewinnt die Runde!". Gilt für Rundenende und Spielende, DE und EN.

## 0.6.104

- 🔊 **Mau Mau: Mischsound auch beim Neumischen** — wenn der Nachziehstapel leer ist und die abgelegten Karten neu gemischt werden, ertönt jetzt zuerst der Mischsound, bevor der Stapel neu aufgebaut wird.

## 0.6.103

- 🔊 **Mau Mau: Reihenfolge beim Austeilen korrigiert** — der Stapel in der Mitte (Nachzieh-/Ablagestapel) erschien vor dem Mischsound. Jetzt stimmt die Reihenfolge: erst Mischsound, dann baut sich der Stapel in der Mitte auf, danach werden die Handkarten verteilt.

## 0.6.102

- 🐛 **Mau Mau: Button „gespielte Karten" beim Laden sichtbar** — bei aktivierter Option war der Button (📋) erst sichtbar, nachdem man die Optionen einmal geöffnet und geschlossen hatte. Die Sichtbarkeit wird jetzt schon beim Spielstart aus der gespeicherten Einstellung übernommen (Präsident war bereits korrekt).

## 0.6.101

- 🐛 **66: Undo nach Trumpf-Bube-Tausch / Zudrehen korrigiert** — wer den Trumpf-Buben tauscht (oder den Talon zudreht) und danach eine Karte spielt, bekam beim Undo nur das Kartenspielen zurück; Tausch bzw. Zudrehen blieben bestehen. Jetzt nimmt Undo die ganze Spielerrunde zurück (Bube/Talon wieder im Ausgangszustand). Gleiche Ursachenklasse wie der Mau-Mau-Buben-Bug (Folgeschritt überschrieb den Undo-Stand). 20 AB, Schwimmen und Präsident wurden mitgeprüft — dort tritt das Muster nicht auf (Undo nur für einzelne, zugbeendende Aktionen).

## 0.6.100

- 🐛 **Mau Mau: Undo nach Bube + Farbwunsch korrigiert** — wer einen Buben spielt und eine Farbe wünscht, konnte den Zug zwar rückgängig machen, aber der Bube blieb in der Mitte liegen und der „wünscht…"-Zustand hing fest. Jetzt legt Undo den Buben wieder auf die Hand und hebt den Farbwunsch komplett auf (der Wunsch-Schritt überschreibt den Undo-Stand des Buben-Zugs nicht mehr).

## 0.6.99

- 🔊 **Kartenmisch-Sound jetzt auch bei 66, 20 AB & Schwimmen** — vor dem Aufbau der Hand ertönt der ~1 s lange Misch-Sound (bei 66 zusätzlich zum bestehenden Auslosen-Drumroll, direkt vor dem Austeilen). Damit haben alle fünf Kartenspiele denselben Sound beim Spielstart und jeder neuen Runde. Nur bei aktiviertem Ton.

## 0.6.98

- 🔊 **Mau Mau & Präsident: Kartenmisch-Sound beim Austeilen** — bei jedem neuen Spiel und jeder neuen Runde ertönt jetzt erst ein ~1 s langer Misch-Sound, bevor sich der Kartenstapel aufbaut. Nur bei aktiviertem Ton; bei reduzierter Bewegung/abgeschaltetem Ton ohne Verzögerung.

## 0.6.97

- 🎲 **Zwei neue Mitglieder-Kartenspiele: Mau Mau & Präsident** — beide gegen zwei KI-Gegner, mit drei Schwierigkeitsgraden, Spielstand-Speicherung pro Mitglied, Cross-Device-Session-Schutz, Undo, Regeln (DE/EN) und Statistik. Mau Mau mit Sonderkarten (7 ziehen, 8 aussetzen, Bube Farbwunsch, Ass Richtungswechsel); Präsident mit Rängen, Überbieten, Revolution und Kartentausch.
- 📊 **Admin & HA-Sensoren erweitert** — die neuen Spiele erscheinen im Admin-Panel (Live-Status, Statistik, Sitzungs-Log) und in den Home-Assistant-Spiel-Sensoren (`sensor.mypage_aktiv_maumau`, `sensor.mypage_aktiv_praesident`).

## 0.6.96

- 🧩 **66-Startbildschirm: Layout korrigiert** — die Statistik wird jetzt komplett in einer Reihe dargestellt (die feste Maximalbreite der Startbox hatte das 6er-Raster auf 5+1 umgebrochen), und der „Zum Mitgliederbereich"-Button sitzt nun immer unten, unterhalb der Statistik (wie bei 20 AB/Schwimmen).

## 0.6.95

- 🕒 **Admin: Sitzungs-Verlauf auf 100 erhöht** — das Sitzungs-Log speichert jetzt bis zu 100 Spielsitzungen pro Mitglied (vorher 50) und das Spiele-Fenster zeigt entsprechend bis zu 100 (vorher 30) an.

## 0.6.94

- 📊 **66: Statistik auf dem Startbildschirm** — wie bei 20 AB und Schwimmen zeigt jetzt auch der 66-Startbildschirm eine Übersicht (Spiele, Siege, Niederlagen, Siegquote, aktuelle Serie, beste Serie), berechnet aus dem Spielverlauf.

## 0.6.93

- 🟡 **20 AB: goldener Trumpf-Rahmen wieder sichtbar** — die Trumpfkarten auf der eigenen Hand sollten (wie bei 66) golden umrandet sein, was beim Knoll-Deck nicht zu sehen war: die Markierung nutzte nur `border-color`, Knoll-Karten haben aber gar keinen Rahmen. Jetzt wird der Trumpf wie bei 66 per Gold-`box-shadow`-Ring markiert, der auf beiden Decks greift.

## 0.6.92

- 🏠 **Home-Assistant-Sensoren für den Live-Spielstatus** — das Add-on meldet jetzt zusätzlich, wer gerade spielt:
  - `binary_sensor.mypage_spielt_jemand` (an/aus, sobald ≥1 Mitglied spielt; Attribut `count`),
  - `sensor.mypage_spieler_aktiv` (Anzahl; Attribute: Liste `spieler` mit Name/Spiel/seit + `pro_spiel`-Aufschlüsselung),
  - `sensor.mypage_aktiv_66` / `_20ab` / `_schwimmen` (Anzahl je Spiel + Namensliste).
  Aktualisierung alle 30 s plus Sofort-Push bei Spielstart/-ende. Die Gesamtzahl der Mitglieder gibt es bereits als `sensor.mypage_members`. (Nur aktiv mit `SUPERVISOR_TOKEN`, d. h. im echten HA-Betrieb.)

## 0.6.91

- 🔄 **Admin: Live-Spielstatus aktualisiert sich automatisch** — die grün/grau-Bubble in der Benutzerliste wurde bisher nur beim Tab-Wechsel neu geladen. Jetzt pollt das Panel alle 10 s einen leichten Status-Endpoint und aktualisiert nur die Bubbles (kein Neuaufbau der Liste, nichts „springt"); das Polling läuft nur, solange der Benutzer-Tab offen und sichtbar ist.

## 0.6.90

- 🟢 **Admin: Live-Spielstatus & Spielstatistik pro Mitglied** — in der Benutzerliste zeigt eine Status-Bubble vor der E-Mail, ob jemand gerade spielt (grün, pulsierend, inkl. Spiel + „seit …") oder inaktiv ist (grau). Der Journal-Button ist jetzt nur noch ein Icon (Platz gespart), dafür gibt es einen neuen 🎮-Button: Er öffnet ein Fenster mit der Spielstatistik (Partien, Siege, zuletzt gespielt — aus dem Spielverlauf) sowie einem Verlauf der letzten Spielsitzungen.
- 🕒 **Persistentes Sitzungs-Log** — Start und Ende jeder Spielsitzung (66 / 20 AB / Schwimmen) werden dauerhaft pro Mitglied festgehalten (`gsessions_<uid>.json`), inkl. Grund (beendet / Timeout / Übernahme). Überlebt Add-on-Neustarts und ist in Backups enthalten.

## 0.6.89

- 👁️ **Schwimmen: Turnier-Auswahl „Anzahl Spiele" wieder lesbar** — im Aufklappmenü auf dem Startbildschirm waren „5 Spiele" und „7 Spiele" kaum erkennbar (dunkelgrau auf dunklem Grund, erst beim Markieren sichtbar). Das Auswahlfeld hatte einen durchscheinenden Hintergrund, wodurch die nicht markierten Optionen unleserlich wurden. Jetzt undurchsichtiger dunkler Grund mit hellem Text. Zusätzlich ist die Beschriftung jetzt zweisprachig („Spiele" / „games") statt fest deutsch.

## 0.6.88

- 🌐 **66: Spielregeln jetzt zweisprachig (DE/EN)** — bisher gab es nur eine deutsche Regel-Datei (`66_REGELN.md`), die auch im englischen Bereich angezeigt wurde. Jetzt liefert `/api/66/rules` die Regeln sprachabhängig aus `game_66_rules_de.md` bzw. `game_66_rules_en.md` (mit DE-Fallback) — wie bereits bei 20 AB und Schwimmen. Die ausführliche deutsche Fassung (inkl. „Andys Oma"-Variante) wurde vollständig ins Englische übersetzt.

## 0.6.87

- 🔓 **Session-Sperre wird beim Schließen sofort freigegeben** — beim Beenden eines Spiels über „✕" (oder „Zurück") wurde die Geräte-Session bisher nicht aktiv freigegeben; der `beforeunload`-Beacon greift beim Schließen im iframe nicht zuverlässig. Folge: ein sofortiger Neustart meldete fälschlich „auf einem anderen Gerät aktiv" (bis der 30-Sekunden-Timeout ablief). `closeGame()` gibt die Sperre jetzt explizit per `release`-Beacon frei (66, 20 AB, Schwimmen).
- 🃏 **20 AB: „Gespielte Karten" nutzt jetzt die Knoll-Karten** — die Übersicht der gespielten/verbleibenden Karten zeigte selbstgebaute Text-Kärtchen statt der Knoll-SVGs. Jetzt werden – wie bei 66 – die echten Kartenbilder gerendert (mit Markierung Hand/Tisch/verbraucht).

## 0.6.86

- 🎴 **Schwimmen: Animation beim Tischwechsel** — wenn alle passen, wurde die neue Mitte bisher nur kurz angeleuchtet, die Karten erschienen aber schlagartig. Jetzt werden die drei alten Tischkarten zum Stapel weggewischt und die drei neuen einzeln vom Deckzentrum eingeteilt (mit Austeil-Sound), genau wie beim Rundenstart — sowohl wenn der Spieler als auch wenn die KI das letzte Passen auslöst. Respektiert „Bewegung reduzieren".

## 0.6.85

- ↶ **66: Zug zurücknehmen funktioniert jetzt** — der Undo-Button (und die Taste „U") war im Client vorhanden, aber die Server-Route fehlte, sodass nichts passierte. Jetzt wird vor jedem Spielerzug ein Schnappschuss abgelegt und `/api/66/undo` stellt den Stand vor dem letzten Zug wieder her — analog zu 20 AB und Schwimmen. Undo ist (wie bisher im Client vorgesehen) nur auf den Stufen Leicht/Mittel verfügbar.

## 0.6.84

- 🃏 **20 AB: Spielerhand zeigt jetzt die Knoll-Karten** — die eigene Hand wurde fälschlich als einfache Text-Karten gerendert (`playerCardHtml` ignorierte das Kartendeck), während die KI-Karten korrekt als Knoll-SVGs erschienen. Jetzt nutzt die Spielerhand dasselbe Knoll-Deck.
- 🚫 **20 AB & Schwimmen: „Nein" am Spielende** — das Spielende-Fenster bot nur „Neues Spiel". Wie bei 66 gibt es jetzt zusätzlich „Nein", das das Fenster nur schließt, sodass der Endstand sichtbar bleibt.

## 0.6.83

- 🎬 **Startbildschirm für alle drei Spiele vereinheitlicht** — auch 66 zeigt jetzt beim Öffnen einen Startbildschirm mit Schwierigkeitswahl (Leicht/Mittel/Schwer/Adaptiv) und Regelvariante (Standard/Oma) statt sofort eine Partie zu starten. Ein laufendes Spiel lässt sich über „Fortsetzen" weiterspielen. `/api/66/state` legt nicht mehr automatisch ein Spiel an.
- 🔙 **„Zum Mitgliederbereich"-Button auf allen Startbildschirmen** — von 66, 20 AB und Schwimmen kommt man jetzt direkt aus dem Startbildschirm zurück zur Übersicht (der Overlay verdeckte zuvor den Schließen-Button der Topbar).
- 🧱 **Z-Index korrigiert** — Tab-/Geräte-Hinweise (Session-Schutz) liegen nun zuverlässig über dem Startbildschirm, sodass „Hier übernehmen" auch dort bedienbar ist.

## 0.6.82

- 🛠️ **Docker-Build-Fix** — der Dockerfile kopierte noch `game66.py` (in 0.6.81 zu `game_66.py` umbenannt) und nicht die neuen Spielmodule/Regeldateien. Jetzt werden `game_66.py`, `game_20ab.py`, `game_schwimmen.py` sowie die `game_*_rules_{de,en}.md` ins Image kopiert.

## 0.6.81

- 🎴 **Zwei neue Mitglieder-Kartenspiele: 20 AB und Schwimmen** — beide spielen server-autoritativ gegen zwei KI-Gegner, sind voll auf Deutsch/Englisch lokalisiert und erscheinen als eigene Kacheln im Mitgliederbereich (Vollfenster-Iframe wie 66). Spielstand, Verlauf und Statistik werden pro Mitglied gespeichert; Schwimmen zusätzlich mit Turniermodus. Spielregeln liegen als Markdown (DE/EN) vor und werden in der Spielseite eingeblendet.
- 🃏 **Karten 7/8/9 ergänzt** — das Knoll-Deck enthält jetzt auch 7er, 8er und 9er (für 20 AB und Schwimmen).
- 🔒 **Cross-Device-Session-Schutz für alle drei Spiele** — zusätzlich zum bestehenden Tab-Schutz (ein Browser) verhindert ein Session-Guard jetzt paralleles Spielen desselben Spielstands auf mehreren Geräten/Browsern: Beim Laden wird die Session beansprucht (Heartbeat alle 15 s, automatische Freigabe nach 30 s ohne Lebenszeichen oder beim Schließen). Ein anderes Gerät kann per „Hier übernehmen" übernehmen; gesperrte Aktionen liefern HTTP 423.
- 🧹 **Einheitliche Dateinamen** — das 66-Spiel heißt nun konsistent `game_66.py` / `game_66.html` (analog `game_20ab`, `game_schwimmen`). URLs und Funktionsnamen unverändert.

## 0.6.80

- 💅 **66: „Gespielte Karten"-Fenster kompakter & zentriert** — das Modal war fix 620px breit, wodurch die Karten linksbündig mit viel Leerraum standen. Jetzt passt sich die Box an den Karteninhalt an und die Kartenreihen sind horizontal zentriert. Im Browser verifiziert (Box ~405px statt 620, Inhalt mittig).

## 0.6.79

- 🐛 **66: Erster Talon-Nachzug wurde manchmal nicht animiert** — beim Nachziehen erschien die Karte des ersten Ziehers gelegentlich sofort am Stapel (ohne Flug), nur der zweite Nachzug war animiert. Ursache: Der Flug lud das Kartenbild frisch per `src` — je nach Decode-/Cache-Timing startete die CSS-Transition dann nicht. Jetzt wird (wie beim Spielerkarten-Flug) die bereits dekodierte Stapelkarte geklont und die Startposition vor dem Flug per Reflow festgeschrieben, sodass die Animation zuverlässig startet.

## 0.6.78

- ❓ **66: Rückfrage beim Wechsel von Schwierigkeit/Regeln** — das Umstellen der KI-Schwierigkeit (oder der Regeln) startet ein neues Match. Vorher passierte das sofort und ohne Vorwarnung; jetzt erscheint dieselbe Sicherheitsabfrage wie beim Neu-Button („Laufendes Match aufgeben und neu beginnen?"). Bei Abbruch bleibt das laufende Spiel erhalten. Das erneute Wählen der **bereits aktiven** Stufe löst keine Rückfrage (und kein neues Spiel) aus. Im Browser verifiziert.

## 0.6.77

- 🎬 **66: Nachziehen vom Talon jetzt nacheinander sichtbar** — nach einem Stich zieht zuerst der **Stichgewinner** eine Karte vom Talon, dann der andere — als **zwei getrennte Animationen**. Vorher liefen beide Nachzüge gleichzeitig (und direkt danach spielte die KI), wodurch der Nachzug der KI optisch unterging und nur der eigene sichtbar war. Im Browser verifiziert (zwei sequenzielle Flüge, Gewinner zuerst, beide Richtungen sichtbar).

## 0.6.76

- 🩹 **66: Talon springt nicht mehr beim letzten Stich** — der Talon-Stapel verschob sich vertikal, wenn der „letzte Stich" ein-/ausgeblendet wurde (z. B. während ein Stich auf dem Tisch liegt). Ursache: Der Bereich wurde per `display:none` ein-/ausgeklappt, wodurch die zentrierte Spielfeldmitte sprang. Jetzt bleibt der Platz reserviert (feste `min-height`); nur die Karten darin werden ein-/ausgeblendet. Im Browser verifiziert (Talon-Position identisch in beiden Zuständen).

## 0.6.75

- 🗂️ **66: Trumpf beim Sortieren immer rechts** — bei aktivierter Hand-Sortierung stehen die **Trumpfkarten jetzt immer ganz rechts** (höchster Trumpf außen), unabhängig von der Farbe — vorher wurden sie nach Farbe einsortiert und konnten in der Mitte landen. Der **goldene Rahmen** um die Trumpfkarten bleibt unverändert erhalten. Im Browser verifiziert.

## 0.6.74

- ⚡ **66: Trumpf-Buben-Tausch-Animation flüssiger** — der Tausch wirkte träge und ruckelte. Zwei Ursachen behoben: (1) `flyExchange` erzeugte zwei **frische `<img>`** und wartete auf deren `load`-Event (bis 200 ms Startverzögerung) bzw. dekodierte das SVG erst während der Animation (Ruckeln) — jetzt werden die **bereits gerenderten Karten geklont** (wie bei der Spielerkarte), plus `will-change:transform`. (2) Vor der Animation lag ein **toter Leerlauf** (~475 ms) im Frame-Player — für den Tausch entfernt, die Animation schließt jetzt direkt an. Im Browser verifiziert (Tausch läuft sauber, Klone werden korrekt aufgeräumt).

## 0.6.73

- 🐛 **66: Talon-Stapel fehlte beim Spielstart** — nach „Neues Spiel" bzw. dem Neu-Button (↻) war der verdeckte Kartenstapel im Talon unsichtbar und tauchte erst nach einem harten Reload (Strg+R) auf. Ursache: `clearBoard()` setzte den Stapel auf `visibility:hidden`, aber `render()` stellte nur die Trumpfkarte wieder her, nicht den Stapel. Jetzt wird auch `#stock-back` zurückgesetzt. Im Browser verifiziert (sichtbar nach Deal **und** nach Neu-Button, ohne Reload).

## 0.6.72

- 🎮 **66: Großes Update — KI, UX & Animationen überarbeitet.** Umfassende Überarbeitung des Kartenspiels:
  - **Stärkere KI** — neues Fähigkeiten-System mit festen Stärkestufen (easy=35, medium=65, hard=100, adaptive passt sich an): Card-Counting, Gegner-Handschätzung, sichere Asse, smarteres Schmieren, punktestandbewusstes Stechen und ein Minimax-Endspiel (perfektes Spiel in Phase 2, nur auf hard).
  - **Animationen behoben** — Kartengeben läuft jetzt auch beim ersten Laden, KI-Karte fliegt zuverlässig zur Mitte, Trumpf-Sichtbarkeit nach Tausch korrigiert, eigene Auslos-Zeremonie („wer fängt an") mit 3D-Kartenflip, Zudreh-Animation.
  - **Neue UX** — Toast-Einblendungen bei KI-Aktionen, vollständige **Tastatur-Steuerung** (1–5, E, Z, J/N, U, P, L, Esc), Inline-Hochzeitsabfrage statt Browser-Dialog, „letzter Stich" auf dem Feld, Übersicht „gespielte Karten", **Undo** (easy/medium), synthetische **Soundeffekte** und Mobile-Optimierung.
  - 🌍 **Vollständig zweisprachig (DE/EN)** — alle 36 neuen UI-Texte (Tastatur-Hints, Toasts, Einstellungen, Rang-Namen, Banner) in `de.json` **und** `en.json` ergänzt; der Spielverlauf-Log bleibt pro Eintrag bilingual. Im echten Browser (Playwright) verifiziert: Seite lädt fehlerfrei in DE+EN, Züge laufen durch, keine JS-Fehler.

## 0.6.71

- ✨ **66: KI-Karte fliegt jetzt wie deine** — die ausgespielte KI-Karte wird jetzt **genauso animiert wie die Spielerkarte**: Sie klont die echte (verdeckte) Karte aus der KI-Hand und lässt sie auf den Tisch fliegen — kein Bild-Nachladen, kein wackeliges Container-Rechteck mehr. Beim Landen wird die Karte aufgedeckt. Im echten Browser verifiziert (KI-Karte startet oben in der KI-Hand und fliegt sichtbar zur Mitte).

## 0.6.70

- ⏪ **66: Revert auf Stand 0.6.65** — die Animations-Experimente aus 0.6.66–0.6.69 (Kartengeben-Animation, KI-Eröffnungs-Flug, Trumpftausch-Flug) werden vollständig zurückgenommen. Spiellogik und Oberfläche entsprechen wieder 0.6.65 (inkl. Hochzeitswert-Anzeige). Die bestehende KI-Kartenanimation im Spielverlauf bleibt erhalten.

## 0.6.69

- 🐛 **66: KI-Karte fliegt jetzt zuverlässig** — die ausgespielte KI-Karte startet ihren Flug nun von einer **echten (verdeckten) Karte** der KI-Hand — genau wie deine Karte von ihrer Handposition fliegt. Vorher startete sie vom Hand-Container, der je nach Zustand Breite 0 hatte → kein Flug. Notfall-Start ist der Talon.

## 0.6.68

- 🐛 **66: Austeil- & KI-Karten-Animation wirklich behoben** (im echten Browser mit Playwright getestet): Beim Austeilen wurden **nur die 5 Karten des Spielers** animiert — die 5 KI-Karten fielen aus, weil der leere KI-Handbereich auf Breite 0 zusammenfällt und der Kartenflug dann verworfen wurde. Jetzt werden **alle 10 Karten** über stabile Zielpunkte mittig über jedem Platz ausgeteilt. Dadurch fliegt auch die **erste KI-Karte** beim Partiebeginn zuverlässig ein (vorher zufällig mal ja, mal nein).

## 0.6.67

- 🐛 **66: Austeil- & KI-Eröffnungs-Animation zuverlässig** — Fix zu 0.6.66: Die Animationen hingen davon ab, dass der Server-Teil neu gestartet wurde, und die KI-Eröffnung wurde nur animiert, wenn der Spieler Vorhand war (wirkte zufällig). Eine neue Partie wird jetzt rein clientseitig erkannt: Die Karten werden immer animiert ausgeteilt, und die erste KI-Karte fliegt zuverlässig in die Mitte — egal, wer gibt.

## 0.6.66

- 🎬 **66: Mehr Animationen** — drei flüssigere Abläufe:
  - **Kartengeben animiert** — zu Beginn jeder Partie werden die Karten jetzt nacheinander vom Talon in beide Hände ausgeteilt.
  - **KI-Eröffnung fliegt ein** — legt die KI als Erste eine Karte in die Mitte (Partiebeginn), ist die Karte jetzt animiert, genau wie beim Nachziehen im Stich.
  - **Trumpf-Bube tauschen animiert** — beim Tauschen fliegt der Bube zum Trumpfplatz und die aufgedeckte Karte in die Hand (Spieler **und** KI).

## 0.6.65

- 🐛 **66: Hochzeitskarte flackert nicht mehr** — Fix zu 0.6.63/0.6.64: Beim Ansagen entfiel ein überflüssiges Zwischenbild mit leerem Tisch. Die Hochzeitskarte fliegt jetzt in die Mitte und **bleibt dort liegen** (samt Wert), statt kurz zu verschwinden und wieder aufzutauchen.

## 0.6.64

- 🐛 **66: Hochzeitskarte wieder sichtbar** — Fix zu 0.6.63: Die ausgespielte Hochzeitskarte wurde durch das Wert-Abzeichen nicht mehr auf dem Tisch angezeigt. Der Wert (20/40) liegt jetzt als reines Overlay über der Karte, ohne das Tisch-Layout zu verändern.

## 0.6.63

- 💍 **66: Hochzeitswert auf dem Tisch** — wird eine **Hochzeit** ausgespielt (von dir oder der KI), erscheint jetzt **über der ausgespielten Karte** der Wert **20** bzw. **40 (Trumpf)** als goldenes Abzeichen. Reine optische Anzeige — sie erscheint unabhängig davon, ob die Hochzeit schon zählt (also auch ohne ersten Stich).

## 0.6.62

- 🗂️ **66: Hand sortieren** — neuer **„⇅ Sortieren"-Button** (links neben „Zudrehen") ordnet dein Blatt nach Wertigkeit: zuerst nach **Farbe** (Kreuz, Karo, Herz, Pik), dann nach **Kartenwert** (Bube, Dame, König, 10, Ass). Die Einstellung ist ein **Umschalter** und bleibt gespeichert; der **blaue Rahmen** der zuletzt vom Talon gezogenen Karte bleibt dabei erhalten.

## 0.6.61

- ✨ **66: Gewinnerkarte blinkt** — sobald ein voller Stich auf dem Tisch liegt, **blinkt die Karte auf, die den Stich gewonnen hat** (grüner Schein), bevor die Karten zum Gewinner fliegen — so erkennt man auf einen Blick, welche Karte gestochen hat. Der goldene Rahmen der KI-Karte bleibt dabei erhalten.

## 0.6.60

- 🪽 **66: Stich fliegt zum Gewinner** — wenn ein voller Stich nach der Liegezeit abgeräumt wird, **fliegen die beiden Karten jetzt animiert** zum Spieler, der den Stich gewonnen hat (zu deiner bzw. zur KI-Stichanzeige), statt einfach zu verschwinden. Dadurch ist auf einen Blick erkennbar, wer den Stich geholt hat.
- 🎨 **66: Trumpf-Farbsymbol in echter Farbe** — das Farbsymbol bei „verbleibende Karten · Trumpf" wird jetzt in der **passenden Spielfarbe** dargestellt (♦/♥ rot, ♠/♣ schwarz, mit weißem Halo zur besseren Lesbarkeit auf dem Filz) statt durchgehend weiß. Per **Mouseover** erscheint zudem der Farbname (Kreuz, Karo, Herz, Pik).

## 0.6.59

- 🔵 **66: Gezogene Karte markiert** — die zuletzt **vom Talon nachgezogene Karte** erhält in deinem Blatt einen **blauen Rand**, damit du sie sofort erkennst. Der Rand verschwindet automatisch, sobald du die nächste Karte ausspielst.

## 0.6.58

- 🎨 **66: Trumpf-Symbol besser erkennbar** — ♠/♣ wurden je nach System als dickes schwarzes Emoji dargestellt und waren auf dem grünen Filz kaum zu sehen. Jetzt werden alle Farbsymbole als **Text** gerendert (♠/♣ in Weiß, ♦/♥ in hellem Rot) und sind klar lesbar.

## 0.6.57

- 💾 **Spielstände im Backup** — die 66-**Spielstände und der Verlauf** (`games/66_<uid>.json`, `games/66hist_<uid>.json`) werden jetzt **mit gesichert und wiederhergestellt** (Admin → Backup/Restore). So gehen laufende Partien und die Historie bei einem Wiederherstellen nicht verloren. Beim Restore werden nur gültige Spieldateinamen akzeptiert (abgesichert gegen Zip-Slip/Fremddateien).

## 0.6.56

- 🔎 **66: Bessere Lesbarkeit am Stapel** — die Anzeige von **Trumpf** und **verbleibenden Talon-Karten** unter dem Stapel ist jetzt **deutlich größer**; rote Trumpffarben (♦/♥) werden farbig dargestellt.
- 🟡 **KI-Karte hervorgehoben** — die von der **KI gespielte Karte** auf dem Tisch erhält jetzt einen **goldenen Rahmen** (auch schon während des Einfliegens), damit man auf einen Blick erkennt, was die KI gelegt hat.

## 0.6.55

- 🐛 **66: KI-Kartenanimation sichtbar gemacht** — die Flugbewegung der **KI-Karte** fehlte, weil das Kartenbild beim Start des Flugs teils noch nicht geladen war (eine „unsichtbare" Karte flog, die Karte erschien erst am Ende). Jetzt startet der Flug erst, **wenn das Bild geladen ist**, und alle Karten-SVGs werden beim Öffnen **vorgeladen**, damit die Animation sofort flüssig läuft.

## 0.6.54

- 🔀 **66: Mehr-Tab-Schutz** — ist das Spiel bereits in einem Browser-Tab offen und du öffnest es in einem **weiteren Tab**, übernimmt der neue Tab und der **alte wird getrennt** (pausiert). Der getrennte Tab zeigt einen Hinweis mit **„Hier weiterspielen"**, um die Kontrolle zurückzuholen. So kommen sich zwei Tabs nicht mehr in die Quere (z. B. doppelte Anzeigen). Umgesetzt über `BroadcastChannel`; dein Spielstand bleibt server­seitig sicher gespeichert.

## 0.6.53

- 🐛 **66: Auslosung erscheint nicht mehr mitten im Spiel** — die „Wer beginnt?"-Anzeige wird jetzt nur noch **ganz zu Beginn** (vor dem ersten Stich) und **einmal pro Browser** gezeigt. Vorher konnte sie in einem **zweiten Tab** (oder nach einem Reload) während der laufenden ersten Partie noch einmal auftauchen.

## 0.6.52

- ✨ **66: Mehr Kartenanimationen** — jetzt fliegt auch die **Karte der KI** sichtbar vom Gegnerblatt auf den Tisch, und beim **Nachziehen vom Talon** fliegen die Karten vom Stapel in die Hände (vorher nur die selbst gespielte Karte). Respektiert „Bewegung reduzieren".
- 🎚 **Größere Tempo-Spannen**: Bewegungsdauer der Karte bis **1 s**, Liegezeit eines Stichs bis **10 s** einstellbar.
- 🧠 Klareres Icon für das Schwierigkeits-Menü (das bisherige Symbol wurde auf manchen Systemen falsch dargestellt).

## 0.6.51

- ⚙ **66: Animations-Tempo einstellbar** — über das neue ⚙-Menü lassen sich die **Bewegungsdauer der Karte** und die **Liegezeit eines Stichs** per Schieberegler frei einstellen (statt fest verdrahtet). Die Werte werden **im Browser gespeichert** und gelten ab dem nächsten Zug; ein Klick auf „Zurücksetzen" stellt die Standardwerte wieder her.

## 0.6.50

- 🏅 **66: Spielverlauf** — über das neue 🏅-Menü siehst du deine **letzten beendeten Matches** mit **Datum & Uhrzeit**, **Endstand** (Bummerl), **Regelvariante**, **Schwierigkeitsgrad** und Anzahl der Partien. Wird pro Benutzer gespeichert (lokal, **nicht** auf dem SMB-Share, max. 50 Einträge) und ist geräteübergreifend abrufbar. Datum/Uhrzeit werden in deiner lokalen Zeitzone angezeigt.
- 📖 **66: Spielregeln in der UI** — das 📖-Menü zeigt die kompletten Regeln (inkl. „Andys Oma" und Schwierigkeitsgrade) direkt im Spiel, gerendert aus dem mitgelieferten Regel-Dokument.
- ✅ Neue Endpoints `GET /api/66/history` und `GET /api/66/rules`; Match-Ende wird einmalig (ohne Doppelzählung) aufgezeichnet. End-to-End getestet.

## 0.6.49

- 🎚 **66: KI-Schwierigkeitsgrade** — über das neue 🎚-Menü wählbar: **Leicht**, **Mittel**, **Schwer** und **Adaptiv**. Ein Wechsel der Schwierigkeit startet (wie beim Regelwechsel) ein **neues Match**. Leicht/Mittel lassen die KI mit steigender Wahrscheinlichkeit unbedacht spielen, Schwer spielt durchgehend nach bester Strategie.
- 🤖 **Adaptiver Modus**: Die KI passt sich laufend an — **gewinnst du eine Partie, wird sie stärker; verlierst du, wird sie schwächer**. Die aktuelle Stärke wird oben als Prozentwert angezeigt. So bleibt es spannend, egal wie gut man spielt.
- ✅ Erweitert um Tests für alle Schwierigkeitsgrade (Epsilon je Level, adaptive Anpassung in beide Richtungen samt Grenzen, Invarianten-Playouts pro Level).

## 0.6.48

- 🃏 **66: zweite Regelvariante „Andys Oma"** — über das neue ⚖-Menü umschaltbar (ein Regelwechsel startet ein neues Match). Dabei wird **kein vorzeitiges Ausmelden** gespielt: Es geht **immer bis zum Ende**, dann wird gezählt — wer 66+ hat gewinnt, sonst der **letzte Stich**. Spielpunkte wie gewohnt (0 → 3, < 33 → 2, ≥ 33 → 1); Zudreher muss 66 schaffen, sonst 3 für den Gegner. Die bisherigen Standardregeln bleiben unverändert wählbar.
- 🎲 **Auslosen zu Spielbeginn**: Jeder zieht eine Karte, die höhere beginnt — bei Gleichrang entscheidet die Farbe (**Kreuz < Karo < Herz < Pik**). Wird kurz angezeigt. In Folgepartien spielt weiterhin der **Gewinner der letzten Partie** aus.
- ✨ **Karten-Fluganimation**: Eine angeklickte Handkarte **fliegt jetzt sichtbar auf den Tisch** (statt einfach zu erscheinen) — deutlich übersichtlicher. Respektiert „Bewegung reduzieren".
- ✅ Regelwerk erweitert und durch Tests abgesichert (Standard **und** Oma je tausende Playouts, Auslos-Logik, Wertungen) sowie End-to-End-Routentests (Varianten, Auslosen).

## 0.6.47

- 🎬 **66: Stiche werden jetzt animiert abgespielt.** Bisher sprang die Anzeige nach einem Stich sofort zum Endzustand — die gespielten Karten waren kaum zu sehen. Der Server liefert pro Zug nun eine Folge von **Zwischenbildern**, die der Client mit kurzen Pausen abspielt: der **volle Stich (deine Karte + die der KI) bleibt ~1,25 s sichtbar liegen**, bevor abgeräumt wird; Karten auf dem Tisch werden sanft eingeblendet. Eingaben sind während der Animation gesperrt. Respektiert „Bewegung reduzieren".

## 0.6.46

- 🃏 **Neues Mitglieder-Spiel: 66 (Sechsundsechzig)** — das klassische Stichspiel gegen eine **KI**. Nur für angemeldete Benutzer (im persönlichen Bereich), öffnet sich als **Vollfenster-Iframe** (kein Browser-Vollbild). 20-Karten-Variante (ohne Neuner, je 5 Karten): Hochzeiten (20/40), Trumpf-Bube tauschen, Zudrehen, Ausmelden bei 66 Augen; Wertung 1/2/3 Spielpunkte, Match (Bummerl) bis 7.
- 💾 **Server-autoritativ & geräteübergreifend**: Regelwerk und KI laufen auf dem Server, **jeder Zug wird gespeichert** (lokal im `addon_config`, **nicht** auf dem SMB-Share) — auf einem anderen Gerät weiterspielen ist möglich. Die KI-Hand bleibt serverseitig verborgen (kein Mogeln).
- 🎴 **Kartendeck austauschbar**: mitgeliefertes, gemeinfreies Deck (*Vector Playing Cards*, Byron Knoll) als SVG unter `/cards/<deck>/…`; weitere Decks später per Ordner ergänzbar.
- ✅ Abgesichert durch ein Test-Harness (Regel-Invarianten, Wertung, tausende Zufalls-Playouts) und End-to-End-Routentests (inkl. geräteübergreifendem Fortsetzen). Voll DE/EN lokalisiert.

## 0.6.45

- 🎴 Video Poker: Nach dem Tauschen werden die **gewinnenden Karten golden hervorgehoben**, die übrigen abgedunkelt — so ist auf einen Blick klar, *warum* eine Hand gewonnen hat (z. B. welches Paar). Die Bewertung selbst war korrekt; „Buben oder besser" erfordert weiterhin ein echtes Paar ab Bube (über alle 2,6 Mio. Hände verifiziert).

## 0.6.44

- 🔔 Slot-Jackpot: Beim Jackpot (3× 7️⃣) ertönt jetzt eine **Casino-Klingel** (metallisches „dring-dring" per Web Audio) und das **Spielfenster wackelt**. Respektiert „Bewegung reduzieren" (kein Wackeln).
- 🧪 **Jackpot-Simulation**: Bei geöffnetem Slot einfach **`jackpot` tippen** → Klingel + Wackeln + 777-Anzeige als Vorschau, **ohne** Auszahlung (Guthaben/Jackpot bleiben unberührt). Praktisch zum Vorführen des Effekts.

## 0.6.43

- 🎴 **Neues 7. Mini-Game: Video Poker (Jacks or Better)** — Geben → Karten antippen zum Halten → Tauschen → werten. Klassische Gewinntabelle (×Einsatz): Royal Flush 250, Straight Flush 50, Vierling 25, Full House 9, Flush 6, Straße 4, Drilling 3, Zwei Paare 2, Buben oder besser 1. Einsatz 10, Aufladen-Button wie bei Slot/17+4 (nur bei leerem Konto), Guthaben in `localStorage`. Voll DE/EN lokalisiert. Damit sind es **7 Mini-Games** 🍀.

## 0.6.42

- 🎰 Slot: Neue, symbolabhängige Gewinntabelle und realistischere Auszahlquote (~62 % bei Basis-Jackpot, steigend mit dem progressiven Jackpot). Neues 8. Symbol **🚫 Niete** (zahlt nie) senkt die Trefferquote. Auszahlungen (Paar = Walze 1+2 gleich von links / Drilling = alle drei): 🍒🍋 20/50 · 🍉 30/80 · 🔔⭐ 40/100 · 💎 50/200 · 7️⃣ 100/Jackpot. Gewinnbetrag wird jetzt dynamisch je Symbol im Hinweis angezeigt.

## 0.6.41

- 🃏 17+4 (Blackjack): Gleicher Aufladen-Fix wie beim Slot. Der „🔄 Aufladen"-Button erscheint jetzt **nur bei leerem Konto** (Guthaben unter dem Einsatz von 10) und das Guthaben wird beim Öffnen **nicht mehr automatisch** auf 100 zurückgesetzt — ein vorhandener Spielstand bleibt erhalten.

## 0.6.40

- 🐛 Einblend-Effekte: Die Auswahl (Einblenden / Hochgleiten / Zoom / Unschärfe) sah optisch immer gleich aus. Ursache: Bei aktivem Stagger (Standard) wurden die Inhaltsblöcke auf reines Einblenden gezwungen, sodass nur die kaum sichtbare Kartenbewegung den Unterschied trug. Jetzt wirkt der gewählte Effekt auf **allen Blöcken** (Überschriften, Hero, Inhalte) — die Effekte sind klar unterscheidbar. Bei Stagger bleiben nur die Karten-Container selbst ruhig (via `:has()`), während ihre Kacheln den Effekt nacheinander tragen.

## 0.6.39

- ✨ **Werdegang-Überschrift frei konfigurierbar**: Im Werdegang-Tab lässt sich jetzt eine eigene Überschrift (DE/EN) vergeben — z. B. „Unsere Geschichte", „Meilensteine" oder „Über den Verein". Sie erscheint dann sowohl als Abschnittsüberschrift als auch im Navigationsmenü. Bleibt das Feld leer, wird wie bisher „Werdegang" verwendet. Der Tab-Name im Admin bleibt „Werdegang".

## 0.6.38

- 🐛 Einblend-Effekte: Animation griff nur beim oberen Bereich (Hero), der Rest der Seite blieb statisch. Ursache: nur der Kopfbereich ist ein `<section>`, die übrigen Blöcke (Überschriften, Projekt-/Service-/Galerie-Raster usw.) sind direkte `main`-Kinder. Reveal zielt jetzt auf **alle Inhaltsblöcke** (`main > *`) — damit blenden Überschriften und Abschnitte beim Scrollen ebenfalls ein, Stagger inklusive.

## 0.6.37

- ✨ **Einblend-Effekte** für die öffentliche Seite (neu im Design-Bereich): Inhalte erscheinen animiert beim Öffnen und beim Scrollen. Auswählbar: **Aus** (Standard), **Sanftes Einblenden**, **Einblenden + Hochgleiten**, **Zoom** oder **Unschärfe → scharf**. Zusätzlich optionaler **Stagger** – Kacheln/Karten eines Abschnitts erscheinen leicht versetzt nacheinander. Abhängigkeitsfrei (reines CSS + `IntersectionObserver`), flackerfrei (Vorbereitung vor dem ersten Rendern) und **barrierefrei**: Wer im System „Bewegung reduzieren" aktiviert hat oder kein JavaScript nutzt, sieht alle Inhalte sofort ohne Animation.

## 0.6.36

- ✨ **Markdown-Editor jetzt als Overlay-Fenster mit Live-Vorschau**: Statt der Toolbar direkt am Feld gibt es nun einen **„✏️ Bearbeiten"-Button**. Ein Klick öffnet ein Editor-Fenster **im selben Tab** (wie die Mini-Games) — **Editor links, gerenderte Vorschau rechts**. Markierst du Text und klickst z. B. **Fett**, erscheint er sofort fett in der Vorschau. „Übernehmen" schreibt das Markdown zurück ins Feld, „Abbrechen"/Esc verwirft. Eigener, abhängigkeitsfreier Markdown-Renderer (Überschriften, Fett/Kursiv, Listen, Zitate, Code, Links); HTML wird escaped und unsichere Links (z. B. `javascript:`) werden verworfen.

## 0.6.35

- ✍️ **Markdown-Editor** für alle längeren Textfelder (Blog-Text, Projekt-Beschreibung, Bio, Tipps, FAQ-Antworten): Mini-Toolbar mit **Fett, Kursiv, Überschrift, Aufzählung, nummerierte Liste, Zitat, Code, Link** und einem **Emoji-Picker** (😀) — „wie ein Mini-Office", erzeugt sauberes Markdown direkt im Textfeld.
- 🌐 **Übersetzer-Button überschreibt nichts mehr**: „DE → EN" füllt jetzt nur noch **leere** englische Felder; vorhandene englische Texte bleiben unangetastet. Ist die Admin-Sprache bereits **EN**, wird der Button gar nicht mehr angezeigt.

## 0.6.34

- 🎰 Slot-Fixes: Der „🔄 Aufladen"-Button erscheint jetzt **nur bei leerem Konto** (zuvor überschrieb er auch ein vorhandenes Guthaben mit 100). Das Guthaben bleibt beim Öffnen erhalten (kein automatisches Zurücksetzen mehr). Einsatz von **5 auf 10** erhöht.

## 0.6.33

- 🔒 Sicherheit (CodeQL HIGH, Reflected XSS): Die IndexNow-Keyfile-Route gibt nun den **serverseitig gespeicherten** Schlüssel zurück statt des Werts aus der URL — der Eingabe-Taint fließt nicht mehr in die Antwort. Verhalten unverändert (war durch die `[a-f0-9]{32}`-Prüfung ohnehin nicht ausnutzbar).

## 0.6.32

- 🌍 Admin-Panel: letzte hartcodierten deutschen Beispiel-Platzhalter lokalisiert (Wasserzeichen, Adresse, Absender-Mail, Markdown-Hinweis) — folgen jetzt der Admin-Sprache (DE/EN). Die sprachspezifischen „(DE)/(EN)"-Beispiele bleiben bewusst.

## 0.6.31

- 🌍 Weitere hartcodierte DE-Texte lokalisiert: aria-labels (Zurück/Weiter/Schließen) auf Startseite & Blog-Beitrag, die Easter-Egg-Standardtexte und der Konsolen-Gruß folgen jetzt der Seitensprache (DE/EN).

## 0.6.30

- 🌍 **Mini Games zweisprachig**: Alle Spieltexte (Buttons, Punkte/Score, Gewinn-/Verlustmeldungen, 17+4 usw.) folgen jetzt der Seitensprache (DE/EN) — waren vorher fest auf Deutsch.

## 0.6.29

- 🃏 **17+4** (Blackjack) als sechstes Mini-Game: gegen den Dealer, Karte ziehen / halten, Guthaben mit Einsatz (Gewinn +10, Blackjack +15), Dealer zieht bis 17. Mit „🔄 Aufladen".

## 0.6.28

- 🎰 Slot-Auszahlungen angehoben: Zwei Gleiche **+50**, Dreierpasch **+200**.
- 💰 **Progressiver Jackpot** (serverseitig, für alle Besucher gemeinsam): startet bei **500**, jeder Spin erhöht ihn um **1**; wer **777** trifft, gewinnt den aktuellen Stand, danach springt er zurück auf 500. Wird in der `site.json` gespeichert.

## 0.6.27

- 🎰 Slot Machine: Leeres Guthaben wird beim Öffnen automatisch wieder auf 100 gesetzt, plus ein **„🔄 Aufladen"-Button** für jederzeit frisches Guthaben — man bleibt also nie stecken.
- 🔊 **Sound bei Gewinn**: kleine Tonfolge je nach Gewinn (Jackpot > Dreierpasch > Zwei Gleiche), erzeugt per Web Audio — keine externen Dateien.

## 0.6.26

- 🐞 **Snake-Fix**: Trifft die Schlange den Rand oder sich selbst, kommt jetzt **Game Over** (mit Bestwert) und ein **Neustart** per Leertaste/Tippen — vorher lief das Spiel einfach weiter.
- 🎰 **Slot Machine** als fünftes Mini-Game: Drehen kostet Guthaben, **777 = Jackpot**, drei gleiche = großer Gewinn, die zwei linken gleich = kleiner Gewinn. Guthaben wird lokal gespeichert.

## 0.6.25

- 🎮 **Mini Games**: Optionaler Footer-Link „Mini Games" (Design-Tab, Standard: aus) öffnet ein kleines Menü mit vier selbst gehosteten Spielen — **Snake**, **Dino-Runner**, **Pong** (gegen KI) und **Foto-Memory** (nutzt automatisch deine Fotoalbum-Bilder, sonst Emojis). Highscores für Snake/Dino werden lokal im Browser gespeichert. Keine externen Libraries.

## 0.6.24

- 🐞 Easter-Egg-Fix: Tastatur-Eggs (Konami, „matrixx") lösen nicht mehr aus, während man in einem Eingabefeld (z. B. Kontaktformular) tippt. Das Matrix-Wort wurde zudem auf „matrixx" geändert.

## 0.6.23

- 🔎 **Meta-Description für alle Seiten**: Blog-Beiträge, Blog-Liste und Projekt-Detailseiten bekommen jetzt eine eigene `<meta name="description">` (+ og:description) — bei Beiträgen automatisch aus den ersten ~155 Zeichen des Textes, bei Projekten aus der Beschreibung, bei der Blog-Liste aus der Seitenbeschreibung. So zeigt Google überall einen sinnvollen Snippet statt zusammengewürfeltem Seitentext.
- ✏️ Optionales **SEO-Feld je Beitrag** (DE/EN) im Bearbeiten-Dialog — leer = automatischer Auszug.

## 0.6.22

- 🔎 **Bessere Google-Snippets**: Neues Feld **SEO-Beschreibung** (DE/EN) im Design-Tab. Ist es leer, nutzt MyPage automatisch Tagline → „Über mich"-Auszug → Name als Meta-Description (`<meta name="description">`, og:description und strukturierte Daten). So zeigt Google eine echte Beschreibung statt der Navigations-Labels.

## 0.6.21

- 💅 Admin-Panel: mehr vertikaler Abstand, wenn nach einem Hinweistext direkt das nächste Feld folgt (z. B. IndexNow-Hinweis → Favicon) — sauberere Trennung der Blöcke.

## 0.6.20

- 💅 Admin-Panel: größerer horizontaler Abstand zwischen den zweispaltigen Feldern (14 → 36 px) — übersichtlicher, vor allem im Design-Tab.

## 0.6.19

- 🥚 **Easter Eggs** (Design-Tab, Standard: aus) — versteckte Spielereien für Besucher:
  - **Konami-Code** (↑↑↓↓←→←→ B A) → Konfetti + frei einstellbare Nachricht
  - **Avatar 5× klicken** → kleine Drehung + geheime Zweit-Tagline (einstellbar)
  - Wort **„matrix"** tippen → kurzer grüner Code-Regen
  - freundlicher **Gruß in der Browser-Konsole** (F12)

## 0.6.18

- 🙈 **Schalter „Von Suchmaschinen indexieren lassen"** (Design-Tab, Standard: **an**). Auf *Nein* gestellt, bittet die Seite alle Suchmaschinen, sie nicht aufzunehmen: `noindex, nofollow`-Meta auf allen öffentlichen Seiten, `robots.txt` mit `Disallow: /`, und IndexNow pausiert automatisch. Praktisch für private Seiten, die nicht öffentlich gefunden werden sollen.

## 0.6.17

- 📝 **IndexNow-Status im Add-on-Log**: Jede Meldung an Bing wird jetzt protokolliert — beim Senden („sende N URL(s)") und mit dem Ergebnis inkl. verständlicher Deutung der Bing-Antwort (HTTP 200/202 = ok, 403/422 = Key-/Domain-Problem usw.). Log-Texte in ASCII, damit sie überall sauber erscheinen.

## 0.6.16

- 🚀 **IndexNow (Bing)**: Neue Option im Design-Tab. Wenn aktiv, benachrichtigt MyPage **Bing** (und Partner wie DuckDuckGo/Ecosia) automatisch, sobald du einen Beitrag oder ein Projekt veröffentlichst — für schnellere Indexierung. Der nötige Schlüssel wird automatisch erzeugt und unter `https://deine-domain.de/<key>.txt` ausgeliefert. Zusätzlich ein Button „Jetzt an Bing melden", der alle öffentlichen URLs (Startseite, Projekt-Detailseiten, Blog) auf einmal übermittelt. Voraussetzung: öffentliche URL gesetzt. (Google nutzt IndexNow nicht — dort weiterhin Sitemap/Search Console.)

## 0.6.15

- 🔍 **Suchmaschinen-Crawler im Besucher-Log erkennbar**: Bekannte Bots (Googlebot, Bingbot, DuckDuckBot, Applebot, GPTBot u. a.) werden jetzt namentlich angezeigt statt nur „Bot". Über dem Log steht außerdem „Zuletzt von Suchmaschinen besucht: Googlebot (Datum) · Bingbot (Datum) …" — so siehst du auf einen Blick, wann Google zuletzt da war.

## 0.6.14

- 🔎 **Sitemap mit `<lastmod>`**: Startseite, `/blog` und Blog-Beiträge tragen jetzt ein Änderungsdatum — hilft Suchmaschinen beim Crawlen. (Hinweis: Die Sitemap ist bewusst kompakt, weil die meisten Inhalte auf der Startseite liegen; eigene URLs gibt es nur für Projekte **mit Detailseite** und Blog-Beiträge.)

## 0.6.13

- 🐞 **Fix: Tipp-Statistik zeigt echte Werte.** „zuletzt gezeigt" und „wie oft" waren zuvor nur **rechnerische Projektionen** (so, als hätte es die Tipps schon immer gegeben) — daher Datumsangaben in der Vergangenheit und unmögliche Zahlen bei frisch angelegten Tipps. Jetzt bekommt jeder Tipp eine ID, und die **tatsächliche** Anzeige wird festgehalten (einmal pro Tag). Neue Tipps zeigen ehrlich „noch nicht gezeigt"; angezeigt wird „zuletzt gezeigt: \<Datum\> · an N Tag(en) gezeigt".

## 0.6.12

- 📥 **Tipps importieren**: Neuer „Importieren"-Button im Tipp-Bereich — ein JSON-Array einfügen, die Tipps werden an die Liste angehängt (überschreibt nichts). Das JSON wird beim Import auf Gültigkeit geprüft; ungültige Eingaben werden mit Hinweis abgelehnt.
- 📊 Beim Tipp-Hinweis jetzt zusätzlich **„wie oft gezeigt"** (Häufigkeit im Fenster: 365 Tage bzw. 52 Wochen) — praktisch, um bei Zufalls-Auswahl die Verteilung zu sehen.

## 0.6.11

- 💡 **Tipps: Rotations-Einstellungen** im Kopf des Tipp-Bereichs: **Täglich** (Überschrift „Tipp des Tages") oder **Wöchentlich** (Überschrift „Tipp der Woche"), plus **Zufalls-Schalter** (zufällige, aber für alle Besucher gleiche Auswahl pro Tag/Woche statt der Reihe nach).
- 🕖 Pro Tipp ein **„zuletzt gezeigt"-Hinweis** im Admin (aus der Rotation berechnet).
- 🌐 **DE→EN-Übersetzer-Button** auch im Tipp-Bereich.

## 0.6.10

- 🐞 **Fix (wirklich diesmal): Sortieren im Inhalt-Tab speichert.** Beim Ziehen hing die Pointer-Capture am Griff *innerhalb* des verschobenen Elements — beim Verschieben im DOM ging die Capture verloren, `pointerup` feuerte nicht mehr und die Reihenfolge wurde nicht gespeichert. `pointermove`/`pointerup` laufen jetzt über `document` und bleiben dadurch stabil (Maus + Touch).

## 0.6.9

- 🐞 **Fix: Sortieren im Inhalt-Tab wird wieder gespeichert.** Die Akkordeon-Bereiche nutzten `<details>/<summary>` mit interaktiven Elementen (Auge-/Sortier-Griff) im `<summary>` — das ist ungültiges HTML und störte die Drag-&-Drop-Events. Umbau auf ein eigenes Klapp-Element (`acc-head`/`acc-body`); Drag-&-Drop speichert jetzt zuverlässig, und die Barrierefreiheits-Warnung („interactive element within summary") ist behoben.

## 0.6.8

- 💡 **Tipp des Tages**: Neuer Inhaltsbereich — pflege eine Liste von Tipps (DE/EN, Markdown), auf der Startseite wird täglich automatisch einer angezeigt (rotiert deterministisch übers Datum, für alle Besucher gleich). Sortier- und ausblendbar wie die anderen Bereiche.

## 0.6.7

- 👁 **Blog-Vorschau im Admin**: Jeder Beitrag hat jetzt einen „Vorschau"-Button — auch **Entwürfe** und **geplante** Beiträge lassen sich im finalen Layout ansehen, bevor sie veröffentlicht sind (öffnet in neuem Tab, login-geschützt, mit Vorschau-Hinweisleiste).

## 0.6.6

- 🔤 **Schriftart gilt jetzt überall**: Die gewählte Schrift (inkl. eigenem Font-Upload) wird nicht mehr nur auf der Startseite, sondern auf allen öffentlichen Seiten angewendet — Blog-Liste & -Beiträge, Projekt-Detailseiten, Impressum/Datenschutz, Mitglieder-Bereich, Wartungs-, 404- und Fehlerseiten.

## 0.6.5

- 🧱 **Gestaltete Fehlerseiten** für **403** (kein Zugriff), **413** (Datei zu groß) und **500** (Serverfehler) — passend zum bestehenden 404-Design, zweisprachig (DE/EN), auf der öffentlichen Seite und im Admin-Panel. Statt der nackten Standard-Fehlerseite gibt es jetzt eine klare Meldung mit Zurück-/Startseite-Link.

## 0.6.4

- 🔒 Sicherheit (CodeQL HIGH): YouTube-Hostprüfung beim Video-Embed gehärtet — exakter Domain-Abgleich (`youtube.com`/`*.youtube.com`) statt Substring, damit z. B. `evilyoutube.com` nicht mehr akzeptiert wird.

## 0.6.3

- 🔎 **Vorschau im Admin-Panel**: Klick auf eine Mini-Kachel (Bilder bei Blog, Alben und Projekten) zeigt das Bild größer in einer Vorschau (begrenzte Größe, nicht volle Auflösung). Drag & Drop zum Sortieren bleibt unverändert.

## 0.6.2

- 🔍 **Fotos zoomen**: Klick auf ein Bild in Fotoalben (Diashow) und in Blog-Beiträgen öffnet es groß; ein weiterer Klick schaltet auf volle Auflösung um (scroll-/schwenkbar), um Details zu sehen.
- 🌓 **Auge-Symbol** (Bereich ein-/ausblenden) jetzt als SVG-Icon — im Dark Mode klar erkennbar.
- 📊 **Referrer-Statistik** filtert lokale/private Adressen (192.168.x.x, 10.x, `*.local`, `localhost` …) aus — interne Aufrufe verfälschen die Liste nicht mehr.

## 0.6.1

- 👁 **Bereiche ein-/ausblenden**: Über das Auge-Symbol am Akkordeon-Bereich lässt sich ein Bereich von der Startseite ausblenden — der Inhalt bleibt erhalten und kann jederzeit wieder eingeblendet werden. Ausgeblendete Bereiche verschwinden auch aus der Navigationsleiste.
- 📱 **Sortieren jetzt auch auf Touch-/Mobilgeräten** (Umstellung auf Pointer-Events).
- 🐞 Fix: 404 für `/favicon.ico` im Admin-Panel.

## 0.6.0

- 🔀 **Flexible Reihenfolge der Startseite**: Die Abschnitte lassen sich im Admin-Panel (Tab „Inhalt“) per Drag & Drop am Griff (⠿) sortieren – die Startseite übernimmt die Reihenfolge sofort. Der Kopf mit Bild bleibt immer oben, das Kontaktformular immer unten.
- Auch **Projekte** und **Blog** lassen sich positionieren (bearbeitet werden sie weiterhin in ihren eigenen Tabs).
- Die Navigationsleiste folgt automatisch der gewählten Reihenfolge.

## 0.5.1

- 🐞 Fix: Der „Speichern"-Button im Inhalt-Tab erschien als großer leerer Kasten — jetzt eine schlichte rechtsbündige Leiste.

## 0.5.0

- ✨ **Neue Inhalts-Bereiche für mehr Zielgruppen** (alle DE/EN, sortierbar):
  - **Leistungen / Angebote** — Karten mit Symbol, Beschreibung und optionalem Preis.
  - **Referenzen / Kundenstimmen** — Zitat, Name, Funktion und optionalem Foto.
  - **Team** — Personen mit Foto, Funktion und Kurzbeschreibung.
  - **Veranstaltungen** — kommende Termine mit Datum, Ort und Link.
  - **Standort & Öffnungszeiten** — Adresse, Zeiten und optionale Karte (datenschutzfreundlich via OpenStreetMap, lädt erst auf Klick) + „Auf Karte öffnen"-Link.
- 📅 **Buchungs-/Termin-Button** im Hero (frei konfigurierbarer Link, z. B. Calendly) — unter Design.
- 🗂 **Inhalt-Tab als Akkordeon**: alle Bereiche sind jetzt einklappbar — kein endloses Scrollen mehr.
- Die neuen Bereiche erscheinen automatisch in der Navigationsleiste, sobald sie Inhalt haben.

## 0.4.2

- 🧭 **Navigationsleiste im Kopf**: Sprungmarken zu den vorhandenen Bereichen (News, Blog, Projekte, Skills, Fotos, Werdegang, Links, FAQ, Kontakt) — es erscheinen nur Bereiche, die auch Inhalt haben. Sanftes Scrollen, sticky am oberen Rand. Im Admin-Panel unter Design ein-/ausschaltbar.

## 0.4.1

- 🖼 **Bild-Galerie für Blog-Beiträge**: mehrere Bilder pro Beitrag (Mehrfach-Upload, per Drag & Drop sortierbar). Auf der Beitragsseite horizontal scrollbar mit Pfeil-Buttons (wie das Album-Karussell), Klick öffnet das Bild groß (Lightbox).

## 0.4.0

- ❓ **FAQ-Bereich**: aufklappbare Fragen & Antworten (Markdown) auf der Startseite, im Inhalte-Tab pflegbar und sortierbar
- ☕ **Support-/Spenden-Button**: frei konfigurierbarer Link (z. B. Buy Me a Coffee, Ko-fi, PayPal, GitHub Sponsors, Patreon) als Button im Profilkopf — Icon wird automatisch aus der URL erkannt
- 🎬 **Video-Einbettung** (YouTube/Vimeo) in Projekt-Detailseiten und Blog-Beiträgen — **datenschutzfreundlich**: das Video wird erst auf Klick geladen (kein YouTube-Request vorab), Einbettung über youtube-nocookie.com

## 0.3.7

- ↕️ **Werdegang und Aktuelles sortierbar**: ↑/↓-Pfeile pro Eintrag (wie bei Linksammlung, Projekten und Alben) — damit sind jetzt alle Inhaltslisten umsortierbar

## 0.3.6

- 🤖 **Captcha im Kontaktformular**: einfache Rechenaufgabe („7 + 3 = ?") gegen automatisierten Spam — zusätzlich zu Honeypot und Rate-Limit. Stateless per signiertem Token (kein externer Dienst, DSGVO-freundlich), Aufgabe ist 10 Minuten gültig und wird nach jedem Versuch erneuert.

## 0.3.5

- 🔧 Robustere Übersetzung: Eine ungültige `translate_email` (MyMemory antwortet „INVALID EMAIL") lässt die Übersetzung nicht mehr scheitern — es wird automatisch auf das anonyme Limit zurückgefallen und eine Warnung geloggt.

## 0.3.4

- ↕️ **Linksammlung sortierbar**: ↑/↓-Pfeile pro Eintrag zum Verschieben (wie bei Projekten und Alben)

## 0.3.3

- 🔗 **Automatische Social-Media-Icons** bei „Weitere Links": Das passende Symbol wird anhand der URL erkannt — unterstützt GitHub, GitLab, Instagram, TikTok, Facebook, LinkedIn, YouTube, X/Twitter, Mastodon, Telegram, Discord, WhatsApp, Bluesky, Xing, Twitch und Reddit. Unbekannte Links bekommen ein neutrales Link-Symbol.

## 0.3.2

- 🏠 **Mehr HA-Sensoren**: `binary_sensor.mypage_storage_online` (SMB-Speicher erreichbar — ideal für Ausfall-Alarm), `binary_sensor.mypage_maintenance` (Wartungsmodus an/aus) sowie Content-Zähler `sensor.mypage_projects`, `_posts`, `_albums`

## 0.3.1

- 🏠 **Vier neue HA-Sensoren**: `sensor.mypage_user_storage` (belegter Speicher aller Mitglieder-Dateien in MB), `sensor.mypage_failed_logins` (fehlgeschlagene Logins der letzten 24 h), `sensor.mypage_messages` (Kontaktnachrichten), `sensor.mypage_members` (Benutzeranzahl)

## 0.3.0

- 🌐 **Auto-Übersetzung DE→EN** per Klick (MyMemory, kostenlos, kein API-Key): Button „🌐 DE→EN übersetzen" in Profil, Projekt-, Blog- und Album-Dialog füllt die englischen Felder automatisch aus den deutschen. Lange Texte werden automatisch aufgeteilt; Ergebnis bleibt editierbar zum Nachbessern. Optionale Add-on-Option `translate_email` erhöht das kostenlose Tageslimit.

## 0.2.2

- 🔧 Fix Schriftauswahl: Die Anführungszeichen im Font-Namen wurden HTML-escaped (`&#39;`) und damit ungültig — die gewählte Schrift griff nicht. Jetzt korrekt eingebunden.

## 0.2.1

- 🔤 **5 zusätzliche Web-Schriften** (Inter, Poppins, Montserrat, Lato, Merriweather) — selbst gehostet, kein externer Request. Die bisherigen System-Schriften bleiben erhalten
- ⬆️ **Eigene Schrift hochladen** (WOFF2/WOFF/TTF/OTF) im Design-Tab — wird selbst ausgeliefert und als Schriftart wählbar
- 🖱 **Drag & Drop** zum Umsortieren der Bilder im Fotoalbum (im Album-Dialog)

## 0.2.0

- 📝 **Entwurf/Veröffentlicht-Status** für Blog-Beiträge und Projekte: Entwürfe sind öffentlich unsichtbar, im Admin mit Badge markiert
- 🕒 **Geplante Beiträge**: Ein veröffentlichter Blog-Beitrag mit Datum in der Zukunft erscheint automatisch erst ab diesem Tag (Badge „Geplant")
- 📡 **RSS-Feed** unter `/feed.xml` (nur sichtbare Beiträge) — mit Auto-Discovery-Link im `<head>`
- 📱 **PWA**: Die Seite ist installierbar (Manifest + Service Worker, eigenes Icon, Offline-Grundfunktion)
- 🔤 **Schriftart-Auswahl** im Design-Tab (System, Klassisch, Weich, Serife, Monospace) — alles System-Fonts, kein externer Request
- 🎨 **Eigenes CSS-Feld** im Design-Tab für individuelle Anpassungen (`</`-Ausbruch wird neutralisiert)

## 0.1.24

- 🔒 **Sicherheitshärtung (CodeQL #136, #142–149, #153)**:
  - Alle Dateipfade aus Eingaben laufen jetzt über `werkzeug.safe_join` (`safe_under`-Helfer) — Path-Traversal/Zip-Slip an Upload, Download, Restore, Speicherort-Browser und Wasserzeichen-Route ausgeschlossen
  - Benutzer-IDs werden vor der Pfadbildung gegen ein striktes Muster geprüft
  - E-Mail-Validierung auf eine ReDoS-sichere Regex umgestellt (kein katastrophales Backtracking mehr — 40k-Zeichen-Stresstest < 2 ms)

## 0.1.23

- 📊 Statistik: Die Kacheln „Länder" und „Letzte Besucher" werden bei vielen Einträgen auf eine sinnvolle Höhe begrenzt und per „Mehr/Weniger anzeigen"-Button auf- und zugeklappt (Button erscheint nur bei Überlauf, mit sanftem Ausblend-Verlauf am unteren Rand).

## 0.1.22

- 🔗 **Linksammlung**: Links zu anderen Seiten mit Titel und Beschreibung (DE/EN), Verwaltung im Inhalte-Tab. Auf der Startseite erscheint ein Button, der ein Overlay mit allen Links öffnet — ein Klick öffnet die Zielseite in einem neuen Tab (`rel="noopener"`). Hält die Startseite schlank.

## 0.1.21

- 🎠 **Fotoalben als horizontales Karussell**: Alben liegen jetzt in einer Reihe zum seitlichen Durchscrollen statt in mehreren Zeilen untereinander — kompakter und übersichtlicher. Mit Pfeil-Buttons (Desktop), Scroll-Snap, angeschnittener nächster Karte als Hinweis und natürlichem Wischen auf Touch. Pfeile erscheinen nur, wenn es mehr Alben gibt als in die Reihe passen.

## 0.1.20

- 🛡 **Bildschutz für Fotoalben**: Schalter „Bilder schützen" im Alben-Bereich. Aktiv brennt MyPage ein **Wasserzeichen** (frei einstellbarer Text, Vorgabe `© deine-domain.de`) in alle Album-Bilder ein und deaktiviert Rechtsklick/Ziehen. Das Wasserzeichen wird dynamisch beim Ausliefern erzeugt (mit Cache) — eine Textänderung wirkt sofort auf alle Bilder. Hinweis: vollständiger Download-Schutz ist im Web technisch nicht möglich (Screenshots), das Wasserzeichen ist der eigentliche Schutz.

## 0.1.19

- 📸 **Fotoalben**: neuer Bereich auf der Startseite (zwischen Skills und Werdegang). Alben mit Titel und Beschreibung (DE/EN), Bilder per Mehrfach-Upload. Ein Klick öffnet eine **Diashow** mit weichem Ausblend-Effekt, Autoplay, Vor/Zurück, Play/Pause und Tastatursteuerung (Pfeile, Leertaste, Esc). Verwaltung im Inhalte-Tab. Bilder werden wie alle Uploads automatisch verkleinert und als WebP gespeichert (Pillow).

## 0.1.18

- 🔒 **Sicherheitsfix**: Bei einem Passwortwechsel (Admin-Reset, „Zugangsdaten erneut senden" oder neues Passwort setzen) werden jetzt alle bestehenden Sitzungen des Benutzers beendet. Vorher blieb ein bereits eingeloggter Browser trotz geändertem Passwort weiter angemeldet.

## 0.1.17

- 📋 **Login-Ereignisse im Add-on-Log**: erfolgreiche, fehlgeschlagene und gesperrte Mitglieder-Anmeldungen werden mit E-Mail und IP protokolliert (Brute-Force-Schutz war bereits aktiv: 5 Fehlversuche → 15 Min. IP-Sperre, auch das Sperren wird geloggt)
- ✉ **Abweichender Absender für Zugangs-Mails**: Im Benutzer-Tab lässt sich ein Alias (z. B. `noreply@…`) für Willkommens-/Passwort-Mails hinterlegen, während Kontaktnachrichten weiter über die Standard-Adresse laufen. Zusätzlich neue Option `smtp_from` als globaler Standard-Absender
- 💬 **Begrüßungsnachricht pro Benutzer**: Der Admin kann jedem Benutzer eine Nachricht (Markdown) hinterlegen, die nach der Anmeldung im persönlichen Bereich angezeigt wird

## 0.1.16

- 🔧 Hotfix: fehlender `import tempfile` ließ den SMB-Mount fehlschlagen („name 'tempfile' is not defined")

## 0.1.15

- 🔧 **Journal repariert**: Die CodeQL-Autofixes (0.1.14.1–0.1.14.3) waren gegen veraltete Dateistände erzeugt und hatten Journal, `noserverino`-SMB-Fix, Referrer-Filter und konfigurierbare Log-Limits mit zurückgedreht — alles wiederhergestellt
- ✅ CodeQL #150 sauber neu angewendet: Passwortgenerator nutzt Rejection-Sampling (kein Modulo-Bias)
- ✅ CodeQL #139 gründlicher gelöst: SMB-Zugangsdaten landen **nie mehr auf der Platte** — weder in app.py (anonymes Tempfile + vererbter Filedescriptor, inkl. `pass_fds`-Fix des Autofix-Bugs) noch in run.sh (der Mount passiert jetzt komplett in app.py)

## [0.1.14.3] - 2026-06-11

Fix  Clear-text storage of sensitive information mypage #139


## [0.1.14.2] - 2026-06-11

Fix: Clear-text storage of sensitive information #139


## [0.1.14.1] - 2026-06-11

Fix: Creating biased random numbers from a cryptographically secure source #150


## 0.1.14

- ⚙️ **Limits konfigurierbar**: neue Optionen `visit_log_max` (Besucher-Log, 50–10000, Standard 500) und `user_journal_max` (Journal pro Benutzer, 20–1000, Standard 100)
- Die Log-Ansicht im Statistik-Tab zeigt jetzt bis zu 500 Einträge (vorher fix 100), abhängig vom konfigurierten Limit

## 0.1.13

- 📊 Referrer-Filter erweitert: alle Subdomains der eigenen Domain (`*.gizmonet.de`) werden gefiltert — per sicherem Suffix-Vergleich, nicht Substring

## 0.1.12

- 📊 Top-Referrer: eigene Domain wird herausgefiltert (interne Navigation ist kein Referrer) — es bleiben nur echte externe Quellen. Voraussetzung: öffentliche URL im Design-Tab ist gesetzt

## 0.1.11

- 📜 **Benutzer-Journal**: neuer Button pro Benutzer — Anmeldungen, Up-/Downloads, Löschungen und Admin-Aktionen mit Zeit, Datei und IP (letzte 100 Einträge)
- 🕐 **Letzter Login** (Zeit + IP) in der Benutzerzeile
- 💾 `users.json` ist jetzt Teil von Backup & Restore

## 0.1.10

- 🎯 **Echte Ursache der stale handles gefunden**: Die FritzBox liefert über SMB instabile Inode-Nummern — ESTALE trat deshalb sogar direkt nach einem Upload auf. Mount jetzt mit **`noserverino`** (Client vergibt eigene, stabile Inode-Nummern)

## 0.1.9

- 🔧 SMB-Mount jetzt mit **`cache=none`** (+ `actimeo=1`): kein Handle-/Seiten-Caching mehr — stale file handles auf FritzBox-Shares werden damit an der Wurzel verhindert

## 0.1.8

- 🔧 **Stale-Handle-Fix, Stufe 2** (Remount reichte nicht immer):
  - Stufe 1: Dentry-/Inode-Cache-Drop — entwertet stale Handles, ohne den Mount anzufassen (Uploads gingen ja immer, nur Reads alter Dateien hingen)
  - Stufe 2: Force-Unmount (`-f -l`) statt nur lazy, Mount wird erst als Erfolg gemeldet, wenn der Share wirklich antwortet
  - Download-Retry wartet und verifiziert den Dateizugriff (bis zu 2 Remount-Zyklen) statt blind sofort erneut zu lesen

## 0.1.7

- 🔧 **Fix „Stale file handle" (Errno 116)** bei Downloads vom FritzBox-SMB: bei stale Handles wird automatisch neu gemountet und der Download sofort wiederholt
- Watchdog prüft jetzt den aktiven Ordner statt nur der Mount-Wurzel (erkennt tote Verbindungen zuverlässiger)
- Mount mit `actimeo=5` (weniger Attribut-Caching → weniger stale Handles)
- Dateiliste im Mitglieder-Bereich wirft bei Speicherfehlern keine 500 mehr, sondern zeigt die Offline-Meldung

## 0.1.6

- 🔧 **Fix Download-Fehler 500** im Mitglieder-Bereich: Downloads laufen jetzt über einen robusten Pfad (expliziter Datei-Check, kein Conditional-Handling auf CIFS); Fehlerursachen landen ab sofort im Add-on-Log
- 🔧 Fix: Dateien mit Kollisions-Suffix waren nicht herunterladbar/löschbar (Klammern überlebten die Namensprüfung nicht) — neue Uploads nutzen `name_1.ext`
- `/favicon.ico` liefert jetzt das eingestellte Favicon bzw. den Avatar (kein 404-Rauschen mehr in der Konsole)

## 0.1.5

- ✉ **„Zugangsdaten erneut senden"-Button** pro Benutzer: erzeugt ein neues Passwort und verschickt die Willkommens-Mail erneut (mit Sicherheitsabfrage; das alte Passwort wird ungültig)

## 0.1.4

- 📧 Willkommens-Mail: Login-Link nutzt die öffentliche URL aus dem Design-Tab (`https://deine-domain/bereich`); fehlt sie, wird die Zeile weggelassen statt ein verwirrendes „/bereich" zu zeigen
- ⚠ Warnung beim Benutzer-Anlegen/Passwort-Reset, wenn die öffentliche URL noch nicht gesetzt ist
- Mail-Text verständlicher formuliert („persönlicher Dateibereich")

## 0.1.3

- 🔧 Fix Ordner-Browser: Auswahl sprang nach dem Speichern auf die Basis zurück; jetzt bleibt der Browser im gewählten Ordner stehen und der **aktive Ordner** wird dauerhaft separat angezeigt

## 0.1.2

- 📁 **Admin kann Benutzern Dateien hinterlegen**: neuer „Dateien"-Button pro Benutzer (auflisten, hochladen, herunterladen, löschen)
- 🎲 **Passwortgenerator** beim Anlegen und Zurücksetzen (8 Zeichen, Groß/Klein/Zahlen, keine Sonderzeichen, keine verwechselbaren Zeichen)
- 📂 **Speicherort wählbar**: Ordner-Browser im Benutzer-Tab — Unterordner auf dem SMB-Share (oder lokal) festlegen
- 🔄 **SMB-Watchdog**: prüft jede Minute und verbindet nach FritzBox-/NAS-Neustart automatisch neu (`soft`-Mount gegen Hänger)
- 🚫 **Kein Fallback mehr auf lokalen Speicher**: Ist der SMB-Speicher weg, geht der Dateibereich offline — Benutzer und Admin sehen eine klare Meldung statt versehentlich lokal gespeicherter Dateien

## 0.1.1

- 🔧 **Fix SMB-Mount** („Permission denied"): eigenes AppArmor-Profil mit mount/umount-Rechten (wie bei FileBox)

## 0.1.0

- 🔐 **Persönlicher Bereich** (`/bereich`, Login-Link im Footer): Multi-User-Dateiablage zum einfachen Teilen
  - Benutzername = E-Mail-Adresse, Passwörter nur als scrypt-Hash gespeichert
  - Neuer Admin-Tab „Benutzer": anlegen, löschen, Passwort zurücksetzen, Speicher-Quota pro Benutzer
  - 📧 Automatische **Willkommens-Mail** mit Zugangsdaten beim Anlegen (wenn SMTP konfiguriert), ebenso bei Passwort-Reset
  - Jeder Benutzer sieht nur seine eigenen Dateien; Uploads zählen gegen die Quota; Downloads immer als Attachment (kein XSS)
  - Brute-Force-Schutz wie beim Admin-Login, eigene Session-Cookies
- 💾 **Optionaler SMB-Mount**: Mitglieder-Dateien auf eine Netzwerk-Freigabe legen statt auf die SD-Karte (`smb_server`, `smb_share`, `smb_user`, `smb_password`); bei Mount-Fehler automatischer Fallback auf lokalen Speicher
- Neue Option `user_upload_max_mb` (Standard 200) als Upload-Limit pro Datei

## 0.0.8

- 🌐 **Exakte Länder-Erkennung per GeoIP** (ipapi.is) — neue Optionen `geoip_lookup` (Standard: aus, da Besucher-IPs an den Dienst übertragen werden) und `geoip_api_key` (optional, ohne Key ~1.000 Lookups/Tag frei)
- Hintergrund-Worker mit IP-Cache (max. 20 Lookups/Minute, jede IP nur einmal), private IPs werden nie gesendet; bestehende Log-Einträge ohne Land werden nachgetragen

## 0.0.7

- 📧 **E-Mail-Benachrichtigung** bei neuen Kontaktnachrichten (SMTP, analog zu GitPulse) — neue Optionen `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `smtp_to`, `smtp_tls`
- Benachrichtigungen (Telegram + E-Mail) blockieren das Kontaktformular nicht mehr (Versand im Hintergrund)

## 0.0.6

- 🌍 **Länder-Statistik**: Verteilung mit Flagge und Ländername im Statistik-Tab, Flagge auch im Besucher-Log
- Erkennung über Cloudflare-Header (`CF-IPCountry`) oder näherungsweise über die Browser-Sprache (NGINX & Co., keine GeoIP-Datenbank nötig)

## 0.0.5

- GitHub-Import: Benutzername wird automatisch aus dem Profil vorbefüllt, neutrale Platzhalter

## 0.0.4

- 🔢 **Fix Besucherzähler**: Der öffentliche Zähler zeigt jetzt eindeutige Besucher (pro Tag dedupliziert) — ein Browser-Refresh zählt nicht mehr hoch
- 🎨 **Layout-Themes**: Projekte als Karten, Liste oder Minimal-Ansicht
- 📰 **Blog**: Beiträge mit Markdown unter `/blog`, die neuesten drei auf der Startseite — neuer Admin-Tab
- 🏠 **Home-Assistant-Sensoren**: Aufrufe/Besucher (gesamt + heute) als `sensor.mypage_*` in HA
- 📥 **README-Import**: Beim GitHub-Import optional das README als Detailtext übernehmen
- 🌗 **Auto-Theme**: folgt auf Wunsch der Systemeinstellung des Besuchers
- 🚫 **Eigene 404-Seite** im Seiten-Design
- 🔍 **SEO**: `sitemap.xml`, `robots.txt` mit Sitemap-Verweis, JSON-LD (Person + BlogPosting), Feld „Öffentliche URL"
- 📦 **Statischer Export**: komplette Seite als HTML-Paket (z. B. für GitHub Pages)
- 🖼 **Bild-Optimierung**: Uploads werden auf max. 1600 px verkleinert und als WebP gespeichert
- 📊 Statistik: neue Karte „Besucher gesamt"

## 0.0.3

- 🛠 **Wartungsmodus**: Schalter im neuen System-Tab — öffentliche Seite zeigt einen Hinweis (HTTP 503), Admin bleibt erreichbar
- 👁 **Live-Vorschau** der öffentlichen Seite im Design-Tab
- ✍️ **Markdown** in Bio, Projekt-Detailtexten und Wartungshinweis
- 🛡 **E-Mail-Schutz**: Adresse wird erst im Browser zusammengesetzt (Spam-Bots sehen sie nicht im HTML)
- ⭐ **Favicon-Upload** in den Design-Einstellungen
- 📚 **Neue Sektionen**: Skills (Chips), Werdegang (Timeline), Aktuelles (News-Liste) — neuer Tab „Inhalte"
- 📄 **Projekt-Detailseiten** (`/p/<id>`) mit Markdown-Text und Bilder-Galerie inkl. Lightbox
- 📊 **Statistik erweitert**: Top-Referrer und Browser-Verteilung, Pfad im Besucher-Log
- 💾 **Backup & Restore**: Inhalte, Statistik, Nachrichten und Uploads als ZIP sichern/einspielen
- 📨 **Kontaktformular** mit Honeypot-Spamschutz und Rate-Limit; Nachrichten im neuen Tab „Nachrichten", optional Telegram-Benachrichtigung (neue Optionen `telegram_bot_token`, `telegram_chat_id`)

## 0.0.2

- ⚖️ Neuer Tab „Rechtliches": Impressum und Datenschutzerklärung (DE/EN) pflegbar
- Links erscheinen automatisch im Footer der öffentlichen Seite (`/impressum`, `/datenschutz`), sobald Text eingetragen ist

## 0.0.1

- 🎉 Erstveröffentlichung
- Öffentliche Homepage auf Port 17760 (Profil, Projektkarten, Social-Links, DE/EN, Hell/Dunkel)
- Admin-Panel auf Port 17761 mit Login, Brute-Force-Schutz und HA-Ingress-Unterstützung
- GitHub-Import: Repos per Klick übernehmen, Sterne werden stündlich aktualisiert
- Design-Einstellungen: Akzentfarbe, Standard-Theme, Seitentitel, Footer
- Besucherzähler mit Tagesstatistik und Besucher-Log (Zeit, IP, Browser, Sprache, Referrer, Bot-Erkennung)
- Bild-Uploads für Avatar und Projekt-Screenshots
