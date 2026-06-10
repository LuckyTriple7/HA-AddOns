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
