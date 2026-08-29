# WhatsApp Add-on API Tester
#
# Spricht den Token-Port an (Standard 17786), nicht mehr 17776. Auf 17776
# liegen Weboberflaeche und API ohne jede Anmeldung - dieser Port wird
# kuenftig nicht mehr veroeffentlicht.
#
# Voraussetzungen im Add-on: Option "REST-API auf eigenem Port" an,
# "API-Token" gesetzt, Port 17786 unter Netzwerk freigegeben.
#
# Den Token nicht hier eintragen - die Datei liegt in git. Entweder vorher
#   $env:WHATSAPP_API_TOKEN = "..."
# setzen oder beim Start eingeben.

$HA_IP   = if ($env:WHATSAPP_HOST) { $env:WHATSAPP_HOST } else { "homeassistant.local" }
$HA_PORT = if ($env:WHATSAPP_API_PORT) { $env:WHATSAPP_API_PORT } else { 17786 }
$BASE    = "http://${HA_IP}:${HA_PORT}"
$TIMEOUT = 5   # Sekunden

$TOKEN = $env:WHATSAPP_API_TOKEN
if (-not $TOKEN) {
    $TOKEN = Read-Host "API-Token (Option api_token im Add-on)"
}
if (-not $TOKEN) {
    Write-Host "Ohne Token antwortet der Port nur mit 401. Abbruch." -ForegroundColor Red
    exit 1
}
$HEADERS = @{ Authorization = "Bearer $TOKEN" }

function Show-Fehler($e) {
    $code = $null
    if ($e.Exception.Response) { $code = [int]$e.Exception.Response.StatusCode }
    if ($code -eq 401) {
        Write-Host "401 - Token abgelehnt. Stimmt er mit der Option api_token ueberein?" -ForegroundColor Red
    } elseif ($code -eq 404) {
        Write-Host "404 - auf diesem Port gibt es nur /api/*, keine Oberflaeche." -ForegroundColor Red
    } else {
        Write-Host "Fehler: $e" -ForegroundColor Red
    }
}

function Show-Menu {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  WhatsApp API Tester  ($BASE)" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  1) Status abrufen"
    Write-Host "  2) Chats auflisten"
    Write-Host "  3) Nachricht senden"
    Write-Host "  4) Beenden"
    Write-Host ""
}

function Get-Status {
    Write-Host "Verbinde mit $BASE/api/status …" -ForegroundColor DarkGray
    try {
        $r = Invoke-RestMethod -Uri "$BASE/api/status" -Method GET -Headers $HEADERS -TimeoutSec $TIMEOUT
        Write-Host ""
        Write-Host "Status  : " -NoNewline; Write-Host $r.status -ForegroundColor Green
        Write-Host "Telefon : $($r.phone)"
        if ($r.error) { Write-Host "Fehler  : $($r.error)" -ForegroundColor Red }
    } catch {
        Show-Fehler $_
    }
}

function Get-Chats {
    Write-Host "Lade Chats …" -ForegroundColor DarkGray
    try {
        $chats = Invoke-RestMethod -Uri "$BASE/api/chats" -Method GET -Headers $HEADERS -TimeoutSec $TIMEOUT
        if ($chats.Count -eq 0) {
            Write-Host "Keine Chats gefunden." -ForegroundColor Yellow
            return
        }
        Write-Host ""
        Write-Host ("{0,-5} {1,-30} {2,-20} {3}" -f "Nr", "Name", "Letzte Nachricht", "Zeit") -ForegroundColor Cyan
        Write-Host ("-" * 80) -ForegroundColor DarkGray
        $i = 1
        foreach ($c in $chats) {
            $time = if ($c.lastTime) { [DateTimeOffset]::FromUnixTimeMilliseconds($c.lastTime).LocalDateTime.ToString("dd.MM. HH:mm") } else { "-" }
            $preview = if ($c.lastMsg -and $c.lastMsg.Length -gt 20) { $c.lastMsg.Substring(0,20) + "…" } else { $c.lastMsg }
            Write-Host ("{0,-5} {1,-30} {2,-20} {3}" -f $i, $c.name, $preview, $time)
            $i++
        }
        return $chats
    } catch {
        Show-Fehler $_
    }
}

function Send-Message {
    Write-Host ""
    $chats = Get-Chats
    if (-not $chats) { return }

    Write-Host ""
    $nr = Read-Host "Chat-Nummer wählen (oder leer lassen für manuelle Eingabe)"
    if ($nr -match '^\d+$' -and [int]$nr -ge 1 -and [int]$nr -le $chats.Count) {
        $to = $chats[[int]$nr - 1].id
        Write-Host "Sende an: $($chats[[int]$nr - 1].name) ($to)" -ForegroundColor Yellow
    } else {
        $to = Read-Host "Telefonnummer oder Chat-ID (z.B. 4917612345678)"
    }

    $msg = Read-Host "Nachricht"
    if (-not $msg) { Write-Host "Keine Nachricht eingegeben." -ForegroundColor Yellow; return }

    Write-Host "Sende …" -ForegroundColor DarkGray
    try {
        $body = @{ to = $to; message = $msg } | ConvertTo-Json
        $r = Invoke-RestMethod -Uri "$BASE/api/send" -Method POST `
             -ContentType "application/json" -Body $body -Headers $HEADERS -TimeoutSec $TIMEOUT
        if ($r.success) {
            Write-Host "Gesendet! ID: $($r.id)" -ForegroundColor Green
        } else {
            Write-Host "Fehler: $($r.error)" -ForegroundColor Red
        }
    } catch {
        Show-Fehler $_
    }
}

# ── Haupt-Loop ────────────────────────────────────────────────────────────────
while ($true) {
    Show-Menu
    $choice = Read-Host "Auswahl"
    switch ($choice) {
        "1" { Get-Status }
        "2" { Get-Chats }
        "3" { Send-Message }
        "4" { Write-Host "Tschüss!" -ForegroundColor Cyan; break }
        default { Write-Host "Ungültige Auswahl." -ForegroundColor Yellow }
    }
    if ($choice -eq "4") { break }
}
