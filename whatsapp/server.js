'use strict';

const { Client, NoAuth } = require('whatsapp-web.js');
const path = require('path');
const express = require('express');
const qrcode = require('qrcode');
const https = require('https');
const http = require('http');
const { URL } = require('url');
const { existsSync, rmSync } = require('fs');

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

const MAX_MSGS_PER_CHAT = 200;
const INITIAL_CHATS = parseInt(process.env.INITIAL_CHATS || '30', 10);
const INITIAL_MESSAGES = parseInt(process.env.INITIAL_MESSAGES || '20', 10);
const chatMap = new Map();          // chatId -> { id, name, phone, lastMsg, lastTime, isGroup }
const messagesByChatId = new Map(); // chatId -> Message[]
const seenIds = new Set();

function getChatMsgs(chatId) {
  if (!messagesByChatId.has(chatId)) messagesByChatId.set(chatId, []);
  return messagesByChatId.get(chatId);
}

function upsertChat(chatId, { name, phone, isGroup }) {
  if (!chatMap.has(chatId)) {
    chatMap.set(chatId, { id: chatId, name: name || chatId, phone: phone || '', isGroup: !!isGroup, lastMsg: '', lastTime: 0 });
  } else {
    const c = chatMap.get(chatId);
    if (name) c.name = name;
    if (phone && !c.phone) c.phone = phone;
  }
}

function addMsg(chatId, msg) {
  if (seenIds.has(msg.id)) return false;
  seenIds.add(msg.id);
  const msgs = getChatMsgs(chatId);
  msgs.push(msg);
  msgs.sort((a, b) => a.timestamp - b.timestamp);
  if (msgs.length > MAX_MSGS_PER_CHAT) msgs.splice(0, msgs.length - MAX_MSGS_PER_CHAT);
  const chat = chatMap.get(chatId);
  if (chat && msg.timestamp >= (chat.lastTime || 0)) {
    chat.lastMsg = msg.body.length > 60 ? msg.body.slice(0, 60) + '…' : msg.body;
    chat.lastTime = msg.timestamp;
  }
  return true;
}

// ── WhatsApp Client ───────────────────────────────────────────────────────────

// Store Chromium profile directly in the persistent addon_config volume.
// Using NoAuth + userDataDir is more reliable than LocalAuth's copy mechanism
// which can fail silently on slow hardware and leave the session folder empty.
const SESSION_CHROMIUM_DIR = path.join(process.env.SESSION_DIR || '/data/session', 'chromium');

