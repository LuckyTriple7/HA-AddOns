# TUIWatch Dev-Setup mit Docker (außerhalb Home Assistant)

Für Entwicklung/Test auf einem separaten Docker-PC, ohne HA-Supervisor.

## Was HA-spezifisch ist (und wie es umgangen wird)

- `homeassistant_api` + `SUPERVISOR_TOKEN` → nur für `ha_sensors`/`notify_ha` genutzt
  ([app.py:485](app.py#L485)). Kein Token vorhanden → Feature bleibt inaktiv, kein Crash.
- `ingress: true` → nicht nötig, Port 17794 ist eh direkt exposed.
- `map: addon_config:rw` → wird zu normalem Docker-Volume-Mount.

Pfade, alle per Env-Var überschreibbar:

| Env-Var | Default | Zweck |
|---|---|---|
| `TUIWATCH_BASE` | `/app` | Code-Verzeichnis |
| `TUIWATCH_DATA` | `/data` | `options.json`, DB, Sessions |
| `TUIWATCH_BACKUP_DIR` | `/config/backups` | Auto-Backups |
| `TUIWATCH_PORT` | `17794` | Web-Port |

Fehlt `options.json` komplett, greift Fallback `admin`/`secret`, 24h Session
([app.py:1973](app.py#L1973)).

## Dateien

- [`docker-compose.dev.yml`](docker-compose.dev.yml) — Service-Definition
- [`dev-docker-setup.sh`](dev-docker-setup.sh) — Setup + Start, idempotent
  (überschreibt vorhandene `options.json` nicht)

## Setup auf dem Docker-PC

Wichtig: Code-Arbeit passiert immer auf Branch `dev`, `main` hinkt oft hinterher.
Gleich mit `-b dev` klonen, sonst landet man auf `main` ohne die neuesten Änderungen.

```bash
git clone -b dev https://github.com/LuckyTriple7/HA-AddOns.git
cd HA-AddOns/tuiwatch
chmod +x dev-docker-setup.sh
./dev-docker-setup.sh
```

Script legt `dev_data/config/backups` an, seedet `options.json` (admin/secret,
`ha_sensors`+`notify_ha` = `false`) falls noch keine da ist, und startet
`docker compose up --build -d`.

Danach: `http://<docker-pc-ip>:17794`, Login `admin`/`secret`.

## Bedienung

```bash
# Neu bauen nach Codeänderung
docker compose -f docker-compose.dev.yml up --build -d

# Stoppen
docker compose -f docker-compose.dev.yml down

# Logs
docker compose -f docker-compose.dev.yml logs -f
```

## Config ändern (`options.json`)

`load_config()` liest die Datei bei jedem Aufruf frisch von Platte
([app.py:146-151](app.py#L146-L151)), kein Caching beim Boot. Auch der Poll-Loop
liest `poll_interval` live pro Durchlauf ([app.py:1555](app.py#L1555)).

→ Werte wie `poll_interval`, `notify_*`, Telegram/SMTP/Nextcloud/KI-Keys greifen
**sofort** nach Speichern, kein Neustart nötig.

Neustart nur nötig für: neuen Login (`username`/`password` geändert, alte Session
bleibt sonst gültig) oder Code-Änderungen testen (siehe unten).

Neue Options in `config.yaml`, die in einer alten `dev_data/options.json` fehlen,
sind unkritisch — Code liest überall mit Fallback (`cfg.get('key', default)`).
Fehlender Key → Default greift, kein Crash, keine Migration nötig.

## Code-Update reinholen

```bash
cd HA-AddOns
git checkout dev
git pull origin dev
cd tuiwatch
docker compose -f docker-compose.dev.yml up --build -d
```

`dev_data/` bleibt unberührt (Volume-Mount außerhalb Image-Build) — Rebuild
betrifft nur den Code-Layer. Vorher `git status` checken, falls auf dem Docker-PC
lokal was verändert wurde (sollte nicht sein, aber sicher ist sicher).

## Echte HA-Werte übernehmen

Das Setup-Script seedet nur Fake-Defaults. Für echte Werte (Telegram-Token,
SMTP, Anthropic/Gemini-Key, poll_interval, ...):

1. **Einfachste:** HA → TUIWatch Add-on → Configuration-Tab, Werte ablesen,
   manuell in `dev_data/options.json` auf dem Docker-PC eintragen.
2. **Direkt kopieren:** Falls SSH/Terminal-Add-on auf HA läuft, liegt die von
   Supervisor injizierte `options.json` im internen Add-on-Datenpfad
   (`/data/options.json` im Container; host-seitig Pfad je nach HA-OS-Version
   unterschiedlich — vorher prüfen statt blind kopieren). Inhalt 1:1 nach
   `dev_data/options.json`.

**Secrets nie committen** — `tuiwatch/dev_data/` ist in `.gitignore` (Zeile 6).
