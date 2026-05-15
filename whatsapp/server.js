'use strict';

const { Client, LocalAuth } = require('whatsapp-web.js');
const express = require('express');
const qrcode = require('qrcode');
const https = require('https');
const http = require('http');
const { URL } = require('url');
const { existsSync } = require('fs');

function findChromium() {
  const candidates = [
    process.env.CHROMIUM_PATH,
    '/usr/bin/chromium-browser',
    '/usr/bin/chromium',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/google-chrome',
  ];
  for (const p of candidates) {
    if (p && existsSync(p)) return p;
  }
  return '/usr/bin/chromium-browser';
}

const CHROMIUM = findChromium();
console.log(`[INFO] Using Chromium: ${CHROMIUM}`);

const app = express();
app.use(express.json());

let qrCodeDataUrl = null;
let status = 'initializing';
let connectedPhone = null;
let lastError = null;

// ── WhatsApp Client ──────────────────────────────────────────────────────────

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: process.env.SESSION_DIR || '/addon_config/session' }),
  puppeteer: {
    executablePath: CHROMIUM,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--headless',
      '--disable-gpu',
      '--disable-dev-shm-usage',
      '--disable-extensions',
    ],
  },
});

client.on('qr', async (qr) => {
  console.log('[INFO] QR code received — scan with WhatsApp');
  status = 'waiting_for_scan';
  qrCodeDataUrl = await qrcode.toDataURL(qr, { width: 300 });
});

client.on('authenticated', () => {
  console.log('[INFO] Authenticated');
  status = 'authenticated';
  qrCodeDataUrl = null;
});

client.on('ready', () => {
  const info = client.info;
  connectedPhone = info?.wid?.user || null;
  status = 'connected';
  lastError = null;
  console.log(`[INFO] WhatsApp ready — phone: ${connectedPhone}`);
});

client.on('disconnected', (reason) => {
  status = 'disconnected';
  connectedPhone = null;
  lastError = reason;
  console.log(`[WARN] Disconnected: ${reason}`);
});

client.on('auth_failure', (msg) => {
  status = 'auth_failed';
  lastError = msg;
  console.error(`[ERROR] Auth failed: ${msg}`);
});

client.on('message', async (msg) => {
  const url = process.env.WEBHOOK_INCOMING;
  if (!url) return;
  postWebhook(url, {
    from: msg.from,
    body: msg.body,
    type: msg.type,
    timestamp: msg.timestamp,
    isGroup: msg.from.endsWith('@g.us'),
  });
});

client.initialize().catch((err) => {
  lastError = String(err?.message || err);
  status = 'error';
  console.error('[ERROR] Init failed:', lastError);
});

// ── Helpers ──────────────────────────────────────────────────────────────────

function postWebhook(url, data) {
  try {
    const parsed = new URL(url);
    const body = JSON.stringify(data);
    const lib = parsed.protocol === 'https:' ? https : http;
    const req = lib.request(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
    });
    req.on('error', (e) => console.warn('[WARN] Webhook error:', e.message));
    req.write(body);
    req.end();
  } catch (e) {
    console.warn('[WARN] Invalid webhook URL:', e.message);
  }
}

function formatNumber(to) {
  // Ensure format: 491234567890@c.us
  if (to.includes('@')) return to;
  return `${to.replace(/[^0-9]/g, '')}@c.us`;
}

// ── API ───────────────────────────────────────────────────────────────────────

app.get('/api/status', (req, res) => {
  res.json({ status, phone: connectedPhone, error: lastError });
});

app.get('/api/qr', (req, res) => {
  if (!qrCodeDataUrl) return res.status(404).json({ error: 'No QR code available' });
  res.json({ qr: qrCodeDataUrl });
});

