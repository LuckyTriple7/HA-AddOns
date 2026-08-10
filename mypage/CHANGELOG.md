# Changelog

## 0.10.20
- 📥 **Vorhandene Texte lassen sich ins Studio holen.** Bisher ging es nur in eine Richtung: erzeugen und übernehmen. Wer einen alten Beitrag überarbeiten, ihm die englische Fassung nachziehen oder eine SEO-Beschreibung nachtragen wollte, musste kopieren. Die Auswahl oben im Text-Studio listet **alle Blogbeiträge, Projekte und Bibliothek-Einträge**; „Laden" füllt die Ergebnisfelder, Textart und Sprachwahl stellen sich passend ein.
- 🔒 **Das Original bleibt unangetastet.** Zurückgeschrieben wird erst über „Übernehmen", und dabei entsteht ein neuer Eintrag — der alte wird nicht ersetzt. Ein geöffneter Entwurf wird beim Laden gelöst, damit Speichern nichts Fremdes überschreibt; „↶ Vorherige Fassung" macht das Laden rückgängig.
- ⚠️ Nicht ganz verlustfrei: ein **Projekt hat nur einen Titel** für beide Sprachen, der steht danach in beiden Titelfeldern.

## 0.10.19
- 💾 **Prompt-Bibliothek im Bild-Studio.** Das Text-Studio kann Entwürfe speichern, das Bild-Studio konnte es nicht — ein mühsam zurechtgefeilter Prompt war nach dem Neuladen weg. **„Prompt speichern"** legt Beschreibung, Anzahl, Seitenverhältnis und Vorlagenbild unter einem Namen ab, **„📂 Übernehmen"** holt alles zurück ins Studio. Ohne Namen werden die ersten Wörter genommen; derselbe Name überschreibt den Eintrag, statt eine zweite Zeile anzulegen.
- 🗄️ Gespeichert wird in einer eigenen Datei `ai_prompts.json` im Add-on-Konfigurationsordner, höchstens 100 Einträge, **im Backup und in der Wiederherstellung enthalten**.
- 🧹 **Ein in der Bibliothek hinterlegtes Vorlagenbild gilt als benutzt** und wird von „Speicher aufräumen" nicht mehr als verwaist gelöscht.

## 0.10.18
- 💰 **Was der nächste Lauf kostet, steht jetzt unter dem Knopf.** Bisher sah man den Preis erst hinterher im Verbrauchs-Bereich. Bild-Studio und Logo-Designer zeigen „≈ 0,16 $ für 4 Bilder", das Text-Studio eine Schätzung samt genannter Annahme („bei rund 800 Wörtern Ausgabe") — abgerechnet wird nach Tokens, die vorher niemand kennt, und eine nackte Zahl wäre hier eine erfundene.
- 🔁 Die Anzeige rechnet **live** mit: Länge, Sprachen, Thema, Modellwechsel und Bildanzahl schlagen sofort durch. Gerechnet wird mit denselben Preisen wie im Verbrauchs-Bereich, eigene Werte schlagen die Vorgaben. Ist für ein Modell kein Preis hinterlegt, steht dort der Hinweis statt einer Zahl.

## 0.10.17
- 📐 **Seitenverhältnis steht jetzt im Bild-Studio**, direkt neben „Anzahl". Bisher lag es nur oben in den Einstellungen: zum Wechseln musste man hochscrollen und speichern, obwohl es bei jedem Lauf einzeln mitgeschickt wird. Beide Felder zeigen denselben Wert und ziehen einander nach; dauerhaft gespeichert wird er weiterhin nur oben.
- ↻ **„Variation" an gespeicherten Bildern.** Ein Klick setzt das Bild als Vorlage und startet sofort einen neuen Lauf mit derselben Beschreibung — statt „Als Vorlage", hochscrollen, „Erzeugen". Nur an gespeicherten Bildern, ein Entwurf hat noch keine taugliche Adresse.
- ↶ **„Vorherige Fassung" im Text-Studio.** Ein zweiter Lauf, eine Überarbeitung oder ein geöffneter Entwurf haben die Felder bisher still überschrieben. Der Knopf holt den Stand davor zurück und führt mit demselben Klick wieder vorwärts. Eine Stufe, nur in der geöffneten Seite — nichts wird gespeichert.
- 🔎 **Suche und Sortierung in der Entwurfsliste.** Ab fünf Entwürfen erscheinen ein Suchfeld (Name und Textart) und die Sortierung nach neueste / älteste / Name A–Z. Reine Anzeige, ohne weiteren Aufruf.

## 0.10.16
- 🗂️ **Übernehmen richtet sich jetzt nach der Textart.** Das Studio kennt fünf Textarten, konnte das Ergebnis aber nur an den Blog weiterreichen — eine Projektbeschreibung musste man von Hand hinüberkopieren. Neu: **„Als Projekt übernehmen"** (SEO-Beschreibung wird Kurzbeschreibung, Fließtext die lange, unveröffentlicht), **„Als Bibliothek-Eintrag übernehmen"** (unsichtbar geschaltet) und bei „nur SEO" **„In die Website-SEO übernehmen"**, das die Beschreibung in beide Felder im Design-Tab einträgt und dorthin springt — gespeichert wird sie dort mit „Speichern". Der Weg zum Blogbeitrag bleibt immer offen, veröffentlicht wird auf keinem Weg automatisch.
- ✂️ **Überarbeiten statt neu erzeugen.** Bisher gab es nur „nochmal", und das warf jede Handarbeit im Formular weg. Unter dem Ergebnis stehen jetzt **„Kürzer"**, **„Länger"**, **„Feinschliff"** und ein freies Feld für einen eigenen Änderungswunsch. Der vorhandene Text geht mit in die Anfrage und kommt vollständig überarbeitet zurück.
- 🇩🇪 **Eine einzelne Sprache überarbeiten.** Die Auswahl „Beide / Nur Deutsch / Nur Englisch" erzeugt nur die gewählte Fassung neu; die andere bleibt unangetastet — ein Korrekturlauf kostet damit die Hälfte. Maßgeblich ist, was wirklich in den Feldern steht: ohne englischen Text gibt es auch nichts auf Englisch zu kürzen.
- 📌 **„Immer beachten" — Dauervorgaben für jeden Text.** Ein Feld in den KI-Einstellungen (bis 800 Zeichen), dessen Inhalt bei jedem Textlauf mitgeht, auch beim Überarbeiten: „Leser duzen", „keine Emojis", „Produktname immer als MyPage schreiben". Leer lassen schaltet es ab.

## 0.10.15
- 📁 **Vorhandene Logo-Sätze klappen jetzt zusammen.** Jeder Satz zeigte alle Vorschaubilder auf einmal — bei mehreren Sätzen war der Logo-Designer damit endlos lang. Zu sehen ist nun je Satz eine Zeile mit Name, Dateizahl und den Knöpfen „Alle als ZIP", „Größen neu rechnen" und „Löschen"; ein Klick auf den Namen zeigt die Dateien, ein zweiter versteckt sie wieder.
- 🔓 **Frisch gespeicherte, eingelesene und neu gerechnete Sätze klappen von selbst auf** — das Ergebnis will man sofort sehen. Welche Sätze offen sind, bleibt auch dann erhalten, wenn sich die Liste zwischendurch neu aufbaut.

## 0.10.14
- ↺ **„Zurücksetzen" im KI-Tab — in allen drei Studios.** Wer einen gespeicherten Entwurf geöffnet hatte und danach etwas Neues anfangen wollte, kam bisher nur über das Neuladen der Seite (Strg+R) zu leeren Feldern zurück. Der neue Knopf steht jeweils direkt neben „Erzeugen".
- 📝 **Text-Studio:** leert Thema, Titel, SEO-Beschreibung, beide Textfassungen, Schlagwörter und den Entwurfsnamen und stellt Textart, Tonfall, Länge, Sprachen und Schreibweise auf die Vorgaben zurück. Ein geöffneter Entwurf wird gelöst, damit das nächste Speichern nicht den alten Eintrag überschreibt.
- 🖼️ **Bild-Studio:** leert Beschreibung, Anzahl und Vorlagenbild. 🏷️ **Logo-Designer:** zusätzlich Name, freies Maß, Zielformate und Freistellen zurück auf den Ausgangszustand.
- 🔒 **Gelöscht wird dabei nichts** — gespeicherte Entwürfe, die erzeugten Bilder im Ergebnis-Streifen und fertige Logo-Sätze bleiben stehen. Stehen noch Eingaben im Formular, fragt der Knopf vorher nach.

## 0.10.13
- 💾 **Das Text-Studio kann Entwürfe speichern.** Bisher lebte ein erzeugter Text nur im Formular: ein zweiter Durchgang, ein Tabwechsel oder das Neuladen der Seite haben ihn ersatzlos verworfen — bezahlt war der Aufruf trotzdem. Neu unter dem Ergebnis: **„💾 Entwurf speichern"** mit Namensfeld (leer = der Titel wird genommen) und darunter die Liste **„Gespeicherte Entwürfe"** mit Textart, Sprachen, Zeichenzahl und Datum. **„Öffnen"** holt alles zurück ins Studio, **„Löschen"** entfernt den Eintrag.
- 🔁 **Mitgespeichert werden auch die Eingaben** — Thema, Textart, Tonfall, Länge, Sprachen und die Wahl „eigenständig schreiben / übersetzen". Ein geöffneter Entwurf lässt sich damit ohne Abtippen neu erzeugen, etwa mit einem anderen Modell oder Tonfall.
- ♻️ Solange ein Entwurf geöffnet ist, **überschreibt** Speichern genau diesen Eintrag, statt bei jedem Klick eine weitere Kopie anzulegen; der Merker „geöffnet" steht in der Liste. **„✕ Lösen"** beendet die Verbindung — danach entsteht beim nächsten Speichern ein neuer Eintrag.
- 🗄️ Entwürfe liegen in einer **eigenen Datei** `ai_drafts.json` im Add-on-Konfigurationsordner (nicht in `site.json`, die bei jedem Admin-Speichern komplett neu geschrieben wird) und sind **im Backup und in der Wiederherstellung enthalten**. Höchstens 200 Entwürfe, danach fällt der jeweils älteste heraus. Öffentlich wird davon nichts: ein Entwurf erscheint weder im Blog noch in Suche oder Feed, bis er über „Als Blogbeitrag übernehmen" ein Beitrag wird und dort veröffentlicht wird.

