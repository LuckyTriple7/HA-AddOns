'use strict';
const express = require('express');
const { TelegramClient } = require('telegram');
const { StringSession } = require('telegram/sessions');
const { NewMessage } = require('telegram/events');
const fs = require('fs');

const app = express();
app.use(express.json());

const PORT = parseInt(process.env.PORT || '3000', 10);
const API_ID = parseInt(process.env.API_ID || '0', 10);
const API_HASH = process.env.API_HASH || '';
const PHONE_NUMBER = process.env.PHONE_NUMBER || '';
const WEBHOOK_INCOMING = process.env.WEBHOOK_INCOMING || '';
const DARK_MODE = process.env.DARK_MODE !== 'false';
const DOWNLOAD_MEDIA = process.env.DOWNLOAD_MEDIA === 'true';
const FETCH_LIMIT = Math.min(Math.max(parseInt(process.env.FETCH_LIMIT || '50', 10), 1), 150);

const SESSION_FILE = '/data/session.txt';
const CHATS_FILE = '/data/chats.json';
const MESSAGES_FILE = '/data/messages.json';
const MEDIA_DIR = '/data/media';
const MAX_MSGS = 200;

// ── State ─────────────────────────────────────────────────────────────────────

let status = 'starting'; // starting | awaiting_code | awaiting_password | connected | error
let lastError = '';
let myId = '';
let myName = '';
let codeResolver = null;
let passwordResolver = null;

const chatMap = new Map();
const messagesByChatId = new Map();
const seenMsgIds = new Set();
const peerMap = new Map(); // chatId (str) -> entity (in-memory, lost on restart)

// ── Persistence ───────────────────────────────────────────────────────────────

function loadFromDisk() {
  try {
    if (fs.existsSync(CHATS_FILE)) {
      const data = JSON.parse(fs.readFileSync(CHATS_FILE, 'utf8'));
      for (const [k, v] of Object.entries(data)) chatMap.set(k, v);
      console.log(`[INFO] Loaded ${chatMap.size} chats from disk`);
    }
  } catch (e) { console.error('[ERROR] loadChats:', e.message); }
  try {
    if (fs.existsSync(MESSAGES_FILE)) {
      const data = JSON.parse(fs.readFileSync(MESSAGES_FILE, 'utf8'));
      for (const [k, v] of Object.entries(data)) {
        messagesByChatId.set(k, v);
        v.forEach(m => seenMsgIds.add(m.id));
      }
      console.log(`[INFO] Loaded messages for ${messagesByChatId.size} chats from disk`);
    }
  } catch (e) { console.error('[ERROR] loadMessages:', e.message); }
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

// ── Telegram client ───────────────────────────────────────────────────────────

const savedSession = fs.existsSync(SESSION_FILE)
  ? fs.readFileSync(SESSION_FILE, 'utf8').trim()
  : '';

const session = new StringSession(savedSession);
const client = new TelegramClient(session, API_ID, API_HASH, { connectionRetries: 5 });

function getEntityName(entity) {
  if (!entity) return '';
  if (entity.firstName !== undefined) {
    return [entity.firstName, entity.lastName].filter(Boolean).join(' ')
      || entity.username || String(entity.id);
  }
  return entity.title || entity.username || String(entity.id);
}

function getEntityId(entity) {
  return String(entity.id);
}

function addMsg(chatId, msg) {
  if (seenMsgIds.has(msg.id)) return false;
  seenMsgIds.add(msg.id);
  if (!messagesByChatId.has(chatId)) messagesByChatId.set(chatId, []);
  const msgs = messagesByChatId.get(chatId);
  msgs.push(msg);
  msgs.sort((a, b) => a.timestamp - b.timestamp);
  if (msgs.length > MAX_MSGS) msgs.splice(0, msgs.length - MAX_MSGS);
  return true;
}

async function downloadMedia(rawMsg, msgId) {
  try {
    const mediaClass = rawMsg.media?.className;
    if (!mediaClass || mediaClass === 'MessageMediaEmpty') return null;
    const safeId = msgId.replace(/-/g, 'm');
    let ext = 'jpg';
    if (mediaClass === 'MessageMediaDocument') {
      const mime = rawMsg.media.document?.mimeType || '';
      if (!mime.startsWith('image/')) return null;
      ext = mime === 'image/webp' ? 'webp' : mime === 'image/png' ? 'png' : 'jpg';
    } else if (mediaClass !== 'MessageMediaPhoto') {
      return null;
    }
    const filePath = `${MEDIA_DIR}/${safeId}.${ext}`;
    if (!fs.existsSync(filePath)) {
      const buf = await client.downloadMedia(rawMsg, {});
      if (buf) fs.writeFileSync(filePath, buf);
    }
    return fs.existsSync(filePath) ? `${safeId}.${ext}` : null;
  } catch (e) {
    console.error('[ERROR] downloadMedia:', e.message);
    return null;
  }
}

async function processMessage(rawMsg, chatId, chatName) {
  const hasText = !!(rawMsg.message);
  const hasMedia = rawMsg.media && rawMsg.media.className && rawMsg.media.className !== 'MessageMediaEmpty';
  if (!hasText && !hasMedia) return;

  const fromMe = rawMsg.out || false;
  const ts = (rawMsg.date || 0) * 1000;
  const msgId = `${chatId}_${rawMsg.id}`;

  if (seenMsgIds.has(msgId)) return;
  seenMsgIds.add(msgId);

  let type = 'text';
  let mediaFile = null;
  if (hasMedia) {
    const mc = rawMsg.media?.className;
    const isImage = mc === 'MessageMediaPhoto' ||
      (mc === 'MessageMediaDocument' && rawMsg.media.document?.mimeType?.startsWith('image/'));
    if (isImage) {
      type = 'photo';
      if (DOWNLOAD_MEDIA) mediaFile = await downloadMedia(rawMsg, msgId);
    }
  }

  const body = rawMsg.message || (type === 'photo' && !mediaFile ? '📷 Foto' : '');
  const preview = body || (type === 'photo' ? '📷 Foto' : '[Medien]');

  if (!messagesByChatId.has(chatId)) messagesByChatId.set(chatId, []);
  const msgs = messagesByChatId.get(chatId);
  msgs.push({ id: msgId, from: fromMe ? myId : chatId, body, type, mediaFile, timestamp: ts, fromMe });
  msgs.sort((a, b) => a.timestamp - b.timestamp);
  if (msgs.length > MAX_MSGS) msgs.splice(0, msgs.length - MAX_MSGS);

  if (!chatMap.has(chatId)) {
    chatMap.set(chatId, { id: chatId, name: chatName, phone: '', lastMsg: preview, lastTime: ts });
  } else {
    const chat = chatMap.get(chatId);
    if (ts >= (chat.lastTime || 0)) { chat.lastMsg = preview; chat.lastTime = ts; }
  }
  scheduleSave();

  if (WEBHOOK_INCOMING && !fromMe) {
    fetch(WEBHOOK_INCOMING, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from: chatId, name: chatName, message: body || '[Foto]', timestamp: ts }),
    }).catch(() => {});
  }
}

