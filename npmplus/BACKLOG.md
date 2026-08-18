# Backlog — NPMplus

Ideen, die nicht dringend sind. Kein Zeitplan.

## Anubis-Add-on (Proof-of-Work vor dem Seitenaufruf)

NPMplus kann pro Proxy Host über das Feld **Auth Request** einen Anubis-Upstream vorschalten. Anubis zeigt beim ersten Besuch eine Zwischenseite, in der der Browser eine Rechenaufgabe löst, und setzt danach ein signiertes Cookie — weitere Aufrufe laufen ohne Unterbrechung durch. Wirkt gegen Scraper und Bot-Netze, ohne Drittanbieter-Captcha und ohne Klickarbeit für Besucher.

Anubis ist ein eigener Container (`ghcr.io/techarohq/anubis`) und als Home-Assistant-Add-on nicht verfügbar. Ein Wrapper wäre klein: Port 8923, Bot-Policy-Datei, Zeitzone.

Anbindung in NPMplus:

```yaml
extra_env:
  - "AUTH_REQUEST_ANUBIS_UPSTREAM=http://127.0.0.1:8923"
```

Danach pro Host im Dropdown **Auth Request** auf `anubis` stellen.

**Wichtig bei der Auswahl der Hosts:** Alles ohne Browser scheitert an der Zwischenseite — Nextcloud-Clients, CalDAV/CardDAV-Synchronisierung, Uptime Kuma, die Home-Assistant-App. Anubis gehört also nur vor Hosts, die tatsächlich mit dem Browser besucht werden, und Sync-Endpunkte müssen in der Bot-Policy ausgenommen werden.

## GoAccess unter /goaccess nachziehen

Im Entwicklungszweig von NPMplus ist GoAccess vom eigenen Port 91 auf einen Unterpfad `/goaccess` der Oberfläche umgezogen — inklusive `auth_request /api/auth/admin`, also endlich mit Anmeldepflicht. Die Envs `GOA_PORT`, `GOA_IPV4_BINDING`, `GOA_IPV6_BINDING` und `GOA_LISTEN_LOCALHOST` werden dann abgelehnt und beenden den Start.

Sobald ein Tag nach `2026-07-24-r1` das enthält, ist beim Anheben von `NPMPLUS_VERSION` fällig:

- `goaccess_listen_localhost` aus Optionen, Schema und beiden Übersetzungen entfernen
- Port 91 aus `ports` und `ports_description` streichen
- GoAccess-Abschnitt in DOCS/README auf `https://<HA-IP>:81/goaccess` umstellen, Warnung zur fehlenden Anmeldung entfernen

## MaxMind-Datenbanken für die GoAccess-Länderauswertung

Die Ländersperre selbst ist seit 0.1.18 erledigt — sie läuft über das eingebaute `geo`-Modul und die CIDR-Listen von ipverse, ganz ohne MaxMind.

Offen bleibt nur die Länderauswertung in GoAccess. Die braucht die MaxMind-Datenbanken unter `/data/goaccess/geoip` (kostenloses Konto, Lizenzschlüssel). NPMplus bindet gefundene Dateien beim Start selbst ein, das Add-on müsste sie nur holen und aktuell halten — MaxMind aktualisiert wöchentlich, ohne den `geoipupdate`-Container müsste das ein Skript übernehmen.

Denkbar wären zwei Optionen `maxmind_account_id` und `maxmind_license_key`, mit demselben Auffrisch-Mechanismus wie die Länderlisten. Nur für eine Statistik allerdings viel Maschinerie.

Das nginx-Modul `NGINX_LOAD_GEOIP2_MODULE=true` und `$geoip2_data_country_code` bräuchte es nur, wenn die Sperre irgendwann genauer werden soll als Registerdaten — bei einer Sperrliste ist der Unterschied belanglos.
