# Telegram Add-on API Tester
$HA_IP   = "homeassistant.local"
$HA_PORT = 17778
$BASE    = "http://${HA_IP}:${HA_PORT}"
$TIMEOUT = 5   # Sekunden

function Show-Menu {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Telegram API Tester  ($BASE)" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  1) Status abrufen"
    Write-Host "  2) Chats auflisten"
    Write-Host "  3) Nachricht senden"
    Write-Host "  4) Login-Code einreichen"
    Write-Host "  5) 2FA-Passwort einreichen"
    Write-Host "  6) Beenden"
    Write-Host ""
}

function Get-Status {
    Write-Host "Verbinde mit $BASE/api/status ..." -ForegroundColor DarkGray
    try {
        $r = Invoke-RestMethod -Uri "$BASE/api/status" -Method GET -TimeoutSec $TIMEOUT
        Write-Host ""
        Write-Host "Status : " -NoNewline
        $color = if ($r.status -eq 'connected') { 'Green' } elseif ($r.status -eq 'starting') { 'Yellow' } else { 'Red' }
        Write-Host $r.status -ForegroundColor $color
        if ($r.name) { Write-Host "Name   : $($r.name)" }
        if ($r.id)   { Write-Host "ID     : $($r.id)" }
        if ($r.error) { Write-Host "Fehler : $($r.error)" -ForegroundColor Red }
    } catch {
        Write-Host "Fehler: $_" -ForegroundColor Red
    }
}

function Get-Chats {
    Write-Host "Lade Chats ..." -ForegroundColor DarkGray
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
            $time    = if ($c.lastTime) { [DateTimeOffset]::FromUnixTimeMilliseconds($c.lastTime).LocalDateTime.ToString("dd.MM. HH:mm") } else { "-" }
            $preview = if ($c.lastMsg -and $c.lastMsg.Length -gt 20) { $c.lastMsg.Substring(0,20) + "..." } else { $c.lastMsg }
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
    $nr = Read-Host "Chat-Nummer waehlen (oder leer fuer manuelle Eingabe)"
    if ($nr -match '^\d+$' -and [int]$nr -ge 1 -and [int]$nr -le $chats.Count) {
        $to = $chats[[int]$nr - 1].id
        Write-Host "Sende an: $($chats[[int]$nr - 1].name) (ID: $to)" -ForegroundColor Yellow
    } else {
        $to = Read-Host "Chat-ID (Zahl, z.B. 123456789)"
    }

    $msg = Read-Host "Nachricht"
    if (-not $msg) { Write-Host "Keine Nachricht eingegeben." -ForegroundColor Yellow; return }

    Write-Host "Sende ..." -ForegroundColor DarkGray
    try {
        $body = @{ to = $to; message = $msg } | ConvertTo-Json
        $r = Invoke-RestMethod -Uri "$BASE/api/send" -Method POST `
             -ContentType "application/json" -Body $body -TimeoutSec $TIMEOUT
        if ($r.success) {
            Write-Host "Gesendet!" -ForegroundColor Green
        } else {
            Write-Host "Fehler: $($r.error)" -ForegroundColor Red
        }
    } catch {
        Write-Host "Fehler: $_" -ForegroundColor Red
    }
}

function Submit-Code {
    $code = Read-Host "SMS/App-Code eingeben"
    if (-not $code) { return }
    try {
        $body = @{ code = $code } | ConvertTo-Json
        $r = Invoke-RestMethod -Uri "$BASE/api/submit-code" -Method POST `
             -ContentType "application/json" -Body $body -TimeoutSec $TIMEOUT
        if ($r.ok) { Write-Host "Code akzeptiert." -ForegroundColor Green }
        else        { Write-Host "Fehler: $($r.error)" -ForegroundColor Red }
    } catch {
        Write-Host "Fehler: $_" -ForegroundColor Red
    }
}

function Submit-Password {
    $pw = Read-Host "2FA-Passwort eingeben" -AsSecureString
    $plain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
                [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($pw))
    if (-not $plain) { return }
    try {
        $body = @{ password = $plain } | ConvertTo-Json
        $r = Invoke-RestMethod -Uri "$BASE/api/submit-password" -Method POST `
             -ContentType "application/json" -Body $body -TimeoutSec $TIMEOUT
        if ($r.ok) { Write-Host "Passwort akzeptiert." -ForegroundColor Green }
        else        { Write-Host "Fehler: $($r.error)" -ForegroundColor Red }
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
        "4" { Submit-Code }
        "5" { Submit-Password }
        "6" { Write-Host "Ende." -ForegroundColor Cyan; break }
        default { Write-Host "Ungueltige Auswahl." -ForegroundColor Yellow }
    }
    if ($choice -eq "6") { break }
}
