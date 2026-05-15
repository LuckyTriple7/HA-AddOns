'use strict';

const { Client, LocalAuth } = require('whatsapp-web.js');
const express = require('express');
const qrcode = require('qrcode');
const https = require('https');
const http = require('http');
const { URL } = require('url');
const { existsSync } = require('fs');

// ── Chromium detection ────────────────────────────────────────────────────────

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

// ── State ─────────────────────────────────────────────────────────────────────

const app = express();
app.use(express.json());

let qrCodeDataUrl = null;
let status = 'initializing';
let connectedPhone = null;
let lastError = null;

const MAX_MESSAGES = 500;
const messages = []; // { id, from, to, body, timestamp, fromMe, contact }
const seenIds = new Set();

function addMessage(msg) {
  if (seenIds.has(msg.id)) return;
  seenIds.add(msg.id);
  messages.push(msg);
  messages.sort((a, b) => a.timestamp - b.timestamp);
  if (messages.length > MAX_MESSAGES) {
    const removed = messages.splice(0, messages.length - MAX_MESSAGES);
    removed.forEach(m => seenIds.delete(m.id));
  }
}

// ── WhatsApp Client ───────────────────────────────────────────────────────────

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

client.on('ready', async () => {
  connectedPhone = client.info?.wid?.user || null;
  status = 'connected';
  lastError = null;
  console.log(`[INFO] WhatsApp ready — phone: ${connectedPhone}`);

  // Load recent messages from last 30 chats
  try {
    const chats = await client.getChats();
    const recent = chats.slice(0, 30);
    for (const chat of recent) {
      const msgs = await chat.fetchMessages({ limit: 20 }).catch(() => []);
      for (const msg of msgs) {
        if (msg.type !== 'chat' && msg.type !== 'text') continue;
        if (!msg.body) continue;
        const contact = msg.fromMe ? null : await msg.getContact().catch(() => null);
        addMessage({
          id: msg.id._serialized,
          from: msg.fromMe ? connectedPhone : chat.id.user,
          to: msg.fromMe ? chat.id.user : connectedPhone,
          body: msg.body,
          timestamp: msg.timestamp * 1000,
          fromMe: msg.fromMe,
          contact: msg.fromMe ? 'Ich' : (contact?.pushname || contact?.name || chat.id.user),
        });
      }
    }
    console.log(`[INFO] Loaded ${messages.length} recent messages from ${recent.length} chats`);
  } catch (err) {
    console.warn('[WARN] Could not load recent messages:', err.message);
  }
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

// Incoming messages
client.on('message', async (msg) => {
  if (msg.type !== 'chat' && msg.type !== 'text') return;
  const contact = await msg.getContact().catch(() => null);
  addMessage({
    id: msg.id._serialized,
    from: msg.from.replace('@c.us', '').replace('@g.us', ''),
    to: connectedPhone,
    body: msg.body,
    timestamp: msg.timestamp * 1000,
    fromMe: false,
    contact: contact?.pushname || contact?.name || msg.from.replace('@c.us', ''),
  });

  const url = process.env.WEBHOOK_INCOMING;
  if (url) postWebhook(url, { from: msg.from, body: msg.body, type: msg.type, timestamp: msg.timestamp });
});

// Messages sent from phone (not via API)
client.on('message_create', async (msg) => {
  if (!msg.fromMe) return;
  if (msg.type !== 'chat' && msg.type !== 'text') return;
  // Avoid duplicates from /api/send (those have __logged flag)
  if (msg.__logged) return;
  addMessage({
    id: msg.id._serialized,
    from: connectedPhone,
    to: msg.to.replace('@c.us', '').replace('@g.us', ''),
    body: msg.body,
    timestamp: msg.timestamp * 1000,
    fromMe: true,
    contact: 'Ich',
  });
});

client.initialize().catch((err) => {
  lastError = String(err?.message || err);
  status = 'error';
  console.error('[ERROR] Init failed:', lastError);
});

// ── Helpers ───────────────────────────────────────────────────────────────────

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

app.get('/api/messages', (req, res) => {
  const since = parseInt(req.query.since || '0', 10);
  res.json(messages.filter(m => m.timestamp > since));
});

app.post('/api/send', async (req, res) => {
  const { to, message } = req.body;
  if (!to || !message) return res.status(400).json({ error: 'to and message required' });
  if (status !== 'connected') return res.status(503).json({ error: `Not connected (status: ${status})` });
  try {
    const result = await client.sendMessage(formatNumber(to), message);
    const entry = {
      id: result.id._serialized,
      from: connectedPhone,
      to: to.replace(/[^0-9]/g, ''),
      body: message,
      timestamp: Date.now(),
      fromMe: true,
      contact: 'Ich',
    };
    result.__logged = true;
    addMessage(entry);
    res.json({ success: true, id: entry.id });
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
           background: #111b21; color: #e9edef; height: 100vh;
           display: flex; flex-direction: column; }

    /* ── Header ── */
    .header { background: #202c33; padding: 12px 16px;
              display: flex; align-items: center; gap: 12px;
              border-bottom: 1px solid #2a3942; flex-shrink: 0; }
    .header .logo { font-size: 28px; }
    .header h1 { font-size: 17px; font-weight: 600; }
    .header .phone { font-size: 12px; color: #8696a0; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; margin-left: auto; flex-shrink: 0; }
    .status-dot.connected { background: #25d366; }
    .status-dot.waiting { background: #f0a500; }
    .status-dot.error, .status-dot.disconnected { background: #f15c5c; }
    .status-dot.initializing { background: #8696a0; }
    .status-label { font-size: 12px; color: #8696a0; }

    /* ── Center (QR or Chat) ── */
    #center { flex: 1; overflow: hidden; display: flex; flex-direction: column; }

    /* QR view */
    #qr-view { flex: 1; display: flex; flex-direction: column;
                align-items: center; justify-content: center; gap: 16px; padding: 24px; }
    #qr-view img { background: white; padding: 12px; border-radius: 8px; max-width: 260px; }
    #qr-view p { color: #8696a0; font-size: 14px; text-align: center; line-height: 1.6; }

    /* Chat view */
    #chat-view { flex: 1; display: none; flex-direction: column; }
    #messages { flex: 1; overflow-y: auto; padding: 12px 16px;
                display: flex; flex-direction: column; gap: 4px; }
    #messages::-webkit-scrollbar { width: 6px; }
    #messages::-webkit-scrollbar-thumb { background: #2a3942; border-radius: 3px; }

    .bubble-wrap { display: flex; flex-direction: column; margin: 2px 0; }
    .bubble-wrap.out { align-items: flex-end; }
    .bubble-wrap.in  { align-items: flex-start; }
    .contact-name { font-size: 11px; color: #8696a0; margin-bottom: 2px; padding: 0 4px; }
    .bubble { max-width: 72%; padding: 7px 12px; border-radius: 8px;
              font-size: 14px; line-height: 1.45; word-break: break-word;
              position: relative; }
    .bubble-wrap.out .bubble { background: #005c4b; border-bottom-right-radius: 2px; }
    .bubble-wrap.in  .bubble { background: #202c33; border-bottom-left-radius: 2px; }
    .bubble .time { font-size: 10px; color: #8696a0; float: right;
                    margin-left: 10px; margin-top: 3px; }
    .no-messages { color: #8696a0; font-size: 14px; text-align: center;
                   margin: auto; padding: 32px; }

    /* Send bar */
    #send-bar { background: #202c33; padding: 10px 12px;
                display: none; gap: 8px; align-items: flex-end;
                border-top: 1px solid #2a3942; flex-shrink: 0; }
    #send-bar input[type=tel] { background: #2a3942; border: none; border-radius: 8px;
                                 padding: 8px 12px; color: #e9edef; font-size: 13px;
                                 width: 140px; flex-shrink: 0; outline: none; }
    #send-bar textarea { flex: 1; background: #2a3942; border: none; border-radius: 8px;
                          padding: 8px 12px; color: #e9edef; font-size: 14px;
                          resize: none; outline: none; max-height: 100px; min-height: 38px; }
    #send-bar button { background: #25d366; border: none; border-radius: 50%;
                        width: 40px; height: 40px; flex-shrink: 0; cursor: pointer;
                        font-size: 18px; display: flex; align-items: center;
                        justify-content: center; transition: background 0.2s; }
    #send-bar button:hover { background: #1da851; }

    /* Logout */
    .logout-btn { background: none; border: none; color: #8696a0; font-size: 18px;
                  cursor: pointer; padding: 4px; transition: color 0.2s; }
    .logout-btn:hover { color: #f15c5c; }

    /* Spinner */
    #spinner { flex: 1; display: flex; align-items: center; justify-content: center;
               color: #8696a0; font-size: 14px; }
  </style>
</head>
<body>
  <div class="header">
    <div class="logo">💬</div>
    <div>
      <h1>WhatsApp</h1>
      <div class="phone" id="header-phone">Home Assistant Add-on</div>
    </div>
    <div style="margin-left:auto;display:flex;align-items:center;gap:8px;">
      <span class="status-label" id="status-label">Starte...</span>
      <div class="status-dot initializing" id="status-dot"></div>
      <button class="logout-btn" title="Abmelden" onclick="logout()">⏻</button>
    </div>
  </div>

  <div id="center">
    <div id="spinner">Verbinde mit WhatsApp...</div>
    <div id="qr-view" style="display:none;">
      <div id="qr-img"></div>
      <p>Öffne WhatsApp auf deinem Handy<br>
         <strong>Verknüpfte Geräte → Gerät hinzufügen</strong><br>
         und scanne den QR-Code</p>
    </div>
    <div id="chat-view">
      <div id="messages"><p class="no-messages">Keine Nachrichten — sende eine!</p></div>
    </div>
  </div>

  <div id="send-bar">
    <input type="tel" id="to" placeholder="4915123456789" title="Nummer mit Ländervorwahl">
    <textarea id="msg" rows="1" placeholder="Nachricht…"
              onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMsg();}"></textarea>
    <button onclick="sendMsg()" title="Senden">➤</button>
  </div>

  <script>
    let currentStatus = '';
    let lastMsgTime = 0;
    let atBottom = true;

    const msgList = document.getElementById('messages');
    msgList.addEventListener('scroll', () => {
      atBottom = msgList.scrollTop + msgList.clientHeight >= msgList.scrollHeight - 20;
    });

    function scrollDown() {
      if (atBottom) msgList.scrollTop = msgList.scrollHeight;
    }

    function fmtTime(ts) {
      return new Date(ts).toLocaleTimeString('de-DE', {hour:'2-digit', minute:'2-digit'});
    }

    function fmtDate(ts) {
      const d = new Date(ts);
      const today = new Date();
      if (d.toDateString() === today.toDateString()) return 'Heute';
      const yesterday = new Date(today); yesterday.setDate(today.getDate()-1);
      if (d.toDateString() === yesterday.toDateString()) return 'Gestern';
      return d.toLocaleDateString('de-DE');
    }

    function renderMessages(msgs) {
      if (!msgs.length) return;
      const noMsg = msgList.querySelector('.no-messages');
      if (noMsg) noMsg.remove();

      let lastDate = null;
      msgs.forEach(m => {
        const date = fmtDate(m.timestamp);
        if (date !== lastDate) {
          lastDate = date;
          const sep = document.createElement('div');
          sep.style.cssText = 'text-align:center;font-size:11px;color:#8696a0;margin:8px 0;';
          sep.textContent = date;
          msgList.appendChild(sep);
        }
        const wrap = document.createElement('div');
        wrap.className = 'bubble-wrap ' + (m.fromMe ? 'out' : 'in');
        const name = document.createElement('div');
        name.className = 'contact-name';
        name.textContent = m.fromMe ? '' : (m.contact || m.from);
        const bubble = document.createElement('div');
        bubble.className = 'bubble';
        bubble.innerHTML = escHtml(m.body) + '<span class="time">' + fmtTime(m.timestamp) + '</span>';
        if (!m.fromMe && m.contact) wrap.appendChild(name);
        wrap.appendChild(bubble);
        msgList.appendChild(wrap);
        if (m.timestamp > lastMsgTime) lastMsgTime = m.timestamp;
      });
      scrollDown();
    }

    function escHtml(s) {
      return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
               .replace(/\\n/g,'<br>');
    }

    async function pollMessages() {
      if (currentStatus !== 'connected') return;
      try {
        const msgs = await fetch('api/messages?since=' + lastMsgTime).then(r => r.json());
        if (msgs.length) renderMessages(msgs);
      } catch(e) {}
    }

    async function refresh() {
      try {
        const s = await fetch('api/status').then(r => r.json());
        const dot = document.getElementById('status-dot');
        const label = document.getElementById('status-label');

        dot.className = 'status-dot ' + (
          s.status === 'connected' ? 'connected' :
          s.status === 'waiting_for_scan' || s.status === 'authenticated' ? 'waiting' :
          s.status === 'initializing' ? 'initializing' : 'error');

        label.textContent = {
          connected: 'Verbunden', waiting_for_scan: 'QR scannen',
          authenticated: 'Authentifiziert…', initializing: 'Starte…',
          disconnected: 'Getrennt', auth_failed: 'Auth-Fehler', error: 'Fehler',
        }[s.status] || s.status;

        if (s.phone) document.getElementById('header-phone').textContent = '+' + s.phone;

        if (s.status !== currentStatus) {
          currentStatus = s.status;
          document.getElementById('spinner').style.display = 'none';
          document.getElementById('qr-view').style.display = 'none';
          document.getElementById('chat-view').style.display = 'none';
          document.getElementById('send-bar').style.display = 'none';

          if (s.status === 'waiting_for_scan') {
            document.getElementById('qr-view').style.display = 'flex';
            const qr = await fetch('api/qr').then(r => r.json()).catch(() => null);
            if (qr?.qr) document.getElementById('qr-img').innerHTML = '<img src="'+qr.qr+'">';
          } else if (s.status === 'connected') {
            document.getElementById('chat-view').style.display = 'flex';
            document.getElementById('send-bar').style.display = 'flex';
            // Load all messages on connect
            const all = await fetch('api/messages').then(r => r.json()).catch(() => []);
            renderMessages(all);
          } else {
            document.getElementById('spinner').style.display = 'flex';
          }
        }
      } catch(e) {}
    }

    async function sendMsg() {
      const to = document.getElementById('to').value.trim();
      const msg = document.getElementById('msg').value.trim();
      if (!to || !msg) return;
      try {
        const r = await fetch('api/send', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({to, message: msg})
        }).then(r => r.json());
        if (r.success) {
          document.getElementById('msg').value = '';
          await pollMessages();
        } else {
          alert('Fehler: ' + r.error);
        }
      } catch(e) { alert('Netzwerkfehler'); }
    }

    async function logout() {
      if (!confirm('Wirklich abmelden?')) return;
      await fetch('api/logout', {method:'POST'});
    }

    refresh();
    setInterval(refresh, 5000);
    setInterval(pollMessages, 3000);
  </script>
</body>
</html>`);
});

// ── Start ─────────────────────────────────────────────────────────────────────

const PORT = parseInt(process.env.PORT || '3000', 10);
app.listen(PORT, () => console.log(`[INFO] Web UI running on port ${PORT}`));