async function loadDialogs() {
  if (status !== 'connected') return;
  try {
    const dialogs = await client.getDialogs({ limit: 50 });
    for (const dialog of dialogs) {
      if (!dialog.entity) continue;
      const entity = dialog.entity;
      const chatId = getEntityId(entity);
      const name = getEntityName(entity);
      peerMap.set(chatId, entity);
      if (!chatMap.has(chatId) || !chatMap.get(chatId).lastTime) {
        chatMap.set(chatId, {
          id: chatId, name, phone: '',
          lastMsg: dialog.message?.message || '',
          lastTime: (dialog.message?.date || 0) * 1000,
        });
      }
    }
    scheduleSave();
    console.log(`[INFO] ${dialogs.length} dialogs loaded`);
  } catch (e) { console.error('[ERROR] loadDialogs:', e.message); }
}

async function fetchMessages(chatId, limit = FETCH_LIMIT) {
  try {
    let entity = peerMap.get(chatId);
    if (!entity) { await loadDialogs(); entity = peerMap.get(chatId); }
    if (!entity) return;
    const msgs = await client.getMessages(entity, { limit });
    const chatName = chatMap.get(chatId)?.name || chatId;
    for (const msg of msgs) processMessage(msg, chatId, chatName);
  } catch (e) { console.error(`[ERROR] fetchMessages(${chatId}):`, e.message); }
}

