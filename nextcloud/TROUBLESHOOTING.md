# Nextcloud Add-on — Probleme, Ursachen & Lösungen

## 1. root:root nach Backup-Restore (Hauptproblem)

**Symptome:**
- "Interner Serverfehler" in Nextcloud
- Collabora zeigt leere Dokumente / Kit crasht
- "Neue Datei konnte nicht aus Vorlage erstellt werden" für normale User
- nginx-Log: `OC\Files\GenericFileException` in richdocuments

**Ursache:**
HA's Backup-Restore extrahiert alle Dateien als `root`, unabhängig von der ursprünglichen Besitzerzuweisung. Dadurch landen `appdata_*/`, User-Verzeichnisse (`andyw/`, `nxtcldadmin/`) und alle Dateien darin als `root:root`.

- `DAC_READ_SEARCH` (im Add-on aktiviert) erlaubt php-fpm (`abc`) zwar das **Lesen** aus `root:root 700`-Verzeichnissen, aber **kein Schreiben** — deshalb schlagen Collabora-Vorlagen und neue Dateien fehl.
- linuxserver's Init-Skripte fixen nur ihre eigenen Verzeichnisse, nicht die NC-Daten.

**Sofort-Fix (im NC-Terminal):**
```bash
chown -R abc:abc /config/data/appdata_ocr5rwk1xjk1/
chown -R abc:abc /config/data/andyw /config/data/nxtcldadmin
```

**Permanente Lösung (ab v1.0.20):**
`ha-config.sh` findet beim Start alle root-owned Unterverzeichnisse in `data/` und setzt sie automatisch auf `abc:abc`:
```bash
find "${DATA_DIR}" -maxdepth 1 -mindepth 1 -type d -user root \
    -exec chown -R abc:abc {} \;
```

---

## 2. overwrite.cli.url zeigt auf lokale IP statt externe Domain

**Symptom:**
- Login funktioniert lokal (192.168.178.200:7443), aber nicht extern (nxtcloud.gizmonet.de)
- Nach 2FA: "Sitzungsfehler — Sitzungstoken abgelaufen"

**Ursache:**
linuxserver setzt `overwrite.cli.url` beim Start auf die Container-IP. Nach einem Backup-Restore oder Neustart wurde der manuell gesetzte Wert überschrieben. `ha-config.sh` hat diesen Wert bisher nicht gesetzt.

**Permanente Lösung (ab v1.0.19):**
`ha-config.sh` liest die erste Nicht-IP-Adresse aus `trusted_domains` und setzt automatisch:
```bash
occ config:system:set overwrite.cli.url --value="https://nxtcloud.gizmonet.de"
occ config:system:set overwritehost --value="nxtcloud.gizmonet.de"
occ config:system:set overwriteprotocol --value="https"
```

---

## 3. NC34 Update hat Apps zerstört

**Symptom:**
- Nach automatischem Update auf NC34: Apps inkompatibel, Nextcloud nicht nutzbar

**Ursache:**
Dockerfile verwendete `:latest`-Tag und zog NC34, obwohl Rollback auf NC33 gewünscht war.

**Lösung:**
- Dockerfile auf exakten Tag gepinnt: `lscr.io/linuxserver/nextcloud:33.0.5-ls436`
- Check-Update-Workflow auf NC 33.x beschränkt (kein automatisches Upgrade auf NC34+)
- NC33 aus Backup wiederhergestellt

---

## 4. maintenance:repair bei jedem Start

**Symptom:**
- Jeder NC-Start dauert unnötig lang
- `maintenance:repair --include-expensive` läuft auch ohne Versionsupgrade

**Ursache:**
`ha-config.sh` rief `maintenance:repair` bei jedem Start auf.

**Lösung (ab v1.0.17):**
Flag-basiertes System — repair läuft nur wenn die NC-Version sich geändert hat:
```bash
REPAIR_FLAG=/config/data/.repair_$(occ config:system:get version | tr -d '.')
if [ ! -f "$REPAIR_FLAG" ]; then
    occ maintenance:repair --include-expensive
    touch "$REPAIR_FLAG"
fi
```

---

## 5. Build-Workflows liefen doppelt (dev + main)

**Symptom:**
- Nach merge-dev-to-main: Image wird zweimal gebaut (einmal für dev-Push, einmal für main-Push)

**Ursache:**
Alle 17 Build-Workflows hatten `branches: [dev, main]`.

**Lösung:**
Alle Build-Workflows auf `branches: [dev]` beschränkt. Auf main wird nur gemergt, nicht gebaut.

---

## 6. Login-Sitzungsfehler nach intensivem Debugging

**Symptom:**
- Nach 2FA: "Sitzungstoken abgelaufen" — passiert nur extern, lokal geht es

**Ursache:**
Staler APCu-Cache durch viele php-fpm-Neustarts und occ-Befehle während des Debuggings. Kein dauerhaftes Problem.

**Lösung:**
NC Add-on neu starten — leert APCu-Cache und PHP-Sessions.

---

## Wichtige Befehle für den NC-Notfall

```bash
# Berechtigungen fixen (nach Restore)
chown -R abc:abc /config/data/

# NC-Log live (gefiltert)
tail -20 /config/data/nextcloud.log | grep -o '"message":"[^"]*"'

# Collabora-Verbindung prüfen
occ richdocuments:setup

# User-Verzeichnisse prüfen
ls -la /config/data/

# appdata-Berechtigungen prüfen
ls -la /config/data/appdata_ocr5rwk1xjk1/ | head -5

# overwrite-URL prüfen
grep -E "overwrite" /config/www/nextcloud/config/config.php
```

---

## Versionsverlauf der Fixes

| Version | Fix |
|---------|-----|
| 1.0.20 | Alle root-owned User-Verzeichnisse beim Start auf abc:abc setzen |
| 1.0.19 | overwrite.cli.url automatisch aus trusted_domains setzen |
| 1.0.18 | chown appdata_* beim Start (war zu eng gefasst) |
| 1.0.17 | maintenance:repair nur nach Versionsupgrade |
| 1.0.16 | occ läuft als abc statt root |
| 1.0.15 | Rollback auf NC33, Check-Update auf 33.x beschränkt |
