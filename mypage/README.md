# MyPage — Homepage-Baukasten

Eigene Homepage direkt aus Home Assistant heraus betreiben — ohne Design-Kenntnisse. Vom Entwickler-Portfolio über die Vereinsseite bis zur Visitenkarte für Dienstleister.

> 🇬🇧 English version: [README.en.md](README.en.md)

## Features

- 🏠 **Öffentliche Homepage** auf Port 17760 — Profil, Inhaltsbereiche, Social-Links
- 🛠 **Admin-Panel** auf Port 17761 (Login + Brute-Force-Schutz) und über HA-Ingress in der Seitenleiste
- 🧩 **Viele Inhaltsbereiche**: Projekte, Blog, Leistungen, Referenzen, Team, Fotoalben, Skills, Werdegang, Aktuelles, Veranstaltungen, Linksammlung, FAQ, Standort & Öffnungszeiten
- 🔀 **Freie Reihenfolge & Sichtbarkeit**: Bereiche per Drag & Drop sortieren und einzeln aus-/einblenden (Kopf bleibt oben, Kontakt unten)
- 🐙 **GitHub-Import**: Benutzername eingeben, Repos auswählen, fertig — Beschreibung, Sterne, Sprache und Topics werden übernommen, Sterne stündlich aktualisiert
- 📅 **Termin-/Buchungs-Button** (z. B. Calendly) — siehe [unten](#-buchungskalender--termin-button)
- ❤️ **Unterstützen-Button** (Buy Me a Coffee, Ko-fi, PayPal, Patreon, GitHub Sponsors …) mit automatischem Icon
- 🎨 **Design**: Akzentfarbe, Hell/Dunkel, Layout, Schriftart (inkl. eigenem Font-Upload), eigenes CSS
- 🌍 **Zweisprachig** (DE/EN) mit optionaler Auto-Übersetzung; Besucher können umschalten
- 👁 **Besucherzähler & Statistik**: Aufrufe, eindeutige Besucher, Länder, Browser, Referrer
- 📷 **Fotoalben** mit Diashow, Wasserzeichen und Bild-Zoom; **Bild-Galerien** in Blog-Beiträgen
- 📝 **Blog** mit Volltextsuche, Schlagwörtern (Tags), **Newsletter-Abo** (Double-Opt-in) und — optional — **Kommentaren & Emoji-Reaktionen** für Mitglieder (moderierbar)
- 🔒 **Mitglieder-Bereich**: passwortgeschützter Dateibereich pro Benutzer (optional auf SMB-Share), optionale **Selbst-Registrierung** (E-Mail-Bestätigung + Admin-Freigabe), **Self-Service-Passwort-Reset** und je Mitglied **abschaltbare Spiele**
- 📨 **Kontaktformular** mit Spam-Schutz (Honeypot + Captcha + Rate-Limit) und Benachrichtigung per Telegram/E-Mail sowie **Home Assistant**
- 🧭 **Navigationsleiste** im Kopf mit Sprungmarken zu den vorhandenen Bereichen
- 📈 **Home-Assistant-Sensoren & -Benachrichtigungen**, RSS, PWA, SEO (Sitemap/robots.txt), Backup & statischer Export

## Schnellstart

1. Add-on installieren und starten
2. In den Add-on-Optionen `username` und `password` setzen
3. Admin-Panel öffnen (Seitenleiste oder `http://<host>:17761`)
4. Profil ausfüllen, Inhalte pflegen, Design wählen
5. Öffentliche Seite läuft auf `http://<host>:17760` — z. B. über einen Cloudflare Tunnel veröffentlichen

> **Tipp:** Nur Port 17760 nach außen freigeben. Das Admin-Panel (17761) bleibt am besten im lokalen Netz bzw. hinter HA.

Die vollständige Dokumentation aller Optionen und Funktionen steht in [DOCS.md](DOCS.md).

## Inhaltsbereiche anordnen & ausblenden

Im Admin-Panel unter **Inhalt** liegt jeder Bereich als einklappbare Karte vor:

- **Reihenfolge ändern:** Am Griff (⠿) links per **Drag & Drop** verschieben — auf Maus **und** Touch. Die Startseite übernimmt die Reihenfolge sofort.
- **Aus-/Einblenden:** Mit dem **Auge-Symbol** blendest du einen Bereich von der Startseite aus. Der **Inhalt bleibt erhalten** und kann jederzeit wieder eingeblendet werden. Ausgeblendete Bereiche verschwinden auch aus der Navigationsleiste.
- Der **Kopfbereich** (Profil/Bild) bleibt immer ganz oben, das **Kontaktformular** immer ganz unten.
- Auch **Projekte** und **Blog** lassen sich positionieren (bearbeitet werden sie in ihren eigenen Tabs).

## 📅 Buchungskalender / Termin-Button

MyPage bringt **keinen eigenen Kalender** mit, sondern verlinkt auf einen **externen Buchungsdienst deiner Wahl** — ideal für Coaches, Berater, Handwerker, Friseure usw. So richtest du es ein:

1. **Buchungslink erstellen** bei einem Dienst deiner Wahl, z. B.:
   - [Calendly](https://calendly.com) — `https://calendly.com/deinname/30min`
   - [Cal.com](https://cal.com) — `https://cal.com/deinname`
   - Microsoft Bookings, TidyCal, SimplyBook.me, Acuity … (jeder öffentliche Buchungslink funktioniert)
2. Im Admin-Panel **→ Tab Design** das Feld **„Termin-/Buchungs-Link"** mit dieser URL füllen.
3. Optional: Feld **„Beschriftung Buchungs-Button"** anpassen (Standard: *Termin buchen* / *Book appointment*).
4. **Speichern.**

Ergebnis: Oben im Kopfbereich der Startseite erscheint ein Button mit **Kalender-Symbol** (neben dem Unterstützen-Button). Ein Klick öffnet den Buchungsdienst in einem **neuen Tab**.

- Ist **kein Link** gesetzt, erscheint **kein Button**.
- Der Link muss mit `http://` oder `https://` beginnen, sonst wird er verworfen.
- **Datenschutz:** Es wird nichts vorab geladen — erst der Klick öffnet die externe Buchungsseite. Wenn du den Dienst nutzt, gehört ein Hinweis darauf in deine Datenschutzerklärung (der Anbieter verarbeitet die Termindaten).

## Eigenes CSS — Beispiele

Im Design-Tab gibt es das Feld **„Eigenes CSS"**. Dort eingetragene Regeln werden
**nach** dem Standard-Design eingebunden und überschreiben es gezielt — so passt du
das Aussehen an, ohne das Grunddesign zu zerstören. Aufbau: `Auswahl { Eigenschaft: Wert; }`.

> **Klassennamen finden:** Auf der öffentlichen Seite **F12** drücken → Rechtsklick auf
> ein Element → „Untersuchen". Dort steht der Name, den du im CSS ansprichst.
> Ungültiges CSS wird vom Browser ignoriert — die Seite geht also nicht kaputt.

```css
/* Hero-Überschrift größer und mit Buchstabenabstand */
.hero h1 { font-size: 2.6rem; letter-spacing: 1px; }

/* Projekt- und Album-Karten stärker abrunden, mit Schatten */
.card, .album-card { border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,.2); }

/* Mehr Abstand über jeder Abschnitts-Überschrift */
.section-title { margin-top: 48px; }

/* Skills-Chips in der Akzentfarbe füllen */
.skill { background: var(--accent); color: #fff; border-color: var(--accent); }

/* Avatar eckig statt rund */
.avatar { border-radius: 12px; }

/* Tagline kursiv */
.tagline { font-style: italic; }

/* Projektkarten beim Überfahren stärker anheben */
.card:hover { transform: translateY(-6px); }
```

**Design-Variablen** (passen sich automatisch an Hell/Dunkel an) kannst du verwenden:
`var(--accent)` (Akzentfarbe), `var(--text)`, `var(--muted)`, `var(--surf)` (Kartenhintergrund),
`var(--bg)` (Seitenhintergrund), `var(--border)`.

Aus Sicherheitsgründen werden `<`-Zeichen aus dem Feld entfernt — es ist also
ausschließlich CSS möglich, kein HTML/Script.
