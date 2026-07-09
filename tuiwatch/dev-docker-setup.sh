#!/bin/sh
# TUIWatch Dev-Setup fuer Docker ausserhalb HA.
# Ausfuehren im tuiwatch/ Ordner (nach git clone/pull des Repos auf dem Docker-PC).
set -e

cd "$(dirname "$0")"

mkdir -p dev_data/config/backups

if [ ! -f dev_data/options.json ]; then
  cat > dev_data/options.json <<'EOF'
{
  "username": "admin",
  "password": "secret",
  "session_hours": 24,
  "poll_interval": 21600,
  "ha_sensors": false,
  "notify_ha": false,
  "notify_price_change": true,
  "notify_cheaper_date": true,
  "cheaper_date_min_diff": 50,
  "notify_errors": true,
  "notify_api_errors": true,
  "notify_booked_drop": true,
  "booked_drop_min_diff": 50,
  "digest_enabled": false,
  "digest_weekday": 1,
  "notify_aktionscodes": true,
  "aktionscode_min": 0,
  "aktionscode_interval": 21600,
  "auto_backup": true,
  "auto_backup_keep": 5,
  "telegram_bot_token": "",
  "telegram_chat_id": "",
  "smtp_host": "",
  "smtp_port": 587,
  "smtp_user": "",
  "smtp_password": "",
  "smtp_from": "",
  "smtp_to": "",
  "smtp_tls": true,
  "nc_addressbook_url": "",
  "nc_user": "",
  "nc_app_password": "",
  "anthropic_api_key": "",
  "anthropic_model": "claude-opus-4-8",
  "ai_provider": "anthropic",
  "gemini_api_key": "",
  "gemini_model": "gemini-3.1-pro",
  "ai_max_web_searches": 12,
  "verbose_log": false
}
EOF
  echo "[INFO] dev_data/options.json neu angelegt (Login admin/secret)."
else
  echo "[INFO] dev_data/options.json existiert schon, unveraendert."
fi

docker compose -f docker-compose.dev.yml up --build -d

echo "[INFO] TUIWatch-Dev laeuft: http://localhost:17794"
echo "[INFO] Login: admin / secret (in dev_data/options.json aenderbar)"
echo "[INFO] Logs: docker compose -f docker-compose.dev.yml logs -f"
