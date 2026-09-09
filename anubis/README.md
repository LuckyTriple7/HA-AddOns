# Anubis

![GitHub Stars](https://img.shields.io/github/stars/LuckyTriple7/HA-AddOns?style=flat-square)
![Commits](https://img.shields.io/github/commit-activity/t/LuckyTriple7/HA-AddOns?style=flat-square&label=commits)
![Last Commit](https://img.shields.io/github/last-commit/LuckyTriple7/HA-AddOns?path=anubis&style=flat-square)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

🇬🇧 [English version](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/anubis/README.en.md)

Proof-of-Work-Bot-Challenge auf Basis von [Anubis](https://github.com/TecharoHQ/anubis) — vorgeschaltet vor einen Reverse Proxy, um automatisierte Zugriffe (Scraper, Scanner, einfache Bots) auszubremsen.

## Funktionsweise

```text
Internet → Reverse Proxy (z.B. NPMplus) → Anubis-Challenge → Anwendung
```

- Reine Engine ohne eigene Oberfläche, ohne Ingress, ohne veröffentlichten Port — nur andere Add-on-Container erreichen sie über ihren Hostnamen auf Port 8923
- Mitgelieferte, eigenständige Policy ohne externe Importe: challenged jeden Client ohne gültiges Auth-Cookie, kein impliziter ALLOW-Zweig
- Google, Bing, DuckDuckGo, Qwant, Internet Archive, Kagi, Marginalia, Mojeek, Common Crawl, Wikimedia und Arquivo.pt standardmäßig ausgenommen (per IP+User-Agent verifiziert), abschaltbar über `allow_search_engines`
- UptimeRobot und updown.io standardmäßig ausgenommen (`allow_monitoring_services`), damit externes Monitoring nicht dauerhaft „down" meldet
- KI-Bot-Stufe `ai_bot_policy` (aus/aggressiv/moderat/permissiv) — feiner steuerbar als die generische Challenge, identisch zu Anubis' eigenen Voreinstellungen
- Eigene vertrauenswürdige IP-Bereiche über `trusted_ip_ranges`, ohne User-Agent-Prüfung
- Fertig verdrahtet mit dem [NPMplus-Add-on](../npmplus/) dieses Repos über dessen `AUTH_REQUEST_ANUBIS_UPSTREAM`
- Policy frei editierbar unter `/data/policy.yaml`

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `TZ` | `Europe/Berlin` | Zeitzone des Containers |
| `log_level` | `info` | Log-Level: `debug`, `info`, `warn`, `error` |
| `allow_search_engines` | `true` | Echte Suchmaschinen-/Archiv-Crawler vom Challenge ausnehmen (verifiziert per IP+User-Agent). Aus = wirklich jeder wird challenged |
| `allow_monitoring_services` | `true` | UptimeRobot & updown.io vom Challenge ausnehmen (verifiziert per IP+User-Agent). Selbstgehostetes Uptime Kuma nicht betroffen (keine feste IP) |
| `ai_bot_policy` | `off` | `off`/`aggressive`/`moderate`/`permissive` — Umgang mit bekannten KI/LLM-Clients, siehe Dokumentation |
| `trusted_ip_ranges` | `[]` | Eigene IPs/CIDR-Bereiche, die den Challenge nie sehen — reine IP-Freigabe ohne User-Agent-Prüfung |

Einrichtung mit NPMplus, Auth-Request-Test, Policy anpassen und Problembehandlung: **[Dokumentation](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/anubis/DOCS.md)**

## Hinweise

- Architektur: amd64 und aarch64.
- Ersetzt kein Login — Anubis ist eine zusätzliche Schutzschicht, keine Zugriffskontrolle.
- Monitoring-Tools wie Uptime Kuma können die Challenge normalerweise nicht lösen — siehe Dokumentation.

## Changelog

Siehe [CHANGELOG.md](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/anubis/CHANGELOG.md)

## Lizenz

Anubis steht unter der [MIT-Lizenz](https://github.com/TecharoHQ/anubis/blob/main/LICENSE). Dieses Add-on kopiert nur das statische Binary aus dem offiziellen Image; Einzelheiten in [LICENSE.md](https://github.com/LuckyTriple7/HA-AddOns/blob/dev/anubis/LICENSE.md).