const client = new Client({
  authStrategy: new NoAuth(),
  authTimeoutMs: 0,
  puppeteer: {
    executablePath: CHROMIUM,
    userDataDir: SESSION_CHROMIUM_DIR,
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
  status = 'authenticated';
  qrCodeDataUrl = null;
});

client.on('ready', async () => {
  connectedPhone = client.info?.wid?.user || null;
  status = 'connected';
  lastError = null;
  console.log(`[INFO] WhatsApp ready — phone: ${connectedPhone}`);

  try {
    const chats = await client.getChats();
    const recent = chats.slice(0, INITIAL_CHATS);
    console.log(`[INFO] Loading ${INITIAL_MESSAGES} messages from ${INITIAL_CHATS} chats`);
    for (const chat of recent) {
      const chatId = chat.id._serialized;
      upsertChat(chatId, { name: chat.name || chat.id.user, phone: chat.id.user, isGroup: chat.isGroup });

      const msgs = await chat.fetchMessages({ limit: INITIAL_MESSAGES }).catch(() => []);
      for (const msg of msgs) {
        if (msg.type !== 'chat' && msg.type !== 'text') continue;
        if (!msg.body) continue;
        let contactName = msg.fromMe ? 'Ich' : (chat.name || chat.id.user);
        if (!msg.fromMe && chat.isGroup) {
          const c = await msg.getContact().catch(() => null);
          contactName = c?.pushname || c?.name || msg.author?.replace('@c.us', '') || contactName;
        }
        addMsg(chatId, {
          id: msg.id._serialized,
          body: msg.body,
          timestamp: msg.timestamp * 1000,
          fromMe: msg.fromMe,
          contact: contactName,
        });
      }
    }
    const total = [...messagesByChatId.values()].reduce((s, a) => s + a.length, 0);
    console.log(`[INFO] Loaded ${total} messages from ${recent.length} chats`);
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

client.on('message', async (msg) => {
  if (msg.type !== 'chat' && msg.type !== 'text') return;
  if (!msg.body) return;
  const chat = await msg.getChat().catch(() => null);
  if (!chat) return;
  const chatId = chat.id._serialized;
  const contact = await msg.getContact().catch(() => null);
  const contactName = contact?.pushname || contact?.name || msg.from.replace('@c.us', '');
  upsertChat(chatId, { name: chat.name || contactName, phone: chat.id.user, isGroup: chat.isGroup });
  addMsg(chatId, {
    id: msg.id._serialized,
    body: msg.body,
    timestamp: msg.timestamp * 1000,
    fromMe: false,
    contact: contactName,
  });
  if (process.env.WEBHOOK_INCOMING) {
    postWebhook(process.env.WEBHOOK_INCOMING, { from: msg.from, body: msg.body, type: msg.type, timestamp: msg.timestamp });
  }
});

client.on('message_create', async (msg) => {
  if (!msg.fromMe) return;
  if (msg.type !== 'chat' && msg.type !== 'text') return;
  if (msg.__logged) return;
  const chat = await msg.getChat().catch(() => null);
  if (!chat) return;
  const chatId = chat.id._serialized;
  upsertChat(chatId, { name: chat.name || msg.to.replace('@c.us', ''), phone: chat.id.user, isGroup: chat.isGroup });
  addMsg(chatId, {
    id: msg.id._serialized,
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

// Puppeteer sometimes throws "No data found for resource" when WhatsApp
// intercepts network responses that are already gone — harmless, but would
// crash Node.js if unhandled.
process.on('unhandledRejection', (reason) => {
  const msg = reason?.message || String(reason);
  if (msg.includes('No data found for resource')) return;
  console.error('[ERROR] Unhandled rejection:', msg);
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

app.get('/api/chats', (req, res) => {
  const list = [...chatMap.values()].sort((a, b) => (b.lastTime || 0) - (a.lastTime || 0));
  res.json(list);
});

app.get('/api/messages', (req, res) => {
  const { chat: chatId, since } = req.query;
  if (!chatId) return res.json([]);
  const msgs = getChatMsgs(chatId);
  const since_ts = parseInt(since || '0', 10);
  res.json(since_ts ? msgs.filter(m => m.timestamp > since_ts) : msgs);
});

app.post('/api/send', async (req, res) => {
  const { to, message } = req.body;
  if (!to || !message) return res.status(400).json({ error: 'to and message required' });
  if (status !== 'connected') return res.status(503).json({ error: `Not connected (status: ${status})` });
  try {
    const jid = formatNumber(to);
    const result = await client.sendMessage(jid, message);
    result.__logged = true;
    const targetChatId = jid;
    if (!chatMap.has(targetChatId)) {
      upsertChat(targetChatId, { name: to.replace('@c.us', '').replace('@g.us', ''), phone: to.replace('@c.us', '').replace('@g.us', '') });
    }
    addMsg(targetChatId, {
      id: result.id._serialized,
      body: message,
      timestamp: Date.now(),
      fromMe: true,
      contact: 'Ich',
    });
    res.json({ success: true, id: result.id._serialized });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/logout', async (req, res) => {
  try {
    await client.logout();
  } catch (err) {
    // ignore — browser may already be gone
  }
  res.json({ success: true });
  setTimeout(() => process.exit(0), 500);
});

app.post('/api/reset', (req, res) => {
  try {
    rmSync(SESSION_CHROMIUM_DIR, { recursive: true, force: true });
    console.log('[INFO] Session deleted, restarting…');
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
  setTimeout(() => process.exit(0), 500);
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
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #111b21; color: #e9edef;
      height: 100vh; display: flex; flex-direction: column; overflow: hidden;
    }

    /* Top bar */
    .topbar {
      background: #202c33; padding: 10px 16px;
      display: flex; align-items: center; gap: 12px;
      border-bottom: 1px solid #2a3942; flex-shrink: 0; height: 56px;
    }
    .topbar .logo { font-size: 24px; }
    .topbar h1 { font-size: 16px; font-weight: 600; flex: 1; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .status-dot.connected { background: #25d366; }
    .status-dot.waiting   { background: #f0a500; }
    .status-dot.error, .status-dot.disconnected { background: #f15c5c; }
    .status-dot.initializing { background: #8696a0; }
    .status-label { font-size: 12px; color: #8696a0; }
    .logout-btn {
      background: none; border: none; color: #8696a0;
      font-size: 20px; cursor: pointer; padding: 4px; line-height: 1;
    }
    .logout-btn:hover { color: #f15c5c; }

    /* Main two-panel layout */
    #main { flex: 1; display: flex; overflow: hidden; }

    /* ── Sidebar ── */
    #sidebar {
      width: 340px; min-width: 260px;
      display: flex; flex-direction: column;
      border-right: 1px solid #2a3942; flex-shrink: 0;
    }
    #sidebar-header {
      padding: 8px 12px; background: #202c33;
      border-bottom: 1px solid #2a3942; flex-shrink: 0;
    }
    #search {
      width: 100%; background: #2a3942; border: none; border-radius: 8px;
      padding: 8px 12px; color: #e9edef; font-size: 14px; outline: none;
    }
    #search::placeholder { color: #8696a0; }
    #chat-list { flex: 1; overflow-y: auto; }
    #chat-list::-webkit-scrollbar { width: 5px; }
    #chat-list::-webkit-scrollbar-thumb { background: #2a3942; border-radius: 3px; }
    .chat-item {
      display: flex; align-items: center; gap: 12px;
      padding: 10px 16px; cursor: pointer;
      border-bottom: 1px solid #1e2b32; transition: background 0.12s;
    }
    .chat-item:hover { background: #202c33; }
    .chat-item.active { background: #2a3942; }
    .avatar {
      width: 46px; height: 46px; border-radius: 50%; flex-shrink: 0;
      display: flex; align-items: center; justify-content: center;
      font-size: 17px; font-weight: 700; color: #fff; user-select: none;
    }
    .chat-info { flex: 1; min-width: 0; }
    .chat-name {
      font-size: 15px; font-weight: 500;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .chat-preview {
      font-size: 13px; color: #8696a0; margin-top: 2px;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .chat-time { font-size: 11px; color: #8696a0; white-space: nowrap; flex-shrink: 0; align-self: flex-start; margin-top: 3px; }
    .no-chats { color: #8696a0; text-align: center; padding: 32px 16px; font-size: 14px; }

    /* ── Right panel ── */
    #chat-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; background: #0b141a; }

    #chat-header {
      background: #202c33; padding: 10px 16px;
      display: flex; align-items: center; gap: 12px;
      border-bottom: 1px solid #2a3942; flex-shrink: 0; min-height: 60px;
    }
    #chat-header .avatar { width: 40px; height: 40px; font-size: 15px; }
    #ch-name { font-size: 15px; font-weight: 600; }
    #ch-phone { font-size: 12px; color: #8696a0; }

    #messages {
      flex: 1; overflow-y: auto; padding: 12px 16px;
      display: flex; flex-direction: column; gap: 1px;
    }
    #messages::-webkit-scrollbar { width: 5px; }
    #messages::-webkit-scrollbar-thumb { background: #2a3942; border-radius: 3px; }

    .bubble-wrap { display: flex; flex-direction: column; margin: 1px 0; }
    .bubble-wrap.out { align-items: flex-end; }
    .bubble-wrap.in  { align-items: flex-start; }
    .contact-name { font-size: 11px; color: #8696a0; margin-bottom: 2px; padding: 0 4px; }
    .bubble {
      max-width: 65%; padding: 6px 10px 8px; border-radius: 7.5px;
      font-size: 14px; line-height: 1.45; word-break: break-word;
    }
    .bubble-wrap.out .bubble { background: #005c4b; border-top-right-radius: 0; }
    .bubble-wrap.in  .bubble { background: #202c33; border-top-left-radius: 0; }
    .bubble .time {
      font-size: 10px; color: rgba(134,150,160,0.85);
      float: right; margin-left: 8px; margin-top: 2px;
    }
    .date-sep {
      align-self: center; font-size: 12px; color: #8696a0;
      background: rgba(17,27,33,0.9); border-radius: 8px;
      padding: 4px 12px; margin: 8px 0;
    }
    .empty-msg { color: #8696a0; text-align: center; margin: auto; font-size: 14px; }

    /* Welcome screen */
    #welcome {
      flex: 1; display: flex; flex-direction: column;
      align-items: center; justify-content: center; gap: 12px; color: #8696a0;
    }
    #welcome .icon { font-size: 64px; }
    #welcome p { font-size: 15px; }

    /* Send bar */
    #send-bar {
      background: #202c33; padding: 10px 12px;
      display: flex; gap: 8px; align-items: flex-end;
      border-top: 1px solid #2a3942; flex-shrink: 0;
    }
    #msg-input {
      flex: 1; background: #2a3942; border: none; border-radius: 8px;
      padding: 9px 12px; color: #e9edef; font-size: 14px; font-family: inherit;
      resize: none; outline: none; max-height: 120px; min-height: 42px; line-height: 1.4;
    }
    #send-bar button {
      background: #25d366; border: none; border-radius: 50%;
      width: 42px; height: 42px; flex-shrink: 0; cursor: pointer;
      font-size: 18px; display: flex; align-items: center; justify-content: center;
    }
    #send-bar button:hover { background: #1da851; }

    /* Overlays */
    .overlay {
      position: fixed; inset: 0; background: #111b21; z-index: 100;
      display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 20px;
    }
    .overlay p { color: #8696a0; font-size: 14px; text-align: center; line-height: 1.7; }
    .overlay h2 { font-size: 20px; }
    #qr-overlay img { background: #fff; padding: 16px; border-radius: 12px; max-width: 280px; }
  </style>
</head>
<body>

  <div id="spinner-overlay" class="overlay">
    <div style="font-size:48px;">💬</div>
    <p id="spinner-text">Verbinde mit WhatsApp…</p>
    <button onclick="resetSession()" style="
      margin-top:16px; background:none; border:1px solid #3d5259;
      color:#8696a0; border-radius:8px; padding:8px 16px;
      font-size:13px; cursor:pointer;">
      Session zurücksetzen
    </button>
  </div>

  <div id="qr-overlay" class="overlay" style="display:none;">
    <div style="font-size:48px;">💬</div>
    <h2>WhatsApp Web</h2>
    <div id="qr-img"></div>
    <p>Öffne WhatsApp auf deinem Handy<br>
       <strong>Verknüpfte Geräte → Gerät hinzufügen</strong><br>
       und scanne den QR-Code</p>
  </div>

  <div class="topbar" id="topbar" style="display:none;">
    <div class="logo">💬</div>
    <h1>WhatsApp</h1>
    <span class="status-label" id="status-label">Verbunden</span>
    <div class="status-dot connected" id="status-dot"></div>
    <button class="logout-btn" title="Abmelden" onclick="logout()">⏻</button>
  </div>

  <div id="main" style="display:none;">

    <div id="sidebar">
      <div id="sidebar-header">
        <input type="text" id="search" placeholder="🔍  Chats durchsuchen…" oninput="filterChats()">
      </div>
      <div id="chat-list"><div class="no-chats">Lade Chats…</div></div>
    </div>

    <div id="chat-panel">
      <div id="welcome">
        <div class="icon">💬</div>
        <p>Wähle einen Chat aus der Liste</p>
      </div>
      <div id="chat-header" style="display:none;">
        <div class="avatar" id="ch-avatar"></div>
        <div>
          <div id="ch-name"></div>
          <div id="ch-phone"></div>
        </div>
      </div>
      <div id="messages" style="display:none;"></div>
      <div id="send-bar" style="display:none;">
        <textarea id="msg-input" rows="1" placeholder="Nachricht…"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMsg();}"
          oninput="autoResize(this)"></textarea>
        <button onclick="sendMsg()" title="Senden">➤</button>
      </div>
    </div>

  </div>

  <script>
    let currentStatus = '';
    let selectedChatId = null;
    let selectedChatPhone = null;
    let lastMsgTime = {};
    let allChats = [];
    let atBottom = true;

    const msgList = document.getElementById('messages');
    msgList.addEventListener('scroll', () => {
      atBottom = msgList.scrollTop + msgList.clientHeight >= msgList.scrollHeight - 30;
    });

    const COLORS = ['#128c7e','#075e54','#25d366','#34b7f1','#00bcd4','#9c27b0','#ff5722','#607d8b','#e91e63','#3f51b5'];
    function avatarColor(name) {
      let h = 0;
      for (let i = 0; i < name.length; i++) h = name.charCodeAt(i) + ((h << 5) - h);
      return COLORS[Math.abs(h) % COLORS.length];
    }
    function avatarInitials(name) {
      const p = name.trim().split(/\\s+/);
      return p.length >= 2 ? (p[0][0] + p[1][0]).toUpperCase() : name.slice(0,2).toUpperCase();
    }

    function fmtTime(ts) {
      return new Date(ts).toLocaleTimeString('de-DE', { hour:'2-digit', minute:'2-digit' });
    }
    function fmtDate(ts) {
      const d = new Date(ts), t = new Date();
      if (d.toDateString() === t.toDateString()) return 'Heute';
      const y = new Date(t); y.setDate(t.getDate()-1);
      if (d.toDateString() === y.toDateString()) return 'Gestern';
      return d.toLocaleDateString('de-DE');
    }
    function fmtChatTime(ts) {
      const d = new Date(ts), t = new Date();
      if (d.toDateString() === t.toDateString())
        return d.toLocaleTimeString('de-DE', { hour:'2-digit', minute:'2-digit' });
      const y = new Date(t); y.setDate(t.getDate()-1);
      if (d.toDateString() === y.toDateString()) return 'Gestern';
      return d.toLocaleDateString('de-DE', { day:'2-digit', month:'2-digit' });
    }
    function esc(s) {
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                      .replace(/\\n/g,'<br>');
    }
    function autoResize(el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    }

    function renderChatList(chats) {
      const list = document.getElementById('chat-list');
      const q = document.getElementById('search').value.toLowerCase();
      const filtered = q ? chats.filter(c => c.name.toLowerCase().includes(q)) : chats;
      if (!filtered.length) {
        list.innerHTML = '<div class="no-chats">Keine Chats</div>';
        return;
      }
      list.innerHTML = '';
      for (const chat of filtered) {
        const item = document.createElement('div');
        item.className = 'chat-item' + (chat.id === selectedChatId ? ' active' : '');
        item.dataset.id = chat.id;
        item.onclick = () => openChat(chat);

        const av = document.createElement('div');
        av.className = 'avatar';
        av.style.background = avatarColor(chat.name);
        av.textContent = avatarInitials(chat.name);

        const info = document.createElement('div');
        info.className = 'chat-info';
        info.innerHTML =
          '<div class="chat-name">' + esc(chat.name) + '</div>' +
          '<div class="chat-preview">' + esc(chat.lastMsg || '') + '</div>';

        const time = document.createElement('div');
        time.className = 'chat-time';
        time.textContent = chat.lastTime ? fmtChatTime(chat.lastTime) : '';

        item.appendChild(av); item.appendChild(info); item.appendChild(time);
        list.appendChild(item);
      }
    }

    function filterChats() { renderChatList(allChats); }

    async function openChat(chat) {
      selectedChatId = chat.id;
      selectedChatPhone = chat.phone;
      document.querySelectorAll('.chat-item').forEach(el => {
        el.classList.toggle('active', el.dataset.id === chat.id);
      });
      document.getElementById('welcome').style.display = 'none';
      document.getElementById('chat-header').style.display = 'flex';
      document.getElementById('messages').style.display = 'flex';
      document.getElementById('send-bar').style.display = 'flex';

      const av = document.getElementById('ch-avatar');
      av.style.background = avatarColor(chat.name);
      av.textContent = avatarInitials(chat.name);
      document.getElementById('ch-name').textContent = chat.name;
      // Only show phone if it looks like a real number (7-15 digits, not a WhatsApp LID)
      const ph = chat.phone || '';
      document.getElementById('ch-phone').textContent = /^\d{7,15}$/.test(ph) ? '+' + ph : '';

      msgList.innerHTML = '';
      lastMsgTime[chat.id] = 0;
      atBottom = true;
      await loadMessages(chat.id);
    }

    async function loadMessages(chatId) {
      if (!chatId) return;
      const since = lastMsgTime[chatId] || 0;
      try {
        const msgs = await fetch('api/messages?chat=' + encodeURIComponent(chatId) + '&since=' + since)
          .then(r => r.json());
        if (msgs.length) renderMessages(msgs, chatId);
      } catch(e) {}
    }

    function renderMessages(msgs, chatId) {
      if (chatId !== selectedChatId) return;
      if (!msgs.length) return;
      const noMsg = msgList.querySelector('.empty-msg');
      if (noMsg) noMsg.remove();

      let lastDate = msgList.querySelector('.date-sep:last-of-type')?.textContent || null;

      msgs.forEach(m => {
        const date = fmtDate(m.timestamp);
        if (date !== lastDate) {
          lastDate = date;
          const sep = document.createElement('div');
          sep.className = 'date-sep';
          sep.textContent = date;
          msgList.appendChild(sep);
        }
        const wrap = document.createElement('div');
        wrap.className = 'bubble-wrap ' + (m.fromMe ? 'out' : 'in');
        if (!m.fromMe && m.contact) {
          const n = document.createElement('div');
          n.className = 'contact-name';
          n.textContent = m.contact;
          wrap.appendChild(n);
        }
        const bub = document.createElement('div');
        bub.className = 'bubble';
        bub.innerHTML = esc(m.body) + '<span class="time">' + fmtTime(m.timestamp) + '</span>';
        wrap.appendChild(bub);
        msgList.appendChild(wrap);
        if (m.timestamp > (lastMsgTime[selectedChatId] || 0)) {
          lastMsgTime[selectedChatId] = m.timestamp;
        }
      });
      if (atBottom) msgList.scrollTop = msgList.scrollHeight;
    }

    async function pollMessages() {
      if (currentStatus !== 'connected' || !selectedChatId) return;
      await loadMessages(selectedChatId);
    }

    async function pollChats() {
      if (currentStatus !== 'connected') return;
      try {
        const chats = await fetch('api/chats').then(r => r.json());
        allChats = chats;
        renderChatList(chats);
      } catch(e) {}
    }

    async function sendMsg() {
      if (!selectedChatId) return;
      const txt = document.getElementById('msg-input').value.trim();
      if (!txt) return;
      try {
        const r = await fetch('api/send', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ to: selectedChatId, message: txt })
        }).then(r => r.json());
        if (r.success) {
          document.getElementById('msg-input').value = '';
          document.getElementById('msg-input').style.height = 'auto';
          atBottom = true;
          await pollMessages();
        } else {
          alert('Fehler: ' + r.error);
        }
      } catch(e) { alert('Netzwerkfehler'); }
    }

    let restartPolling = false;

    function waitForRestart(msg) {
      if (restartPolling) return;
      restartPolling = true;
      document.getElementById('spinner-overlay').style.display = 'flex';
      document.getElementById('spinner-text').textContent = msg || 'Starte neu…';
      document.getElementById('topbar').style.display = 'none';
      document.getElementById('main').style.display = 'none';
      document.getElementById('qr-overlay').style.display = 'none';
      currentStatus = '';
      // Wait 5s, then poll every 2s until server responds, then resume normal refresh
      setTimeout(function poll() {
        fetch('api/status')
          .then(r => r.json())
          .then(() => { restartPolling = false; refresh(); })
          .catch(() => setTimeout(poll, 2000));
      }, 5000);
    }

    async function logout() {
      if (!confirm('Wirklich abmelden?')) return;
      await fetch('api/logout', { method: 'POST' }).catch(() => {});
      waitForRestart('Abgemeldet — starte neu…');
    }

    async function resetSession() {
      if (!confirm('Session löschen und neu starten? Du musst den QR-Code erneut scannen.')) return;
      await fetch('api/reset', { method: 'POST' }).catch(() => {});
      waitForRestart('Session gelöscht — starte neu…');
    }

    async function refresh() {
      try {
        const s = await fetch('api/status').then(r => r.json());
        document.getElementById('status-dot').className = 'status-dot ' + (
          s.status === 'connected' ? 'connected' :
          s.status === 'waiting_for_scan' || s.status === 'authenticated' ? 'waiting' :
          s.status === 'initializing' ? 'initializing' : 'error'
        );
        document.getElementById('status-label').textContent = ({
          connected: 'Verbunden', waiting_for_scan: 'QR scannen',
          authenticated: 'Authentifiziert…', initializing: 'Starte…',
          disconnected: 'Getrennt', auth_failed: 'Auth-Fehler', error: 'Fehler',
        })[s.status] || s.status;

        if (s.status !== currentStatus) {
          currentStatus = s.status;
          const connecting = s.status === 'initializing' || s.status === 'authenticated' || s.status === 'disconnected';
          document.getElementById('spinner-text').textContent =
            s.status === 'disconnected' ? 'Abgemeldet — starte neu…' : 'Verbinde mit WhatsApp…';
          const qr = s.status === 'waiting_for_scan';
          const connected = s.status === 'connected';
          document.getElementById('spinner-overlay').style.display = connecting ? 'flex' : 'none';
          document.getElementById('qr-overlay').style.display = qr ? 'flex' : 'none';
          document.getElementById('topbar').style.display = connected ? 'flex' : 'none';
          document.getElementById('main').style.display = connected ? 'flex' : 'none';
          if (qr) {
            const d = await fetch('api/qr').then(r => r.json()).catch(() => null);
            if (d?.qr) document.getElementById('qr-img').innerHTML = '<img src="' + d.qr + '">';
          }
          if (connected) await pollChats();
        }
      } catch(e) {}
    }

    refresh();
    setInterval(refresh, 5000);
    setInterval(pollMessages, 2000);
    setInterval(pollChats, 10000);
  </script>
</body>
</html>`);
});

// ── Start ─────────────────────────────────────────────────────────────────────

const PORT = parseInt(process.env.PORT || '3000', 10);
app.listen(PORT, () => console.log(`[INFO] Web UI running on port ${PORT}`));
