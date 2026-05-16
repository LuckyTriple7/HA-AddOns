'use strict';
(function () {
  const _ts = () => new Date().toLocaleTimeString('de-DE', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  ['log','warn','error'].forEach(m => {
    const orig = console[m].bind(console);
    console[m] = (...a) => {
      if (a.length && typeof a[0] === 'string' && /^\[(INFO|WARN|ERROR|DEBUG)\]/.test(a[0]))
        orig(a[0], `[${_ts()}]`, ...a.slice(1));
      else
        orig(`[INFO] [${_ts()}]`, ...a);
    };
  });
})();
const express = require('express');
const fetch = require('node-fetch');
const QRCode = require('qrcode');
const fs = require('fs');

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3000;
const SIGNAL_API = process.env.SIGNAL_API_URL || 'http://localhost:8080';
const WEBHOOK_INCOMING = process.env.WEBHOOK_INCOMING || '';
let PHONE_NUMBER = process.env.PHONE_NUMBER || '';
const DARK_MODE = process.env.DARK_MODE === 'true';
const DEBUG = process.env.DEBUG_MODE === 'true';
function dbg(...args) { if (DEBUG) console.log('[DEBUG]', ...args); }

let status = 'starting'; // starting | not-linked | linked | error
let lastError = '';
let qrSvg = null;      // inline SVG if API returns text URI
let qrUri = null;      // raw sgnl:// URI (if API returns text)
let qrDataUrl = null;  // data URL if API returns image directly
let qrFetching = false;

const chatMap = new Map();           // chatId -> { id, name, phone, lastMsg, lastTime }
const messagesByChatId = new Map();  // chatId -> Message[]
const seenMsgIds = new Set();

const CHATS_FILE = '/data/chats.json';
const MESSAGES_FILE = '/data/messages.json';

function normPhone(num) {
  if (!num) return '';
  const s = String(num).trim().replace(/[\s-]/g, '');
  if (s.startsWith('+')) return s;
  if (s.startsWith('00')) return '+' + s.slice(2);
  if (/^\d{7,15}$/.test(s)) return '+' + s;
  return s;
}

function loadFromDisk() {
  try {
    if (fs.existsSync(CHATS_FILE)) {
      const data = JSON.parse(fs.readFileSync(CHATS_FILE, 'utf8'));
      for (const [k, v] of Object.entries(data)) chatMap.set(k, v);
      console.log(`[INFO] Loaded ${chatMap.size} chats from disk`);
    }
  } catch (e) { console.error('[ERROR] loadChats from disk:', e.message); }
  try {
    if (fs.existsSync(MESSAGES_FILE)) {
      const data = JSON.parse(fs.readFileSync(MESSAGES_FILE, 'utf8'));
      for (const [k, v] of Object.entries(data)) {
        messagesByChatId.set(k, v);
        v.forEach(m => seenMsgIds.add(m.id));
      }
      console.log(`[INFO] Loaded messages for ${messagesByChatId.size} chats from disk`);
    }
  } catch (e) { console.error('[ERROR] loadMessages from disk:', e.message); }

  // Normalize phone-number keys to consistent +prefix (fixes duplicate chats after restarts)
  for (const [k, v] of [...chatMap.entries()]) {
    const nk = normPhone(k);
    if (nk !== k && !chatMap.has(nk)) { chatMap.set(nk, { ...v, id: nk }); chatMap.delete(k); }
  }
  for (const [k, v] of [...messagesByChatId.entries()]) {
    const nk = normPhone(k);
    if (nk !== k && !messagesByChatId.has(nk)) { messagesByChatId.set(nk, v); messagesByChatId.delete(k); }
  }
}

let saveTimer = null;
function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try {
      fs.writeFileSync(CHATS_FILE, JSON.stringify(Object.fromEntries(chatMap)));
      fs.writeFileSync(MESSAGES_FILE, JSON.stringify(Object.fromEntries(messagesByChatId)));
    } catch (e) { console.error('[ERROR] saveToDisk:', e.message); }
  }, 5000);
}

async function checkStatus() {
  try {
    const aboutRes = await fetch(`${SIGNAL_API}/v1/about`, { timeout: 5000 });
    if (!aboutRes.ok) throw new Error('API not responding');

    const accountsRes = await fetch(`${SIGNAL_API}/v1/accounts`, { timeout: 5000 });
    if (!accountsRes.ok) { status = 'not-linked'; return; }

    const accounts = await accountsRes.json();
    const list = Array.isArray(accounts)
      ? accounts.map(a => (typeof a === 'string' ? a : a.number)).filter(Boolean)
      : [];

    if (list.length === 0) { status = 'not-linked'; return; }

    if (!PHONE_NUMBER) PHONE_NUMBER = normPhone(list[0]);

    if (status !== 'linked') {
      status = 'linked';
      qrSvg = null;
      qrUri = null;
      qrDataUrl = null;
      console.log(`[INFO] Linked as ${PHONE_NUMBER}`);
      if (DEBUG) console.log('[DEBUG] Debug-Modus aktiv');
      loadContacts();
      loadGroups();
    }
  } catch (e) {
    if (status === 'starting') status = 'error';
    lastError = String(e.message || e);
  }
}