async function startClient() {
  if (!API_ID || !API_HASH || !PHONE_NUMBER) {
    status = 'error';
    lastError = 'Bitte api_id, api_hash und phone_number in der Add-on-Konfiguration setzen';
    return;
  }
  try {
    await client.start({
      phoneNumber: async () => PHONE_NUMBER,
      phoneCode: async () => {
        status = 'awaiting_code';
        console.log('[INFO] Waiting for SMS/app code...');
        return new Promise(resolve => { codeResolver = resolve; });
      },
      password: async () => {
        status = 'awaiting_password';
        console.log('[INFO] Waiting for 2FA password...');
        return new Promise(resolve => { passwordResolver = resolve; });
      },
      onError: (err) => {
        console.error('[ERROR] Auth:', err.message);
        lastError = err.message;
      },
    });

    fs.writeFileSync(SESSION_FILE, String(client.session.save()));

    const me = await client.getMe();
    myId = String(me.id);
    myName = getEntityName(me);
    status = 'connected';
    lastError = '';
    console.log(`[INFO] Connected as ${myName} (${myId})`);

    client.addEventHandler(async (event) => {
      try {
        const msg = event.message;
        if (!msg) return;
        const chat = await msg.getChat();
        const chatId = getEntityId(chat);
        const chatName = getEntityName(chat);
        if (!peerMap.has(chatId)) peerMap.set(chatId, chat);
        await processMessage(msg, chatId, chatName);
      } catch (e) {}
    }, new NewMessage({}));

    await loadDialogs();
  } catch (e) {
    status = 'error';
    lastError = e.message;
    console.error('[ERROR] startClient:', e.message);
  }
}

// ── API ───────────────────────────────────────────────────────────────────────

app.get('/api/status', (req, res) => {
  res.json({ status, name: myName, id: myId, error: lastError });
});

app.post('/api/submit-code', (req, res) => {
  const { code } = req.body;
  if (!code) return res.status(400).json({ error: 'Code fehlt' });
  if (!codeResolver) return res.status(400).json({ error: 'Kein Code erwartet' });
  codeResolver(String(code).trim());
  codeResolver = null;
  status = 'starting';
  res.json({ ok: true });
});

app.post('/api/submit-password', (req, res) => {
  const { password } = req.body;
  if (!password) return res.status(400).json({ error: 'Passwort fehlt' });
  if (!passwordResolver) return res.status(400).json({ error: 'Kein Passwort erwartet' });
  passwordResolver(password);
  passwordResolver = null;
  status = 'starting';
  res.json({ ok: true });
});

app.post('/api/reconnect', async (req, res) => {
  res.json({ ok: true });
  codeResolver = null;
  passwordResolver = null;
  status = 'starting';
  lastError = '';
  try { await client.disconnect(); } catch (e) {}
  setTimeout(startClient, 1000);
});

app.get('/api/chats', (req, res) => {
  const chats = Array.from(chatMap.values()).sort((a, b) => (b.lastTime || 0) - (a.lastTime || 0));
  res.json(chats);
});

app.get('/api/messages/:chatId', async (req, res) => {
  const { chatId } = req.params;
  const existing = messagesByChatId.get(chatId) || [];
  if (existing.length === 0 && status === 'connected') {
    await fetchMessages(chatId);
    return res.json(messagesByChatId.get(chatId) || []);
  }
  res.json(existing);
});