app.post('/api/send', async (req, res) => {
  const { to, message } = req.body;
  if (!to || !message) return res.status(400).json({ error: 'to and message required' });
  if (status !== 'connected') return res.status(503).json({ error: `Not connected (status: ${status})` });
  try {
    const result = await client.sendMessage(formatNumber(to), message);
    res.json({ success: true, id: result.id._serialized });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/logout', async (req, res) => {
  try {
    await client.logout();
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── Web UI ────────────────────────────────────────────────────────────────────

app.get('/', (req, res) => {
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.send(`<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WhatsApp</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #111b21; color: #e9edef; min-height: 100vh;
           display: flex; flex-direction: column; align-items: center;
           justify-content: center; padding: 20px; }
    .card { background: #202c33; border-radius: 12px; padding: 32px;
            max-width: 420px; width: 100%; text-align: center; }
    .logo { font-size: 48px; margin-bottom: 8px; }
    h1 { font-size: 22px; font-weight: 600; margin-bottom: 4px; }
    .subtitle { color: #8696a0; font-size: 14px; margin-bottom: 24px; }
    .status-badge { display: inline-flex; align-items: center; gap: 8px;
                    padding: 6px 14px; border-radius: 20px; font-size: 13px;
                    font-weight: 500; margin-bottom: 24px; }
    .status-badge.connected { background: #1f3a2a; color: #25d366; }
    .status-badge.waiting { background: #3a2a1f; color: #f0a500; }
    .status-badge.disconnected, .status-badge.error { background: #3a1f1f; color: #f15c5c; }
    .status-badge.initializing { background: #1f2a3a; color: #8696a0; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
    #qr-container img { border-radius: 8px; background: white; padding: 12px; max-width: 280px; }
    #qr-hint { color: #8696a0; font-size: 13px; margin-top: 12px; line-height: 1.5; }
    .send-form { margin-top: 8px; text-align: left; }
    .send-form label { display: block; font-size: 12px; color: #8696a0;
                       margin-bottom: 4px; margin-top: 14px; }
    .send-form input, .send-form textarea {
      width: 100%; background: #2a3942; border: 1px solid #2a3942;
      border-radius: 8px; padding: 10px 14px; color: #e9edef;
      font-size: 14px; outline: none; resize: vertical; }
    .send-form input:focus, .send-form textarea:focus { border-color: #25d366; }
    .btn { width: 100%; margin-top: 16px; padding: 12px;
           background: #25d366; color: #111b21; border: none;
           border-radius: 8px; font-size: 15px; font-weight: 600;
           cursor: pointer; transition: background 0.2s; }
    .btn:hover { background: #1da851; }
    .btn:disabled { background: #2a3942; color: #8696a0; cursor: not-allowed; }
    .result { margin-top: 12px; font-size: 13px; padding: 8px 12px;
              border-radius: 6px; display: none; }
    .result.ok { background: #1f3a2a; color: #25d366; }
    .result.err { background: #3a1f1f; color: #f15c5c; }
    .phone-info { font-size: 13px; color: #8696a0; margin-bottom: 16px; }
    .logout-btn { background: none; border: 1px solid #2a3942; color: #8696a0;
                  border-radius: 8px; padding: 8px 16px; font-size: 13px;
                  cursor: pointer; margin-top: 16px; transition: all 0.2s; }
    .logout-btn:hover { border-color: #f15c5c; color: #f15c5c; }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">💬</div>
    <h1>WhatsApp</h1>
    <p class="subtitle">Home Assistant Add-on</p>
    <div id="status-badge" class="status-badge initializing">
      <div class="dot"></div>
      <span id="status-text">Verbinde...</span>
    </div>
    <div id="qr-container" style="display:none;"></div>
    <p id="qr-hint" style="display:none;">
      Öffne WhatsApp auf deinem Handy →<br>
      Verknüpfte Geräte → Gerät hinzufügen
    </p>
    <div id="connected-ui" style="display:none;">
      <p class="phone-info" id="phone-info"></p>
      <div class="send-form">
        <label>Telefonnummer (mit Ländervorwahl, ohne +)</label>
        <input id="to" type="tel" placeholder="4915123456789">
        <label>Nachricht</label>
        <textarea id="msg" rows="3" placeholder="Hallo!"></textarea>
        <button class="btn" onclick="sendMsg()">Senden</button>
        <div id="result" class="result"></div>
      </div>
      <button class="logout-btn" onclick="logout()">Abmelden</button>
    </div>
  </div>

  <script>
    let currentStatus = '';

    async function refresh() {
      try {
        const s = await fetch('api/status').then(r => r.json());
        const badge = document.getElementById('status-badge');
        const text = document.getElementById('status-text');

        if (s.status !== currentStatus) {
          currentStatus = s.status;
          badge.className = 'status-badge ' + (
            s.status === 'connected' ? 'connected' :
            s.status === 'waiting_for_scan' || s.status === 'authenticated' ? 'waiting' :
            s.status === 'initializing' ? 'initializing' : 'disconnected');
          text.textContent = {
            connected: 'Verbunden',
            waiting_for_scan: 'QR-Code scannen',
            authenticated: 'Authentifiziert...',
            initializing: 'Starte...',
            disconnected: 'Getrennt',
            auth_failed: 'Auth fehlgeschlagen',
            error: 'Fehler',
          }[s.status] || s.status;

          document.getElementById('qr-container').style.display = 'none';
          document.getElementById('qr-hint').style.display = 'none';
          document.getElementById('connected-ui').style.display = 'none';

          if (s.status === 'waiting_for_scan') {
            const qr = await fetch('api/qr').then(r => r.json()).catch(() => null);
            if (qr?.qr) {
              document.getElementById('qr-container').innerHTML = '<img src="' + qr.qr + '">';
              document.getElementById('qr-container').style.display = 'block';
              document.getElementById('qr-hint').style.display = 'block';
            }
          } else if (s.status === 'connected') {
            document.getElementById('phone-info').textContent = s.phone ? '📱 +' + s.phone : '';
            document.getElementById('connected-ui').style.display = 'block';
          }
        }
      } catch(e) {}
    }

    async function sendMsg() {
      const to = document.getElementById('to').value.trim();
      const msg = document.getElementById('msg').value.trim();
      const result = document.getElementById('result');
      if (!to || !msg) return;
      try {
        const r = await fetch('api/send', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({to, message: msg})
        }).then(r => r.json());
        result.className = 'result ' + (r.success ? 'ok' : 'err');
        result.textContent = r.success ? '✓ Gesendet' : '✗ ' + r.error;
        result.style.display = 'block';
        if (r.success) document.getElementById('msg').value = '';
        setTimeout(() => result.style.display = 'none', 4000);
      } catch(e) {
        result.className = 'result err';
        result.textContent = '✗ Netzwerkfehler';
        result.style.display = 'block';
      }
    }

    async function logout() {
      if (!confirm('Wirklich abmelden?')) return;
      await fetch('api/logout', {method: 'POST'});
    }

    refresh();
    setInterval(refresh, 5000);
  </script>
</body>
</html>`);
});

// ── Start ─────────────────────────────────────────────────────────────────────

const PORT = parseInt(process.env.PORT || '3000', 10);
app.listen(PORT, () => console.log(`[INFO] Web UI running on port ${PORT}`));