async function fetchQR() {
  if (qrFetching) return;
  qrFetching = true;
  try {
    console.log('[INFO] Requesting QR code from signal-cli-rest-api...');
    const r = await fetch(`${SIGNAL_API}/v1/qrcodelink?device_name=HomeAssistant`, { timeout: 120000 });
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      throw new Error(`HTTP ${r.status}: ${body}`);
    }
    const contentType = r.headers.get('content-type') || '';
    console.log('[INFO] QR response content-type:', contentType);
    if (contentType.includes('image/')) {
      // API returns a ready-made QR image — use it directly
      const buf = await r.buffer();
      qrDataUrl = `data:${contentType.split(';')[0]};base64,` + buf.toString('base64');
      qrSvg = null;
      qrUri = null;
      console.log('[INFO] QR image ready (' + buf.length + ' bytes)');
    } else {
      // API returns sgnl:// URI as text — generate QR ourselves
      qrUri = (await r.text()).trim();
      qrSvg = await QRCode.toString(qrUri, { type: 'svg', errorCorrectionLevel: 'L', margin: 2 });
      qrDataUrl = null;
      console.log('[INFO] QR URI received:', qrUri.substring(0, 60) + '...');
    }
  } catch (e) {
    console.error('[ERROR] QR fetch failed:', e.message);
    lastError = 'QR-Code Fehler: ' + String(e.message || e);
  }
  qrFetching = false;
  // Retry after 5s if still no QR
  if (!qrSvg && !qrDataUrl && status === 'not-linked') {
    setTimeout(fetchQR, 5000);
  }
}

async function loadContacts() {
  if (!PHONE_NUMBER) return;
  try {
    const r = await fetch(`${SIGNAL_API}/v1/contacts/${encodeURIComponent(PHONE_NUMBER)}`, { timeout: 10000 });
    if (!r.ok) return;
    const contacts = await r.json();
    if (!Array.isArray(contacts)) return;
    for (const c of contacts) {
      const num = normPhone(c.number || c.phone);
      if (!num || num === PHONE_NUMBER) continue;
      if (!chatMap.has(num)) {
        chatMap.set(num, { id: num, name: c.name || num, phone: num, lastMsg: '', lastTime: 0 });
      } else if (c.name) {
        chatMap.get(num).name = c.name;
      }
    }
    scheduleSave();
  } catch (e) {
    console.error('[ERROR] loadContacts:', e.message);
  }
}

async function loadGroups() {
  if (!PHONE_NUMBER) return;
  try {
    const r = await fetch(`${SIGNAL_API}/v1/groups/${encodeURIComponent(PHONE_NUMBER)}`, { timeout: 10000 });
    if (!r.ok) return;
    const groups = await r.json();
    if (!Array.isArray(groups)) return;
    for (const g of groups) {
      const id = g.id || g.internal_id;
      if (!id) continue;
      if (!chatMap.has(id)) {
        chatMap.set(id, { id, name: g.name || 'Gruppe', phone: '', lastMsg: '', lastTime: 0, isGroup: true });
      }
    }
    scheduleSave();
  } catch (e) {
    console.error('[ERROR] loadGroups:', e.message);
  }
}

function processEnvelope(envelope) {
  const env = envelope.envelope || envelope;
  const dm = env.dataMessage;
  const source = normPhone(env.sourceNumber || env.source);
  dbg(`processEnvelope: source=${source} hasDataMessage=${!!dm} body="${(dm?.message||'').slice(0,60)}"`);
  if (!dm || !source || !dm.message) { dbg(`processEnvelope: skipping — no dataMessage or message text`); return; }

  const msgId = `${source}_${dm.timestamp}`;
  if (seenMsgIds.has(msgId)) { dbg(`processEnvelope: duplicate skipped ${msgId}`); return; }
  seenMsgIds.add(msgId);

  const isOwn = source === PHONE_NUMBER;
  const chatId = source;
  const senderName = env.sourceName || source;

  const msg = { id: msgId, from: source, body: dm.message, timestamp: dm.timestamp, fromMe: isOwn };

  if (!messagesByChatId.has(chatId)) messagesByChatId.set(chatId, []);
  messagesByChatId.get(chatId).push(msg);

  if (!chatMap.has(chatId)) {
    chatMap.set(chatId, { id: chatId, name: senderName, phone: source, lastMsg: dm.message, lastTime: dm.timestamp });
  } else {
    const chat = chatMap.get(chatId);
    chat.lastMsg = dm.message;
    chat.lastTime = dm.timestamp;
    if (senderName && senderName !== source) chat.name = senderName;
  }

  scheduleSave();

  dbg(`processEnvelope: stored msgId=${msgId} fromMe=${isOwn} chatId=${chatId}`);

  if (WEBHOOK_INCOMING && !isOwn) {
    dbg(`Firing incoming webhook: ${WEBHOOK_INCOMING}`);
    fetch(WEBHOOK_INCOMING, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from: source, name: senderName, message: dm.message, timestamp: dm.timestamp }),
    }).catch(() => {});
  }
}

