"""Einstellungen aus der Oberfläche — settings.json statt Add-on-Optionen.

Bis Version 0.103.1 kamen alle Einstellungen aus `/data/options.json`, also aus
der Home-Assistant-Konfiguration. Das hatte zwei Nachteile: ohne Home Assistant
(Standalone unter Docker) gab es dafür keine Oberfläche, und Tokens sowie
Passwörter lagen im Klartext in jedem Backup.

Dieses Modul hält die Einstellungen stattdessen in `settings.json` im Datenordner
und verschlüsselt die geheimen Felder mit einem eigenen Fernet-Schlüssel
(`settings.key`). In der HA-Konfiguration bleiben nur noch Benutzername, Passwort
und Sitzungsdauer — der Notzugang, falls man sich über die Oberfläche aussperrt.

Vorrang beim Lesen: Standardwerte < options.json < settings.json.

Aufbau eines Feldes:
    key: (typ, standard, extra, gruppe, beschriftung, erklärung)
    typ   'bool' | 'int' | 'float' | 'str' | 'choice'
    extra 'int'/'float' → (min, max) · 'str' → Maximallänge · 'choice' → Werte
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading

import atomic_io

log = logging.getLogger('tuiwatch')

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    _HAS_CRYPTO = True
except Exception:   # Bibliothek fehlt → geheime Felder bleiben ungesetzt
    _HAS_CRYPTO = False

ENC_PREFIX = 'enc:'

# Diese Felder verwaltet weiterhin Home Assistant. Sie dürfen niemals in
# settings.json landen, sonst wäre der Notzugang weg.
LOCKED_KEYS = ('username', 'password', 'session_hours')

# Reihenfolge und Überschriften der Gruppen im Einstellungen-Dialog
GROUPS: tuple = (
    ('poll',      '🔄 Prüfen & Zeitplan'),
    ('market',    '📊 Preisbarometer & Trend'),
    ('notify',    '🔔 Benachrichtigungen'),
    ('digest',    '📰 Wochenbericht'),
    ('aktion',    '🏷️ Aktionscodes'),
    ('telegram',  '✈️ Telegram'),
    ('mail',      '📧 E-Mail (SMTP)'),
    ('nextcloud', '📇 Nextcloud-Adressbuch'),
    ('ai',        '✦ KI'),
    ('modules',   '🧩 Zusatzmodule'),
    ('share',     '🌍 Öffentliche Angebots-Links'),
    ('backup',    '💾 Backup'),
    ('misc',      '⚙️ Sonstiges'),
)

FIELDS: dict = {
    # ── poll ──
    "poll_interval": ("int", 21600, (600, 604800), "poll",
        "Prüfintervall (Sekunden)",
        "Pause zwischen zwei automatischen Preisprüfungen. Reisepreise ändern sich langsam — Standard 21600 (6 Stunden), Minimum 600 (10 Minuten). Bitte fair wählen, nicht im Minutentakt."),
    "poll_gap": ("int", 10, (0, 300), "poll",
        "Abstand zwischen Abrufen (Sekunden)",
        "Pause zwischen zwei aufeinanderfolgenden Hintergrund-Abrufen (Angebote und Suchabos werden nacheinander geprüft). Verhindert einen Abruf-Burst, wenn viele Angebote gleichzeitig fällig sind. Standard 10, dazu 0–5 Sekunden Zufall; 0 schaltet die Pause ab."),
    "calendar_daily_refresh": ("bool", True, None, "poll",
        "Täglicher Kalender-Refresh",
        "Hält den Preiskalender aktiver Angebote 1×/Tag aktuell (macht Trend-Ansicht und Buchungsscore-Signal aussagekräftiger). Standard an."),
    "calendar_archived_refresh": ("bool", True, None, "poll",
        "Kalender bei archivierten Angeboten weiterführen",
        "Ruft den Preiskalender auch für archivierte (abgelaufene) Angebote weiter ab — alle 3 Tage statt täglich, und immer erst nachdem die aktiven Angebote dran waren. Der Preis des abgelaufenen Angebots wird weiterhin NICHT geprüft; der Kalender beschreibt aber Hotel, Zimmer, Verpflegung und Dauer und schaut immer ab heute nach vorn. So wächst über Jahre ein Preisverlauf für dasselbe Hotel weiter. Fällt ein Hotel aus dem TUI-Inventar, pausiert der Kalender nach 5 Fehlschlägen in Folge von selbst. Standard an."),
    # ── market ──
    "market_trend_threshold": ("float", 1.0, (0.0, 100.0), "market",
        "Schwelle für Markttrend (%)",
        "Kumulierte Preisbewegung über 14 Tage, ab der der Markttrend als steigend/fallend statt stabil gilt. Standard 1.0 — kleinerer Wert reagiert empfindlicher auf kleine Bewegungen."),
    "market_basket_enabled": ("bool", True, None, "market",
        "Preisbarometer",
        "Führt 1×/Tag jede deiner gespeicherten Suchen erneut aus (mit deinen Reiseterminen und Filtern) und berechnet den Markttrend aus allen gefundenen Hotels statt nur aus deinen Angeboten. Deutlich breitere Basis, und der Trend gilt genau für deinen Reisetermin. Standard an."),
    "market_basket_lead_days": ("int", 91, (1, 720), "market",
        "Ersatz-Vorlaufzeit fürs Preisbarometer (Tage)",
        "Nur Rückfallebene: Messreihen holen ihren Reisetermin aus der gespeicherten Suche bzw. dem getrackten Angebot. Fehlt dort ein Datum, wird ersatzweise „heute + X Tage“ gesucht. Standard 91."),
    "market_basket_max_regions": ("int", 20, (1, 200), "market",
        "Maximale Messreihen",
        "Obergrenze für die täglich abgefragten Messreihen (1…50), also für die Zahl der gespeicherten Suchen, die neu ausgeführt werden. Reiner Lastschutz: je 50 Hotels ein API-Aufruf pro Tag (typisch 1–6 je Suche). Werden mehr gefunden als erlaubt, nennt das Add-on-Log die weggelassenen. Standard 20."),
    "booking_window_enabled": ("bool", True, None, "market",
        "Buchungszeitpunkt-Ampel",
        "Wertet die Tagesbewegungen des Preisbarometers zusätzlich nach Vorlaufzeit aus (Booking-Kurve) und leitet daraus eine Ampel ab: grün = guter Buchungszeitpunkt, rot = eher warten. Verrechnet den 14-Tage-Trend, die Lage im bisherigen Verlauf und die bis zur Abreise erwartete Preisbewegung. Braucht das Preisbarometer und einige Wochen Daten. Standard an."),
    # ── notify ──
    "ha_sensors": ("bool", True, None, "notify",
        "Home-Assistant-Sensoren",
        "Je verfolgtem Angebot einen Sensor (sensor.tuiwatch_<hotelname>) in Home Assistant anlegen. Wert = aktueller Preis in €, bei Fehler 'unknown'; Reise-Eckdaten stehen im Attribut 'description'. Standard an."),
    "notify_ha": ("bool", True, None, "notify",
        "HA-Benachrichtigungen",
        "Bei Preisänderung oder erreichtem Wunschpreis eine persistente Home-Assistant-Benachrichtigung anzeigen. Standard an."),
    "ha_notify_service": ("str", "", 400, "notify",
        "Zusätzlicher HA-Notify-Dienst",
        "Optional: Name eines notify-Dienstes (z. B. mobile_app_mein_handy für Push über die Companion-App), an den jede Benachrichtigung zusätzlich geht. Mehrere Dienste mit Komma trennen; leer = nur persistente Benachrichtigung."),
    "notify_price_change": ("bool", True, None, "notify",
        "Bei jeder Preisänderung benachrichtigen",
        "Benachrichtigen, sobald sich ein Preis ändert (gestiegen/gefallen). Wunschpreis-Benachrichtigungen kommen unabhängig davon immer. Standard an."),
    "notify_cheaper_date": ("bool", True, None, "notify",
        "Günstigerer-Termin-Alarm",
        "Benachrichtigen, wenn der Preiskalender einen anderen Abreisetag (auch außerhalb deines Zeitraums) deutlich günstiger zeigt als dein getrackter Preis. Standard an."),
    "cheaper_date_min_diff": ("int", 50, (0, 10000), "notify",
        "Mindest-Ersparnis für Termin-Alarm (€)",
        "Ab welcher Ersparnis pro Person der Günstigerer-Termin-Alarm auslöst. Standard 50 €."),
    "notify_calendar_trend": ("bool", True, None, "notify",
        "Kalender-Preisänderung",
        "Benachrichtigen, wenn sich im Preiskalender eines Angebots ein Preis für ein bereits bekanntes Reisedatum ändert (Hotelname + betroffener Monat, keine Details). Standard an."),
    "calendar_trend_min_diff": ("int", 20, (0, 10000), "notify",
        "Mindest-Änderung für Kalender-Preisänderung (€)",
        "Ab welcher Preisänderung pro Reisedatum die Kalender-Preisänderung-Benachrichtigung auslöst. Standard 20 € — kleinere Schwankungen werden nicht gemeldet (im Kalender selbst, Trend-Ansicht, weiterhin sichtbar, nur die Benachrichtigung wird gefiltert)."),
    "notify_errors": ("bool", True, None, "notify",
        "Ausverkauft-/Fehler-Alarm",
        "Benachrichtigen, wenn ein Angebot mehrmals hintereinander kein Ergebnis liefert (Kontingent ausgebucht oder URL veraltet). Standard an."),
    "notify_api_errors": ("bool", True, None, "notify",
        "API-Ausfall-Alarm",
        "Benachrichtigen, wenn der API-Selbsttest einen kritischen TUI-Endpunkt als gestört erkennt (TUI hat evtl. die API geändert), und Entwarnung geben, sobald wieder alles läuft. Standard an."),
    "notify_unavailable": ("bool", True, None, "notify",
        "Alarm nicht mehr buchbar",
        "Benachrichtigen, wenn das TUI-Buchungssystem ein zuvor bestätigtes Angebot nicht mehr bestätigt (evtl. ausgebucht) — und Entwarnung geben, sobald es wieder bestätigt wird. Standard an."),
    "notify_booking_changes": ("bool", True, None, "notify",
        "Alarm Buchungsdetails geändert",
        "Benachrichtigen, wenn sich bestätigte Buchungsdetails eines Angebots ändern: Flugzeiten/Flugnummern/Buchungsklasse oder die Veranstalter-Hinweise (Errata). Standard an."),
    "notify_booked_drop": ("bool", True, None, "notify",
        "Alarm günstiger als gebucht",
        "Benachrichtigen, wenn der Preis nach deiner Buchung unter den hinterlegten gebuchten Preis fällt (Umbuchen könnte sich lohnen). Standard an."),
    "booked_drop_min_diff": ("int", 50, (0, 10000), "notify",
        "Mindest-Ersparnis unter Buchungspreis (€)",
        "Ab welcher Ersparnis pro Person der Alarm günstiger als gebucht auslöst. Standard 50 €."),
    "notify_share_comments": ("bool", True, None, "notify",
        "Benachrichtigung bei neuen Kommentaren",
        "Meldet jeden neuen Kommentar auf einer geteilten Seite über Home Assistant und Telegram — mit Name, Text und Absender-IP. Standard an."),
    # ── digest ──
    "digest_enabled": ("bool", False, None, "digest",
        "Wochenüberblick senden",
        "Wöchentliche Zusammenfassung (größte Rückgänge, neue Tiefstwerte, Angebote unter Wunschpreis) per Telegram und/oder E-Mail verschicken. Benötigt Telegram oder SMTP. Standard aus."),
    "digest_weekday": ("int", 1, (1, 7), "digest",
        "Wochentag für den Überblick",
        "An welchem Wochentag der Wochenüberblick verschickt wird: 1 = Montag … 7 = Sonntag. Standard 1 (Montag)."),
    # ── aktion ──
    "notify_aktionscodes": ("bool", True, None, "aktion",
        "Aktionscode-Alarm",
        "Benachrichtigen, wenn neue öffentliche TUI-Aktionscodes erscheinen. Standard an."),
    "aktionscode_min": ("int", 0, (0, 100000), "aktion",
        "Mindestwert für Aktionscode-Alarm (€)",
        "Nur Aktionscodes ab diesem Wert melden (0 = alle). Standard 0."),
    "aktionscode_interval": ("int", 21600, (1800, 604800), "aktion",
        "Aktionscode-Prüfintervall (Sekunden)",
        "Wie oft die öffentlichen Aktionscodes geprüft werden. Standard 21600 (6 Stunden), Minimum 1800."),
    # ── telegram ──
    "telegram_bot_token": ("str", "", 400, "telegram",
        "Telegram Bot Token",
        "Token eines Telegram-Bots (Format 123456789:ABC-...), um Benachrichtigungen per Telegram zu erhalten. Leer lassen, um Telegram zu deaktivieren. Bot erstellen via @BotFather."),
    "telegram_chat_id": ("str", "", 400, "telegram",
        "Telegram Chat ID",
        "Chat-ID des Empfängers für Telegram-Nachrichten. Ermitteln via @userinfobot oder dem Bot /start schicken."),
    # ── mail ──
    "smtp_host": ("str", "", 400, "mail",
        "SMTP-Server",
        "Mailserver für den E-Mail-Versand der Angebote (z. B. smtp.gmail.com). Leer lassen = E-Mail-Funktion aus."),
    "smtp_port": ("int", 587, (1, 65535), "mail",
        "SMTP-Port",
        "Port des Mailservers. 587 für STARTTLS (Standard), 465 für SSL."),
    "smtp_user": ("str", "", 400, "mail",
        "SMTP-Benutzer",
        "Benutzername/Anmeldung am Mailserver (oft die E-Mail-Adresse)."),
    "smtp_password": ("str", "", 400, "mail",
        "SMTP-Passwort",
        "Passwort bzw. App-Passwort für den Mailserver."),
    "smtp_from": ("str", "", 400, "mail",
        "Absenderadresse",
        "Sichtbare Absenderadresse. Leer = SMTP-Benutzer wird verwendet."),
    "smtp_to": ("str", "", 400, "mail",
        "Standard-Empfänger",
        "Vorbelegter Empfänger für die Angebots-E-Mail (kann vor dem Senden im UI geändert werden)."),
    "smtp_tls": ("bool", True, None, "mail",
        "STARTTLS verwenden",
        "An = STARTTLS (Port 587). Aus = SSL/TLS direkt (Port 465)."),
    # ── nextcloud ──
    "nc_addressbook_url": ("str", "", 400, "nextcloud",
        "Nextcloud-Adressbuch-URL",
        "Volle CardDAV-URL des Adressbuchs, wie sie Nextcloud in der Kontakte-App zum Kopieren anbietet (z. B. https://cloud.example.com/remote.php/dav/addressbooks/users/nutzer/contacts/). Leer lassen = kein Adressbuch, E-Mail-Empfänger bleibt Freitext."),
    "nc_user": ("str", "", 400, "nextcloud",
        "Nextcloud-Benutzername",
        "Nextcloud-Benutzername für den Zugriff auf das Adressbuch."),
    "nc_app_password": ("str", "", 400, "nextcloud",
        "Nextcloud-App-Passwort",
        "App-Passwort (nicht das normale Login-Passwort!) — erstellbar unter Nextcloud-Einstellungen → Sicherheit → Geräte & Sitzungen → Neues App-Passwort."),
    # ── ai ──
    "ai_provider": ("choice", "anthropic", ("anthropic", "gemini", "perplexity"), "ai",
        "KI-Anbieter",
        "Welcher KI-Anbieter für ALLE KI-Features genutzt wird (KI-Fazit, Vergleich, TripPilot/Tagesausflug, Auto-Tags, Portfolio-Frage). anthropic = Claude (Standard), gemini = Google Gemini (z. B. für Google-Search-Grounding), perplexity = Perplexity Sonar (auf Websuche spezialisiert, teurer). Braucht den jeweils passenden API-Key unten. Sind mehrere Keys hinterlegt, lässt sich im Footer der Web-Oberfläche live umschalten."),
    "anthropic_api_key": ("str", "", 400, "ai",
        "Anthropic API-Key",
        "API-Key für Claude (console.anthropic.com), aktiviert das 'KI-Fazit' in der Hotelsuche (Lage, Zimmer, Restaurants, Pool, Ausstattung). Leer lassen = Funktion aus."),
    "anthropic_model": ("choice", "claude-opus-5", ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5", "claude-fable-5"), "ai",
        "Claude-Modell fürs KI-Fazit",
        "Welches Claude-Modell für die Hotel-Zusammenfassung genutzt wird. Opus = Standard, sehr gründlich. Sonnet = schneller/günstiger bei kaum schlechterer Qualität. Haiku = am günstigsten, kürzer. Fable = leistungsfähigstes Modell, teuerster Aufruf."),
    "gemini_api_key": ("str", "", 400, "ai",
        "Gemini API-Key",
        "API-Key für Google Gemini (aistudio.google.com), nur relevant wenn 'KI-Anbieter' = gemini. Leer lassen = Funktion aus."),
    "gemini_model": ("choice", "gemini-3.1-pro", ("gemini-3.1-pro", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-flash"), "ai",
        "Gemini-Modell",
        "Welches Gemini-Modell genutzt wird, wenn 'KI-Anbieter' = gemini. 3.1 Pro = Flaggschiff, sehr gründlich. 3.6 Flash = neuestes Flash-Modell, günstiger als 3.5. 3.5 Flash = ausgewogen. 2.5 Flash = am günstigsten, wird aber am 16.10.2026 von Google abgeschaltet — rechtzeitig umstellen."),
    "perplexity_api_key": ("str", "", 400, "ai",
        "Perplexity API-Key",
        "API-Key für Perplexity (perplexity.ai/settings/api), nur relevant wenn 'KI-Anbieter' = perplexity. Angesprochen wird die Agent API; TUIWatch schaltet die Websuche je Aufgabe zu (Recherche ja, interne Aufgaben wie Auto-Tags nein), ein Websuche-Schalter ist nicht nötig. Recherche-Aufrufe sind teurer als bei Claude/Gemini, inkl. zusätzlicher Request-Gebühr oben auf die Tokenkosten. Die angezeigten Kosten sind hier keine Schätzung, sondern der von Perplexity je Aufruf abgerechnete Betrag. Leer lassen = Funktion aus."),
    "perplexity_model": ("choice", "pplx-low", ("pplx-fast", "pplx-low", "pplx-medium", "pplx-high", "pplx-xhigh"), "ai",
        "Perplexity-Stufe",
        "Wie gründlich Perplexity recherchiert, wenn 'KI-Anbieter' = perplexity. pplx-fast = einzelne Fakten, Definitionen, kurze Zusammenfassungen. pplx-low = Standard, alltägliche Recherchefragen mit aktuellen Informationen. pplx-medium = mehrstufiges Browsen, breite Auswertung über viele Quellen. pplx-high = Expertenniveau mit erschöpfender Quellenabdeckung. pplx-xhigh = wie high, mit noch größerem Budget. Diese Stufen (Perplexity nennt sie Presets) haben die früheren Sonar-Modelle abgelöst; eine bestehende Sonar-Auswahl wird automatisch auf die entsprechende Stufe gehoben (sonar-pro wird pplx-low usw.)."),
    "ai_max_web_searches": ("int", 12, (0, 50), "ai",
        "Max. Websuchen pro KI-Aufruf",
        "Deckelt, wie oft Claude bei einem einzelnen KI-Aufruf (Fazit, Vergleich, Reiseberater/TripPilot, Tagesausflug) selbstständig das Web durchsuchen darf. Mehr Suchen = gründlicher, aber mehr Input-Tokens und höhere Kosten. Standard 12 — z. B. 8 für sparsamer, 20 für sehr gründlich bei mehreren Zielen/Hotels. Gilt nur bei Anthropic/Claude — Gemini/Perplexity kennen kein Limit für die Anzahl Websuchen."),
    "perplexity_timeout": ("int", 300, (60, 900), "ai",
        "Perplexity: Zeitlimit je Anfrage (Sekunden)",
        "Wie lange auf eine Perplexity-Antwort gewartet wird, bevor abgebrochen wird. Anders als bei Claude/Gemini führt eine Stufe eine mehrstufige Recherche aus, die je nach Frage Minuten dauern kann — Perplexity selbst spricht bei den gründlichen Stufen von Laufzeiten im Minutenbereich. Standard 300 (5 Minuten). Höher setzen, wenn Vergleiche über mehrere Ziele mit 'Read timed out' abbrechen; niedriger, wenn lieber früh abgebrochen werden soll. Gilt nur für Perplexity."),
    "ai_prompt_preview": ("bool", False, None, "ai",
        "KI-Prompt vor dem Senden anzeigen",
        "Zeigt bei interaktiven KI-Anfragen (KI-Fazit, Vergleich, Buchungsscore, Kalender-Analyse, Region-Ausblick, Portfolio-Frage, TripPilot/Tagesausflug, Verlauf-Wiederholen, Folgefrage) den fertigen Prompt vorher in einem editierbaren Fenster an — erst nach Bestätigung/ggf. Anpassung wird er wirklich an die KI geschickt. Automatische Hintergrund-Läufe (Wochenüberblick, Aktionscode-Check, Auto-Tags) sind davon nicht betroffen. Standard aus."),
    # ── modules ──
    "enable_check24_compare": ("bool", False, None, "modules",
        "Check24-Preisvergleich (Beta)",
        "Erlaubt, ein Angebot mit einem manuell verknüpften Check24-Hotel zu vergleichen (andere Reiseveranstalter, gleiche Reisedaten). Nutzt Headless-Chromium gegen Check24 (kein offenes API), daher fragiler als der TUI-Abruf und ein zusätzliches externes ToS-Risiko. Standard aus — bewusst opt-in."),
    "enable_str_flights": ("bool", False, None, "modules",
        "Flugplan ab Stuttgart Airport (STR)",
        "Schaltet den ✈️-Knopf in der Kopfzeile frei: eigenständige Suche nach Linienflug-Verbindungen ab/nach STR (Fluggesellschaft, Wochentage, Zeiten, Saisonzeitraum) über Zielflughafen oder Land. Nutzt das offene JSON-API des Flughafen-Betreibers, unabhängig von TUI-/Check24-Angeboten. Standard aus."),
    "enable_fra_flights": ("bool", False, None, "modules",
        "Flugplan ab Frankfurt Airport (FRA)",
        "Ergänzt den ✈️-Knopf um den Flugplan ab/nach Frankfurt. Anders als beim Stuttgarter Flugplan liefert Frankfurt Einzelflüge je Datum (statt Saisonstrecken mit Wochentagen) — dafür mit Terminal, Halle, Gate, Check-in-Schaltern, Flugzeugtyp und Codeshare-Nummern. Sind beide Flughäfen aktiv, fragt der ✈️-Knopf zuerst nach dem Flughafen. Nutzt das offene JSON der Flughafen-Website, unabhängig von TUI-/Check24-Angeboten. Standard aus."),
    "enable_muc_flights": ("bool", False, None, "modules",
        "Flugplan ab München Airport (MUC)",
        "Ergänzt den ✈️-Knopf um den Flugplan ab/nach München. München bietet kein Flugplan-API — die Daten stammen aus dem offiziellen Saison-Flugplan-PDF des Flughafens (rund 3.300 Verbindungen mit Wochentagen, Zeiten, Terminal und Gültigkeitszeitraum, wie beim Stuttgarter Plan). Das PDF wird täglich neu erzeugt; das Add-on prüft alle drei Stunden, ob eine neue Fassung hängt, und liest sie nur dann neu ein. Achtung: Das PDF deckt immer nur die laufende Saison ab (Sommer bzw. Winter), nicht 12 Monate im Voraus. Standard aus."),
    "enable_fkb_flights": ("bool", False, None, "modules",
        "Saisonflugplan ab Karlsruhe/Baden-Baden (FKB)",
        "Ergänzt den ✈️-Knopf um den Saisonflugplan ab/nach Karlsruhe/Baden-Baden (FKB, „Baden-Airpark“). Zeigt rund 1.000 Verbindungen mit Wochentagen, Zeiten, Flugzeugtyp, Airline und Gültigkeitszeitraum — anders als München über mehrere Saisons hinweg (Sommer- und Winterflugplan des laufenden und nächsten Jahres). Die Daten stammen aus der Saisonflugplan-Ansicht der Flughafen-Website; sie liefert fertiges HTML statt Daten, das Add-on liest es aus und hält es sechs Stunden im Speicher. Standard aus."),
    # ── share ──
    "enable_public_share": ("bool", False, None, "share",
        "Öffentliche Angebots-Links",
        "Schaltet Links frei, mit denen sich ausgewählte Angebote ohne Login anschauen lassen (wie die Angebotsseite eines Reisebüros) — inklusive gespeicherter Klimatabelle, Reiseführer und Reiseberater-Ergebnis. Die Seite läuft auf einem eigenen Port (siehe „Port für öffentliche Links“), zeigt nur einen beim Erzeugen eingefrorenen Stand und erlaubt keinerlei Abfragen. Nur diesen zweiten Port im Reverse-Proxy nach außen geben, niemals 17794. Standard aus."),
    "public_port": ("int", 17796, (1, 65535), "share",
        "Port für öffentliche Links",
        "Port, auf dem die öffentlichen Angebots-Seiten ausgeliefert werden. Standard 17796. Der Port muss zusätzlich in der Konfiguration des Add-ons unter „Netzwerk“ veröffentlicht werden, sonst ist er nur containerintern erreichbar."),
    "public_base_url": ("str", "", 400, "share",
        "Öffentliche Basis-URL",
        "Adresse, unter der die öffentlichen Links von außen erreichbar sind, z. B. https://reise.example.com — daraus baut TUIWatch den fertigen Link zum Weitergeben. Bleibt das Feld leer, wird nur der Pfad /s/<token> angezeigt."),
    "public_share_days": ("int", 30, (1, 365), "share",
        "Gültigkeit öffentlicher Links (Tage)",
        "Voreingestellte Gültigkeit beim Erzeugen eines öffentlichen Links. Danach zeigt der Link nur noch einen Hinweis; im Dialog lässt sich pro Link ein anderer Wert wählen (1 bis 365). Standard 30."),
    # ── backup ──
    "auto_backup": ("bool", True, None, "backup",
        "Automatisches Backup",
        "Wöchentlich ein vollständiges Backup (Angebote inkl. Verlauf, Reisen inkl. PDF, gespeicherte Suchen) als ZIP unter /addon_config/backups ablegen — übersteht eine Neuinstallation des Add-ons. Standard an."),
    "auto_backup_keep": ("int", 5, (0, 60), "backup",
        "Auto-Backups behalten (Anzahl)",
        "Wie viele automatische Backups aufbewahrt werden; ältere werden gelöscht. Standard 5."),
    # ── misc ──
    "trippilot_home_location": ("str", "", 400, "misc",
        "TripPilot Heimatort (PLZ/Ort)",
        "Vorbelegung für die TripPilot-Frage 'Von wo geht's los?' (bei Anreise mit Auto/Bus/Bahn oder Tagesausflug). Leer lassen, wenn nicht gewünscht — im Fragebogen jederzeit änderbar."),
    "verbose_log": ("bool", False, None, "misc",
        "Ausführliches Logging",
        "Gibt mehr Details pro Prüfung im Log aus. Standard aus — nur Fehler und wichtige Ereignisse werden geloggt."),
}

# Verschlüsselt gespeichert und nie an den Browser zurückgegeben.
SECRET_KEYS = frozenset({
    'telegram_bot_token', 'smtp_password', 'nc_app_password',
    'anthropic_api_key', 'gemini_api_key', 'perplexity_api_key',
})

# Diese Werte liest TUIWatch nur beim Start: der zweite Webserver für die
# öffentlichen Angebots-Seiten wird einmalig gebunden (_start_public_server).
RESTART_KEYS = frozenset({'enable_public_share', 'public_port'})

_lock = threading.Lock()
_path = ''
_key_path = ''
_fernet = None
_cache: dict = {}
_cache_mtime = -1.0


def init(data_dir: str) -> None:
    """Pfade festlegen. Muss einmal beim Start aufgerufen werden.

    Cache und Schlüssel werden dabei verworfen: sie gehören zum alten Datenordner
    und wären nach einem Wechsel schlicht falsch (im Betrieb läuft `init` genau
    einmal, in den Tests dagegen je Fixture mit einem frischen tmp-Verzeichnis).
    """
    global _path, _key_path
    _path = os.path.join(data_dir, 'settings.json')
    _key_path = os.path.join(data_dir, 'settings.key')
    reset_cache()


def path() -> str:
    return _path


def key_path() -> str:
    return _key_path


def reset_cache() -> None:
    """Cache und Schlüssel verwerfen — nach einem Restore kann beides neu sein."""
    global _cache, _cache_mtime, _fernet
    with _lock:
        _cache, _cache_mtime, _fernet = {}, -1.0, None


def _get_fernet(create: bool = False):
    """Fernet-Instanz zum Schlüssel im Datenordner.

    `create=False` (Lesen/Entschlüsseln) legt bewusst KEINEN Schlüssel an: sonst
    entstünde direkt nach einem Restore ein frischer Zufallsschlüssel, und der
    danach eingespielte echte Schlüssel gälte als „anderer" und würde abgelehnt.
    Erzeugt wird nur, wenn wirklich etwas verschlüsselt werden soll.
    """
    global _fernet
    if _fernet is not None:
        return _fernet
    if not _HAS_CRYPTO or not _key_path:
        return None
    try:
        if os.path.exists(_key_path):
            with open(_key_path, 'rb') as f:
                key = f.read().strip()
        elif not create:
            return None
        else:
            key = Fernet.generate_key()
            # atomar: ein halb geschriebener Schlüssel macht ALLE verschlüsselten
            # Felder unlesbar (siehe atomic_io)
            atomic_io.write_bytes(_key_path, key, mode=0o600)
            log.info("Schlüssel für die Einstellungen neu erzeugt")
        _fernet = Fernet(key)
        return _fernet
    except Exception as e:
        log.warning("Schlüssel für die Einstellungen nicht nutzbar: %s", e)
        return None


def _encrypt(value: str) -> str:
    if not value:
        return ''
    f = _get_fernet(create=True)
    if f is None:
        # Ohne Verschlüsselung lieber gar nicht speichern, als den Token im
        # Klartext in den Datenordner (und damit ins Backup) zu schreiben.
        log.warning("Geheimes Feld nicht gespeichert — Verschlüsselung nicht verfügbar")
        return ''
    return ENC_PREFIX + f.encrypt(value.encode('utf-8')).decode('ascii')


def _decrypt(value: str) -> str:
    if not isinstance(value, str) or not value.startswith(ENC_PREFIX):
        return value if isinstance(value, str) else ''
    f = _get_fernet()
    if f is None:
        return ''
    try:
        return f.decrypt(value[len(ENC_PREFIX):].encode('ascii')).decode('utf-8')
    except (InvalidToken, ValueError):
        # Passiert, wenn settings.json aus einem Backup kommt, settings.key aber
        # nicht — dann ist der Wert verloren und muss neu eingetragen werden.
        log.warning("Geheimes Feld konnte nicht entschlüsselt werden (falscher Schlüssel?)")
        return ''


def _read_raw() -> dict:
    """settings.json roh lesen (Geheimes noch verschlüsselt), mit mtime-Cache."""
    global _cache, _cache_mtime
    if not _path:
        return {}
    try:
        mtime = os.path.getmtime(_path)
    except OSError:
        return {}
    if mtime != _cache_mtime:
        try:
            with open(_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _cache = data if isinstance(data, dict) else {}
            _cache_mtime = mtime
        except Exception as e:
            log.warning("settings.json nicht lesbar: %s", e)
            return _cache or {}
    return _cache


def load() -> dict:
    """Alle gesetzten Einstellungen, geheime Felder entschlüsselt."""
    out = {}
    for key, value in _read_raw().items():
        if key not in FIELDS:
            continue
        out[key] = _decrypt(value) if key in SECRET_KEYS else value
    return out


def exists() -> bool:
    return bool(_path) and os.path.exists(_path)


def coerce(key: str, value):
    """Einen Wert auf den Typ des Feldes bringen. None = ungültig, ignorieren."""
    spec = FIELDS.get(key)
    if spec is None:
        return None
    kind, default, extra = spec[0], spec[1], spec[2]
    if kind == 'bool':
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ('1', 'true', 'yes', 'on')
        return bool(value)
    if kind in ('int', 'float'):
        try:
            n = int(str(value).strip()) if kind == 'int' else float(str(value).strip().replace(',', '.'))
        except (TypeError, ValueError):
            return None
        lo, hi = extra
        return max(lo, min(hi, n))
    if kind == 'choice':
        v = str(value or '').strip()
        return v if v in extra else default
    v = str(value if value is not None else '').strip()
    return v[:extra]


def save(values: dict, clear=()) -> list:
    """Einstellungen schreiben. Gibt die tatsächlich geänderten Schlüssel zurück.

    `values` enthält nur Felder, die der Benutzer angefasst hat; geheime Felder
    ohne neuen Wert bleiben unverändert. `clear` leert einzelne Felder gezielt.
    """
    with _lock:
        raw = dict(_read_raw())
        changed = []
        for key in clear or ():
            if key in FIELDS and raw.get(key) not in (None, ''):
                raw[key] = '' if FIELDS[key][0] in ('str', 'choice') else FIELDS[key][1]
                changed.append(key)
        for key, value in (values or {}).items():
            if key not in FIELDS or key in LOCKED_KEYS:
                continue
            new = coerce(key, value)
            if new is None:
                continue
            if key in SECRET_KEYS:
                if new == '':
                    continue          # leeres Feld heißt „unverändert lassen"
                new = _encrypt(new)
                if not new:
                    continue          # Verschlüsselung nicht möglich
            if raw.get(key) != new:
                raw[key] = new
                changed.append(key)
        if not changed:
            return []
        _write(raw)   # OSError meldet der Aufrufer als Fehler an die Oberfläche
        return changed


def _write(raw: dict) -> None:
    global _cache, _cache_mtime
    atomic_io.write_json(_path, raw, mode=0o600, indent=2, ensure_ascii=False)
    _cache = raw
    try:
        _cache_mtime = os.path.getmtime(_path)
    except OSError:
        _cache_mtime = -1.0



# ── Schlüssel sichern und zurückholen ─────────────────────────────────────────
# Der Schlüssel liegt bewusst nicht im Backup — sonst wäre die Verschlüsselung
# der Zugangsdaten dort wertlos. Damit ein Restore auf einer frischen
# Installation trotzdem gelingt, lässt sich der Schlüssel einzeln exportieren:
# verpackt mit einer Passphrase, die nur der Nutzer kennt. Die exportierte Datei
# darf deshalb neben dem Backup liegen — ohne Passphrase ist sie wertlos.
EXPORT_FORMAT = 'tuiwatch-settings-key'
KEY_EXPORT_VERSION = 1
KEY_PASSPHRASE_MIN = 10
# scrypt-Parameter: 32 MB Speicher je Versuch. Bremst Wörterbuchangriffe auf die
# Passphrase spürbar aus und bleibt für einen einzelnen Export unmerklich.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 15, 8, 1


def _passphrase_key(passphrase: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode('utf-8')))


def export_key(passphrase: str) -> bytes:
    """Schlüssel mit einer Passphrase verpackt ausgeben (JSON-Datei).

    Wirft ValueError, wenn es noch keinen Schlüssel gibt oder die Passphrase zu
    kurz ist — beides meldet die Oberfläche im Klartext.
    """
    if not _HAS_CRYPTO:
        raise ValueError('crypto_unavailable')
    if len(passphrase or '') < KEY_PASSPHRASE_MIN:
        raise ValueError('passphrase_short')
    if not os.path.exists(_key_path):
        raise ValueError('no_key')
    with open(_key_path, 'rb') as f:
        raw = f.read().strip()
    salt = os.urandom(16)
    blob = Fernet(_passphrase_key(passphrase, salt)).encrypt(raw)
    return json.dumps({
        'format': EXPORT_FORMAT,
        'version': KEY_EXPORT_VERSION,
        'kdf': 'scrypt', 'n': _SCRYPT_N, 'r': _SCRYPT_R, 'p': _SCRYPT_P,
        'salt': base64.b64encode(salt).decode('ascii'),
        'key': blob.decode('ascii'),
    }, indent=2).encode('utf-8')


def import_key(data: bytes, passphrase: str, overwrite: bool = False) -> int:
    """Exportierten Schlüssel zurückschreiben. Gibt die Zahl lesbarer Geheimfelder zurück.

    Wirft ValueError mit einem der Gründe: crypto_unavailable, invalid_file,
    wrong_passphrase, exists (es liegt bereits ein anderer Schlüssel da und
    `overwrite` wurde nicht gesetzt).
    """
    if not _HAS_CRYPTO:
        raise ValueError('crypto_unavailable')
    try:
        meta = json.loads(data.decode('utf-8'))
        salt = base64.b64decode(meta['salt'])
        blob = str(meta['key']).encode('ascii')
        n, r, p = int(meta.get('n', _SCRYPT_N)), int(meta.get('r', _SCRYPT_R)), int(meta.get('p', _SCRYPT_P))
    except Exception:
        raise ValueError('invalid_file')
    # Parameter aus der Datei nur innerhalb vernünftiger Grenzen übernehmen:
    # eine manipulierte Datei soll den Server nicht mit 16 GB scrypt beschäftigen.
    if not (2 ** 12 <= n <= 2 ** 17 and 1 <= r <= 16 and 1 <= p <= 4):
        raise ValueError('invalid_file')
    try:
        kdf = Scrypt(salt=salt, length=32, n=n, r=r, p=p)
        wrap = Fernet(base64.urlsafe_b64encode(kdf.derive((passphrase or '').encode('utf-8'))))
        raw = wrap.decrypt(blob).strip()
        Fernet(raw)          # muss ein gültiger Fernet-Schlüssel sein
    except (InvalidToken, ValueError, TypeError):
        raise ValueError('wrong_passphrase')
    # Ein vorhandener, anderer Schlüssel darf nur nach ausdrücklicher Bestätigung
    # weichen — mit ihm verschlüsselte Zugangsdaten wären danach unlesbar. Schließt
    # er dagegen gar nichts auf (frische Installation, alles leer), ist nichts zu
    # verlieren und der Import läuft ohne Rückfrage durch.
    if os.path.exists(_key_path) and not overwrite:
        with open(_key_path, 'rb') as f:
            current = f.read().strip()
        if current != raw and any(load().get(k) for k in SECRET_KEYS):
            raise ValueError('exists')
    with _lock:
        atomic_io.write_bytes(_key_path, raw, mode=0o600)
    reset_cache()
    return sum(1 for k in SECRET_KEYS if load().get(k))


def key_exists() -> bool:
    return bool(_key_path) and os.path.exists(_key_path)


def crypto_ready() -> bool:
    """Lassen sich geheime Felder speichern?

    Nicht dasselbe wie „es gibt bereits einen Schlüssel“: auf einer frischen
    Installation entsteht der erst beim ersten Speichern eines Geheimfeldes
    (`_get_fernet(create=True)`). Bis 0.113.6 fragte die Oberfläche stattdessen
    `_get_fernet()` — das legt bewusst keinen an — und meldete deshalb
    „Verschlüsselung nicht verfügbar“, obwohl gar nichts fehlte.

    Gefragt ist also: Bibliothek vorhanden, und der Schlüssel entweder da und
    brauchbar oder im Datenordner anlegbar.
    """
    if not _HAS_CRYPTO or not _key_path:
        return False
    if os.path.exists(_key_path):
        return _get_fernet() is not None
    return os.access(os.path.dirname(_key_path) or '.', os.W_OK)

def migrate(options: dict) -> bool:
    """Beim ersten Start die bisherigen Add-on-Optionen übernehmen.

    Läuft nur, solange settings.json fehlt. Geheime Felder werden dabei
    verschlüsselt — der Klartext bleibt in options.json stehen, bis Home
    Assistant die Optionen mit einer späteren Version aus dem Schema wirft.
    """
    if exists() or not isinstance(options, dict):
        return False
    seed = {}
    for key, value in options.items():
        if key in FIELDS and key not in LOCKED_KEYS and value not in (None, ''):
            seed[key] = value
    with _lock:
        raw = {}
        for key, value in seed.items():
            new = coerce(key, value)
            if new is None:
                continue
            raw[key] = _encrypt(new) if key in SECRET_KEYS else new
        try:
            _write(raw)
        except OSError as e:
            # Ein nicht beschreibbarer Datenordner darf den Start nicht kosten:
            # ohne settings.json gelten weiter die Werte aus options.json.
            log.warning("settings.json konnte nicht angelegt werden: %s", e)
            return False
    log.info("Einstellungen aus den Add-on-Optionen übernommen: %d Feld(er) "
             "in settings.json (geheime Felder verschlüsselt)", len(raw))
    return True


def public_view(effective: dict) -> dict:
    """Ansicht für die Oberfläche: Feldbeschreibung + Werte.

    Geheime Felder kommen nie im Klartext zurück, sondern nur als „gesetzt".
    """
    fields = []
    for group, title in GROUPS:
        items = []
        for key, spec in FIELDS.items():
            if spec[3] != group:
                continue
            kind, default, extra = spec[0], spec[1], spec[2]
            item = {'key': key, 'kind': kind, 'label': spec[4], 'hint': spec[5],
                    'restart': key in RESTART_KEYS}
            if key in SECRET_KEYS:
                item['secret'] = True
                item['set'] = bool(str(effective.get(key) or '').strip())
            else:
                value = effective.get(key, default)
                item['value'] = default if value is None else value
                if kind in ('int', 'float'):
                    item['min'], item['max'] = extra
                elif kind == 'choice':
                    item['choices'] = list(extra)
            items.append(item)
        if items:
            fields.append({'group': group, 'title': title, 'items': items})
    return {'groups': fields,
            'crypto': crypto_ready(),
            'key': key_exists()}
