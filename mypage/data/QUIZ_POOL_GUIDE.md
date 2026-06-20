# Anleitung: Jeopardy-Fragenpool erweitern/pflegen

Diese Datei richtet sich an eine andere Claude-Session, die **Fragen für das
Mitglieder-Spiel „Jeopardy"** hinzufügen oder pflegen soll. Halte dich genau an
die Regeln unten – das Spiel ist server-autoritativ und validiert die Struktur.

## Wo

- **Einzige Datei, die du bearbeitest:** [quiz_pool.json](quiz_pool.json) (in `mypage/data/`).
- **Engine** (nur zur Info, NICHT ändern nötig): `mypage/game_jeopardy.py`. Sie liest
  Kategorien und Fragen zur Laufzeit aus der JSON. Neue Kategorien wirken sofort.

## Aufbau der Datei

```json
{
  "_meta": { "source": "...", "license": "CC BY-SA 4.0", "diff_to_value": {...} },
  "categories": {
    "general": {"de": "Allgemeinwissen", "en": "General Knowledge"},
    "history": {"de": "Geschichte", "en": "History"}
  },
  "questions": [
    {"cat": "geo", "diff": "easy",
     "q_de": "Wie heißt die Hauptstadt Spaniens?",
     "q_en": "What is the capital of Spain?",
     "opts_de": ["Madrid", "Barcelona", "Sevilla", "Toledo"],
     "opts_en": ["Madrid", "Barcelona", "Seville", "Toledo"],
     "c": 0}
  ]
}
```

## Harte Regeln (sonst bricht das Spiel)

1. **`c`** = Index der richtigen Antwort (0–3). **Konvention: richtige Antwort an
   Index 0 setzen, `"c": 0`.** Die Optionen werden im Spiel zur Laufzeit gemischt.
2. **Genau 4 Optionen** in `opts_de` UND `opts_en`. Innerhalb einer Sprache **keine
   doppelten** Optionen.
3. **`opts_de` und `opts_en` müssen dieselbe Reihenfolge haben** – `opts_de[i]` ist
   die Übersetzung von `opts_en[i]`. Sonst stimmt `c` nicht für beide Sprachen.
4. **`cat`** muss ein Schlüssel aus `categories` sein. **`diff`** ist genau einer von
   `easy` | `medium` | `hard`.
5. **Beide Sprachen Pflicht** (`q_de`, `q_en`, `opts_de`, `opts_en`) und nach der
   Übersetzung **eindeutig** (keine Wortspiele, die nur in einer Sprache funktionieren).
6. JSON muss gültig bleiben (UTF-8, doppelte Anführungszeichen, keine Trailing-Kommas).

## Schwierigkeit ↔ Punktwert (warum `diff` wichtig ist)

Das Board hat 5 Werte; sie mappen auf `diff`:
`200/400 = easy`, `600 = medium`, `800/1000 = hard`.
**Pro Kategorie und Board werden gebraucht:** 2× easy, 1× medium, 2× hard.
Für ordentlichen Wiederspielwert also **mindestens** je Kategorie:
~4 easy, ~3 medium, ~4 hard (mehr ist besser). Eine Kategorie wird erst auf dem
Board verwendet, wenn sie **≥ 5 Fragen** insgesamt hat.

## Zusätzliche Kategorien hinzufügen (rein über die JSON!)

1. Neuen Schlüssel in `categories` ergänzen, z. B.
   `"music": {"de": "Musik", "en": "Music"}`.
2. Genug Fragen mit `"cat": "music"` ergänzen (≥ 5, besser ≥ 11 verteilt über die
   Stufen).
3. Fertig. Das Board zieht pro Spiel **6 zufällige** Kategorien aus allen
   vorhandenen – mehr Kategorien = mehr Abwechslung. **Kein Code-Eingriff nötig.**
   (Es müssen insgesamt ≥ 6 nutzbare Kategorien existieren.)