async function pollMessages() {
  if (status !== 'linked' || !PHONE_NUMBER) return;
  try {
    const r = await fetch(`${SIGNAL_API}/v1/receive/${encodeURIComponent(PHONE_NUMBER)}`, { timeout: 5000 });
    if (!r.ok) return;
    const messages = await r.json();
    if (Array.isArray(messages) && messages.length > 0) {
      dbg(`pollMessages: received ${messages.length} envelope(s)`);
      messages.forEach(processEnvelope);
    }
  } catch (e) {}
}

// --- API ---

app.get('/api/status', (req, res) => {
  res.json({ status, phone: PHONE_NUMBER, error: lastError });
});

app.get('/api/qr', async (req, res) => {
  if (status === 'linked') return res.json({ status: 'linked' });
  if (!qrSvg && !qrDataUrl && !qrFetching) fetchQR();
  res.json({ svg: qrSvg, dataUrl: qrDataUrl, uri: qrUri, status, error: (!qrSvg && !qrDataUrl && !qrFetching) ? lastError : null });
});

app.get('/api/chats', (req, res) => {
  const chats = Array.from(chatMap.values()).sort((a, b) => (b.lastTime || 0) - (a.lastTime || 0));
  res.json(chats);
});

app.get('/api/messages/:chatId', (req, res) => {
  res.json(messagesByChatId.get(req.params.chatId) || []);
});

app.post('/api/send', async (req, res) => {
  const { to, message } = req.body;
  if (!to || !message) return res.status(400).json({ error: 'Missing to/message' });
  try {
    dbg(`Sending message to ${to}: "${message.slice(0,60)}${message.length>60?'…':''}"`);
    const r = await fetch(`${SIGNAL_API}/v2/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, number: PHONE_NUMBER, recipients: [to] }),
      timeout: 10000,
    });
    const result = await r.json();
    if (!r.ok) return res.status(500).json({ error: result });

    const msgId = `${PHONE_NUMBER}_${Date.now()}`;
    if (!seenMsgIds.has(msgId)) {
      seenMsgIds.add(msgId);
      const msg = { id: msgId, from: PHONE_NUMBER, body: message, timestamp: Date.now(), fromMe: true };
      if (!messagesByChatId.has(to)) messagesByChatId.set(to, []);
      messagesByChatId.get(to).push(msg);
      if (!chatMap.has(to)) {
        chatMap.set(to, { id: to, name: to, phone: to, lastMsg: message, lastTime: Date.now() });
      } else {
        const chat = chatMap.get(to);
        chat.lastMsg = message;
        chat.lastTime = Date.now();
      }
      scheduleSave();
    }
    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
});

app.post('/api/qr/refresh', (req, res) => {
  qrSvg = null;
  qrUri = null;
  qrDataUrl = null;
  fetchQR();
  res.json({ ok: true });
});

app.delete('/api/messages/:chatId/:msgId', async (req, res) => {
  const { chatId, msgId } = req.params;
  dbg(`Deleting message ${msgId} in chat ${chatId}`);
  // Always remove locally so the message disappears from the UI
  const msgs = messagesByChatId.get(chatId);
  if (msgs) {
    const idx = msgs.findIndex(m => m.id === msgId);
    if (idx !== -1) { msgs.splice(idx, 1); seenMsgIds.delete(msgId); scheduleSave(); }
  }
  // Try platform delete in background (requires signal-cli-rest-api with deleteForEveryone support)
  if (status === 'linked') {
    try {
      const rawTs = parseInt(msgId.split('_').pop(), 10);
      const tsMs = rawTs > 1e12 ? rawTs : rawTs * 1000;
      const r = await fetch(`${SIGNAL_API}/v2/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ number: PHONE_NUMBER, recipients: [chatId], deleteForEveryone: true, deleteForEveryoneTimestamp: tsMs }),
        timeout: 10000,
      });
      if (!r.ok) {
        const t = await r.text().catch(() => '');
        console.warn(`[WARN] Signal delete-for-everyone not supported by this API version: ${t.trim()}`);
      }
    } catch (e) {
      console.warn('[WARN] Signal delete-for-everyone:', e.message);
    }
  }
  res.json({ success: true });
});