## 0.10.12
- 🛡️ **Dieselbe CodeQL-Meldung, dritter Anlauf — jetzt ohne Umweg.** Der Fehlercode des Preiskatalogs gilt als aus Googles Antwort stammend, und die Markierung überlebt jede Weiterverarbeitung: weder das Nachschlagen im Wörterbuch (0.10.10) noch das Holen aus einer Konstantenliste (0.10.11) hat sie abgestreift. Jetzt wird gar kein Wert mehr übergeben, sondern die Meldung ausgewählt — im Log steht nur noch fester Text („Abrechnung im Google-Projekt nicht aktiviert", „Schlüssel zurückgewiesen", „kein passender Dienst im Katalog"). Aussagekräftiger als der Code ist es obendrein. Code und Klartextgrund bekommt der Admin unverändert in der Antwort.

## 0.10.11
- 🛡️ **Nachtrag zu 0.10.10:** Eine der fünf CodeQL-Meldungen kam wieder — der Fehlercode des Preiskatalogs steht selbst unter Verdacht. Er entsteht durch Nachschlagen mit einem Schlüssel aus Googles Antwort, und die kam auf eine Anfrage mit dem Abrechnungs-Schlüssel; damit gilt auch das Nachschlage-Ergebnis als aus der Antwort stammend, obwohl es nur eines von vier festen Wörtern sein kann. Der Code wird jetzt vor dem Loggen aus einer festen Liste geholt statt aus der Variablen — nachweislich eine Konstante, und ein unbekannter Code landet als `unbekannt` im Log statt ungeprüft.

## 0.10.10
- 🛡️ **Fünf CodeQL-Meldungen behoben.**
  - **Pfad aus einem Anfragewert (2×, `py/path-injection`):** Die Spielregeln wurden aus `game_<spiel>_rules_<sprache>.md` zusammengesetzt, und die Sprache kommt seit 0.10.9 auch aus `?lang=` in der Adresszeile — also direkt vom Aufrufer in einen Dateinamen. Die Sprache wird jetzt auf eines von zwei festen Kürzeln zurückgeführt, bevor sie einen Pfad berührt, und der Pfad zusätzlich über `safe_join` gebaut. Ein Wert wie `?lang=../../etc/passwd` landet damit auf den deutschen Regeln statt irgendwo im Dateisystem.
  - **Antwortdaten des Abrechnungs-Katalogs im Log (3×, `py/clear-text-logging-sensitive-data`):** Der Abruf der Google-Preise geht mit dem Abrechnungs-Schlüssel raus; alles, was zurückkommt, gilt damit als schutzbedürftig. Aus dem Log fliegen die gelesenen Dienstnamen und Googles Klartext-Begründung. Zu sehen ist beides weiterhin — es steht im Preise-Bereich des Admin, wo es hingehört, statt in einer Datei, die beim Support-Fall mitgeschickt wird.
- Am Verhalten ändert sich nichts: Spielregeln laden weiter in beiden Sprachen (alle neun Spiele geprüft), und die Preisabfrage meldet Fehler unverändert im Admin.

## 0.10.9
- 🌍 **Suchmaschinen bekamen auf einer deutschen Seite die englische Fassung.** Ohne Sprach-Cookie entschied bisher die Kopfzeile `Accept-Language` — und Googlebot schickt keine. Der Rückfall lautete `en`, also sah Google `<html lang="en">`, englischen Titel und englische Beschreibung, und bewertete die Seite entsprechend für deutsche Suchanfragen. Neu: **Standardsprache der Website** unter *Design* (Vorgabe **Deutsch**). Die Reihenfolge lautet jetzt `?lang=` → Cookie → Einstellung; die Browser-Einstellung entscheidet nur noch, wenn die Einstellung ausdrücklich auf *Automatisch* steht.
  - Besucher schalten weiter über die Sprachumschaltung um, und die Wahl bleibt im Cookie gespeichert. Wer das alte Verhalten will, stellt *Automatisch* ein — dann bleibt aber der Suchmaschinen-Nachteil.
- 🔗 **`<link rel="canonical">` gab es auf keiner einzigen Seite.** Jetzt auf allen indexierbaren öffentlichen Seiten, **ohne Filter- und Suchparameter**: `/blog`, `/blog?tag=x` und `/blog?q=y` melden alle `/blog` als die eine richtige Adresse, statt die Signale auf drei fast gleiche Seiten zu verteilen.
- 🈯 **`hreflang`-Angaben** verbinden die deutsche und die englische Fassung jeder Seite (`?lang=de` / `?lang=en`, dazu `x-default`). Damit ist beiden Fassungen eine feste Adresse zugeordnet — vorher gab es überhaupt keine, unter der sich eine bestimmte Sprache verlässlich abrufen ließ.
- 🧊 **`Vary: Cookie` und `Content-Language` fehlten.** Ohne `Vary` darf jeder Zwischenspeicher — nginx, Cloudflare, ein Firmen-Proxy — die erste Fassung, die durch ihn hindurchgeht, für alle festhalten. Bei zwei Sprachen auf derselben Adresse hieß das: kommt der Suchmaschinen-Roboter zuerst, sehen danach auch Besucher dessen Fassung. Steht die Standardsprache auf *Automatisch*, kommt zusätzlich `Vary: Accept-Language` dazu.
- Hinweis zu „Gefunden – zurzeit nicht indexiert" in der Search Console: Das heißt, dass Google die Adresse kennt, aber noch nicht abgerufen hat — eine Entscheidung von Google, kein Fehler der Seite. Die Punkte oben nehmen ihr die technischen Gründe; erzwingen lässt sich die Indexierung nur über *URL-Prüfung → Indexierung beantragen*. Am meisten bringt das für `/blog`, weil erst diese Seite alle Beiträge verlinkt.

## 0.10.8
- 🔒 **Mitglieder-only-Beiträge standen ungefiltert im RSS-Feed.** Der Feed prüfte die Sperre gar nicht und lieferte jedem 300 Zeichen des Textes — bei kurzen Beiträgen also alles. Die Website zeigt Gästen an derselben Stelle höchstens die *halbe* Textlänge. Jetzt stehen gesperrte Beiträge, Reisen und Bibliothek-Einträge mit Titel und Adresse im Feed, aber ohne Text und ohne Bild; an der Stelle des Anrisses steht der Hinweis auf die Anmeldung.
- 🐛 **`&` erschien im Feed als `&amp;`.** Der Text wurde zweimal maskiert: einmal beim Markdown-Rendern, einmal beim Zusammenbauen des XML. Aus „Rum & Cola" wurde im Reader wörtlich „Rum &amp;amp; Cola". Betraf auch die **Meta-Descriptions** der Seiten — dieselbe Hilfsfunktion, derselbe Fehler.
- 🐛 **Spitze Klammern im Text verschwanden.** Der Ausdruck zum Entfernen der HTML-Tags fraß alles zwischen `<` und `>`; aus „Platzhalter `<Name>` einsetzen" wurde „Platzhalter einsetzen". Jetzt werden nur die Tags entfernt, die tatsächlich aus dem Markdown stammen.
- 📰 **Der Feed enthält jetzt Reisetage** — bisher nur Blogbeiträge. Projekte und Bibliothek-Einträge lassen sich unter *Design* einzeln zuschalten; sie ändern sich selten und würden den Feed beim Einschalten einmalig mit Altbestand fluten. Projekte erscheinen nur mit Detailseite und ohne Datum, also am Ende.
- 🖼️ **Volltext, Bild und Schlagwörter im Feed.** Neu je Eintrag: `<content:encoded>` mit dem ganzen Beitrag (Bild- und Link-Adressen absolut), `<enclosure>` mit dem Titelbild und `<category>` je Schlagwort. Statt eines mitten im Wort abgeschnittenen Anrisses steht jetzt die gepflegte SEO-Beschreibung im `<description>`, sonst ein an der Wortgrenze gekürzter Auszug.
- 🌍 **Die Feed-Sprache ist einstellbar** (*Design → Sprache des RSS-Feeds*) statt vom Browser des Abrufers abzuhängen. Ein Feed-Leser holt dieselbe Adresse für alle seine Nutzer und schickt meist gar keine Sprachkennung — bisher entschied das den Inhalt. Die andere Fassung gibt es unter `/feed.xml?lang=en`.
- 🕛 **Zeitstempel auf 12:00 UTC** statt Mitternacht: bei `00:00` stand ein Beitrag für jeden Leser westlich von Greenwich unter dem **Vortag**. Mehrere Einträge desselben Tages werden um je eine Minute versetzt, damit ihre Reihenfolge im Reader feststeht.
- ⚡ **`ETag` und `Cache-Control`**: ein unveränderter Feed kommt als `304` zurück statt jedes Mal komplett.
- 📭 **Ohne Beiträge liefert der Feed einen gültigen leeren Feed statt 404.** Ein 404 heißt für einen Reader „kaputt", und manche tragen einen so gemeldeten Feed dauerhaft aus. Aus demselben Grund ist der Feed jetzt **immer** im Seitenkopf verlinkt.
- Dazu die üblichen Kanal-Angaben, die bisher fehlten: `<language>`, `<lastBuildDate>`, `<atom:link rel="self">`, `<generator>`, `<ttl>`, Kanal-Logo und Herausgeber.

## 0.10.7
- 🎚️ **Ein abgeschaltetes Modul verschwindet jetzt auch aus dem Admin.** Stehen **Reiseblog** oder **Formulare** unter *Design → Module* auf NEIN, sind nicht mehr nur Abschnitt, Navi-Einträge und Seiten auf der Website weg — es verschwinden auch der **Reiter** und der **Abschnitt unter *Inhalte***. Bisher pflegte man dort weiter Inhalte, die nirgends ankamen, und der Schalter blieb für alles folgenlos, was man täglich sieht.
  - **Nichts wird gelöscht.** Reisen, Tage, Formulare und eingegangene Antworten bleiben gespeichert; auch **Position und Augen-Zustand** des Abschnitts bleiben erhalten und kommen beim Einschalten unverändert zurück.
  - Wer gerade auf einem Reiter steht, den er abschaltet, landet automatisch wieder im Design-Tab.
  - **Zum Vorbereiten muss der Schalter nicht aus:** ein Reisetag ohne „veröffentlichen" und ein Formular ohne „aktiv" gehen ohnehin nicht online. Die Hinweistexte an beiden Schaltern sagen das jetzt.
  - Zu beachten: **Werkseinstellung des Reiseblogs ist NEIN** — sein Reiter erscheint also erst, wenn er unter *Design → Module* eingeschaltet wird.

## 0.10.6
- 🏷️ **Logo-Designer im KI-Tab.** Erzeugt fertige Logo-Sätze in exakten Pixelmaßen: Home-Assistant-Add-on (`icon.png` 256×256, `logo.png` 250×100), PWA (`icon-192`, `icon-512`, `apple-touch-icon`), Favicon (`favicon.ico` mit 16/32/48 in einer Datei) und Link-Vorschaubild (`og-image.png` 1200×630). Dazu ein freies Maß von 16 bis 4096 px.
  - **Die Maße rechnet MyPage, nicht die KI.** Gemini kennt nur Seitenverhältnisse — der Entwurf entsteht quadratisch und wird je Ziel zugeschnitten und mittig eingepasst. Die Vorlage bleibt als `source.png` liegen, weitere Größen lassen sich später **ohne neuen KI-Aufruf** nachziehen.
  - **Eigener Ablageort:** `logos/<name>/` im Add-on-Konfigurationsordner, also direkt über den Share erreichbar — nicht bei den Uploads. Dort würde aus jedem Logo ein WebP mit höchstens 1600 px **und** eingebrannter KI-Kennzeichnung; beides macht ein Logo unbrauchbar. Die Herkunft steht stattdessen unsichtbar in den PNG-Textfeldern und in `prompt.txt`.
  - **Hintergrund freistellen** (Standard an, vier Stufen): entfernt den vom Bildrand aus zusammenhängenden einfarbigen Grund. Geschlossene Flächen im Motiv — das Auge eines Maskottchens, die Fläche in einem „O" — bleiben erhalten.
  - **Auch ohne Gemini-Schlüssel nutzbar:** „Eigenes Bild einlesen" schickt ein vorhandenes Bild durch dieselbe Aufbereitung. Damit lassen sich zu einem längst gezeichneten Icon die fehlenden Größen nachziehen. Ohne Schlüssel zeigt der KI-Tab nur noch dieses eine Panel.
  - Herausholen per Einzeldownload, als ZIP über den ganzen Satz — oder gar nicht, weil die Dateien ohnehin im Share-Ordner liegen. Logo-Sätze sind **Teil des Backups**.

## 0.10.5
- 💶 **Ausgaben stehen jetzt im Tagesbericht** — Kategorie, Zweck und Betrag als Aufstellung, darunter die Summe. Auf der Reise-Seite zusätzlich die Summe der ganzen Reise. Getrennt je Währung, nicht umgerechnet: ein geratener Wechselkurs wäre eine erfundene Zahl. Nur veröffentlichte Tage zählen mit — sonst stünde dort ein Betrag, den kein sichtbarer Tag erklärt.
  - Gesteuert vom vorhandenen Schalter **„Preise im Bericht nennen"** je Reise. Wer der KI verbietet, über Geld zu schreiben, will es auch nicht als Tabelle auf derselben Seite haben.
- 🌦️ **Die Auswahllisten sind übersetzt.** Wetter, Wind, Art des Erlebnisses, Empfehlung, Verkehrsmittel, Mahlzeit, Kategorie des Moments und der Ausgabe standen auf Englisch bisher **auf Deutsch** da — im Admin wie im Tagesbericht. Gespeichert wird weiterhin der deutsche Klartext, weil er Teil des Prompts ist; übersetzt wird nur die Beschriftung.
- 🖼️ **Eigene Bildunterschrift je Foto** im Wizard-Schritt *Fotos*. Sie schlägt die der KI — und ist der einzige Weg, ein Foto **ohne Hinweis** zu beschriften: für die schreibt die KI gar keine.
- 📋 **Formulare haben einen Abschnitt auf der Startseite.** Er lässt sich unter *Inhalte* einsortieren und ausblenden wie jeder andere. Steht er in der Navigationsleiste, entfallen dort die einzelnen Formular-Links — sonst stünde erst „Formulare" und daneben nochmal jedes einzelne.
- 🔧 **Der Schalter *Formulare* unter Design → Module wirkte nicht.** Er sollte die Formulare auf der Website ein- und ausblenden, wurde öffentlich aber nirgends abgefragt: die Seiten unter `/formular/…` blieben erreichbar und die Navi-Einträge stehen. Jetzt greift er — auch für das Absenden.
- ✳️ **Pflichtfelder im Reise-Wizard sind mit `*` gekennzeichnet** (Reisetag und Datum). Der Satz „Nur diese beiden Felder sind Pflicht" stand unter vier Feldern, ohne zu verraten, welche beiden gemeint waren.

## 0.10.4
- 🌍 **Der Reiseblog ist jetzt öffentlich sichtbar.** Drei neue Seiten: die Übersicht aller Reisen (`/reiseblog`), die Tage einer Reise (`/reiseblog/<reise>`) und der Tagesbericht selbst (`/reiseblog/<reise>/<tag>`) — aufgebaut wie die Bibliothek, mit Bildergalerie, Blättern zwischen den Tagen, SEO-Angaben und Druckansicht.
- 🔒 **Nichts steht ungefragt im Netz.** Ein Tag erscheint erst mit dem Haken **„Tag veröffentlichen"** im letzten Wizard-Schritt — und auch dann nur, wenn er einen Bericht hat. Eine freigegebene Seite ohne Text wäre eine Seite mit Datum und sonst nichts.
- 🏷️ **Reisen und Tage haben feste Adressen.** Die Adresse einer Reise lässt sich im Reise-Dialog frei wählen; leer gelassen wird sie aus dem Namen gebildet. Einmal vergeben bleibt sie bestehen, auch wenn die Reise später umbenannt wird — sonst führte jeder geteilte Link ins Leere.
- 👥 **Eine Reise kann auf Mitglieder beschränkt werden.** Die Sperre gilt für die ganze Reise: Titel und Anrisstexte bleiben sichtbar, die Berichte nicht. Eine Reise halb zu zeigen ergäbe eine Geschichte mit Löchern.
- 🏠 **Der Abschnitt auf der Startseite ist damit aktiv** — sichtbar, sobald der Reiseblog freigegeben ist und mindestens ein Tag veröffentlicht wurde. Position und Sichtbarkeit wie gehabt unter *Inhalte*.
- 🔎 **Sitemap, Volltextsuche, IndexNow und der statische Export** kennen den Reiseblog jetzt ebenfalls; Entwürfe bleiben in allen vier Fällen außen vor.
- 👁️ **Vorschau je Reisetag** im Reiter *Reiseblog* — zeigt auch noch nicht freigegebene Tage, damit man vor dem Veröffentlichen sieht, was tatsächlich herauskommt.
- 🖼️ **Bildunterschriften hingen am falschen Foto**, sobald ein Foto ohne Hinweis dazwischenlag: die KI schreibt nur zu Fotos **mit** Hinweis eine Unterschrift, zugeordnet wurde aber über die volle Fotoliste. Betrifft die Anzeige im Wizard und jetzt auch die öffentliche Galerie.
- Bei zweisprachigen Reisen lassen sich die Bildunterschriften jetzt in **beiden Sprachen** bearbeiten — vorher nur auf Deutsch.

## 0.10.3
- 🗂️ **Die Reiter *Reiseblog* und *Formulare* sind jetzt immer sichtbar.** Die Schalter unter Design steuern ab sofort die **Website**, nicht den Reiter — sonst liesse sich nichts vorbereiten, bevor der Bereich online geht.
- 🧭 **Formulare stehen jetzt ebenfalls unter *Inhalte*** und lassen sich dort einsortieren und ausblenden, genau wie der Reiseblog.
- 💾 **Ein gescheitertes Speichern im Reiseblog blieb unbemerkt.** Drei Stellen konnten still versagen und einen eingetippten Tag verlieren, während die Oberfläche nichts oder sogar „Gespeichert“ meldete:
  - Ein **Schreibfehler auf der Platte** wurde nur ins Log geschrieben, die Antwort lautete trotzdem „ok“. Jetzt meldet der Server einen Fehler.
  - Ein **Netzfehler** (Add-on gerade neu gestartet, WLAN weg) löste gar keine Meldung aus. Jetzt bleibt der Dialog offen, es erscheint eine rote Meldung, und der lokale Entwurf bleibt ausdrücklich liegen.
  - Eine **abgelaufene Anmeldung** sah aus wie ein beliebiger Fehler. Jetzt steht da, dass man sich neu anmelden und dann erneut speichern soll.
- Die Rückfrage nach einem gespeicherten Zwischenstand kommt nur noch, wenn der Entwurf überhaupt Inhalt hat.

## 0.10.2
- 🖥️ **Das Admin-Panel nutzt jetzt die Breite des Fensters.** Die Arbeitsfläche war auf 1100 px festgenagelt — auf einem breiten Bildschirm blieb links und rechts alles leer, während Tabellen, Kachelraster und der Reise-Wizard unnötig scrollten. Nach oben bei 1900 px gedeckelt, damit Textzeilen nicht unlesbar lang werden.
- Große Dialoge (Markdown-Editor, Reise-Wizard) wachsen mit bis 1400 px, normale Dialoge bis 760 px — jeweils höchstens 94 % der Fensterbreite, damit auf dem Handy nichts übersteht.

## 0.10.1
- ⚙️ **Reiseblog und Formulare lassen sich ab- und anschalten** (Design → Module). Ein Reiter, der zu einem ungenutzten Modul gehört, ist nur Ballast. Der Reiseblog startet **aus**, Formulare bleiben **an**, damit bestehende Installationen ihren Reiter behalten.
- 🧭 **Der Reiseblog lässt sich unter *Inhalte* einsortieren und ausblenden** wie jeder andere Abschnitt. Auf der Startseite erscheint er erst mit den öffentlichen Seiten — bis dahin wäre die Sprungmarke ein Verweis ins Leere.
- 📅 **Datumsfelder zeigen wieder einen Kalender.** Ohne `color-scheme` zeichnete der Browser Symbol und Auswahlfenster hell auf dunklem Grund — das Kalendersymbol war praktisch unsichtbar. Betrifft auch Beitragsdatum und Countdown.
- Das Sinnbild am Reiter *Reiseblog* ist weg.

## 0.10.0
- 🧳 **Neues Modul Reiseblog** (Tab *Reiseblog*). Unterwegs ein paar Stichpunkte erfassen — den Tagesbericht schreibt die KI daraus. Bewusst getrennt vom normalen Blog, mit eigenem Datenmodell und eigener Speicherung.
- **Wizard mit acht Schritten** statt eines langen Formulars: Tag & Ort, Wetter, Erlebnisse, Essen, Eindrücke, Momente & Ausgaben, Fotos & Notizen, Bericht. **Pflicht sind nur Tagesnummer und Datum.** Leere Felder tauchen im Prompt gar nicht erst auf — sonst stünde dort „Wetter: —“ und das Modell dichtet etwas dazu.
- **Schreibvorgaben je Reise** (Stil, Perspektive, Länge, Humor, Sprache, ob Preise, praktische Hinweise und Bewertungen genannt werden) — einmal einstellen, gilt für alle Tage.
- Erzeugt **Titel, Anrisstext, Fließtext, Schlagwörter und Bildunterschriften**, auf Wunsch **deutsch und englisch in einem Durchgang**. Alles danach frei editierbar.
- Die **vorherigen Reisetage** gehen als Kurzfassung mit in den Prompt, damit sich die Berichte nicht wiederholen.
- **Zwischenstand wird laufend lokal gesichert.** Erfasst wird das unterwegs im Hotel-WLAN; ein Verbindungsabbruch nach zwanzig Minuten Tippen soll die Eingabe nicht kosten.
- Eigene Datei **`travel.json`**, im Backup und in der Wiederherstellung enthalten. Wichtig dabei: **Aufräumen und Löschschutz lesen sie mit** — sonst hätte „Speicher aufräumen“ jedes Reisefoto für verwaist gehalten und gelöscht.
- Noch **nicht öffentlich sichtbar**: die Berichte entstehen und werden im Admin verwaltet, die öffentlichen Seiten folgen als nächster Schritt.

## 0.9.20
- 🔍 **Fehlgeschlagene KI-Anfragen sagen jetzt, woran es lag.** Im Add-on-Log stand der Grund längst (`PROHIBITED_CONTENT`, „enthielt kein Bild“), im Admin kam nur „Die Anfrage ist fehlgeschlagen“ an. Googles Abbruchgrund steht jetzt **in der Oberfläche**.
- Liefert Gemini statt eines Bildes eine **Erklärung im Text** — der häufigste Fall bei einer stillen Absage — wird sie angezeigt statt weggeworfen. Genau daran erkennt man, welches Wort in der Beschreibung gestört hat.
- Der Fall „200, aber kein Bild“ hatte in der Oberfläche **gar keine eigene Meldung** und fiel auf den allgemeinen Fehlertext zurück. Er hat jetzt einen: die Beschreibung wurde vermutlich als unzulässig eingestuft, ohne dass es als Ablehnung gemeldet wird.
- Das Log nennt zusätzlich `finish_reason` und `block_reason` — beide fehlten bisher genau in dem Zweig, in dem sie gebraucht werden.
- Gilt für **Bild-Studio, Text-Studio und den Knopf im Bibliothek-Editor**. Letzterer hatte eine eigene, kürzere Fehlerliste und kannte den Fall gar nicht.

## 0.9.19
- 🗂️ **Neuer Datei-Browser im Tab *System*.** Zeigt alle hochgeladenen **Bilder** und die **PDFs der Bibliothek** mit Datum, Größe und der Plakette „unbenutzt“. Bisher liess sich nur im Rutsch aufräumen — sehen, was da liegt, ging gar nicht.
- **Linksklick öffnet** die Datei in einem neuen Tab. PDFs erscheinen dabei inline (mit `sandbox` und `nosniff`); öffentlich bleiben sie weiterhin reine Downloads.
- **Rechtsklick löscht**, nach Nachfrage. Bewusst das Kontextmenü: ein Fehlklick in einem Raster aus hunderten Kacheln darf keine Datei kosten. Eingebundene Dateien bleiben geschützt.
- ✨ **Kontrollkästchen „Nur KI-erzeugte Bilder“** — im neuen Browser und im Medien-Browser hinter jedem „Bild wählen“. KI-Kacheln tragen zusätzlich ein Sternchen.

## 0.9.18
- 🚫 **Ein nicht mehr existierendes Modell meldet sich jetzt als solches.** Wer noch einen Modellnamen aus einer früheren Version gespeichert hatte, bekam bei jeder Anfrage nur „Die Anfrage ist fehlgeschlagen“ — obwohl Google klar mit 404 antwortet. Die Meldung nennt jetzt den Namen und verweist auf die Einstellungen.
- Im Auswahlfeld wird ein gespeichertes Modell, das Google **nicht listet**, als „nicht in Googles Liste“ gekennzeichnet. Wählbar bleibt es — die Live-Abfrage kann ausfallen, dann soll die eigene Einstellung nicht verlorengehen — aber es ist nun erkennbar.
- Hintergrund: die Vorgabeliste enthielt bis v0.9.12 geratene Namen (`gemini-3-pro`, `gemini-3-flash`). Wer einen davon gespeichert hat, muss im Tab *KI* einmal ein gültiges Modell wählen und speichern.

## 0.9.17
- 💸 **Die Preis-Abfrage zog Sondertarife heran.** Google führt Stapelverarbeitung, zwischengespeicherte Eingaben, feinabgestimmte Modelle und Recherche-Aufschläge als eigene Posten — MyPage löst nichts davon aus. Ein solcher Posten als Normaltarif ergab eine Summe, die zu niedrig ist und deshalb nicht auffällt (im Test: 0,05 statt 0,90 je Mio. Eingabe-Tokens). Diese Zeilen bleiben jetzt draußen.
- Bleiben mehrere Kandidaten übrig, **gewinnt der höchste**. Unter dem Normaltarif zu liegen ist der gefährliche Irrtum — eine zu hohe Summe fällt auf, eine zu niedrige nicht.
- **Bildmodelle werden nur noch über den Posten je Bild befüllt.** Vorher konnte ein Token-Posten daneben landen und nach dem Speichern **doppelt** zählen — einmal je Bild aus der Vorgabe, einmal je Token aus dem Abruf.

## 0.9.16
- 🐞 **Die Preis-Abfrage trug Unsinn ein.** Sie prüfte zuerst auf „image“ und hielt damit „Gemini 3 Flash **Image Input** Tokens“ — den Aufschlag für ein Bild als *Eingabe* — für den Preis eines erzeugten Bildes. Ergebnis: jedes Textmodell bekam einen Bildpreis, und bei Bildmodellen überschrieb der falsche Wert die brauchbare Vorgabe.
- Erkannt wird jetzt in der richtigen Reihenfolge: **Ausgabe vor Eingabe vor Bild**. Posten mit Bild-, Video- oder Audio-*Eingabe* bleiben ganz draußen — Google rechnet sie getrennt ab, und die Preistabelle bildet diese Dimension nicht ab. Sie als Textpreis zu buchen wäre schlicht falsch.
- Bei **Bildmodellen** landen die Ausgabe-Tokens jetzt als Ausgabepreis statt als Preis je Bild. Google rechnet dort in Tokens, und die Verbrauchszählung führt für diese Modelle ebenfalls Ausgabe-Tokens — das rechnet sich von selbst zusammen.
- Ein eingetragener Preis ersetzt die Vorgabe jetzt **nur in der jeweiligen Spalte**. Vorher verlor man mit einem einzelnen Eintrag die Vorgabewerte der anderen Spalten — das Ergebnis wäre eine zu niedrige Summe gewesen, die niemandem auffällt.
- Kommt derselbe Posten mehrfach vor (Google führt Stufen und Regionen getrennt), gilt der erste Treffer statt des zufällig letzten.

## 0.9.15
- 🔎 **Die Preis-Abfrage fand den Dienst nicht.** Sie verglich den Namen im Preiskatalog buchstabengetreu mit „Generative Language API“ — wie Google den Dienst dort nennt, ist aber nirgends zugesichert. Gesucht wird jetzt unscharf nach „generative language“ und „gemini“, und **alle** passenden Dienste werden durchsucht statt nur des ersten.
- **„Nichts gefunden“ war zweideutig** und stand sowohl für „Dienst nicht gefunden“ als auch für „Dienst gefunden, aber keine Posten-Bezeichnung passte“ — zwei völlig verschiedene Ursachen. Die Meldungen sind jetzt getrennt und nennen die Zahlen: wie viele Dienste gelesen wurden bzw. welche Dienste durchsucht und wie viele Posten gefunden wurden.
- Passt keine Bezeichnung, zeigt der Tab jetzt **einen Auszug der echten Posten-Namen** von Google. Daran lässt sich erkennen, wie Google die Modelle benennt — statt vor einem „nichts gefunden“ ohne Anhaltspunkt zu stehen.

## 0.9.14
- ⬇ **„Preise bei Google abfragen“ ist zurück — jetzt mit eigenem Schlüssel.** In v0.9.13 hatte ich den Knopf entfernt in der Annahme, der Preiskatalog von Google Cloud nehme nur OAuth. Das war falsch: er akzeptiert sehr wohl einen API-Schlüssel — nur nicht den aus AI Studio, denn der ist auf die Generative Language API beschränkt.
- Neue Option **`gemini_billing_key`**: ein zweiter Schlüssel aus einem Projekt, in dem die **Cloud Billing API** freigeschaltet ist. Ist er nicht gesetzt, bleibt der Knopf unsichtbar — er könnte ohne ihn nur scheitern.
- Die Dienstliste wird jetzt **vollständig durchgeblättert**. Vorher holte ein einzelner Aufruf die erste Seite; Google liefert mehrere tausend Dienste seitenweise, der gesuchte Eintrag wäre schlicht verfehlt worden.
- Treffer landen weiterhin **nur in den Feldern**, gespeichert wird erst auf Klick — Google beschreibt seine Posten im Fließtext, die Zuordnung zum Modell ist geraten.

## 0.9.13
- 💰 **Die Preistabelle deckt jetzt alle gängigen Gemini-Modelle ab** — 13 Einträge mit den Listenpreisen von [ai.google.dev/pricing](https://ai.google.dev/pricing), Textmodelle je Mio. Tokens, Bildmodelle je erzeugtem Bild. Damit rechnet die Kostenspalte für die üblichen Fälle ohne jede Eingabe.
- ❌ **Der Knopf „Preise bei Google abfragen" ist wieder raus.** Er sollte den Preiskatalog von Google Cloud anzapfen, aber der verlangt ein OAuth-Konto statt eines API-Schlüssels — mit einem Gemini-Key ist er nicht erreichbar. Der Weg war eine Sackgasse und kostete nur Einrichtungsschritte, die nichts brachten.
- Die Rückfall-Liste der Textmodelle nannte Namen, die es so nicht gibt (`gemini-3-pro`, `gemini-3-flash`); sie führt jetzt die tatsächlich gelisteten. Sie greift ohnehin nur, wenn die Live-Abfrage bei Google scheitert.

## 0.9.12
- 🔍 Die Preis-Abfrage hängt Googles Grund-Code jetzt an **jede** Fehlermeldung an, nicht nur an unbekannte. „Schlüssel abgelehnt" hat zwei Ursachen mit völlig verschiedenen Schritten — `API_KEY_INVALID` (Schlüssel taugt nicht) und `API_KEY_SERVICE_BLOCKED` (Schlüssel ist auf andere Dienste beschränkt). Ohne den Code war nicht zu erkennen, welche vorliegt.

## 0.9.11
- 🔍 **Die Fehlermeldung der Preis-Abfrage sagt jetzt die Wahrheit.** Bisher wurde *jeder* 403 von Google als „Cloud Billing API nicht freigeschaltet" gedeutet — auch „API-Keys werden von diesem Dienst nicht unterstützt". Wer der Meldung folgte, schaltete Dienste frei, die gar nicht das Problem waren.
- Ausgewertet wird jetzt ausschließlich der `reason` aus Googles Antwort. Neuer eigener Fall: **der Preiskatalog nimmt womöglich nur OAuth und keinen API-Schlüssel** — dann sagt die Meldung genau das und rät zur Eingabe von Hand, statt in die Irre zu führen.
- Unbekannte Gründe werden **im Klartext angehängt** (`Der Preiskatalog war nicht erreichbar. (REASON)`), statt hinter einer allgemeinen Meldung zu verschwinden.

## 0.9.10
- 💰 **Die Preistabelle ist vorbelegt.** Für bekannte Gemini-Modelle sind die Listenpreise von Google hinterlegt; sie stehen grau im Feld und werden gerechnet, ohne dass du etwas eintippen musst. Bisher blieb die Kostenspalte leer, bis man alles von Hand eingetragen hatte. Ein selbst eingetragener Wert schlägt die Vorgabe weiterhin.
- Die Vorgaben sind **bewusst unvollständig**: Google benennt Modelle laufend um, und ein geratener Preis wäre schlimmer als eine leere Zeile — die fragt nach, eine falsche Zahl nicht. Eine neue Spalte sagt je Modell, ob gerade *Vorgabe*, *eigener Wert* oder *kein Vorgabepreis* gilt.
- ⬇ **Neuer Knopf „Preise bei Google abfragen".** Holt die Posten aus dem öffentlichen Preiskatalog von Google Cloud und trägt die Treffer in die Felder ein — gespeichert wird erst mit „Speichern", denn Google beschreibt seine Posten im Fließtext und die Zuordnung zum Modell ist geraten. Braucht die **Cloud Billing API** im Google-Cloud-Projekt; ist sie aus oder der Schlüssel eingeschränkt, sagt die Meldung genau das.
- **Beträge jetzt in US-Dollar** statt Euro — Google weist seine Preise so aus, die Euro-Beschriftung war schlicht falsch.
- 🎨 Zahlen-, Datums- und Datum/Zeit-Felder waren im Admin **weiß statt dunkel**: die CSS-Regel führte nur `text`, `email` und `url` auf. Betraf neben der Preistabelle auch das Beitragsdatum und den Countdown-Zeitpunkt.

## 0.9.9
- 🎠 **Die Entwürfe im Bild-Studio stehen jetzt in einem waagerechten Streifen mit Pfeilen** statt in einem Raster. Bisher blieb jeder Durchgang untereinander stehen und schob Text-Studio und Verbrauch immer weiter nach unten — nach ein paar Versuchen war der Tab meterlang. Alle Entwürfe der Sitzung bleiben zum Vergleich erhalten, brauchen aber nur noch eine Zeile.
- **Neue Zeile darunter sagt, wie viele es sind** und wie viele davon schon gespeichert wurden. Vorher war nicht erkennbar, ob links noch etwas aus dem Bild gescrollt ist.
- 🗑 **Löschen-Knopf für gespeicherte Bilder.** Gefällt ein Bild nach dem Speichern doch nicht, ließ es sich bisher nur über *System → Speicher aufräumen* wieder entfernen — und auch das nur im Rutsch. Der Knopf sitzt jetzt direkt an der Karte.
  - **Eingebundene Bilder bleiben tabu**: steckt die Datei irgendwo in `site.json`, verweigert das Add-on das Löschen mit einem Hinweis, statt einem Beitrag oder Bibliothek-Eintrag das Bild unter den Füßen wegzuziehen. Geprüft wird mit demselben Vorkommen-Scan wie beim Aufräumen.

## 0.9.8
- 💶 **Verbrauchsanzeige im Tab *KI*.** Bisher gab es nur Stundenlimits — die verhindern Ausreißer, sagen aber nichts darüber, was der Monat gekostet hat. Jede Anfrage wird jetzt nach **Monat und Modell** festgehalten: Aufrufe, erzeugte Bilder sowie Ein- und Ausgabe-Tokens, direkt aus der Antwort von Google. Denk-Tokens zählen zur Ausgabe, weil sie so abgerechnet werden; abgelehnte und leere Antworten zählen mit, weil sie die Eingabe genauso kosten.
- **Preise trägst du selbst ein** (€ je Mio. Tokens rein/raus und € je Bild, je Modell) — daraus rechnet der Tab die Kosten je Modell und die Monatssumme. Die Gemini-API liefert keine Preise, und eine fest eingebaute Tabelle wäre nach der nächsten Google-Anpassung still falsch. Ohne Preis bleibt es bei den reinen Token-Zahlen.
- Gespeichert in `ai_usage.json` (24 Monate, im Backup enthalten), Monatswähler für die letzten 12 Monate.
- **Es bleibt eine Schätzung**, und das steht auch so im Tab: Freikontingente, Rundungen und Preisänderungen kennt das Add-on nicht. Die echten Kosten sind mit dem Gemini-Key nicht abrufbar — der berechtigt nur zum Modellaufruf. Ein Link neben der Überschrift führt zur Abrechnung bei Google.

## 0.9.7
- 🐛 **Kein Gemini-Aufruf kam durch.** Bilder, Texte und die Modellliste scheiterten alle mit „Cannot send a request, as the client has been closed" und erreichten Google nie. Der Client hatte im neuen KI-Tab keine feste Referenz mehr, wurde mitten im Aufruf eingesammelt, und sein Destruktor schloss die Verbindung. Er wird jetzt zwischengespeichert (neu aufgebaut, wenn sich der API-Key ändert) und an jeder Aufrufstelle festgehalten.
- 🔒 Die Adresse des **Vorlagenbilds** im Bild-Studio wird nicht mehr aus dem Eingabefeld zurückgelesen, sondern intern gehalten und vor der Verwendung gegen die Form einer eigenen Upload-Adresse geprüft (CodeQL `js/xss-through-dom`).
- 🔇 `google-genai` meldete bei **jeder** Anfrage „AFC is enabled with max remote calls: 10" ins Add-on-Log — eine Einstellung, die MyPage gar nicht nutzt. Nur noch Warnungen, wie schon bei fontTools.

## 0.9.6
- ✦ **Neuer Tab „KI" im Admin-Panel** — sichtbar nur, wenn ein `gemini_api_key` hinterlegt ist. Bisher steckte die KI-Bilderzeugung ausschließlich im Bibliothek-Editor und konnte nur Titelbilder für genau diesen einen Eintrag liefern.
- 🖼️ **Bild-Studio**: Beschreibung, **Stil-Bausteine** zum Anklicken (Fotorealistisch, Illustration, Flat/Vektor, 3D-Render, Aquarell, Retro), **bis zu 4 Entwürfe** je Anfrage und ein optionales **Vorlagenbild** aus den eigenen Uploads, das abgewandelt statt neu erfunden wird.
  - Entwürfe liegen zunächst **nur zwischengespeichert** auf dem Server und sind **nicht öffentlich abrufbar**. Erst „Speichern" legt sie in den Uploads ab — mit KI-Kennzeichnung, wie gehabt auf 1600 px verkleinert und ohne Metadaten. „Verwerfen" löscht sofort, unbestätigte Entwürfe verfallen nach einer Stunde. Ausschuss landet damit nicht mehr in der Bildersammlung.
- 📝 **Text-Studio**: erzeugt **Titel, SEO-Beschreibung, Fließtext in Markdown und Schlagwörter** aus Thema und Stichpunkten — mit Textart (Blogartikel, Kurzmeldung, Projektbeschreibung, Bibliothek-Zusammenfassung, nur SEO), Tonfall und Länge.
  - **Deutsch und Englisch in einem Durchgang**, wahlweise **jede Fassung eigenständig geschrieben** (idiomatischer) oder die englische **aus der deutschen übersetzt** (gleiche Gliederung).
  - Das Ergebnis ist vor der Übernahme editierbar. „Als Blogbeitrag übernehmen" öffnet den Beitrags-Dialog **als Entwurf** — veröffentlicht wird nichts automatisch. „Titelbild dazu vorbereiten" füllt das Bild-Studio passend zum Text.
- 🌐 **Übersetzung wahlweise über Gemini** statt MyMemory — einstellbar im neuen Tab, wirkt auf **alle 🌐-Knöpfe im Admin**. Gemini übersetzt den Text am Stück statt in 450-Zeichen-Häppchen und lässt Markdown, Links und Code-Blöcke intakt. Scheitert die Anfrage, springt MyMemory automatisch ein.
- ⚙️ **Modell-Auswahl kommt live von Google** (stündlich zwischengespeichert): neue Modelle stehen ohne Add-on-Update zur Verfügung. Die Auswahl im Tab **überschreibt** `gemini_image_model` und `gemini_image_ratio`, ein Modellwechsel braucht also keinen Neustart mehr.
- Getrennte Stundenlimits: **20 Bilder**, **60 Textanfragen**. Das verbrauchte Kontingent steht sichtbar im Tab.

## 0.9.5
- 🧹 **Neuer Knopf „Ungenutzte PDFs aufräumen"** unter *System → Speicher aufräumen*. Bisher erfasste das Aufräumen nur den Bilder-Ordner — verwaiste Bibliothek-PDFs waren dort weder sichtbar noch löschbar, und ein PDF ist deutlich größer als ein Bild.
- Im Normalbetrieb räumt die Bibliothek selbst auf (neu gerendert, PDF-Modus gewechselt, Eintrag gelöscht). Der Knopf fängt die Fälle ab, die daran vorbeigehen: ein **abgebrochenes Rendern** zwischen Schreiben der Datei und Eintragen in `site.json`, oder eine **Wiederherstellung aus einem Backup mit weniger Einträgen**.
- Erkannt wird wie bei den Bildern über einen Vorkommen-Scan in `site.json`; gelöscht wird erst nach Rückfrage mit Anzahl und Größe. Beide Aufräum-Werkzeuge sind getrennt — eines fasst den Ordner des anderen nie an.

## 0.9.4
- ⏳ **Die PDF-Erzeugung zeigt sich jetzt.** Beim Speichern eines Bibliothek-Eintrags mit „Aus dem Text erzeugen" erscheint oben ein **Banner mit Spinner** („PDF wird erzeugt …"), das stehen bleibt, bis das Rendern durch ist — danach wird es **grün** („PDF erzeugt.") oder **rot** mit dem Grund. Bisher passierte sichtbar nichts und der Ausgang stand nur im Add-on-Log oder für 2 Sekunden im Toast.
- Der **Speichern-Knopf ist währenddessen gesperrt** — das Rendern läuft im selben Request, ein zweiter Klick hätte es unnötig noch einmal angestoßen.
- Gleiches beim **Kopieren** eines Eintrags: die Kopie erbt die PDF-Einstellung und rendert mit, das war bisher genauso unsichtbar.
- Fehlermeldungen bleiben **7 Sekunden** stehen (Erfolg 3,5) — bei „PDF-Erzeugung ist auf diesem System nicht verfügbar" ist der Text zu lang für einen kurzen Einblender.
- Ohne PDF-Erzeugung bleibt alles wie gehabt: kurzer Toast „Gespeichert", kein Banner.

## 0.9.3
- ⚙️ **„Bilder schützen" ist jetzt auch im Tab *Bibliothek* bedienbar.** Seit v0.9.2 wirkt die Einstellung auf Bibliothek-Bilder, ließ sich aber nur unter *Inhalt → Fotoalben* umstellen — dort sucht sie niemand, der gerade an der Bibliothek arbeitet. Schalter und Wasserzeichen-Text stehen nun in beiden Bereichen.
- Es bleibt **eine** Einstellung: eine Änderung an der einen Stelle erscheint sofort an der anderen. Der Hinweistext unter den Feldern sagt das ausdrücklich, damit niemand zwei getrennte Schalter vermutet.

## 0.9.2
- ⚖️ **KI-erzeugte Bilder werden gekennzeichnet.** Bilder aus „✨ Bild generieren" tragen beim Ausliefern den eingebrannten Hinweis **„KI generiert"** (auf der englischen Seite „AI generated"). Das erfüllt die Transparenzpflicht für KI-Inhalte und ist deshalb **bewusst nicht abschaltbar** — anders als das Wasserzeichen, das eine Komfortfunktion bleibt.
  - Die Kennzeichnung erscheint auch beim **direkten Aufruf der Bildadresse** und im **erzeugten PDF**. Sonst wäre der Download des PDF oder ein Rechtsklick der einfachste Weg, sie loszuwerden.
  - Erkannt wird ein KI-Bild am Dateinamen (Endung `-ai`, z. B. `a1b2…-ai.webp`). Der Marker steckt bewusst im Dateinamen statt in einer Liste: so übersteht er Backup und Wiederherstellung und gilt auch, wenn dasselbe Bild in mehreren Einträgen benutzt wird. Wer eine Datei außerhalb des Add-ons umbenennt, verliert die Kennzeichnung.
- 🖼️ **„Bilder schützen" wirkt jetzt auch in der Bibliothek.** Bisher betraf das Wasserzeichen nur die Fotoalben; ist die Option an, erscheint es nun ebenso im **Titelbild und in den Bildern im Text** eines Bibliothek-Eintrags — auch im erzeugten PDF. Eingebundene Fremd-URLs bleiben unangetastet. Rechtsklick-Sperre bleibt weiterhin den Alben vorbehalten.
- Sind beide Fälle zusammen gegeben, stehen sie als **eine Zeile** unten rechts: `@deine-domain.de · KI generiert`.
- Ändert sich der Wasserzeichen-Text, werden **PDFs von Bibliothek-Einträgen neu erzeugt** — vorher hätte ein unveränderter Text weiter das alte PDF mit dem alten Wasserzeichen geliefert.

## 0.9.1
- 🖼️ **Medien-Browser: bereits hochgeladene Bilder auswählen, statt sie erneut hochzuladen.** Überall, wo bisher „Hochladen" stand, heißt der Knopf jetzt **„Bild wählen"** und öffnet eine Galerie aller vorhandenen Bilder — neueste zuerst, mit Datum und Dateigröße. Ein Klick übernimmt das Bild ins Feld. Wer doch etwas Neues braucht: **„Neues Bild hochladen"** in derselben Galerie führt zum gewohnten Dateidialog.
- Verfügbar bei **Titelbild der Bibliothek, Beitrags- und Projektbild, Favicon, Karten-Bild, Mitglieder-Avatar, Team-Fotos, Fotoalben** und im **Markdown-Editor**: Der Bild-Knopf fragt weiterhin nach einer URL — bleibt das Feld leer, kommt jetzt die Galerie statt sofort der Dateidialog.
- Bilder, die **nirgends verwendet** werden, tragen in der Galerie die Plakette „unbenutzt" — praktisch, um vor dem Aufräumen im Tab *System* zu sehen, was übrig ist. Gelöscht wird dabei nichts.
- Aus Rücksicht auf große Sammlungen zeigt die Galerie die **neuesten 300 Bilder** und nennt in der Kopfzeile die Gesamtzahl. Abgebrochene 0-Byte-Uploads werden übersprungen, damit keine kaputten Kacheln erscheinen.

## 0.9.0
- ✨ **Titelbild eines Bibliothek-Eintrags von der KI erzeugen lassen.** Neben dem Bild-Feld sitzt ein Knopf **„Bild generieren"**, der ein Feld mit einer **vorgeschlagenen Bildbeschreibung aus Titel, Kategorie, Schlagwörtern und Kurzbeschreibung** des Eintrags öffnet. Trägt der Eintrag das Schlagwort „Rhodos", steht es im Vorschlag und das Bild passt dazu. Die Beschreibung ist frei änderbar; das fertige Bild wird sofort als Titelbild eingetragen. Gespeichert ist der Eintrag damit noch nicht — dazu braucht es weiterhin „Speichern".
- **Der Knopf erscheint nur, wenn ein Key hinterlegt ist.** Neue Optionen `gemini_api_key` (Key auf [aistudio.google.com](https://aistudio.google.com)), `gemini_image_model` und `gemini_image_ratio` (Standard `16:9`). Ohne Key bleibt alles wie bisher. **Bildgenerierung ist bei Google je nach Modell kostenpflichtig** — deshalb sind höchstens 20 Bilder pro Stunde möglich und die Beschreibung ist auf 1200 Zeichen begrenzt, damit nicht versehentlich ein ganzer Artikel an eine Bezahl-API geht.
- Warum Google und nicht Claude: Anthropic-Modelle erzeugen keine Bilder. Gemini ist bereits in der TUIWatch-App eingebunden, das Muster ließ sich übernehmen.
- Das erzeugte Bild läuft durch **dieselbe Verarbeitung wie jeder Upload** — auf 1600 px verkleinert, als WebP gespeichert, ohne Metadaten. Es liegt lokal unter `/uploads/` und nie als Google-Adresse im Eintrag; sonst würde die PDF-Erzeugung scheitern, die aus Sicherheitsgründen nur lokale Dateien lädt.
- Ein KI-Bild entsteht beim Klick auf „Erzeugen", nicht erst beim Speichern. Schließt du den Dialog, ohne zu speichern, **bleibt die Datei zunächst liegen** — genau wie ein von Hand hochgeladenes Bild. Sie verschwindet über „Unbenutzte Uploads aufräumen" im Tab *System*; von allein löscht das Add-on nie etwas.
- Lehnt die KI eine Beschreibung ab, sagt der Admin das ausdrücklich („Bitte die Beschreibung anpassen") statt einen allgemeinen Fehler zu zeigen — bei einer Ablehnung hilft nur eine andere Formulierung, kein erneuter Versuch.

## 0.8.19
- 🐛 Fix: Im **PDF eines Bibliothek-Eintrags** stand vor dem Kategorienamen ein leeres Kästchen. Ursache war das Emoji-Symbol der Kategorie: der Druck-Zeichensatz (DejaVu) enthält keine Emoji, und der PDF-Erzeuger setzt für ein unbekanntes Zeichen ein Kästchen. Im Browser fällt das nicht auf, weil der dort vorhandene System-Zeichensatz einspringt. Das Symbol entfällt im PDF jetzt, die Kopfzeile lautet nur noch `Kategoriename · Datum` — in der Weboberfläche bleibt das Symbol wie gehabt.
- Neu erzeugt wird ein PDF weiterhin nur beim **Speichern** des Eintrags. Damit Layout-Änderungen künftig überhaupt greifen, fließt jetzt eine Layout-Kennung in die Zwischenspeicher-Prüfsumme ein — vorher blieb bei unverändertem Text das alte PDF bestehen, obwohl das Layout ein anderes war.

## 0.8.18
- 🗂️ **Dauerhaftes Besucher-Archiv als Datei** (neue Option `visit_file_log`, Standard: aus). Das Besucher-Log im Admin ist ein Ringpuffer und zeigt nur die neuesten 500 Aufrufe — ist die Option an, wird jeder Aufruf zusätzlich unter `addon_configs/XXX_mypage/visits/visits-JJJJ-MM.csv` festgehalten, eine Datei je Monat, über den Share direkt erreichbar.
- **Format bewusst Excel-tauglich**: CSV mit Semikolon als Trennzeichen und UTF-8-BOM — per Doppelklick korrekt in Spalten und mit richtigen Umlauten. Spalten: `datum`, `ip`, `land`, `browser`, `system`, `pfad`, `referrer`, `sprache`, `bot`, `neuer_besucher`, `user_agent`. Semikolons und Anführungszeichen in Referrer und User-Agent werden maskiert.
- Neue Option **`visit_file_keep`**: wie viele Monatsdateien aufbewahrt werden (0–120, Standard 12; `0` = unbegrenzt). Aufgeräumt wird beim Anlegen einer neuen Monatsdatei.
- Geschrieben werden — wie im Admin-Log — nur **öffentliche IPs**. Das Archiv ist bewusst **nicht** Teil des Backups: es würde jedes Backup mit der Zeit aufblähen.
- Der Datenschutz-Grund für „Standard: aus": IP-Adressen sind personenbezogene Daten; ein zeitlich unbegrenztes Archiv soll bewusst eingeschaltet werden.
- Dokumentiert: die Liste im Admin zeigt immer höchstens die neuesten 500 Einträge, auch wenn `visit_log_max` höher steht — die übrigen fließen weiter in Referrer-, Browser-, Länder- und Top-Seiten-Auswertung.

## 0.8.17
- 🐛 **Fix: echte Besucher-IP kam seit v0.8.10 nicht mehr an.** Waitress entfernt `X-Forwarded-*`-Kopfzeilen standardmäßig, bevor die Anwendung sie sieht (`clear_untrusted_proxy_headers=True`). Hinter Reverse Proxy oder Cloudflare Tunnel blieb dadurch nur noch die Adresse des letzten Zwischenglieds übrig — im Home-Assistant-Setup für **alle** Besucher dasselbe Docker-Gateway (`172.30.32.1`). Die vorhandene ProxyFix-Auswertung lief ins Leere, weil die Kopfzeilen gar nicht mehr da waren. Waitress reicht sie jetzt durch.
  - Nebenwirkung des Fehlers, die damit ebenfalls behoben ist: **Brute-Force-Sperre und Rate-Limits** rechneten alle Besucher als eine einzige IP — fünf Fehlversuche irgendeines Besuchers hätten alle anderen mitgesperrt.
- **Besucher-IP wird robuster ermittelt**: `CF-Connecting-IP`, `True-Client-IP`, `X-Real-IP`, dann die erste **öffentliche** Adresse aus `X-Forwarded-For`. Zwischenglieder hängen ihre eigenen, privaten Adressen an die Kette an — die werden jetzt übersprungen statt als Besucher gezählt.
- 📊 **Besucher-Log zeigt nur noch öffentliche IPs.** Aufrufe aus dem Heimnetz und die internen Zugriffe von Home Assistant selbst sagen nichts über Besucher aus und füllten die Liste. Die Aufrufzähler laufen unverändert weiter.
- Kommt gar keine öffentliche Adresse an, steht **einmal pro Stunde** eine Meldung im Add-on-Log — inklusive der tatsächlich vorhandenen Proxy-Kopfzeilen. Ohne sie wäre nur zu sehen, dass das Besucher-Log leer bleibt, nicht warum.

## 0.8.16
- 🐛 Fix: Der Schalter **„In der Navigation zeigen"** der Bibliothek blieb auf der Startseite wirkungslos, solange der Abschnitt dort sichtbar war — die Sprungmarke kam aus der Abschnitts-Navigation und ignorierte den Schalter. Jetzt gilt er überall: aus heißt aus.

## 0.8.15
- 🏷️ **Schlagwort-Filter jetzt auch im Startseiten-Abschnitt.** Unter der Überschrift der Sammlung steht eine Chip-Reihe mit allen Schlagwörtern der angerissenen Einträge; ein Klick filtert die Kacheln **ohne Neuladen** der Startseite. Bisher gab es die Filter nur auf `/bibliothek`.
- 🔗 **Weg zur Übersicht.** Der Link unter dem Abschnitt („Zur Übersicht →") erschien bisher nur, wenn es mehr Einträge gab als angerissen — bei wenigen Einträgen führte von der Startseite also **gar nichts** zu `/bibliothek`. Er steht jetzt immer da und übernimmt ein gewähltes Schlagwort (`/bibliothek?tag=…`), damit auch Treffer außerhalb des Anrisses erreichbar sind.
- Ist der Bibliothek-Abschnitt im Tab *Inhalt* ausgeblendet oder auf Mitglieder beschränkt, erscheint die Sammlung in der Navigation jetzt als **echter Link** auf `/bibliothek` statt als Sprungmarke ins Leere. Steht der Abschnitt sichtbar auf der Startseite, bleibt es beim Anker — nicht beides.
- Fix: In der Chip-Reihe standen Schlagwörter, die sich nur in der Groß-/Kleinschreibung unterschieden, doppelt („Griechenland" und „griechenland"). Startseite und Übersicht fassen sie jetzt gleich zusammen.

## 0.8.14
- 📋 **Bibliothek: Kopieren-Knopf je Eintrag.** Legt ein Duplikat direkt hinter dem Original an — mit Text, Bild, Kategorie, Schlagwörtern und PDF-Einstellung, aber **als Entwurf** (eine Kopie wird fast immer noch überarbeitet und stünde sonst sofort ein zweites Mal öffentlich und in der Sitemap). Der Titel bekommt je Sprache das passende Suffix („(Kopie)" / „(copy)"), der Dialog öffnet sich gleich zum Bearbeiten. Ein hochgeladenes PDF wird als **eigene Datei** kopiert — sonst hätte das Löschen des einen Eintrags dem anderen die Datei weggenommen.
- 🏷️ **Bibliothek: Schlagwort-Filter auf der Übersicht.** Unter den Kategorie-Chips steht jetzt eine Reihe mit allen vergebenen Schlagwörtern; ein Klick filtert die Kacheln, ein erneuter Klick hebt den Filter auf. Kategorie, Schlagwort und Suchfeld lassen sich frei kombinieren, jeder Chip behält die übrigen Filter bei. Groß-/Kleinschreibung wird zusammengefasst. Auf der Eintragsseite sind die Schlagwörter jetzt Links auf die gefilterte Übersicht.
- 🎠 **Bibliothek auf der Startseite als Karussell.** Der Abschnitt scrollt seitwärts wie die Fotoalben (mit Pfeilen, Snap und Touch-Wischen), statt bei vielen Einträgen die Startseite in die Länge zu ziehen. Es werden bis zu 12 Kacheln angerissen (vorher 6), darüber führt „Alle anzeigen →" auf `/bibliothek`. Die Übersichtsseite selbst bleibt ein umbrechendes Raster.

## 0.8.13
- 🐛 Fix: In den Dialogen **Eintrag bearbeiten** (Bibliothek), **Seite** und **Formular** schob eine lange Adresse (Slug) das Layout auseinander — die Vorschau-URL unter dem Feld ist eine umbruchlose Zeichenkette, und Grid-Spalten schrumpfen von sich aus nicht unter ihren Inhalt (`min-width: auto`). Die linke Spalte wuchs mit jedem getippten Zeichen, die rechte („Kategorie", „Veröffentlicht", „Nur für Mitglieder") wanderte aus dem Dialog. Spalten dürfen jetzt schrumpfen (`min-width: 0`), Hinweistexte brechen um (`overflow-wrap: anywhere`).

## 0.8.12
- 🔒 Fix: Bei Bibliothek-Einträgen mit **Nur für Mitglieder** stand der gesperrte Text in der Meta-Description (`<meta name="description">` und `og:description`) — er wurde aus dem vollen Markdown gebildet statt aus dem Anriss. Damit wären die ersten ~155 Zeichen im Suchmaschinen-Snippet und in Link-Vorschauen gelandet. Jetzt wie bei eigenen Seiten aus dem bereits gekürzten Anriss.
- fontTools protokollierte bei jeder PDF-Erzeugung jeden Teilschritt der Schrift-Optimierung auf INFO („glyf pruned", „GDEF pruned", …) — pro PDF dutzende Zeilen im Add-on-Log. Auf WARNING gesetzt.

## 0.8.11
- 📚 **Neues Modul „Bibliothek".** Eine Sammlung eigenständiger Markdown-Dokumente mit frei wählbaren Kategorien — gedacht für alles, was kein Blog-Beitrag und keine einzelne Seite ist: Reiseführer, Kochrezepte, Anleitungen, Handbücher. Übersicht unter `/bibliothek` (Karten-Raster mit Kategorie-Chips und Suchfeld), Einzeleintrag unter `/bibliothek/<slug>`. Neuer Admin-Tab **Bibliothek**.
- **Name und Kategorien sind frei wählbar.** Der Anzeigename der Sammlung wird im Admin gesetzt (DE/EN, leer = „Bibliothek"), die Kategorien legst du selbst an — dieselbe Installation kann die Sammlung also „Reiseführer" nennen und darin „Reisen", „Kochen" und „Technik" führen. Kategorien haben ein frei wählbares Emoji und lassen sich per Drag & Drop sortieren, Einträge ebenso.
- **Je Eintrag:** Titel, Kurzbeschreibung, Titelbild, Schlagwörter, Markdown-Text (DE/EN, gleicher Editor mit Live-Vorschau wie Blog und Seiten), eigene SEO-Beschreibung, Entwurfs-Status und der 🔒-Schalter **Nur für Mitglieder** (Gäste sehen dann nur einen Anriss).
- 📄 **PDF je Eintrag — wahlweise erzeugt oder hochgeladen.** Im Modus *„Aus dem Text erzeugen"* rendert das Add-on beim Speichern ein PDF aus dem Markdown (Deckblatt-Kopf, Seitenzahlen, Tabellen, Code-Blöcke) und bietet es zum Download an; alternativ lädst du ein eigenes PDF hoch (max. 25 MB). Erzeugte PDFs werden über einen Fingerabdruck des Quelltexts zwischengespeichert — unveränderte Einträge werden beim Speichern nicht neu gerendert.
- **Drucken geht immer.** Jede Eintragsseite hat einen Druck-Knopf mit eigenem Druck-Stylesheet (ohne Navigation, Fußzeile und Knöpfe, mit ausgeschriebenen Links) — auch ohne serverseitige PDF-Erzeugung lässt sich so ein sauberes PDF speichern.
- **Sichtbar für Suchmaschinen wie der Blog:** veröffentlichte Einträge landen in `sitemap.xml`, im IndexNow-Ping, in der Volltextsuche und im statischen Export (inklusive der PDF-Dateien). Einzeleinträge liefern strukturierte Daten (`schema.org/Article`). Mitglieder-Einträge erscheinen in der Suche wie gehabt nur als Titel mit 🔒, ohne Textvorschau.
- **Startseite:** Die Bibliothek ist ein eigener Startseiten-Abschnitt (die ersten sechs Einträge als Karten) und lässt sich im Tab *Inhalt* wie jeder andere Abschnitt sortieren, ausblenden oder auf Mitglieder beschränken.
- **Sicherheit:** PDFs liegen in einem eigenen Ordner (`docs/`) und werden **ausschließlich** über eine eigene Route mit `Content-Disposition: attachment` und `X-Content-Type-Options: nosniff` ausgeliefert — nie inline über die offene `/uploads/`-Route. Uploads werden zusätzlich am Dateikopf (`%PDF-`) geprüft, nicht nur an der Endung. Der PDF-Renderer bekommt einen eigenen URL-Fetcher, der nur lokale `/uploads/`-Dateien lädt und **jede** externe Adresse ablehnt (sonst wäre ein Bild-Link im Markdown ein SSRF-Weg in interne Dienste).
- PDFs werden im Backup mitgesichert und beim Wiederherstellen — nach Prüfung des Dateikopfs — zurückgeschrieben.
- Neue Abhängigkeit `weasyprint` (plus `pango`/`libffi` im Image) für die PDF-Erzeugung. Fehlt sie, startet das Add-on unverändert und der Modus *„Aus dem Text erzeugen"* meldet das im Admin — Druck-Knopf und PDF-Upload funktionieren weiterhin.

## [0.8.10.1] - 2026-08-05

chore(deps): bump cryptography from 48.0.1 to 50.0.0 in /mypage


## 0.8.10
- ⚙️ **Produktions-Webserver (Waitress) statt Flask-Entwicklungsserver.** Beide Ports liefen bisher über den in Flask eingebauten Werkzeug-Server, der ausdrücklich nicht für den Produktivbetrieb gedacht ist: er legt **pro Verbindung einen Thread** an — ohne Obergrenze — und kennt weder Verbindungslimit noch Timeout für hängende Verbindungen. Gemessen im Vergleich: bei 300 gleichzeitigen Zugriffen brauchte Werkzeug **301 Threads**, Waitress konstant **21** (fester Thread-Pool mit Warteschlange davor, 8 Threads öffentlich / 4 im Admin). Der Ressourcenverbrauch ist damit gedeckelt statt offen.
- Tempo und Verhalten bleiben im Alltag gleich (Durchsatz ~40–60 Seiten/s, begrenzt durch Python selbst, nicht durch den Server); unter hoher Last antwortet Waitress etwas zügiger (bei 200 gleichzeitig: 53,5 statt 40,1 Anfragen/s). Keine Anfrage schlug in den Tests fehl.
- Der `Server`-Header entfällt (`ident=None`) — vorher standen dort Werkzeug- und Python-Version.
- Das Upload-Limit wird an Waitress durchgereicht, damit große Dateien nicht schon vom Webserver abgewiesen werden, bevor die konfigurierte Grenze (`user_upload_max_mb`) greift.

## 0.8.9
- 💾 **Automatische tägliche Backups.** Das Add-on legt einmal pro Tag dasselbe vollständige ZIP wie der Download-Button automatisch unter `addon_configs/<slug>_mypage/autobackup/` ab (`mypage-auto-JJJJ-MM-TT.zip`). Die neue Option **`auto_backup_keep`** steuert, wie viele Stände aufbewahrt werden (Standard 7, `0` = aus); ältere werden automatisch gelöscht. Damit gibt es endlich einen sauberen Vorgängerstand, wenn eine Datei beschädigt wird oder etwas versehentlich gelöscht wurde — bisher existierte nur das manuelle Backup.
- Neues Panel **„Automatische Backups"** im Tab *System*: vorhandene Stände mit Datum und Größe, einzeln herunterladbar und löschbar, plus Knopf **„Jetzt sichern"**. Vollständig DE/EN lokalisiert, inklusive der Beschreibung der neuen Option in den Add-on-Einstellungen.
- Der Zip-Aufbau ist jetzt eine gemeinsame Funktion (`write_backup_zip()`) für Download und Auto-Backup — beide können nicht mehr auseinanderlaufen. Das Backup selbst wird atomar geschrieben (`.tmp` + `os.replace`), es wird also nie ein halb geschriebenes Archiv sichtbar. Der `autobackup/`-Ordner ist bewusst **nicht** Teil des Backup-Inhalts, sonst würde jedes Backup alle Vorgänger mitschleppen.

## 0.8.8
- 🛡️ **Datenverlust-Schutz: alle Kerndateien werden jetzt atomar geschrieben.** Bisher kürzte jedes Speichern die Zieldatei erst auf 0 Byte — starb der Prozess in diesem Moment (z. B. SIGKILL beim Add-on-Stop, wie bis v0.8.2 bei jedem Update), blieb eine halbe oder leere Datei zurück. Neuer Helfer `_atomic_write_json()` schreibt erst vollständig in eine `.tmp`-Datei (inkl. `fsync`) und benennt dann per `os.replace()` um: es existiert immer entweder der alte oder der neue Stand, nie etwas dazwischen. Betrifft `site.json`, `stats.json`, `messages.json`, `comments.json`, `polls.json`, `dm.json`, `subscribers.json`, `users.json`, `sessions.json`, `user_sessions.json` und `admin_2fa.json` (Spielstände waren bereits atomar).
- 🛡️ **Beschädigte Dateien setzen die Seite nicht mehr still zurück.** Zuvor lieferte `load_site()` bei defekter `site.json` kommentarlos die Standardwerte und der nächste Speichervorgang — z. B. aus dem stündlichen GitHub-Sterne-Thread — schrieb diese Defaults endgültig fest: **alle Inhalte, Projekte und Einstellungen weg, im Log nur eine Warnung.** Jetzt wird die defekte Datei als `<name>.corrupt-<zeitstempel>` zur Seite gelegt, als `ERROR` protokolliert und eine persistente Home-Assistant-Benachrichtigung ausgelöst. Gilt ebenso für die übrigen Kerndateien; bei `admin_2fa.json` ist das zusätzlich sicherheitsrelevant, weil eine unlesbare Datei 2FA als deaktiviert gelten ließ.
- Die Dateirechte `0600` für `admin_2fa.json` werden jetzt auf der `.tmp`-Datei **vor** dem Umbenennen gesetzt — vorher gab es ein kurzes Fenster mit Standardrechten.

## 0.8.7
- Fix: trust2fa-Cookie wird jetzt mit `itsdangerous.URLSafeTimedSerializer` signiert (Flask `SECRET_KEY` in `secret.key`) statt den rohen Token direkt zu speichern — genau der Fix, den GitHubs eigener CodeQL-Autofix für Alert #193 vorgeschlagen hat. Der 0.8.6-Versuch (Token 1:1 wie beim session-Cookie speichern) hat den Alert nicht behoben.

## 0.8.6
- Fix: trust2fa-Speicherung auf das gleiche Muster wie normale Admin-Sessions umgestellt (Zufalls-Token als Dict-Key in `admin_2fa.json`, mit Ablaufzeit) statt Hash-Vergleich. Der 0.8.5-Versuch (Fernet-Verschlüsselung des Cookie-Werts) wurde von CodeQL trotzdem als „clear-text storage of sensitive data" erkannt (neuer Alert #193) — CodeQL erkennt die Hash-Vergleich-Formel als Credential-Muster, unabhängig von der Verschlüsselung. Das jetzige Muster entspricht exakt dem seit Jahren unauffälligen `session`-Cookie.

## 0.8.5
- (zurückgenommen) trust2fa-Cookie mit Fernet verschlüsselt — siehe 0.8.6.

## 0.8.4
- 🔐 **2FA: „Dieses Gerät merken"** — Checkbox beim Code-Schritt (default an) legt ein 30 Tage gültiges Geräte-Cookie an (`trust2fa`); danach fragt der direkte Login (Port 17761) auf diesem Gerät nur noch Benutzername/Passwort ab. Deaktivieren oder Neueinrichten von 2FA verwirft alle gemerkten Geräte automatisch.

## 0.8.3
- map: `addon_config` → `app_config` (Home-Assistant-Supervisor hat `addon_config` seit 2026.07 als Legacy-Name markiert, neuer Name ist `app_config`).

## 0.8.2

- Fix: Add-on beendete sich bei jedem Stop/Update mit Exit-Code 137 (SIGKILL statt sauberem Stop) — der Flask-Prozess läuft als PID 1 ohne eigenes Init-System, ohne Signal-Handler ignoriert der Kernel bei PID 1 unbehandelte Signale wie SIGTERM. `init: false` → `init: true` in `config.yaml` sorgt für ein echtes Mini-Init als PID 1, zusätzlich fängt ein neuer `SIGTERM`-Handler (`os._exit(0)`, alle Hintergrund-Threads sind daemon) das Signal sauber ab und beendet den Prozess mit Exit-Code 0.

## 0.8.1

- Fix: Abgelaufene Admin-Session wurde nicht erkannt: `refreshPlaying()` ignorierte 401-Antworten still, „Wer spielt"-Anzeige blieb eingefroren statt zum Login weiterzuleiten

## 0.8.0

- 🗳️ **Neue Startseiten-Sektion: Umfrage** — Eine Frage mit 2–5 Antwortoptionen (DE/EN), gepflegt im Inhalte-Tab. Mitglieder stimmen mit ihrem Konto ab, Gäste anonym per Cookie — jeder hat genau eine Stimme und kann sie jederzeit ändern. Nach der Abstimmung erscheint ein **Balkendiagramm** mit Prozentwerten, Stimmenzahl und der eigenen Auswahl (✓), ohne Neuladen der Seite. Die Sektion lässt sich wie üblich per Drag & Drop anordnen, ausblenden oder auf „nur Mitglieder" stellen; im Admin gibt es einen Button **„Ergebnisse zurücksetzen"**. Die Stimmen liegen getrennt von den Inhalten in `polls.json`.
- 🏆 **Bestenliste für die Spiele** — Neue Seite im Mitgliederbereich: **Gesamtwertung** (Siege, Partien, Quote über alle 9 Spiele) plus aufklappbare **Rangliste je Spiel** (Top 10), mit Medaillen für die ersten drei und hervorgehobener eigener Zeile. Gezählt werden alle bereits aufgezeichneten Partien — die Liste ist also ab der ersten Sekunde gefüllt.
- 🏅 **Erfolge im Mitgliederbereich** — Zwölf Abzeichen, live aus vorhandenen Daten berechnet (keine extra Speicherung): Erste Partie, 25/100 Partien, Erster Sieg, 10/50 Siege, Allrounder (jedes Spiel gespielt), Blog-Kommentare, erste Nachricht, erste Datei, ein Jahr Mitgliedschaft. Noch offene Abzeichen werden ausgegraut mit Fortschritt (z. B. „7 / 25") angezeigt.
- 🦊 **Mau Mau: Spieler-Kartenflug in Firefox sichtbar** — Wie zuvor bei 66 und 20 ab (v0.7.31) startete die Flug-Animation der eigenen Karte in Firefox nicht (Karte sprang ohne Übergang auf den Ablagestapel). Vor dem Start wird jetzt ein Reflow erzwungen; die KI-Flüge waren nicht betroffen.

## 0.7.66

- ⏱️ **Countdown-Größe einstellbar** — Im Countdown-Abschnitt lässt sich jetzt über ein Auswahlfeld **Klein / Mittel / Groß** wählen. Der gesamte Block (Ziffern, Kacheln, Abstände, Labels und optionales Bild) wird dabei proportional skaliert. „Mittel" bleibt der bisherige Standard, sodass bestehende Seiten unverändert aussehen.

## 0.7.65

- ✍️ **Neues Freitext-Modul** — Ein frei gestaltbarer Startseiten-Abschnitt: Über den eingebauten **Markdown-Editor** lassen sich beliebig **Text und Bilder** einfügen (Formatierung, Listen, Tabellen, Links, Bild-Upload per Klick). Die **Überschrift ist optional** (DE/EN) — bleibt sie leer, wird keine Titelzeile angezeigt und der Inhalt gestaltet sich komplett selbst. Der Block lässt sich wie jede andere Sektion **per Drag & Drop anordnen, aus-/einblenden** und auf „nur Mitglieder" stellen.

## 0.7.64

- 🃏 **20 AB — Regeln verfeinert** — Drei Anpassungen beim Reizen: (1) Bei der **„Nächste Karte"** als Trumpf müssen jetzt nur noch alle mitspielen, wenn ein **Kreuz** gezogen wird — bei jeder anderen Farbe wird **normal gereizt**, man darf also aussteigen. (2) **Aussteigen nach Aussteigen verboten:** Wer in einer Runde passt, **muss die nächste Runde mitspielen**. (3) **Punkte-Sperre:** Wer **weniger als 6 Punkte** hat, **darf nicht mehr aussteigen**. KI und Bedienung (Passen-Button wird ausgeblendet) halten sich daran; Regeltexte (DE/EN) ergänzt.

## 0.7.63

- 📖 **Blog: Lesezeit & ähnliche Beiträge** — Jeder Beitrag zeigt jetzt neben dem Datum eine geschätzte **Lesezeit** (≈200 Wörter/Min). Unter dem Beitrag erscheint außerdem ein Block **„Ähnliche Beiträge"** mit bis zu drei verwandten Beiträgen, ermittelt über gemeinsame Schlagwörter (nach Anzahl gemeinsamer Tags und Datum). Hat ein Beitrag keine Tags oder keine Verwandten, bleibt der Block aus. Für Mitglieder-only-Anrisse wird nichts angezeigt.
- 💾 **Mitglieder-Speicher: Warnfarben & Prozentanzeige** — Der Speicherbalken im persönlichen Bereich zeigt jetzt die **Auslastung in Prozent** und färbt sich ab 80 % **orange** bzw. ab 95 % **rot**; zusätzlich erscheint ein kurzer Hinweis, wenn der Speicher fast voll ist.
- 📊 **Wöchentlicher Statistik-Rückblick** — Optionaler Schalter im **Design-Tab** („Wöchentlicher Rückblick", Standard aus): Montags ab 8 Uhr verschickt MyPage eine Zusammenfassung der Vorwoche (Aufrufe inkl. Trend ggü. Vorwoche, eindeutige Besucher, Top-Seite, neue Mitglieder und neue Nachrichten) als **Home-Assistant-Benachrichtigung** und — falls SMTP eingerichtet ist — zusätzlich **per E-Mail**. Höchstens einmal pro Kalenderwoche.
- 🛡️ **DSGVO-Self-Service für Mitglieder** — Im Profil gibt es jetzt zwei neue Funktionen: **„Meine Daten exportieren"** lädt ein ZIP mit allen eigenen Daten (Kontodaten, hochgeladene Dateien, eigene Blog-Kommentare, gesendete Nachrichten, Profilbild) — Art. 15/20 DSGVO. **„Konto löschen"** entfernt nach Passwort-Bestätigung das Konto und alle eigenen Dateien unwiderruflich (Art. 17 DSGVO) und meldet das Mitglied ab.

## 0.7.62

- 📱 **Chicago — kompaktes Querformat-Layout (kein Scrollen mehr)** — Auf dem Handy passt das Spielfeld jetzt auf eine Seite: Bei niedriger Höhe werden Spieler-Chips, Würfel, Punkte und Buttons verdichtet, der Halten-Hinweis ausgeblendet, und das Ansage- bzw. Richtungs-Panel schwebt mittig ein, statt die Ansicht in die Höhe zu treiben. Kein Hoch-/Runterscrollen mehr während der Partie.

## 0.7.61

- 🎲 **Chicago — „Zur Wahl" (Richtung offen lassen)** — Bleibt der Vorleger mit einem **Fish** stehen (keine 1, keine 6 — ein reiner Mittelwert), darf er die Richtung **offen lassen** statt selbst hoch/tief anzusagen. Dann legt der **nächste Spieler vor seinem ersten Wurf** „hoch" oder „tief" fest — und das gilt für die ganze Runde. Die KI beherrscht beides: sie gibt als harter Vorleger bei einem mittleren Fish die Wahl ab und entscheidet als Folgespieler die Richtung. Regeltexte (DE/EN) ergänzt.

## 0.7.60

- 🎲 **Chicago — 6→1-Umwandlung nur innerhalb eines Wurfs** — Zwei Sechser dürfen nur dann in eine 1 umgewandelt werden (und drei Sechser nur dann automatisch zu zwei Einsern), wenn sie **im selben Wurf** fallen. Lag schon eine 6 und im nächsten Wurf kommt eine dazu, zählt das **nicht** mehr. Gilt für Mensch (Button erscheint nicht) und KI; Regeltexte ergänzt.

## 0.7.59

- 📱 **Kniffel & Chicago — Startbildschirm auf Mobilgeräten scrollbar** — Der Startbildschirm zentrierte den Inhalt in einem fixen Container und schnitt ihn auf kleinen/Querformat-Displays oben ab, ohne Scrollmöglichkeit. Jetzt ist er **scrollbar** (zentriert bei genug Platz, scrollt bei Überlauf) und wird auf niedrigen Viewports zusätzlich **kompakter** dargestellt.

## 0.7.58

- 🔒 **Sicherheit** — CodeQL-Alerts geschlossen: Path-Injection bei Avatar- und DM-Anhang-Pfaden auf `safe_join` umgestellt, Open-Redirect bei den Nachrichten-Weiterleitungen über `_safe_next` (Pfad-Neuaufbau) entschärft. Außerdem `cryptography` auf 48.0.1 angehoben (OpenSSL- und SECT-Kurven-Schwachstellen).

## 0.7.57

- 🃏 **20 ab — Handsortierung korrigiert** — Innerhalb einer Farbe wird die Hand jetzt nach der echten Rangfolge sortiert (Ass > König > Dame > Bube > 10 > 9 > 8 > 7). Vorher stand die **10 fälschlich rechts vom König** (Reihenfolge versehentlich von 66 übernommen). Die Stich-Wertung war immer schon korrekt — nur die Anzeige war falsch.

## 0.7.56

- 🎉 **Konfetti-Regen bei Gewinn in den Kartenspielen** — Wie beim Glücksrad regnet es jetzt auch bei **66, 20 ab, Schwimmen, Mau Mau und Präsident** Konfetti, wenn man selbst gewinnt (bei Schwimmen zusätzlich beim Turniersieg, bei 66 beim Match-Sieg). Respektiert „Reduzierte Bewegung".

## 0.7.55

- 🎲 **Chicago — gleicher Wert ist echter Gleichstand („Mit ist Shit")** — Der Vergleich nutzt jetzt den **angezeigten Gesamtwert** (z. B. „12") statt der einzelnen Würfel-Kombination. Dadurch sind zwei gleiche Anzeigen (z. B. 6·4·2 und 5·4·3 = beide 12) ein **echter Gleichstand** → der **spätere** Spieler verliert — unabhängig von Würfel-Kombination **und Wurfzahl** (eine 12 in einem Wurf schlägt eine 12 in zwei Würfen nicht). Vorher konnte eine „bessere" 12 die andere schlagen.

## 0.7.54

- 🤖 **Chicago — alleine wieder bis zu 3 KI** — Die KI-Auswahl reicht jetzt bis **3** (alleine also 1–3 KI wie früher). Gesamtgrenze bleibt **5 Spieler**, daher bei 3 Menschen weiterhin max 2 KI. Die Bierfilze skalieren automatisch mit (immer Spielerzahl + 1): 4 Spieler = 5 Filze, 5 Spieler = 6 Filze.

## 0.7.53

- 👥 **Chicago — Hotseat: bis zu 3 Menschen am selben Gerät** — Neben dir können jetzt **1–2 weitere menschliche Spieler** am selben PC mitspielen (insgesamt **2–5 Spieler**, KI weiter optional, max 2 KI). Auf dem Startbildschirm wählst du „Menschliche Spieler" und „KI-Gegner"; wer dran ist, steht oben („… ist dran"), danach gibt man das Gerät weiter.
- ✏️ **Chicago — eigene Namen für menschliche Spieler** — Jeder Mensch bekommt einen **eigenen Namen** (Felder auf dem Startbildschirm), **jederzeit änderbar** über ⚙ Einstellungen. Mit Namen heißt es korrekt in der **3. Person** („Beate gewinnt", „Beate bekommt einen Bierfilz"); der namenlose Spieler 1 bleibt wie gewohnt „Du gewinnst/bekommst". Namen werden sicher dargestellt (kein HTML).
- 📊 **Statistik weiterhin nur für Spieler 1** (`Du`) — wie gewünscht unverändert.

## 0.7.52

- 🎲 **Chicago — „Mit ist Shit" bei Gleichstand korrigiert** — Bei gleichem Wurf (z. B. beide 12 groß) verlor fälschlich der **frühere** Spieler. Richtig ist: Wer **gleichzieht, ist „mit" und damit Shit** — also verliert der **spätere** Spieler in der Reihenfolge. Würfelst du als Vorleger 12 und die KI zieht mit 12 gleich, verliert jetzt die **KI** (und umgekehrt). Betrifft die Ermittlung des Runden-Verlierers (Phase 1 & 2), hoch wie tief.

## 0.7.51

- 👤 **„Mein Profil" als Accordion** — die Profil-Karte (Name, E-Mail-Sprache, Nachrichten-Empfang, Verzeichnis/Avatar, Passwort ändern) ist jetzt **aufklappbar** und standardmässig **zugeklappt** — das verkürzt den Mitgliederbereich weiter. Der Zustand wird gemerkt (localStorage). Nach dem **Speichern** (oder bei einem Fehler, z. B. falsches Passwort) klappt das Profil **automatisch auf**, damit die Rückmeldung sichtbar ist.

## 0.7.50

- 🎲 **Chicago — nur 1 und 6 dürfen stehen bleiben** — Beim Halten zwischen den Würfen können jetzt **nur 1en und 6en** liegen bleiben; **2–5 wandern immer zurück in den Becher** und werden neu geworfen. Gilt für dich **und** die KI, ist in den Spielregeln ergänzt und der Halte-Hinweis wurde angepasst.
- 📊 **Chicago — „Chicago"-Zähler in der Statistik** — Die Statistik auf dem Startbildschirm zeigt neben Spiele/Siege/Niederlagen jetzt einen vierten Wert **„Chicago"**: wie oft du per Chicago (drei 1er) gewonnen hast.

## 0.7.49

- ⏸ **Kniffel & Chicago — echte Pause (wie Glücksrad)** — Wird der Tab in den Hintergrund geschoben, pausiert das Spiel jetzt automatisch: laufende Wartezeiten, KI-Züge und die Würfelbecher-Animation werden **eingefroren** und beim Zurückkehren exakt dort fortgesetzt (kein Vorspringen mehr, kein Auseinanderlaufen von Anzeige und echtem Spielstand). Zusätzlich ein **manueller Pause-Button** ⏸ in der Kopfzeile (auch per Taste **P**); fortsetzen per Klick auf die Pause-Anzeige, den Button oder P. Während der Pause ist alles stumm.

## 0.7.48

- 🤖 **Chicago — KI sagt jetzt chancenoptimal an (inkl. „klein")** — Bisher sagte die KI als Vorleger nie „klein" an und ließ damit starke Tief-Ansagen liegen. Jetzt bewertet sie alle Kombinationen aus Wertung (groß/klein/ohne 1) und Richtung (hoch/tief) über die tatsächliche Gegner-Schlagwahrscheinlichkeit und nimmt die am schwersten zu schlagende Ansage. Beispiel: **1·1·2** wird als **„4 tief (klein)"** angesagt (nur durch Chicago schlagbar) statt „202 hoch (groß)". Mit einer 6 bleibt es bei der natürlichen Lesart, z. B. **6·2·4 → „66 hoch (ohne 1)"**.
- 🪧 **Chicago — Ansage zeigt immer die Wertung** — In der „Zu schlagen"-Zeile stand bei „groß" bisher kein Wertungs-Wort (nur „… (hoch)"). Jetzt steht die Wertung immer dabei, z. B. „Zu schlagen: 12 auf 3 (tief · groß)", damit klar ist, wie 1 und 6 zählen.

## 0.7.47

- 🐛 **Chicago — Grammatik in den Bierfilz-Bannern** — Wenn DU einen Bierfilz bekamst oder abwarfst, stand fälschlich „Du bekommt einen Bierfilz" / „Du wirft einen Bierfilz ab". Jetzt korrekt in der 2. Person: „Du bekommst einen Bierfilz" / „Du wirfst einen Bierfilz ab" (KI bleibt „… bekommt/wirft"). DE und EN. Kniffel wurde geprüft — Sieg-/Niederlagentexte waren bereits korrekt.

## 0.7.46

- 🎉 **Kniffel — Konfettiregen beim Sieg** — Gewinnt der Spieler, regnet es jetzt Konfetti (wie beim Glücksrad und Chicago), zusammen mit dem Gewinn-Sound.

## 0.7.45

- 🪧 **Chicago — Hinweise als Mitte-Banner statt schneller Toast** — Vorlage (Ansage), Bierfilz-Aufnahme/-Abwurf und ein KI-Chicago erscheinen jetzt als großes Banner in der Bildschirmmitte, das **langsam nach oben ausfliegt**, statt eines schnellen kleinen Hinweises oben. Eigene Bierfilz-Aufnahme wird rot, Abwurf/Vorlage golden hervorgehoben. Die Anzeigedauer skaliert mit dem **Tempo-Regler** (Pausen), damit der Hinweis bei langsamerem Spiel länger steht.

## 0.7.44

- 🎲 **Chicago — „ohne 1" nur bei einer 6** — Die Ansage „ohne 1" unterscheidet sich von „klein" nur durch die 6 (zählt 60 statt 6). Ohne eine 6 im Wurf ist sie identisch mit „klein" und damit sinnlos (z. B. 3 4 1: groß 107, klein 8, ohne 1 8). Der Knopf und die Vorschau zeigen „ohne 1" jetzt nur noch, wenn tatsächlich eine 6 dabei ist. Die KI hat das ohnehin schon so gehandhabt.

## 0.7.43

- 🔌 **Kniffel & Chicago: „Hier übernehmen" repariert** — Nach dem Schließen/Beenden eines Spiels und erneutem Öffnen erschien teils der Hinweis „Auf anderem Gerät aktiv", und der **„Übernehmen"**-Knopf funktionierte nicht (man musste ~30 s warten und neu laden). Ursache: Nach der Übernahme wurde die gerade frisch beanspruchte Session **sofort erneut** angefragt und dabei als „fremd gesperrt" gewertet. Die Übernahme lädt den Spielstand jetzt direkt, ohne doppeltes Beanspruchen — wie bei den Kartenspielen.

## 0.7.42

- 🎉 **Chicago — Sieg-Banner mit Konfetti, wenn DU Chicago würfelst** — Würfelt der Spieler drei 1er, hat er sofort gewonnen. Statt nur eines Hinweises erscheint nun ein **Sieg-Banner** mit **Gewinn-Sound** und **Konfettiregen** (wie beim Glücksrad): „CHICAGO! — Gewonnen nach X Runden". Danach die Wahl: **„KIs weiter zuschauen"** (die Runde/das Spiel läuft normal weiter) oder **„Spiel beenden"** (sofort Schluss, Sieg wird gewertet).

## 0.7.41

- 🤖 **Chicago — KI spielt jetzt wertungs- & richtungsbewusst** — Bisher hielt die KI stur 1er/6er und sagte als Vorleger immer „gross" an. Jetzt richtet sie ihr **Halten** nach der angesagten Wertung (groß/klein/**ohne 1**) **und** Richtung (hoch/tief) aus und **sagt selbst sinnvoll an**: mit einer 1 → *gross hoch*, mit 6 aber ohne 1 → **ohne 1 hoch** (nimmt den Gegnern die starke 100), bei niedrigen Augen → *gross tief*. Schwierigkeitsgrade greifen wieder spürbar (leicht zufälliger, mittel reizt nicht alles aus, schwer spielt optimal inkl. 6er-Trick nur wenn es passt).
- 🗣️ **„Zu schlagen" zeigt die Wertung** — bei einer „ohne 1"- oder „klein"-Ansage steht sie jetzt mit in der Klammer, z. B. **„Zu schlagen: 69 auf 3 (hoch · ohne 1)"**.

## 0.7.40

- 🎲 **Chicago — neue Ansage „Ohne 1"** — Der Vorleger kann jetzt zusätzlich zu *groß* (1 = 100, 6 = 60) und *klein* (1 = 1, 6 = 6) auch **„ohne 1"** ansagen: dann zählt die **1** in der ganzen Runde **nur 1** (statt 100), die **6** bleibt **60**. **Chicago (drei 1er)** ist davon ausgenommen und gewinnt weiterhin sofort. Die Ansage-Auswahl zeigt alle drei Wertungen mit der jeweils tatsächlichen Punktzahl, und die laufende Ansage weist *„ohne 1"* bzw. *„klein"* für die Mitspieler aus.

## 0.7.39

- 🗂️ **Spiele im Mitgliederbereich gruppiert** — die lange Liste einzelner Karten ist jetzt in **drei aufklappbare Kategorien** (Accordion) gegliedert: **Kartenspiele** (66, Schnapsen 20-Ab, Schwimmen, Mau-Mau, Präsident), **Quizspiele** (Jeopardy, Glücksrad) und **Würfelspiele** (Kniffel, Chicago). Innerhalb jeder Kategorie liegen die Spiele als kompakte Kacheln (Icon, Titel, Kurzbeschreibung) im 2-spaltigen Raster — auf dem Handy einspaltig. Der **auf-/zugeklappte Zustand wird pro Kategorie gemerkt** (localStorage). Standardmässig sind die Kartenspiele offen, der Rest zugeklappt — das verkürzt die Seite deutlich.

## 0.7.38

- 🎲 **Chicago — drei Korrekturen:**
  - **Becher-Animation sauber** — ab und zu (v. a. beim 3. Wurf) blitzten die Würfel kurz auf dem Tisch auf, **bevor** der Becher wackelte. Das Ausgangsbild wird jetzt vor dem Schütteln festgeschrieben (gehaltene Würfel sichtbar, alle anderen verdeckt).
  - **Chicago = sofort gewonnen** — wer **drei 1er** würfelt, ist **sofort gerettet** und raus; die übrigen Spieler spielen die Runde regulär zu Ende (**„Mit ist Shit"** bleibt). Beim Spieler wird automatisch stehengeblieben (keine Ansage/kein Re-Roll nötig), mit Jubel-Hinweis und Sound — auch für die KI.
  - **Mehr Sound** — **negativer** Klang, wenn man selbst einen **Bierfilz aufnimmt**, ein **leicht positiver**, wenn eine **KI** einen Filz bekommt, und ein **positiver** beim **Abwurf** eines Filzes.

## 0.7.37

- 🎲 **Chicago-Verbesserungen** — Würfel können **innerhalb eines Wurfs** an- und wieder **abgewählt** werden; **sobald erneut gewürfelt** wird, sind die gehaltenen Würfel fix (kein Zurück in den Becher). Beim **Stehenbleiben** wird die **tatsächliche Punktzahl** angezeigt (gross/klein direkt als Auswahl, z. B. „161" / „7"), zusätzlich live unter den Würfeln. **„Zu schlagen"** zeigt jetzt korrekt die **Ansage des Vorlegers, fix für die ganze Runde** (statt sich mit jedem KI-Wurf zu ändern). Die **restlichen Bierfilze** stehen im Phasen-Badge. Der Begriff „Fish" wurde entfernt — solche Würfe erscheinen einfach als Punktzahl.
- 🃏 **Button-Darstellung korrigiert (Kniffel & Chicago)** — Die Buttons **„Schließen"** (Spielende) und **„Zurücksetzen"** (Einstellungen) erhielten die fehlende Basis-Stilklasse und werden nun korrekt dargestellt.

## 0.7.36

- 🔧 **Kniffel & Chicago vollständig integriert** — Beide Würfelspiele waren in zentralen Registern noch nicht eingetragen. Jetzt nachgezogen: **Admin-Anzeige „wer spielt gerade"** (Benutzerliste), **Home-Assistant-Sensoren** (`sensor.mypage_aktiv_kniffel` / `…_chicago` + Gesamtübersicht) und — am wichtigsten — die **Backup-Aufnahme**: Spielstände/Verläufe von Kniffel und Chicago werden nun in Sicherungen ein- und zurückgespielt (vorher fehlten sie im Backup-Filter). Die Spielregeln (📖) waren bereits angebunden.

## 0.7.35

- 🎲 **Neues Spiel: Chicago (Tschigg)** — Der Kneipen-Würfelklassiker gegen **2–3 KI** (Schwierigkeit wählbar). Mit **3 Würfeln** und bis zu 3 Würfen; **1 = 100, 6 = 60**. Der **Vorleger** bestimmt das **Wurf-Limit der Runde** und sagt **hoch/tief** sowie die Wertung (**gross/klein**) an. Mit **Becher-Tricks** (zwei 6er → eine 1; drei 6er → zwei 1er), **Chicago** (drei 1er = sofort gerettet) und **Fish**, Regel **„Mit ist Shit"**. **Bierfilz-Match (n+1)**: Phase 1 sammelt der Schlechteste, Phase 2 wirft der Beste ab — wer zuletzt Filze hat, verliert. Würfelbecher-Animation, Bierfilz-Anzeige, Ansage-UI, Spielende-Dialog, Statistik, Regeln DE/EN, Menü-Kachel, Tab-/Geräte-Schutz — alles server-autoritativ & fortsetzbar.

## 0.7.34

- 🛠️ **Startfehler behoben** — Das Add-on startete in v0.7.33 nicht (`ModuleNotFoundError: game_kniffel`), weil die neuen Dateien `game_dice.py`, `game_kniffel.py` und die Kniffel-Regeln **nicht ins Docker-Image kopiert** wurden (das Dockerfile listet jedes Spielmodul einzeln auf). Die fehlenden `COPY`-Zeilen wurden ergänzt.

## 0.7.33

- 🎲 **Neues Spiel: Kniffel** — Der Würfelklassiker gegen **1–2 KI-Gegner** (Schwierigkeit Leicht/Mittel/Schwer). Pro Zug bis zu **dreimal würfeln**, beliebige Würfel **halten** und in eines der **13 Felder** eintragen — mit **63er-Bonus** und **Kniffel-Bonus** (inkl. Joker). Server-autoritativ und seed-deterministisch (manipulationssicher, auf jedem Gerät fortsetzbar). Highlights:
  - **Würfelbecher-Animation**: Becher erscheint, **schüttelt**, **kippt um** und die Würfel **fallen** mit Bounce und Zufalls-Streuung auf den Tisch — Tempo über die **Würfeldauer** einstellbar, dazu Regler für **Pause zwischen Aktionen**, **KI-Geschwindigkeit** und **Sound** (materialechtes Würfel-„Tok" statt Pieptöne).
  - **Wertungsblock** zentral neben den Würfeln (auf schmalen/niedrigen Schirmen als ein-/ausklappbares Overlay), **Spielende-Dialog** mit Endklassement, **Statistik** (Spiele/Siege/Niederlagen/Bestwert) auf dem Startbildschirm.
  - **Tab-/Geräte-Schutz** wie bei den anderen Spielen, Regeln-Doku DE/EN, vollständig lokalisiert.

## 0.7.32

- 🧹 **Aufgeräumte Benutzerliste** — Die Aktions-Buttons pro Konto sind jetzt durchgehend **kompakte Icons** statt teils Text: „Passwort" → 🔑, „Quota" → 💾, „Freigeben" → ✅. Der **Sprach-Knopf** zeigt nur noch **DE/EN** (ohne 🌐-Kugel). Die Beschriftung steckt jeweils im **Mouseover-Tooltip** — so passt die Zeile auch bei vielen Optionen wieder sauber nebeneinander.

## 0.7.31

- 🃏 **Kartenflug des Spielers in Firefox repariert (66 & 20AB)** — Auf manchen Browsern (v. a. **Firefox**, auch auf älteren Tablets) **sprang die selbst gespielte Karte ohne Flug-Animation sofort auf den Tisch**, während die KI-Karten korrekt flogen. Ursache: Der Spieler-Flug stieß die CSS-Transition nur per `requestAnimationFrame` an — Firefox fasst „Klon erscheint" und „Ziel gesetzt" dann zu einem Schritt zusammen, sodass kein Flug entsteht. Jetzt wird (wie bei den bereits funktionierenden KI-Flügen) vor dem Start ein **Reflow erzwungen**, damit die Startposition zuverlässig festgeschrieben wird. Betrifft Spieler-Flug, Stich-Einzug und Trumpf-/Bube-Tausch in beiden Spielen.

## 0.7.30

- 🌐 **Zweisprachige Mitglieder-Mails (DE/EN)** — Jedes Mitglied hat jetzt ein **Sprachfeld** (Deutsch/Englisch), das bestimmt, in welcher Sprache **alle automatischen E-Mails** ankommen: Zugangsdaten/Willkommen, neues Passwort, Passwort-Zurücksetzen, E-Mail-Bestätigung, „Konto besteht bereits", Konto-Freischaltung, Kommentar-Antworten und die Postfach-Erinnerung. Bei der **Selbst-Registrierung** wird die Sprache automatisch aus der gewählten Seitensprache übernommen; beim **Anlegen im Admin** ist sie wählbar und lässt sich jederzeit über den neuen **🌐-Knopf** in der Benutzerliste umschalten. Mitglieder können ihre Mail-Sprache zudem **selbst im Profil** einstellen. Sämtliche Mailtexte liegen nun lokalisiert in `de.json`/`en.json`.

## 0.7.29

- 🃏 **Präsident: klarerer Spiel-Hinweis & hilfreichere Tipps** — Der verwirrende Platzhalter „Gleichen Rang wählen, dann Spielen drücken" wurde ersetzt durch **„Karte(n) antippen, dann ‚Spielen' – mehrere nur gleichen Werts"**. Die **💡 Tipp-Funktion** wurde von Grund auf überarbeitet: Statt überwiegend „Passen" zu empfehlen, folgt sie jetzt einer echten Strategie (kleine Karten zuerst loswerden, beim Ausspielen **Paare/Drillinge** legen um Gegner zum Passen zu zwingen, günstig überbieten statt zu passen, hohe Karten für die Endphase aufsparen, Gegner blockieren die kurz vorm Ausspielen stehen). Jeder Tipp zeigt zusätzlich eine **kurze Begründung** an (z. B. „— niedrige Karten zuerst loswerden", „— hohe Karten für später aufsparen").

## 0.7.28

- 📱 **Mobile Admin-Ansicht korrigiert** — Im **Benutzer-Tab** (und allen anderen Listen wie Projekte, Seiten, Formulare, Alben, Dateien) lagen auf schmalen Bildschirmen die vielen Aktions-Buttons über dem Namen und waren nicht bedienbar. Die Listenzeilen werden auf Handys jetzt **vertikal gestapelt**: Name/Info oben, die Aktions-Buttons darunter mit **Umbruch** — alles wieder antippbar. Zudem wird im **mobilen Admin-Header** der Schriftzug „MyPage" ausgeblendet (das Haus-Icon bleibt), damit mehr Platz für die Tab-Navigation bleibt.

## 0.7.27

- 🔍 **Volltextsuche** — Eine neue, optionale Suche durchsucht **Blog-Beiträge, Projekte und Seiten** (Titel, Inhalt und Tags, jeweils DE & EN). Ist sie im Design-Tab aktiviert, erscheint ein **Suchfeld im Kopfbereich** der Startseite; die Ergebnisseite (`/suche`) zeigt pro Treffer die Art (Beitrag/Projekt/Seite), den Titel und einen **Auszug mit hervorgehobenen Suchbegriffen**. **Mitglieder-Inhalte** (gesperrte Beiträge/Seiten) erscheinen für Gäste nur als Titel mit 🔒, **ohne Inhalts-Vorschau** — Mitglieder sehen nach Anmeldung die volle Vorschau. Die Suchseite ist auf `noindex` gesetzt.

## 0.7.26

- 📎 **Verschlüsselte Datei-Anhänge in Nachrichten** — Mitglieder können an eine Nachricht eine **Datei anhängen** (max. 25 MB; Bilder, PDF, Office-Dokumente, Archive, Audio/Video). Anhänge werden — wie der Nachrichtentext — **mit Fernet verschlüsselt** auf der Platte abgelegt (`dm_files/`) und nur für die Gesprächsteilnehmer beim Download wieder entschlüsselt; sie werden immer als Datei-Download ausgeliefert (nie inline ausgeführt). Eine Nachricht darf auch **nur aus einem Anhang** bestehen. Beim endgültigen Löschen einer Nachricht wird die Anhang-Datei mitentfernt; Backups sichern die verschlüsselten Anhänge mit.

## 0.7.25

- 📢 **Admin-Rundnachricht an alle Mitglieder** — Im Benutzer-Tab kannst du eine **Ankündigung** verfassen, die im **Postfach aller Mitglieder** landet (verschlüsselt wie normale Nachrichten). Sie erscheint als Unterhaltung mit deinem Seitentitel und 📢-Markierung; Mitglieder können sie lesen und für sich löschen, aber **nicht beantworten**. Setzt aktivierte Mitglieder-Nachrichten voraus.

## 0.7.24

- 👥 **Mitglieder-Verzeichnis (opt-in)** — Mitglieder können sich freiwillig mit **Avatar** und **Kurzvorstellung** in einem internen Verzeichnis zeigen, damit man weiß, wem man schreibt. Sichtbarkeit steuert jedes Mitglied selbst im Profil (Standard: verborgen). Vom Verzeichnis führt ein **„Schreiben"-Knopf** direkt in die Nachrichten (sofern das Mitglied Nachrichten empfängt). Avatare werden quadratisch zugeschnitten, auf 256 px verkleinert und **ohne EXIF-Metadaten** als JPEG gespeichert. Global im Design-Tab ein-/ausschaltbar; das Verzeichnis ist nur für eingeloggte Mitglieder sichtbar.

## 0.7.23

- 🐛 **2FA: Backup-Codes wurden nach dem Einrichten nicht angezeigt** — Nach dem Aktivieren (und beim Neu-Erzeugen) wurden die Backup-Codes sofort wieder ausgeblendet, weil die anschließende Status-Aktualisierung sie überdeckte. Reihenfolge korrigiert: Status zuerst, Codes danach — sie bleiben jetzt sichtbar. Wer 2FA bereits aktiviert hat, holt sich über **„Backup-Codes neu erzeugen"** einen sichtbaren Satz.

## 0.7.22

- 🔔 **HA-Benachrichtigung bei neuer Mitglieder-Nachricht** — Optionaler Schalter (Design-Tab): Bekommt ein Mitglied eine neue Nachricht, erhält der **Betreiber** sofort eine Home-Assistant-Benachrichtigung — ohne Inhalt, je Empfänger zusammengefasst (gleiche Notification-ID, kein Zuspammen). Standard aus; greift nur unter Home Assistant.

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
