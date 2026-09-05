# Changelog

## [0.0.1] - 2026-09-05

### Neu
- Erste Veröffentlichung. Kopiert das statische Binary aus dem offiziellen
  `ghcr.io/techarohq/anubis`-Image und startet es über `run.sh` mit
  einer eigenständigen, importfreien Policy (keine `(data)/...`-Abhängigkeit
  auf eingebettete Anubis-Assets).
- Läuft im reinen Auth-Request-Modus (`TARGET=" "`) für nginx' auth_request-
  Modul — gedacht für NPMplus' `AUTH_REQUEST_ANUBIS_UPSTREAM` (Auth-Request-
  Dropdown je Proxy Host), funktioniert aber mit jedem Reverse Proxy, der
  auth_request/forward-auth beherrscht.
- Kein Ingress, kein veröffentlichter Port — nur über den Add-on-Hostnamen
  auf Port 8923 aus anderen Containern erreichbar.
- Mitgelieferte Standard-Policy: Catch-all-Regel challenged jeden Client ohne
  gültiges Auth-Cookie (kein impliziter ALLOW-Zweig für unbekannte Clients).
