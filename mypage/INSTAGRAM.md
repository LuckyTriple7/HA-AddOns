# Instagram automatisch bespielen — Recherche

**Stand: 2026-08-10.** Meta ändert diese Regeln regelmäßig; vor dem Bauen die
aktuellen Meta-Docs gegenlesen. Quellen stehen unten.

**Ausgangsfrage:** Kann MyPage einen neuen Beitrag automatisch auf Instagram
veröffentlichen, und gibt es dafür etwas Fertiges, das die Registrierung einer
eigenen App bei Meta erspart?

**Kurzantwort:** Fertige Projekte gibt es reichlich, aber keines nimmt einem die
Meta-App ab. Der offene Quelltext bringt keinen Plattform-Zugang mit — wer selbst
hostet, registriert seine eigene App und geht durch Metas App Review. Ohne
eigene App geht es nur, wenn ein **gehosteter Dienst** die App besitzt.

---

## Was Meta in jedem Fall verlangt

Unabhängig davon, wer die App besitzt:

- Instagram muss ein **Professional-Konto** sein (Business oder Creator).
- Es muss mit einer **Facebook-Seite** verknüpft sein.
- Veröffentlichen läuft **zweistufig**: erst `POST /{ig-user-id}/media` (Container
  anlegen), dann `POST /{ig-user-id}/media_publish`.
- Die Publishing-API nimmt **keine Bild-Bytes**, sondern eine **öffentlich
  erreichbare Bild-URL**.
- Limits: 200 API-Aufrufe je Nutzer und Stunde, dazu ein Tageslimit für
  Veröffentlichungen (aktuellen Wert nachschlagen).

Was nur bei **eigener** App dazukommt:

- Berechtigung `instagram_content_publish`. Für **das eigene** Konto reicht in
  der Regel der Dev-Modus mit einem selbst als Admin/Tester. **App Review**
  (2–4 Wochen je Einreichung) braucht es erst, wenn fremde Konten posten sollen.
- **Token-Lebenszyklus**: kurzlebig → langlebig (60 Tage) → muss erneuert werden.
  Das ist der eigentliche Dauerbetrieb, nicht der Post selbst.

---

## Die drei Wege

### 1. Gehosteter Dienst + RSS — empfohlen zum Anfangen

Buffer, Publer, Later, Make, Zapier: die App ist dort registriert und durch das
Review. MyPage veröffentlicht ganz normal, der Dienst beobachtet den Feed.

- **Kein Code im Add-on, keine Meta-App, kein Review, kein Token-Handling.**
- Nachteil: ein weiterer Dienst in der Kette, Caption-Aufbau nur so gut wie
  dessen Textfunktionen.
- Buffer ist eher „Entwurf in die Warteschlange, du gibst frei" als
  Vollautomatik; wie weit RSS im Gratis-Tarif geht, wechselt. Für echte
  Automatik ist Make (oder Zapier) der verlässlichere Weg.

### 2. Eigene Anbindung in MyPage

Zwei POSTs, also rund 40 Zeilen `requests`. Eine Bibliothek spart davon wenig —
die Arbeit steckt in App-Registrierung und Token-Pflege, nicht im Aufruf.

- Passt gut, weil die Publishing-API eine öffentliche Bild-URL will und MyPage
  die unter `/uploads/…` ohnehin hat.
- Preis: eigene Meta-App und die 60-Tage-Token-Erneuerung im Add-on.

### 3. Fertige Self-Hosted-Scheduler — kaufen nichts ein

