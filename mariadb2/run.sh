#!/bin/bash
set -e

DATA_DIR=/data/databases
SOCKET=/run/mysqld/mysqld.sock

# Read options
DBS=$(jq -r '.databases // [] | join(", ")' /data/options.json)
USERS=$(jq -r '.logins // [] | map(.username) | join(", ")' /data/options.json)

# Log configuration
echo "[INFO] Configuration:"
echo "[INFO]   databases : ${DBS:-none}"
echo "[INFO]   logins    : ${USERS:-none}"

mkdir -p /run/mysqld "$DATA_DIR"

# First run: initialize data directory
if [ ! -d "$DATA_DIR/mysql" ]; then
    echo "[INFO] First run — initializing MariaDB data directory..."
    mariadb-install-db --user=root --datadir="$DATA_DIR" --skip-test-db > /dev/null
    echo "[INFO] Database initialized"
fi

# Start MariaDB temporarily without networking for setup
echo "[INFO] Starting MariaDB for setup..."
mysqld --user=root --datadir="$DATA_DIR" --socket="$SOCKET" --skip-networking &
MYSQL_PID=$!

# Wait for socket (max 30s)
for i in $(seq 1 30); do
    [ -S "$SOCKET" ] && break
    sleep 1
    if [ "$i" -eq 30 ]; then
        echo "[ERROR] MariaDB did not start within 30 seconds"
        exit 1
    fi
done
echo "[INFO] MariaDB ready for setup"

# Create databases
jq -r '.databases // [] | .[]' /data/options.json | while read -r DB; do
    [ -z "$DB" ] && continue
    echo "[INFO] Creating database: $DB"
    mysql --socket="$SOCKET" -e "CREATE DATABASE IF NOT EXISTS \`${DB}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
done

# Create logins
jq -c '.logins // [] | .[]' /data/options.json | while read -r LOGIN; do
    USER=$(echo "$LOGIN" | jq -r '.username')
    PASS=$(echo "$LOGIN" | jq -r '.password // ""')
    [ -z "$USER" ] && continue
    if [ -n "$PASS" ]; then
        echo "[INFO] Creating/updating user: $USER"
        mysql --socket="$SOCKET" -e "CREATE USER IF NOT EXISTS '${USER}'@'%' IDENTIFIED BY '${PASS}';"
        mysql --socket="$SOCKET" -e "ALTER USER '${USER}'@'%' IDENTIFIED BY '${PASS}';"
    else
        echo "[INFO] Creating user (no password): $USER"
        mysql --socket="$SOCKET" -e "CREATE USER IF NOT EXISTS '${USER}'@'%';"
    fi
done

# Grant rights
jq -c '.rights // [] | .[]' /data/options.json | while read -r RIGHT; do
    USER=$(echo "$RIGHT" | jq -r '.username')
    DB=$(echo "$RIGHT" | jq -r '.database')
    [ -z "$USER" ] || [ -z "$DB" ] && continue
    echo "[INFO] Granting ALL PRIVILEGES: $USER → $DB"
    mysql --socket="$SOCKET" -e "GRANT ALL PRIVILEGES ON \`${DB}\`.* TO '${USER}'@'%';"
done

mysql --socket="$SOCKET" -e "FLUSH PRIVILEGES;"

# Stop temp instance
echo "[INFO] Setup complete — starting MariaDB with network access..."
kill "$MYSQL_PID"
wait "$MYSQL_PID" 2>/dev/null || true
rm -f "$SOCKET"

# Start MariaDB in foreground on port 3306
echo "[INFO] MariaDB 2 listening on port 3306 (host: 3307)"
echo "[INFO] Hostname (for Nextcloud migration): $(hostname)"
exec mysqld --user=root \
    --datadir="$DATA_DIR" \
    --socket="$SOCKET" \
    --port=3306 \
    --bind-address=0.0.0.0 \
    --character-set-server=utf8mb4 \
    --collation-server=utf8mb4_unicode_ci