app.post('/api/logout', async (req, res) => {
  res.json({ success: true });
  try {
    await fetch(`${SIGNAL_API}/v1/unregister/${encodeURIComponent(PHONE_NUMBER)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delete_account: false }),
    });
  } catch (e) {}
  PHONE_NUMBER = process.env.PHONE_NUMBER || '';
  status = 'not-linked';
  qrSvg = null;
  qrUri = null;
  qrDataUrl = null;
  chatMap.clear();
  messagesByChatId.clear();
  seenMsgIds.clear();
  try { fs.unlinkSync(CHATS_FILE); } catch (e) {}
  try { fs.unlinkSync(MESSAGES_FILE); } catch (e) {}
  fetchQR();
});

// --- UI ---

app.get('*', (req, res) => {
  if (req.path !== '/' && !req.path.startsWith('/api')) {
    return res.redirect(req.baseUrl + '/');
  }
  res.send(getHtml());
});

function getHtml() {
  return `<!DOCTYPE html>
<html lang="de" class="${DARK_MODE ? 'dark' : 'light'}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Signal</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; height: 100vh; display: flex; flex-direction: column; background: #f0f2f5; color: #111; }

#spinner-overlay { display: flex; flex-direction: column; align-items: center; justify-content: center; position: fixed; inset: 0; background: #1b1c22; z-index: 100; gap: 20px; }
#spinner-overlay .spinner { width: 48px; height: 48px; border: 4px solid #3a76f8; border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
#spinner-text { color: #fff; font-size: 16px; text-align: center; padding: 0 24px; }

#qr-overlay { display: none; flex-direction: column; align-items: center; justify-content: center; position: fixed; inset: 0; background: #1b1c22; z-index: 99; gap: 14px; padding: 24px; overflow-y: auto; }
#qr-overlay h2 { color: #fff; font-size: 20px; }
#qr-overlay p { color: #aaa; text-align: center; font-size: 14px; max-width: 360px; line-height: 1.5; }
#qr-img { background: white; padding: 12px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 14px; color: #666; }
#qr-img svg { width: 300px; height: 300px; display: block; }
#qr-uri { font-size: 10px; color: #555; word-break: break-all; max-width: 360px; text-align: center; }
#qr-refresh-btn { background: #3a76f8; color: white; border: none; padding: 8px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; }
#qr-refresh-btn:hover { background: #2960d6; }

#topbar { display: none; align-items: center; background: #1b1b21; color: #fff; padding: 0 16px; height: 56px; gap: 12px; flex-shrink: 0; }
#topbar h1 { font-size: 18px; flex: 1; }
#topbar .phone { font-size: 13px; color: #aaa; }
#logout-btn { background: transparent; border: 1px solid #555; color: #fff; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; }
#logout-btn:hover { background: rgba(255,255,255,0.1); }

#main { display: none; flex: 1; overflow: hidden; }

#sidebar { width: 360px; min-width: 280px; background: #fff; display: flex; flex-direction: column; border-right: 1px solid #e0e0e0; }
#search-wrap { padding: 8px 12px; border-bottom: 1px solid #e0e0e0; }
#search-input { width: 100%; padding: 8px 12px; border-radius: 20px; border: none; background: #f0f2f5; font-size: 14px; outline: none; }
#chat-list { flex: 1; overflow-y: auto; }
.chat-item { display: flex; align-items: center; padding: 12px 16px; cursor: pointer; gap: 12px; border-bottom: 1px solid #f5f5f5; }
.chat-item:hover { background: #f5f5f5; }
.chat-item.active { background: #e9edf5; }
.avatar { width: 46px; height: 46px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 18px; color: white; flex-shrink: 0; }
.chat-info { flex: 1; overflow: hidden; }
.chat-name { font-size: 15px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.chat-preview { font-size: 13px; color: #999; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; }
.chat-time { font-size: 12px; color: #999; white-space: nowrap; }

#chat-panel { flex: 1; display: flex; flex-direction: column; background: #e5ddd5; }
#chat-header { background: #1b1b21; color: #fff; padding: 12px 16px; display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
#back-btn { display: none; background: none; border: none; color: #fff; font-size: 20px; cursor: pointer; padding: 0 8px 0 0; line-height: 1; }
#ch-name { font-weight: 600; font-size: 16px; flex: 1; }
#ch-phone { font-size: 12px; color: #aaa; }
#messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 4px; }
#no-chat { flex: 1; display: flex; align-items: center; justify-content: center; color: #999; font-size: 15px; }
.bubble { max-width: 65%; padding: 8px 12px; border-radius: 8px; font-size: 14px; line-height: 1.4; word-break: break-word; }
.bubble.in { background: #fff; border-bottom-left-radius: 2px; }
.bubble.out { background: #dcf8c6; border-bottom-right-radius: 2px; }
.bubble-row { display: flex; align-items: center; gap: 6px; }
.bubble-row.out { justify-content: flex-end; }
.bubble-row.in { justify-content: flex-start; }
.bubble-row.out .del-btn { order: -1; }
.del-btn { display: none; background: none; border: none; cursor: pointer; font-size: 15px; padding: 4px 6px; line-height: 1; border-radius: 6px; flex-shrink: 0; }
.bubble-row:hover .del-btn { display: block; }
html.dark .del-btn { color: rgba(233,237,239,0.6); }
html.light .del-btn { color: rgba(0,0,0,0.4); }
.del-btn:hover { color: #e74c3c !important; }
.bubble-time { font-size: 11px; color: #999; text-align: right; margin-top: 2px; }
.day-sep { text-align: center; margin: 8px 0; }
.day-sep span { background: rgba(255,255,255,0.8); padding: 4px 12px; border-radius: 12px; font-size: 12px; color: #666; }

#input-bar { background: #f0f2f5; padding: 8px 16px; display: flex; gap: 8px; align-items: flex-end; flex-shrink: 0; position: relative; }
#emoji-picker { display: none; position: absolute; bottom: 100%; left: 0; right: 0; background: #fff; border-top: 1px solid #e0e0e0; padding: 8px 12px; max-height: 200px; overflow-y: auto; z-index: 20; box-shadow: 0 -2px 8px rgba(0,0,0,0.08); }
#emoji-picker.open { display: block; }
.emoji-grid { display: flex; flex-wrap: wrap; gap: 2px; }
.emoji-btn { background: none; border: none; font-size: 22px; cursor: pointer; padding: 3px 5px; border-radius: 6px; line-height: 1; }
.emoji-btn:hover { background: #f0f2f5; }
#emoji-toggle { background: none; border: none; font-size: 20px; cursor: pointer; padding: 6px; border-radius: 50%; flex-shrink: 0; line-height: 1; }
#emoji-toggle:hover { background: rgba(0,0,0,0.08); }
#msg-input { flex: 1; padding: 10px 14px; border-radius: 20px; border: none; background: #fff; font-size: 14px; outline: none; resize: none; max-height: 120px; overflow-y: auto; font-family: inherit; }
#send-btn { width: 40px; height: 40px; border-radius: 50%; border: none; background: #3a76f8; color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
#send-btn:hover { background: #2960d6; }

@media (max-width: 768px) {
  #sidebar { width: 100%; max-width: 100%; border-right: none; }
  #chat-panel { display: none; }
  #back-btn { display: block; }
  body.chat-open #sidebar { display: none; }
  body.chat-open #chat-panel { display: flex; }
}

html.dark body { background: #0b141a; color: #e9edef; }
html.dark #sidebar { background: #111b21; border-color: #2a3942; }
html.dark #search-wrap { border-color: #2a3942; }
html.dark #search-input { background: #2a3942; color: #e9edef; }
html.dark .chat-item { border-color: #1e2b32; }
html.dark .chat-item:hover { background: #202c33; }
html.dark .chat-item.active { background: #2a3942; }
html.dark .chat-name { color: #e9edef; }
html.dark .chat-preview { color: #8696a0; }
html.dark .chat-time { color: #8696a0; }
html.dark #chat-panel { background: #0b141a; }
html.dark .bubble.in { background: #202c33; color: #e9edef; }
html.dark .bubble.out { background: #005c4b; color: #e9edef; }
html.dark .bubble-time { color: rgba(134,150,160,0.85); }
html.dark .day-sep span { background: rgba(17,27,33,0.9); color: #8696a0; }
html.dark #no-chat { color: #8696a0; }
html.dark #input-bar { background: #202c33; }
html.dark #msg-input { background: #2a3942; color: #e9edef; }
html.dark #emoji-picker { background: #202c33; border-color: #2a3942; }
html.dark .emoji-btn:hover { background: #2a3942; }
html.dark #emoji-toggle { color: #8696a0; }
</style>
</head>
<body>

<div id="spinner-overlay">
  <div class="spinner"></div>
  <div id="spinner-text">Starte Signal…</div>
</div>

<div id="qr-overlay">
  <h2>Signal verknüpfen</h2>
  <p>Signal öffnen → Einstellungen → Verknüpfte Geräte → Gerät hinzufügen → QR-Code scannen</p>
  <div id="qr-img">Lade QR-Code…</div>
  <button id="qr-refresh-btn" onclick="refreshQR()">QR-Code neu laden</button>
  <p id="qr-uri"></p>
</div>

<div id="topbar">
  <h1>Signal</h1>
  <span class="phone" id="my-phone"></span>
  <button id="logout-btn" onclick="logout()">Abmelden</button>
</div>

<div id="main">
  <div id="sidebar">
    <div id="search-wrap">
      <input id="search-input" type="text" placeholder="Suchen…" oninput="filterChats(this.value)">
    </div>
    <div id="chat-list"></div>
  </div>
  <div id="chat-panel">
    <div id="chat-header">
      <button id="back-btn" onclick="closeChat()">&#8592;</button>
      <div class="avatar" id="ch-avatar" style="width:36px;height:36px;font-size:14px;background:#3a76f8">?</div>
      <div style="flex:1;overflow:hidden">
        <div id="ch-name">Kein Chat ausgewählt</div>
        <div id="ch-phone"></div>
      </div>
    </div>
    <div id="messages"><div id="no-chat">Wähle einen Chat aus der Liste</div></div>
    <div id="input-bar">
      <div id="emoji-picker"><div class="emoji-grid" id="emoji-grid"></div></div>
      <button id="emoji-toggle" onclick="toggleEmojiPicker(event)" title="Emoji">😊</button>
      <textarea id="msg-input" rows="1" placeholder="Nachricht…" onkeydown="handleKey(event)" oninput="autoResize(this)"></textarea>
      <button id="send-btn" onclick="sendMsg()">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="white"><path d="M2 21l21-9L2 3v7l15 2-15 2v7z"/></svg>
      </button>
    </div>
  </div>
</div>

<script>
const BASE = location.pathname.replace(/\\/$/, '');
let currentStatus = '';
let selectedChatId = null;
let allChats = [];

function api(path) { return BASE + path; }

function showSpinner(msg) {
  document.getElementById('spinner-overlay').style.display = 'flex';
  document.getElementById('spinner-text').textContent = msg || 'Verbinde…';
  document.getElementById('topbar').style.display = 'none';
  document.getElementById('main').style.display = 'none';
  document.getElementById('qr-overlay').style.display = 'none';
  currentStatus = '';
}

function showQR() {
  document.getElementById('spinner-overlay').style.display = 'none';
  document.getElementById('qr-overlay').style.display = 'flex';
  document.getElementById('topbar').style.display = 'none';
  document.getElementById('main').style.display = 'none';
  loadQR();
}

function showMain(phone) {
  document.getElementById('spinner-overlay').style.display = 'none';
  document.getElementById('qr-overlay').style.display = 'none';
  document.getElementById('topbar').style.display = 'flex';
  document.getElementById('main').style.display = 'flex';
  document.getElementById('my-phone').textContent = phone || '';
}

let qrInterval = null;

function loadQR() {
  fetch(api('/api/qr'))
    .then(r => r.json())
    .then(d => {
      if (d.status === 'linked') { refresh(); return; }
      const el = document.getElementById('qr-img');
      const uriEl = document.getElementById('qr-uri');
      if (d.dataUrl) {
        // API returned PNG image directly — display as-is
        el.innerHTML = '<img src="' + d.dataUrl + '" style="width:300px;height:300px;image-rendering:pixelated;">';
      } else if (d.svg) {
        // API returned text URI — our generated SVG
        el.innerHTML = d.svg;
        const svg = el.querySelector('svg');
        if (svg) { svg.style.width = '300px'; svg.style.height = '300px'; }
      } else if (d.error) {
        el.textContent = 'Fehler: ' + d.error;
      } else {
        el.textContent = 'Lade QR-Code… (kann bis zu 60s dauern)';
      }
      if (uriEl) uriEl.textContent = d.uri ? 'URI: ' + d.uri.substring(0, 40) + '…' : '';
    }).catch(() => {});
  if (!qrInterval) qrInterval = setInterval(loadQR, 5000);
}

function refreshQR() {
  const el = document.getElementById('qr-img');
  el.textContent = 'Lade QR-Code…';
  document.getElementById('qr-uri').textContent = '';
  // Tell server to fetch a fresh QR code
  fetch(api('/api/qr/refresh'), { method: 'POST' }).catch(() => {});
  setTimeout(loadQR, 1000);
}

async function refresh() {
  try {
    const d = await fetch(api('/api/status')).then(r => r.json());
    if (d.status === currentStatus) return;
    currentStatus = d.status;

    if (d.status === 'starting') {
      showSpinner('Starte Signal…');
    } else if (d.status === 'not-linked') {
      if (qrInterval) { clearInterval(qrInterval); qrInterval = null; }
      showQR();
    } else if (d.status === 'linked') {
      if (qrInterval) { clearInterval(qrInterval); qrInterval = null; }
      showMain(d.phone);
      loadChats();
    } else if (d.status === 'error') {
      showSpinner('Fehler: ' + d.error);
    }
  } catch (e) {}
}

setInterval(refresh, 3000);
refresh();

// Chat list
const COLORS = ['#e53935','#8e24aa','#1e88e5','#00897b','#43a047','#fb8c00','#d81b60','#6d4c41'];
function avatarColor(s) {
  let h = 0; for (const c of String(s)) h = (h * 31 + c.charCodeAt(0)) & 0xffff;
  return COLORS[h % COLORS.length];
}
function avatarInitial(s) { return (String(s || '?')).charAt(0).toUpperCase(); }

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts > 1e12 ? ts : ts * 1000);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function loadChats() {
  try {
    const chats = await fetch(api('/api/chats')).then(r => r.json());
    allChats = chats;
    renderChats(chats);
    if (selectedChatId) loadMessages(selectedChatId);
  } catch (e) {}
}
setInterval(loadChats, 5000);

function renderChats(chats) {
  const q = document.getElementById('search-input').value.toLowerCase();
  const filtered = q ? chats.filter(c => (c.name||'').toLowerCase().includes(q) || (c.phone||'').includes(q)) : chats;
  const el = document.getElementById('chat-list');
  el.innerHTML = filtered.map(c => \`
    <div class="chat-item\${c.id === selectedChatId ? ' active' : ''}" data-chatid="\${escHtml(c.id)}" onclick="openChatById(this.dataset.chatid)">
      <div class="avatar" style="background:\${avatarColor(c.name || c.id)}">\${avatarInitial(c.name || c.id)}</div>
      <div class="chat-info">
        <div class="chat-name">\${escHtml(c.name || c.id)}</div>
        <div class="chat-preview">\${escHtml(c.lastMsg || '')}</div>
      </div>
      <div class="chat-time">\${formatTime(c.lastTime)}</div>
    </div>
  \`).join('');
}

function filterChats() {
  renderChats(allChats);
}

function openChatById(chatId) {
  const chat = allChats.find(c => c.id === chatId);
  if (chat) openChat(chat);
}

function openChat(chat) {
  selectedChatId = chat.id;
  document.body.classList.add('chat-open');
  document.getElementById('ch-name').textContent = chat.name || chat.id;
  const ph = chat.phone || '';
  document.getElementById('ch-phone').textContent = /^\\+?\\d{7,15}$/.test(ph) ? ph : '';
  const av = document.getElementById('ch-avatar');
  av.textContent = avatarInitial(chat.name || chat.id);
  av.style.background = avatarColor(chat.name || chat.id);
  renderChats(allChats);
  loadMessages(chat.id);
}

function closeChat() {
  document.body.classList.remove('chat-open');
  selectedChatId = null;
}

async function loadMessages(chatId) {
  if (!chatId) return;
  try {
    const msgs = await fetch(api('/api/messages/' + encodeURIComponent(chatId))).then(r => r.json());
    renderMessages(msgs);
  } catch (e) {}
}

function renderMessages(msgs) {
  const el = document.getElementById('messages');
  if (!msgs.length) { el.innerHTML = '<div id="no-chat">Noch keine Nachrichten</div>'; return; }
  let lastDate = '';
  el.innerHTML = msgs.map(m => {
    const d = new Date(m.timestamp > 1e12 ? m.timestamp : m.timestamp * 1000);
    const dateStr = d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
    let sep = '';
    if (dateStr !== lastDate) { sep = \`<div class="day-sep"><span>\${dateStr}</span></div>\`; lastDate = dateStr; }
    const time = d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    return sep + \`<div class="bubble-row \${m.fromMe ? 'out' : 'in'}" data-msgid="\${escHtml(m.id)}" data-chatid="\${escHtml(selectedChatId)}"><div class="bubble \${m.fromMe ? 'out' : 'in'}">\${escHtml(m.body)}<div class="bubble-time">\${time}</div></div><button class="del-btn" title="Löschen">✕</button></div>\`;
  }).join('');
  el.scrollTop = el.scrollHeight;
}

async function sendMsg() {
  if (!selectedChatId) return;
  const inp = document.getElementById('msg-input');
  const text = inp.value.trim();
  if (!text) return;
  inp.value = '';
  inp.style.height = '';
  try {
    await fetch(api('/api/send'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to: selectedChatId, message: text }),
    });
    await loadMessages(selectedChatId);
    await loadChats();
  } catch (e) { alert('Fehler: ' + e.message); }
}

async function logout() {
  showSpinner('Abmelden…');
  await fetch(api('/api/logout'), { method: 'POST' }).catch(() => {});
}

async function deleteMsg(chatId, msgId) {
  try {
    await fetch(api('/api/messages/'+encodeURIComponent(chatId)+'/'+encodeURIComponent(msgId)), {method:'DELETE'});
    await loadMessages(chatId);
  } catch(e) {}
}
document.getElementById('messages').addEventListener('click', e => {
  const btn = e.target.closest('.del-btn');
  if (!btn) return;
  const row = btn.closest('.bubble-row');
  if (!row) return;
  deleteMsg(row.dataset.chatid, row.dataset.msgid);
});

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg(); }
}
function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

const EMOJIS = [
  '😀','😂','🤣','😊','😇','🥰','😍','🤩','😘','😋','😜','🤪','😎','🥳','😏','🤔','🤗','😐','🙄','😒',
  '😔','🙃','😢','😭','😤','😠','🤬','🤯','😳','😱','🥺','😷','🤒','🤕','🤧','😴','🥱','🤤','😵','🤮',
  '👍','👎','👋','🤝','🙏','💪','✌️','🤞','🤟','🤘','🤙','👈','👉','👆','👇','👏','🙌','🤲','✋','🖐️',
  '❤️','🧡','💛','💚','💙','💜','🖤','🤍','🤎','💔','💕','💞','💓','💗','💖','💘','💝',
  '🎉','🎊','🎈','🎁','🎂','🏆','🥇','⭐','🌟','💫','✨','🔥','💯','💎','🚀','🌈','☀️','🌙','⛅','🌊',
  '🌸','🌺','🌹','🌻','🌼','🍀','🍁','🌴','🌵','🍄','🌍','🗺️',
  '🍕','🍔','🌮','🌯','🍜','🍝','🍣','🍱','🍦','🍰','🎂','🍫','🍬','🍭','🍺','🥂','☕','🍵','🥤','🍷',
  '🐶','🐱','🐭','🐰','🦊','🐻','🐼','🐨','🐯','🦁','🐮','🐷','🐸','🐵','🐔','🐧','🐦','🐤','😸','🐠',
  '🎵','🎶','🎸','🎹','🎤','🎮','📱','💻','📷','🎬','🏖️','🏔️','🚗','✈️','🚢','🏠','🔑','💡','📚','🎯'
];

(function buildEmojiGrid() {
  const grid = document.getElementById('emoji-grid');
  EMOJIS.forEach(e => {
    const btn = document.createElement('button');
    btn.className = 'emoji-btn';
    btn.textContent = e;
    btn.onclick = () => insertEmoji(e);
    grid.appendChild(btn);
  });
})();

function toggleEmojiPicker(evt) {
  evt.stopPropagation();
  document.getElementById('emoji-picker').classList.toggle('open');
}

function insertEmoji(emoji) {
  const inp = document.getElementById('msg-input');
  const start = inp.selectionStart;
  const end = inp.selectionEnd;
  inp.value = inp.value.slice(0, start) + emoji + inp.value.slice(end);
  inp.selectionStart = inp.selectionEnd = start + emoji.length;
  inp.focus();
  autoResize(inp);
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('#emoji-picker') && e.target.id !== 'emoji-toggle') {
    document.getElementById('emoji-picker').classList.remove('open');
  }
});
</script>
</body>
</html>`;
}

process.on('unhandledRejection', (reason) => {
  console.error('[ERROR] Unhandled rejection:', reason?.message || reason);
});

async function init() {
  console.log('[INFO] Signal UI starting...');
  loadFromDisk();
  let retries = 30;
  while (retries-- > 0) {
    try {
      const r = await fetch(`${SIGNAL_API}/v1/about`, { timeout: 3000 });
      if (r.ok) break;
    } catch (e) {}
    await new Promise(r => setTimeout(r, 2000));
  }
  await checkStatus();
  if (status === 'not-linked') fetchQR();
  if (status === 'linked') { loadContacts(); loadGroups(); }

  // Fast poll only when not yet linked, slow otherwise (accounts call blocks 1-2s in signal-cli)
  setInterval(() => {
    if (status !== 'linked') checkStatus();
  }, 5000);
  setInterval(() => {
    if (status === 'linked') checkStatus(); // detect unexpected unlink
  }, 60000);

  setInterval(pollMessages, 10000);  // receive is also signal-cli work — 10s is enough
  setInterval(() => { if (status === 'linked') { loadContacts(); loadGroups(); } }, 120000);
}

app.listen(PORT, () => {
  console.log(`[INFO] Signal UI listening on port ${PORT}`);
  init();
});