app.post('/api/send', async (req, res) => {
  const { to, message } = req.body;
  if (!to || !message) return res.status(400).json({ error: 'to und message erforderlich' });
  if (status !== 'connected') return res.status(503).json({ error: 'Nicht verbunden' });
  try {
    let entity = peerMap.get(to);
    if (!entity) { await loadDialogs(); entity = peerMap.get(to); }
    if (!entity) return res.status(404).json({ error: 'Chat nicht gefunden' });

    const result = await client.sendMessage(entity, { message });
    const msgId = `${to}_${result.id}`;
    if (!seenMsgIds.has(msgId)) {
      seenMsgIds.add(msgId);
      const ts = Date.now();
      if (!messagesByChatId.has(to)) messagesByChatId.set(to, []);
      messagesByChatId.get(to).push({ id: msgId, from: myId, body: message, timestamp: ts, fromMe: true });
      if (chatMap.has(to)) { chatMap.get(to).lastMsg = message; chatMap.get(to).lastTime = ts; }
      scheduleSave();
    }
    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/logout', async (req, res) => {
  res.json({ success: true });
  try { await client.destroy(); } catch (e) {}
  [SESSION_FILE, CHATS_FILE, MESSAGES_FILE].forEach(f => { try { fs.unlinkSync(f); } catch (e) {} });
  chatMap.clear(); messagesByChatId.clear(); seenMsgIds.clear(); peerMap.clear();
  myId = ''; myName = ''; codeResolver = null; passwordResolver = null;
  status = 'starting'; lastError = '';
  setTimeout(startClient, 1000);
});

setInterval(loadDialogs, 60000);

app.get('/api/media/:filename', (req, res) => {
  const { filename } = req.params;
  if (!/^[\w.-]+$/.test(filename)) return res.status(400).end();
  const filePath = `${MEDIA_DIR}/${filename}`;
  if (!fs.existsSync(filePath)) return res.status(404).end();
  const ext = filename.split('.').pop();
  const mime = ext === 'webp' ? 'image/webp' : ext === 'png' ? 'image/png' : 'image/jpeg';
  res.setHeader('Content-Type', mime);
  res.setHeader('Cache-Control', 'max-age=86400');
  res.sendFile(filePath);
});

// ── UI ────────────────────────────────────────────────────────────────────────

app.get('*', (req, res) => {
  if (req.path !== '/' && !req.path.startsWith('/api')) return res.redirect(req.baseUrl + '/');
  res.send(getHtml());
});

function getHtml() {
  return `<!DOCTYPE html>
<html lang="de" class="${DARK_MODE ? 'dark' : 'light'}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Telegram</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }

html.dark body { background: #17212B; color: #C1C9D4; }
html.light body { background: #fff; color: #222; }

/* ── Overlays ── */
.overlay { display: flex; flex-direction: column; align-items: center; justify-content: center; position: fixed; inset: 0; z-index: 100; gap: 16px; padding: 32px; }
html.dark .overlay { background: #17212B; }
html.light .overlay { background: #F1F1F1; }
.overlay h2 { font-size: 22px; font-weight: 600; }
html.dark .overlay h2 { color: #fff; }
html.light .overlay h2 { color: #222; }
.overlay p { font-size: 14px; text-align: center; line-height: 1.6; max-width: 340px; }
html.dark .overlay p { color: #8E9EAD; }
html.light .overlay p { color: #555; }
.tg-logo { font-size: 64px; }
.spinner { width: 48px; height: 48px; border: 4px solid #2AABEE; border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.auth-box { width: 100%; max-width: 360px; display: flex; flex-direction: column; gap: 10px; }
.auth-input { width: 100%; padding: 12px 16px; border-radius: 10px; border: none; font-size: 16px; outline: none; font-family: inherit; text-align: center; letter-spacing: 4px; }
.auth-input.text { letter-spacing: normal; }
html.dark .auth-input { background: #232E3C; color: #fff; }
html.dark .auth-input::placeholder { color: #6B7B8D; letter-spacing: normal; }
html.light .auth-input { background: #fff; color: #222; border: 1px solid #ddd; }
html.light .auth-input::placeholder { color: #aaa; letter-spacing: normal; }
.auth-btn { padding: 12px; border-radius: 10px; border: none; background: #2AABEE; color: #fff; font-size: 15px; font-weight: 600; cursor: pointer; font-family: inherit; }
.auth-btn:hover { background: #1E98D4; }
.auth-btn.ghost { background: transparent; color: #2AABEE; font-weight: 400; font-size: 13px; }
.auth-btn.ghost:hover { background: rgba(42,171,238,0.1); }
.auth-error { color: #e74c3c; font-size: 13px; text-align: center; display: none; }

/* ── Topbar ── */
#topbar { display: none; align-items: center; padding: 0 16px; height: 56px; gap: 12px; flex-shrink: 0; }
html.dark #topbar { background: #232E3C; color: #fff; }
html.light #topbar { background: #517DA2; color: #fff; }
#topbar h1 { font-size: 17px; flex: 1; }
#topbar .uname { font-size: 13px; opacity: 0.7; }
#logout-btn { background: transparent; border: 1px solid rgba(255,255,255,0.3); color: #fff; padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; }
#logout-btn:hover { background: rgba(255,255,255,0.1); }

/* ── Main layout ── */
#main { display: none; flex: 1; overflow: hidden; }

/* ── Sidebar ── */
#sidebar { width: 360px; min-width: 260px; display: flex; flex-direction: column; flex-shrink: 0; }
html.dark #sidebar { background: #232E3C; border-right: 1px solid #1A2432; }
html.light #sidebar { background: #fff; border-right: 1px solid #e0e0e0; }
#search-wrap { padding: 8px 12px; }
html.dark #search-wrap { border-bottom: 1px solid #1A2432; }
html.light #search-wrap { border-bottom: 1px solid #e0e0e0; }
#search-input { width: 100%; padding: 8px 12px; border-radius: 20px; border: none; font-size: 14px; outline: none; font-family: inherit; }
html.dark #search-input { background: #17212B; color: #C1C9D4; }
html.dark #search-input::placeholder { color: #6B7B8D; }
html.light #search-input { background: #F1F1F1; color: #222; }
#chat-list { flex: 1; overflow-y: auto; }
.chat-item { display: flex; align-items: center; padding: 10px 16px; cursor: pointer; gap: 12px; }
html.dark .chat-item { border-bottom: 1px solid #1A2432; }
html.light .chat-item { border-bottom: 1px solid #f5f5f5; }
html.dark .chat-item:hover { background: #2B3A4A; }
html.dark .chat-item.active { background: #2B5278; }
html.light .chat-item:hover { background: #F1F1F1; }
html.light .chat-item.active { background: #E3F2FD; }
.avatar { width: 46px; height: 46px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 17px; color: #fff; flex-shrink: 0; }
.chat-info { flex: 1; overflow: hidden; }
.chat-name { font-size: 15px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
html.dark .chat-name { color: #fff; }
html.light .chat-name { color: #222; }
.chat-preview { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; }
html.dark .chat-preview { color: #6B7B8D; }
html.light .chat-preview { color: #999; }
.chat-time { font-size: 12px; white-space: nowrap; }
html.dark .chat-time { color: #6B7B8D; }
html.light .chat-time { color: #999; }

/* ── Chat panel ── */
#chat-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
html.dark #chat-panel { background: #0E1621; }
html.light #chat-panel { background: #DAE6F0; }
#no-chat-wrap { flex: 1; display: flex; align-items: center; justify-content: center; font-size: 15px; }
html.dark #no-chat-wrap { color: #6B7B8D; }
html.light #no-chat-wrap { color: #888; }
#chat-header { display: none; align-items: center; gap: 12px; padding: 10px 16px; flex-shrink: 0; min-height: 56px; }
html.dark #chat-header { background: #232E3C; border-bottom: 1px solid #1A2432; }
html.light #chat-header { background: #517DA2; }
#back-btn { display: none; background: none; border: none; color: #fff; font-size: 20px; cursor: pointer; padding: 4px 8px 4px 0; }
#ch-name { font-size: 16px; font-weight: 600; color: #fff; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#messages { flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 2px; display: none; }
.bubble { max-width: 65%; padding: 8px 12px; border-radius: 10px; font-size: 14px; line-height: 1.45; word-break: break-word; }
.bubble.in { align-self: flex-start; border-bottom-left-radius: 2px; }
.bubble.out { align-self: flex-end; border-bottom-right-radius: 2px; }
html.dark .bubble.in { background: #182533; color: #C1C9D4; }
html.dark .bubble.out { background: #2B5278; color: #fff; }
html.light .bubble.in { background: #fff; color: #222; }
html.light .bubble.out { background: #EEFFDE; color: #222; }
.bubble-time { font-size: 11px; float: right; margin-left: 8px; margin-top: 2px; }
html.dark .bubble-time { color: rgba(193,201,212,0.6); }
html.light .bubble-time { color: rgba(0,0,0,0.35); }
.day-sep { align-self: center; font-size: 12px; padding: 4px 12px; border-radius: 12px; margin: 6px 0; }
html.dark .day-sep { background: rgba(14,22,33,0.9); color: #6B7B8D; }
html.light .day-sep { background: rgba(255,255,255,0.8); color: #666; }

/* ── Input bar ── */
#input-bar { display: none; gap: 8px; align-items: flex-end; padding: 8px 16px; flex-shrink: 0; position: relative; }
html.dark #input-bar { background: #232E3C; border-top: 1px solid #1A2432; }
html.light #input-bar { background: #F1F1F1; border-top: 1px solid #e0e0e0; }
#msg-input { flex: 1; padding: 10px 14px; border-radius: 20px; border: none; font-size: 14px; outline: none; resize: none; max-height: 120px; font-family: inherit; }
html.dark #msg-input { background: #17212B; color: #C1C9D4; }
html.dark #msg-input::placeholder { color: #6B7B8D; }
html.light #msg-input { background: #fff; color: #222; }
#send-btn { width: 42px; height: 42px; border-radius: 50%; border: none; background: #2AABEE; color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
#send-btn:hover { background: #1E98D4; }

/* ── Emoji picker ── */
#emoji-picker { display: none; position: absolute; bottom: 100%; left: 0; right: 0; padding: 8px 12px; max-height: 200px; overflow-y: auto; z-index: 20; }
html.dark #emoji-picker { background: #232E3C; border-top: 1px solid #1A2432; }
html.light #emoji-picker { background: #fff; border-top: 1px solid #e0e0e0; }
#emoji-picker.open { display: block; }
.emoji-grid { display: flex; flex-wrap: wrap; gap: 2px; }
#input-bar .emoji-btn { background: none; border: none; font-size: 22px; cursor: pointer; padding: 3px 5px; border-radius: 6px; width: auto; height: auto; line-height: 1; }
html.dark #input-bar .emoji-btn:hover { background: rgba(255,255,255,0.06); }
html.light #input-bar .emoji-btn:hover { background: #F1F1F1; }
#emoji-toggle { background: none; border: none; font-size: 20px; cursor: pointer; padding: 6px; border-radius: 50%; flex-shrink: 0; width: auto; height: auto; line-height: 1; }
html.dark #emoji-toggle { color: #6B7B8D; }
html.light #emoji-toggle { color: #888; }

/* ── Mobile ── */
@media (max-width: 768px) {
  #sidebar { width: 100%; border-right: none; }
  #chat-panel { display: none; }
  #back-btn { display: block; }
  body.chat-open #sidebar { display: none; }
  body.chat-open #chat-panel { display: flex; }
}
</style>
</head>
<body>

<div id="overlay-spinner" class="overlay">
  <div class="tg-logo">✈️</div>
  <div class="spinner"></div>
  <p id="spinner-text">Verbinde mit Telegram…</p>
</div>

<div id="overlay-code" class="overlay" style="display:none">
  <div class="tg-logo">✈️</div>
  <h2>Code eingeben</h2>
  <p>Telegram hat einen Code an deine App oder per SMS gesendet.</p>
  <div class="auth-box">
    <input class="auth-input" id="code-input" type="text" inputmode="numeric" maxlength="8" placeholder="12345">
    <div class="auth-error" id="code-error"></div>
    <button class="auth-btn" onclick="submitCode()">Bestätigen</button>
  </div>
</div>

<div id="overlay-password" class="overlay" style="display:none">
  <div class="tg-logo">✈️</div>
  <h2>2-Faktor-Passwort</h2>
  <p>Dein Konto ist durch ein Cloud-Passwort geschützt.</p>
  <div class="auth-box">
    <input class="auth-input text" id="pw-input" type="password" placeholder="Passwort">
    <div class="auth-error" id="pw-error"></div>
    <button class="auth-btn" onclick="submitPassword()">Bestätigen</button>
  </div>
</div>

<div id="overlay-error" class="overlay" style="display:none">
  <div class="tg-logo">✈️</div>
  <h2>Fehler</h2>
  <p id="error-text"></p>
  <button class="auth-btn" style="max-width:220px;margin-top:8px" onclick="reconnect()">Erneut verbinden</button>
</div>

<div id="topbar">
  <h1>Telegram</h1>
  <span class="uname" id="my-name"></span>
  <button id="logout-btn" onclick="logout()">Abmelden</button>
</div>

<div id="main">
  <div id="sidebar">
    <div id="search-wrap">
      <input id="search-input" type="text" placeholder="Suchen…" oninput="filterChats()">
    </div>
    <div id="chat-list"></div>
  </div>
  <div id="chat-panel">
    <div id="no-chat-wrap">Wähle einen Chat aus der Liste</div>
    <div id="chat-header">
      <button id="back-btn" onclick="closeChat()">&#8592;</button>
      <div class="avatar" id="ch-avatar" style="width:36px;height:36px;font-size:14px;background:#2AABEE">?</div>
      <div style="flex:1;overflow:hidden">
        <div id="ch-name">–</div>
      </div>
    </div>
    <div id="messages"></div>
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
const BASE = location.pathname.replace(/\\/+$/, '');
let currentStatus = '';
let selectedChatId = null;
let allChats = [];

function api(p) { return BASE + p; }

const COLORS = ['#E17076','#F28C28','#8ECC44','#2AABEE','#7B68EE','#E84393','#00BCD4','#FF8C00'];
function avatarColor(s) { let h=0; for(const c of String(s)) h=(h*31+c.charCodeAt(0))&0xffff; return COLORS[h%COLORS.length]; }
function avatarInitial(s) { return (String(s||'?')).charAt(0).toUpperCase(); }

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts), now = new Date();
  if (d.toDateString()===now.toDateString()) return d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
  return d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit'});
}
function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// ── Status polling ─────────────────────────────────────────────────────────────
async function refresh() {
  try {
    const d = await fetch(api('/api/status')).then(r=>r.json());
    if (d.status === currentStatus) return;
    currentStatus = d.status;
    ['overlay-spinner','overlay-code','overlay-password','overlay-error','topbar','main'].forEach(id => {
      document.getElementById(id).style.display = 'none';
    });
    if (d.status==='starting') {
      document.getElementById('overlay-spinner').style.display = 'flex';
    } else if (d.status==='awaiting_code') {
      document.getElementById('overlay-code').style.display = 'flex';
      setTimeout(()=>document.getElementById('code-input').focus(), 100);
    } else if (d.status==='awaiting_password') {
      document.getElementById('overlay-password').style.display = 'flex';
      setTimeout(()=>document.getElementById('pw-input').focus(), 100);
    } else if (d.status==='error') {
      document.getElementById('overlay-error').style.display = 'flex';
      document.getElementById('error-text').textContent = d.error || 'Unbekannter Fehler';
    } else if (d.status==='connected') {
      document.getElementById('topbar').style.display = 'flex';
      document.getElementById('main').style.display = 'flex';
      document.getElementById('my-name').textContent = d.name || '';
      loadChats();
    }
  } catch(e) {}
}
setInterval(refresh, 2000);
refresh();

// ── Auth ───────────────────────────────────────────────────────────────────────
async function submitCode() {
  const code = document.getElementById('code-input').value.trim();
  if (!code) return;
  const errEl = document.getElementById('code-error');
  errEl.style.display = 'none';
  try {
    const r = await fetch(api('/api/submit-code'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})}).then(r=>r.json());
    if (!r.ok) { errEl.textContent = r.error; errEl.style.display = 'block'; }
    else document.getElementById('code-input').value = '';
  } catch(e) {}
}
document.getElementById('code-input').addEventListener('keydown', e => { if(e.key==='Enter') submitCode(); });

async function submitPassword() {
  const password = document.getElementById('pw-input').value;
  if (!password) return;
  const errEl = document.getElementById('pw-error');
  errEl.style.display = 'none';
  try {
    const r = await fetch(api('/api/submit-password'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})}).then(r=>r.json());
    if (!r.ok) { errEl.textContent = r.error; errEl.style.display = 'block'; }
    else document.getElementById('pw-input').value = '';
  } catch(e) {}
}
document.getElementById('pw-input').addEventListener('keydown', e => { if(e.key==='Enter') submitPassword(); });

async function reconnect() {
  currentStatus = '';
  document.getElementById('overlay-error').style.display = 'none';
  document.getElementById('overlay-spinner').style.display = 'flex';
  await fetch(api('/api/reconnect'),{method:'POST'}).catch(()=>{});
}

async function logout() {
  if (!confirm('Abmelden und Session löschen?')) return;
  currentStatus = '';
  document.getElementById('topbar').style.display = 'none';
  document.getElementById('main').style.display = 'none';
  document.getElementById('overlay-spinner').style.display = 'flex';
  document.getElementById('spinner-text').textContent = 'Abmelden…';
  await fetch(api('/api/logout'),{method:'POST'}).catch(()=>{});
}

// ── Chats ──────────────────────────────────────────────────────────────────────
async function loadChats() {
  try {
    const chats = await fetch(api('/api/chats')).then(r=>r.json());
    allChats = chats;
    renderChats(chats);
    if (selectedChatId) loadMessages(selectedChatId);
  } catch(e) {}
}
setInterval(loadChats, 5000);

function renderChats(chats) {
  const q = document.getElementById('search-input').value.toLowerCase();
  const filtered = q ? chats.filter(c=>(c.name||'').toLowerCase().includes(q)) : chats;
  document.getElementById('chat-list').innerHTML = filtered.map(c => \`
    <div class="chat-item\${c.id===selectedChatId?' active':''}" data-id="\${escHtml(c.id)}" onclick="openChatById(this.dataset.id)">
      <div class="avatar" style="background:\${avatarColor(c.name||c.id)}">\${avatarInitial(c.name||c.id)}</div>
      <div class="chat-info">
        <div class="chat-name">\${escHtml(c.name||c.id)}</div>
        <div class="chat-preview">\${escHtml(c.lastMsg||'')}</div>
      </div>
      <div class="chat-time">\${formatTime(c.lastTime)}</div>
    </div>
  \`).join('');
}

function filterChats() { renderChats(allChats); }

function openChatById(id) { const c = allChats.find(c=>c.id===id); if(c) openChat(c); }

function openChat(chat) {
  selectedChatId = chat.id;
  document.body.classList.add('chat-open');
  document.getElementById('no-chat-wrap').style.display = 'none';
  document.getElementById('chat-header').style.display = 'flex';
  document.getElementById('messages').style.display = 'flex';
  document.getElementById('input-bar').style.display = 'flex';
  document.getElementById('ch-name').textContent = chat.name || chat.id;
  const av = document.getElementById('ch-avatar');
  av.textContent = avatarInitial(chat.name||chat.id);
  av.style.background = avatarColor(chat.name||chat.id);
  renderChats(allChats);
  loadMessages(chat.id);
}

function closeChat() {
  document.body.classList.remove('chat-open');
  selectedChatId = null;
  document.getElementById('no-chat-wrap').style.display = 'flex';
  document.getElementById('chat-header').style.display = 'none';
  document.getElementById('messages').style.display = 'none';
  document.getElementById('input-bar').style.display = 'none';
}

async function loadMessages(chatId) {
  if (!chatId) return;
  try {
    const msgs = await fetch(api('/api/messages/'+encodeURIComponent(chatId))).then(r=>r.json());
    renderMessages(msgs);
  } catch(e) {}
}

function renderMessages(msgs) {
  const el = document.getElementById('messages');
  if (!msgs||!msgs.length) { el.innerHTML='<div style="text-align:center;padding:24px;opacity:0.5">Noch keine Nachrichten</div>'; return; }
  let lastDate='';
  el.innerHTML = msgs.map(m => {
    const d=new Date(m.timestamp);
    const dateStr=d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit',year:'numeric'});
    let sep='';
    if(dateStr!==lastDate){sep=\`<div class="day-sep">\${dateStr}</div>\`;lastDate=dateStr;}
    const time=d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
    let content='';
    if(m.type==='photo'&&m.mediaFile){
      content=\`<img src="\${BASE}/api/media/\${encodeURIComponent(m.mediaFile)}" style="max-width:240px;max-height:300px;border-radius:8px;display:block;cursor:pointer" loading="lazy" onclick="this.style.maxWidth=this.style.maxWidth==='none'?'240px':'none'">\`;
      if(m.body) content+=\`<div style="margin-top:4px">\${escHtml(m.body)}</div>\`;
    } else {
      content=escHtml(m.body);
    }
    return sep+\`<div class="bubble \${m.fromMe?'out':'in'}">\${content}<span class="bubble-time">\${time}</span></div>\`;
  }).join('');
  el.scrollTop = el.scrollHeight;
}

async function sendMsg() {
  if (!selectedChatId) return;
  const inp = document.getElementById('msg-input');
  const text = inp.value.trim();
  if (!text) return;
  inp.value=''; inp.style.height='';
  try {
    await fetch(api('/api/send'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({to:selectedChatId,message:text})});
    await loadMessages(selectedChatId);
    await loadChats();
  } catch(e) {}
}

function handleKey(e) { if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMsg();} }
function autoResize(el) { el.style.height='auto'; el.style.height=Math.min(el.scrollHeight,120)+'px'; }

// ── Emoji picker ───────────────────────────────────────────────────────────────
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
(function(){
  const grid=document.getElementById('emoji-grid');
  EMOJIS.forEach(e=>{const b=document.createElement('button');b.className='emoji-btn';b.textContent=e;b.onclick=()=>insertEmoji(e);grid.appendChild(b);});
})();
function toggleEmojiPicker(evt){evt.stopPropagation();document.getElementById('emoji-picker').classList.toggle('open');}
function insertEmoji(emoji){const inp=document.getElementById('msg-input');const s=inp.selectionStart,e=inp.selectionEnd;inp.value=inp.value.slice(0,s)+emoji+inp.value.slice(e);inp.selectionStart=inp.selectionEnd=s+emoji.length;inp.focus();autoResize(inp);}
document.addEventListener('click',e=>{if(!e.target.closest('#emoji-picker')&&e.target.id!=='emoji-toggle')document.getElementById('emoji-picker').classList.remove('open');});
</script>
</body>
</html>`;
}

process.on('unhandledRejection', (reason) => {
  console.error('[ERROR] Unhandled:', reason?.message || reason);
});

fs.mkdirSync(MEDIA_DIR, { recursive: true });
loadFromDisk();
if (!DOWNLOAD_MEDIA) {
  try {
    const files = fs.readdirSync(MEDIA_DIR);
    files.forEach(f => { try { fs.unlinkSync(`${MEDIA_DIR}/${f}`); } catch (e) {} });
    if (files.length) console.log(`[INFO] Deleted ${files.length} cached media files (download_media=off)`);
  } catch (e) {}
  let dirty = false;
  for (const msgs of messagesByChatId.values()) {
    for (const m of msgs) {
      if (m.mediaFile) { m.mediaFile = null; dirty = true; }
    }
  }
  if (dirty) scheduleSave();
}
app.listen(PORT, () => {
  console.log(`[INFO] Telegram UI on port ${PORT}`);
  startClient();
});