## Optional: Fragen aus OpenTDB ziehen (einmalig, als Seed)

OpenTDB ist gratis, kein Key. **Nur zum Befüllen verwenden, nicht zur Laufzeit.**

1. **Ziehen** (je Kategorie ein Call, Rate-Limit ~1 Request/5 s → einzeln, nicht bündeln):
   `curl -s --max-time 25 "https://opentdb.com/api.php?amount=50&category=<id>&type=multiple" -o cat<id>.json`
   Kategorie-IDs: 9 General, 23 History, 22 Geo, 17 Science, 21 Sports, 11 Film
   (volle Liste: `https://opentdb.com/api_category.php`). Erfolg = `response_code: 0`.
2. **Dekodieren:** HTML-Entities mit `html.unescape` auflösen (`&quot;` etc.).
3. **Filtern – raus mit:** US-/Nischen-Trivia (General Knowledge ist schwach),
   veraltenden Fragen („aktueller …"), mehrdeutigen, faktisch schiefen, und solchen,
   die beim Übersetzen ihren Sinn verlieren (Wortspiele wie „Stern/Heck").
4. **Übersetzen:** EN → DE, Frage und alle 4 Optionen, auf Deutsch eindeutig.
   Richtige Antwort an Index 0, `"c": 0`.
5. **Dedup:** gegen vorhandene Fragen prüfen (Vergleich über `q_en`).
6. **Lizenz:** OpenTDB = **CC BY-SA 4.0**. `_meta.source`/`_meta.license` belassen
   und die Namensnennung in `DOCS.md` (Abschnitt „Credits") nicht entfernen.

## Pflicht: nach jeder Änderung validieren

Im Ordner `mypage/` ausführen (`PYTHONUTF8=1`):

```python
import json, collections
d=json.load(open('data/quiz_pool.json',encoding='utf-8'))
cats=set(d['categories']); qs=d['questions']
errs=[]
seen=set()
for i,q in enumerate(qs):
    if q['cat'] not in cats: errs.append(f'{i}: cat unbekannt {q["cat"]}')
    if q['diff'] not in ('easy','medium','hard'): errs.append(f'{i}: diff {q["diff"]}')
    for k in ('q_de','q_en','opts_de','opts_en'):
        if not q.get(k): errs.append(f'{i}: {k} fehlt')
    if len(q.get('opts_de',[]))!=4 or len(q.get('opts_en',[]))!=4: errs.append(f'{i}: !=4 Optionen')
    if len(set(q.get('opts_de',[])))!=4: errs.append(f'{i}: doppelte Option (de)')
    if not (0<=q.get('c',-1)<=3): errs.append(f'{i}: c ausserhalb 0-3')
    key=q['q_en']
    if key in seen: errs.append(f'{i}: Dublette {key[:40]}')
    seen.add(key)
print('FEHLER:', errs or 'keine')
# Verteilung + Board-Tauglichkeit (pro Kategorie 2 easy /1 med /2 hard)
for cat in d['categories']:
    c=collections.Counter(q['diff'] for q in qs if q['cat']==cat)
    boards=min(c['easy']//2, c['medium']//1, c['hard']//2)
    print(f'{cat:10} e{c["easy"]} m{c["medium"]} h{c["hard"]}  -> ~{boards} Board(s)')
usable=sum(1 for cat in d['categories'] if sum(1 for q in qs if q['cat']==cat)>=5)
print('nutzbare Kategorien (>=5 Fragen):', usable, '(>=6 noetig)')
```

Alles muss „FEHLER: keine" zeigen und es müssen **≥ 6 nutzbare Kategorien** existieren.

## Projekt-Konventionen (für den Maintainer)

- Reine Daten-Erweiterung (nur `quiz_pool.json`) braucht **keinen** Versions-Bump.
- Commit auf den **`dev`**-Branch, nie direkt `main`.
- Spiel-Engine, Template, Routen NICHT anfassen – nur die JSON.
