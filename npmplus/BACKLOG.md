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

## GeoIP im nginx (statt nur über CrowdSec)

Ländersperren laufen derzeit über CrowdSec, greifen also erst ab der zweiten Anfrage. Nativ ginge es sofort:

```yaml
extra_env:
  - "NGINX_LOAD_GEOIP2_MODULE=true"
```

Voraussetzung sind die MaxMind-Datenbanken unter `/data/goaccess/geoip` (kostenloses Konto) und eigene Konfigurationsschnipsel pro Host, die `$geoip2_data_country_code` auswerten. Dieselben Datenbanken würden auch die GoAccess-Statistik um eine Länderauswertung erweitern — dafür braucht es keine Regeln, nur die Dateien.

Offen bleibt die Pflege: MaxMind aktualisiert wöchentlich, ohne den `geoipupdate`-Container müsste das ein Skript übernehmen.
