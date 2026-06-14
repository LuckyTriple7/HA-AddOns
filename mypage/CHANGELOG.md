# Changelog

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
