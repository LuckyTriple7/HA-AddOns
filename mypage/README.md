# MyPage — Homepage-Baukasten

Eigene Homepage direkt aus Home Assistant heraus betreiben — ohne Design-Kenntnisse.

## Features

- 🏠 **Öffentliche Homepage** auf Port 17760 — Profil, Projekte, Social-Links
- 🛠 **Admin-Panel** auf Port 17761 (Login + Brute-Force-Schutz) und über HA-Ingress in der Seitenleiste
- 🐙 **GitHub-Import**: Benutzername eingeben, Repos auswählen, fertig — Beschreibung, Sterne, Sprache und Topics werden übernommen, Sterne werden stündlich aktualisiert
- 🎨 **Design-Einstellungen**: Akzentfarbe, Hell/Dunkel, Seitentitel, Footer — alles per Klick
- 🌍 **Zweisprachig**: Inhalte in DE und EN pflegbar, Besucher können umschalten
- 👁 **Besucherzähler**: Aufrufe und eindeutige Besucher pro Tag, Statistik im Admin-Panel
- 📷 **Bild-Uploads** für Avatar und Projekt-Screenshots

## Schnellstart

1. Add-on installieren und starten
2. In den Add-on-Optionen `username` und `password` setzen
3. Admin-Panel öffnen (Seitenleiste oder `http://<host>:17761`)
4. Profil ausfüllen, Projekte importieren, Design wählen
5. Öffentliche Seite läuft auf `http://<host>:17760` — z. B. über einen Cloudflare Tunnel veröffentlichen

> **Tipp:** Nur Port 17760 nach außen freigeben. Das Admin-Panel (17761) bleibt am besten im lokalen Netz bzw. hinter HA.

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