- [Postiz](https://github.com/gitroomhq/postiz-app) — der bekannteste, viele
  Netzwerke. Die Doku verlangt ausdrücklich Instagram App ID und Secret aus der
  **eigenen** Meta-App in der `.env`, und `instagram_content_publish` braucht
  Review — oder das eigene Konto muss Developer/Tester der App sein.
- [TryPost](https://github.com/trypostit/trypost),
  [OpenPost](https://github.com/rodrgds/openpost) — dasselbe Muster, schlanker.
- Activepieces, n8n, Huginn — Zapier-Alternativen zum Selberhosten, ebenfalls
  mit eigener App.

**Fazit zu 3:** Ein zweiter selbst gehosteter Dienst, der die Meta-App trotzdem
verlangt, bringt gegenüber Weg 2 wenig — außer Zeitplanung und weitere Netzwerke.

### Nicht empfohlen: inoffizielle Clients

`instagrapi` (Python) und `instagram-private-api` (Node) melden sich als App an
und brauchen keine Meta-App. Sie verstoßen gegen die Nutzungsbedingungen,
riskieren die Konto-Sperre und brechen bei jeder App-Änderung.

---

## Rezept für Weg 1 (Make + `feed.xml`)

MyPage liefert unter `https://<domain>/feed.xml` bereits alles Nötige
(gebaut in `app.py`, Route `rss_feed`):

| Feld im Feed | Inhalt | Verwendung im Post |
|---|---|---|
| `<title>` | Titel | Anfang der Caption |
| `<description>` | Kurzfassung | Rest der Caption |
| `<enclosure url=…>` | Titelbild | das Bild des Posts |
| `<category>` | Schlagwörter | Hashtags |
| `<link>` | Adresse des Beitrags | „Link in Bio"-Hinweis |

Enthalten sind Blog und Reiseblog, Projekte und Bibliothek je nach Schalter im
Design-Tab. Der Feed hat **eine** Sprache (`feed_lang`).

Szenario in Make:

1. Trigger **RSS → Watch RSS feed items**, URL `https://<domain>/feed.xml`,
   Intervall z. B. 15 Minuten.
2. **Filter: nur weiter, wenn `enclosure` gefüllt ist.** Instagram-Posts
   brauchen ein Bild; Beiträge ohne Titelbild und Mitglieder-Inhalte (die
   bewusst ohne Bild in den Feed gehen) würden den Post scheitern lassen.
3. Modul **Instagram for Business → Create a Photo Post**, Konto einmalig
   verbinden (App des Dienstes, nicht die eigene).
4. Felder: *Photo URL* = Enclosure-Adresse, *Caption* = Titel + Beschreibung +
   „Link in Bio" + Categories als Hashtags.

Makes Gratis-Tarif liegt bei 1.000 Operationen im Monat — für gelegentliche
Beiträge weit ausreichend.

**Voraussetzungen auf unserer Seite:** Die Website muss von außen erreichbar
sein (läuft über den Cloudflare Tunnel), damit der Dienst Feed **und** Bild
abrufen kann.

**Vorab prüfen:** `feed.xml` im Browser öffnen und nachsehen, ob bei den
Beiträgen eine `<enclosure>`-Zeile steht. Fehlt sie, hat der Beitrag kein
Titelbild — dann gibt es nichts zu posten.

---

## Nebeneffekte, die für MyPage sprechen

- Die Bild-Adresse zeigt auf `/uploads/`, und diese Route brennt KI-erzeugten
  Bildern die Kennzeichnung ein. Die geht damit auch nach Instagram mit raus.
- Instagram-Captions haben keine klickbaren Links — der `<link>` aus dem Feed
  taugt nur als Hinweis („Link in Bio"), nicht als Verweis.

---

## Quellen

- [Post to Instagram via API: Guide (2026) — Postproxy](https://postproxy.dev/blog/post-to-instagram-via-api/)
- [Instagram API Integration Guide 2026 — Phyllo](https://www.getphyllo.com/post/instagram-api-integration-101-for-developers-of-the-creator-economy)
- [Instagram Graph API in 2026: Versions, Rate Limits & Content Publishing — netrows](https://www.netrows.com/blog/instagram-graph-api-guide-2026)
- [Instagram — Postiz Documentation](https://docs.postiz.com/providers/instagram)
- [What Is Postiz? Self-Hosting Your Social Scheduling — Joche Ojeda](https://www.jocheojeda.com/2026/06/16/what-is-postiz-self-hosting-social-scheduling/)
- [GitHub Topic: social-media-scheduler](https://github.com/topics/social-media-scheduler)
