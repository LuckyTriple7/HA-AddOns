# SEO-Anleitung für MyPage

Diese Anleitung zeigt Schritt für Schritt, wie deine MyPage-Seite bei Google
auffindbar wird. Das technische Fundament bringt MyPage mit — du musst es nur
einmal bei Google anmelden.

---

## Voraussetzung (einmalig)

Im Admin-Panel → **Design-Tab** → Feld **„Öffentliche URL"** deine Domain
eintragen, z. B. `https://www.gizmonet.de`, und speichern.

Erst dann enthalten `sitemap.xml` und die strukturierten Daten vollständige
Links statt nur Pfade. **Ohne diesen Schritt funktioniert SEO nicht richtig.**

---

## Was MyPage automatisch bereitstellt

| Adresse | Zweck |
|---|---|
| `https://deine-domain/sitemap.xml` | Liste aller öffentlichen Seiten für Suchmaschinen |
| `https://deine-domain/robots.txt` | Erlaubt das Crawlen, verweist auf die Sitemap |

Zusätzlich auf jeder Seite: individueller Seitentitel, Beschreibung (aus deiner
Tagline), Open-Graph-Vorschau (für WhatsApp/Facebook/Discord) und strukturierte
Daten (JSON-LD: Person auf der Startseite, BlogPosting bei Blog-Beiträgen).

Wie der Treffer bei Google aussehen wird, zeigt die **Snippet-Vorschau** direkt
im Admin — im Design-Tab für die Startseite, in den Dialogen von Blog-Beitrag,
eigener Seite und Bibliothek-Eintrag für die jeweilige Unterseite. Dort siehst du
auch, ob Titel und Beschreibung zu kurz oder zu lang sind.

Impressum, Datenschutz, der Mitglieder-Bereich und die 404-Seite sind bewusst
auf `noindex` gesetzt — sie tauchen nicht in Suchergebnissen auf.

### Alle Beschreibungen an einer Stelle

Im **Design-Tab** steht unter der Vorschau der Bereich **„Alle SEO-Beschreibungen"**:
Startseite, Blog-Beiträge, eigene Seiten und Bibliothek-Einträge in einer Liste,
je Sprache umschaltbar. Wo kein eigener Text gesetzt ist, steht darunter, was
Google heute stattdessen bekommt — meist der Anfang des Fließtextes. Der Filter
**„Nur ohne eigene Beschreibung"** zeigt genau die Lücken; geschrieben wird erst
mit **„Beschreibungen speichern"**.

### Beschreibung von der KI schreiben lassen

Ist ein Gemini-Schlüssel hinterlegt (KI-Reiter), steht neben jedem Feld — in der
Übersicht wie in der Snippet-Vorschau der Dialoge — der Knopf **„✦ KI-Beschreibung"**.
Er fasst den vorhandenen Text zu einem Satz zusammen, in der Sprache, die gerade
gewählt ist, mit Ziellänge 120–155 Zeichen. In der Übersicht füllt **„Leere per KI
füllen"** alle Lücken der Reihe nach. Das Ergebnis ist ein Vorschlag: es landet im
Feld, nicht auf der Platte — geprüft und gespeichert wird von Hand.

---

## Schritt 1: Google Search Console einrichten

1. Auf <https://search.google.com/search-console> mit deinem Google-Konto anmelden.
2. **Property hinzufügen** → Variante **„URL-Präfix"** wählen und die volle Adresse
   eintragen (z. B. `https://www.gizmonet.de`).
3. **Inhaberschaft bestätigen.** Am einfachsten per HTML-Datei oder DNS-Eintrag:
   - **DNS** (empfohlen, wenn du Zugriff auf die Domain-Einstellungen hast):
     Google zeigt dir einen TXT-Eintrag, den du beim Domain-Anbieter hinterlegst.
   - **HTML-Tag** (in MyPage eingebaut): Google bietet neben der Datei auch ein
     Meta-Tag an. Den Code trägst du im Admin-Panel → **Design-Tab** unter
     *Google-Search-Console-Code* ein (das komplette Tag geht auch, der Code wird
     herausgelesen). MyPage setzt das Tag dann in den Kopf der Startseite. Für
     Bing gibt es daneben das Feld *Bing-Webmaster-Code*.
   - **HTML-Datei**: Die Variante `googleXXXX.html` zum Ablegen im Web-Verzeichnis
     unterstützt MyPage **nicht** — nimm dafür die beiden Wege oben.

> Tipp: Trage am besten **beide** Varianten deiner Domain ein — mit und ohne
> `www` (`https://gizmonet.de` und `https://www.gizmonet.de`) — und lege im
> Design-Tab die fest, die du wirklich verwendest.

---

## Schritt 2: Sitemap einreichen

1. In der Search Console links auf **„Sitemaps"**.
2. Unter „Neue Sitemap hinzufügen" eintragen: `sitemap.xml`
3. Auf **Senden** klicken.

Google holt sich ab jetzt automatisch deine Seitenliste. Nach ein paar Tagen
siehst du dort, wie viele Seiten gefunden und indexiert wurden.

---

## Schritt 3: Geduld

SEO ist kein Schalter, sondern ein Prozess:

- **Tage bis Wochen**, bis Google die Seiten indexiert hat.
- Über **„URL-Prüfung"** in der Search Console kannst du eine einzelne Seite
  sofort zur Indexierung anstoßen.
- Unter **„Leistung"** siehst du später, mit welchen Suchbegriffen Besucher
  zu dir finden.

---

## Was du selbst zur guten Platzierung beiträgst

Die Technik ist nur die halbe Miete. Den größten Unterschied machen Inhalt und
Bekanntheit:

- **Aussagekräftiger Seitentitel und Tagline** im Profil — daraus baut Google
  Titel und Beschreibung im Suchergebnis.
- **Echte, ausführliche Texte** in Projektbeschreibungen und Blog-Beiträgen.
  Schreibe so, wie Leute suchen würden („Home Assistant Add-on für …").
- **Backlinks** sind der stärkste Hebel: Wenn deine Seite woanders verlinkt wird
  (Home-Assistant-Forum, dein GitHub-Profil, Reddit, ein Blog), wertet Google
  das als Vertrauenssignal. Verlinke deine Seite überall, wo es passt.
- **Regelmäßige Updates** (z. B. neue Blog-Beiträge) signalisieren eine lebendige
  Seite.

---

## Schnell-Check

- [ ] Öffentliche URL im Design-Tab gesetzt
- [ ] `https://deine-domain/sitemap.xml` im Browser erreichbar und zeigt deine Seiten
- [ ] `https://deine-domain/robots.txt` erreichbar
- [ ] Google Search Console eingerichtet und Domain bestätigt
- [ ] Sitemap in der Search Console eingereicht
- [ ] Seite woanders verlinkt (Forum, GitHub, …)
