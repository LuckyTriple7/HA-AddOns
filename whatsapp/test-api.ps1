# WhatsApp Add-on API Tester
$HA_IP   = "homeassistant.local"
$HA_PORT = 3000
$BASE    = "http://${HA_IP}:${HA_PORT}"
$TIMEOUT = 5   # Sekunden

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
        $r = Invoke-RestMethod -Uri "$BASE/api/status" -Method GET -TimeoutSec $TIMEOUT
        Write-Host ""
        Write-Host "Status  : " -NoNewline; Write-Host $r.status -ForegroundColor Green
        Write-Host "Telefon : $($r.phone)"
        if ($r.error) { Write-Host "Fehler  : $($r.error)" -ForegroundColor Red }
    } catch {
        Write-Host "Fehler: $_" -ForegroundColor Red
    }
}

function Get-Chats {
    Write-Host "Lade Chats …" -ForegroundColor DarkGray
    try {
        $chats = Invoke-RestMethod -Uri "$BASE/api/chats" -Method GET -TimeoutSec $TIMEOUT
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
        Write-Host "Fehler: $_" -ForegroundColor Red
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
             -ContentType "application/json" -Body $body -TimeoutSec $TIMEOUT
        if ($r.success) {
            Write-Host "Gesendet! ID: $($r.id)" -ForegroundColor Green
        } else {
            Write-Host "Fehler: $($r.error)" -ForegroundColor Red
        }
    } catch {
        Write-Host "Fehler: $_" -ForegroundColor Red
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
