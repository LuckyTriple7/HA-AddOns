'use strict';
(function () {
  const _ts = () => new Date().toLocaleTimeString('de-DE', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  ['log','warn','error'].forEach(m => {
    const orig = console[m].bind(console);
    console[m] = (...a) => {
      if (a.length && typeof a[0] === 'string') {
        const match = a[0].match(/^(\[(?:INFO|WARN|ERROR|DEBUG)\])(.*)/s);
        if (match) {
          const rest = match[2].trimStart();
          orig(`${match[1]} [${_ts()}]${rest ? ' ' + rest : ''}`, ...a.slice(1));
          return;
        }
      }
      orig(`[INFO] [${_ts()}]`, ...a);
    };
  });
})();

const { Client, NoAuth } = require('whatsapp-web.js');
const path = require('path');
const express = require('express');
const qrcode = require('qrcode');
const https = require('https');
const http = require('http');
const { URL } = require('url');
const fs = require('fs');
const { existsSync, rmSync } = fs;

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

const DARK_MODE = process.env.DARK_MODE !== 'false';
const DOWNLOAD_MEDIA = process.env.DOWNLOAD_MEDIA === 'true';
const DEBUG = process.env.DEBUG_MODE === 'true';
const HA_NOTIFY = process.env.HA_NOTIFICATIONS === 'true';
const HA_PRIVACY = process.env.HA_NOTIFICATIONS_PRIVACY === 'true';
function dbg(...args) { if (DEBUG) console.log('[DEBUG]', ...args); }
if (DEBUG) console.log('[DEBUG] Debug-Modus aktiv');
const MEDIA_DIR = '/data/media';
const MAX_MSGS_PER_CHAT = 200;
const INITIAL_CHATS = parseInt(process.env.INITIAL_CHATS || '30', 10);
const INITIAL_MESSAGES = parseInt(process.env.INITIAL_MESSAGES || '20', 10);
const chatMap = new Map();          // chatId -> { id, name, phone, lastMsg, lastTime, isGroup }
const messagesByChatId = new Map(); // chatId -> Message[]
const seenIds = new Set();

// Filtert Status-Updates, Broadcasts und WhatsApp-Channels (@newsletter = "Aktuelles"-Tab)
function isFilteredChat(chatId) {
  return chatId.endsWith('@broadcast') || chatId.endsWith('@newsletter');
}

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
  if (seenIds.has(msg.id)) { dbg(`addMsg: duplicate skipped ${msg.id}`); return false; }
  seenIds.add(msg.id);
  dbg(`addMsg: chatId=${chatId} fromMe=${msg.fromMe} type=${msg.type} body="${(msg.body||'').slice(0,60)}"`);
  const msgs = getChatMsgs(chatId);
  msgs.push(msg);
  msgs.sort((a, b) => a.timestamp - b.timestamp);
  if (msgs.length > MAX_MSGS_PER_CHAT) msgs.splice(0, msgs.length - MAX_MSGS_PER_CHAT);
  const chat = chatMap.get(chatId);
  if (chat && msg.timestamp >= (chat.lastTime || 0)) {
    const preview = msg.body || (msg.type === 'photo' ? '📷 Foto' : '[Medien]');
    chat.lastMsg = preview.length > 60 ? preview.slice(0, 60) + '…' : preview;
    chat.lastTime = msg.timestamp;
  }
  return true;
}

async function downloadWAMedia(msg, msgId) {
  try {
    const safeId = msgId.replace(/[^a-zA-Z0-9]/g, '_');
    const ext = msg.type === 'sticker' ? 'webp' : 'jpg';
    const filePath = `${MEDIA_DIR}/${safeId}.${ext}`;
    if (!existsSync(filePath)) {
      dbg(`Downloading media: ${safeId}.${ext}`);
      const media = await msg.downloadMedia();
      if (media?.data) fs.writeFileSync(filePath, Buffer.from(media.data, 'base64'));
    } else {
      dbg(`Media already cached: ${safeId}.${ext}`);
    }
    return existsSync(filePath) ? `${safeId}.${ext}` : null;
  } catch (e) {
    console.error('[ERROR] downloadWAMedia:', e.message);
    return null;
  }
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
      if (isFilteredChat(chatId)) continue;
      // For 1:1 chats, prefer pushname over bare phone number
      let chatName = chat.name || chat.id.user;
      if (!chat.isGroup) {
        const ct = await client.getContactById(chatId).catch(() => null);
        chatName = ct?.name || ct?.pushname || chatName;
      }
      upsertChat(chatId, { name: chatName, phone: chat.id.user, isGroup: chat.isGroup });

      const msgs = await chat.fetchMessages({ limit: INITIAL_MESSAGES }).catch(() => []);
      for (const msg of msgs) {
        const isText = msg.type === 'chat' || msg.type === 'text';
        const isImage = msg.type === 'image' || msg.type === 'sticker';
        if (!isText && !isImage) continue;
        if (!msg.body && !isImage) continue;
        let contactName = msg.fromMe ? 'Ich' : (chat.name || chat.id.user);
        if (!msg.fromMe && chat.isGroup) {
          const c = await msg.getContact().catch(() => null);
          contactName = c?.pushname || c?.name || msg.author?.replace('@c.us', '') || contactName;
        }
        addMsg(chatId, {
          id: msg.id._serialized,
          body: msg.body || '',
          type: isImage ? 'photo' : 'text',
          mediaFile: null,
          timestamp: msg.timestamp * 1000,
          fromMe: msg.fromMe,
          contact: contactName,
          ack: msg.ack || 0,
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
  dbg(`Incoming message: type=${msg.type} from=${msg.from} body="${(msg.body||'').slice(0,60)}"`);
  if (msg.isStatus || isFilteredChat(msg.from || '')) { dbg('Skipping status/newsletter update'); return; }
  const isText = msg.type === 'chat' || msg.type === 'text';
  const isImage = msg.type === 'image' || msg.type === 'sticker';
  if (!isText && !isImage) { dbg(`Skipping unsupported type: ${msg.type}`); return; }
  if (!msg.body && !isImage) return;
  const chat = await msg.getChat().catch(() => null);
  if (!chat) return;
  const chatId = chat.id._serialized;
  if (isFilteredChat(chatId)) { dbg(`Skipping filtered chat: ${chatId}`); return; }
  const contact = await msg.getContact().catch(() => null);
  const contactName = contact?.pushname || contact?.name || msg.from.replace('@c.us', '');
  upsertChat(chatId, { name: chat.name || contactName, phone: chat.id.user, isGroup: chat.isGroup });
  let type = 'text', mediaFile = null;
  if (isImage) {
    type = 'photo';
    if (DOWNLOAD_MEDIA) mediaFile = await downloadWAMedia(msg, msg.id._serialized);
  }
  const added = addMsg(chatId, {
    id: msg.id._serialized,
    body: msg.body || '',
    type, mediaFile,
    timestamp: msg.timestamp * 1000,
    fromMe: false,
    contact: contactName,
  });
  if (added) {
    sendHANotification(chatId, contactName, msg.body || (type === 'photo' ? '📷 Foto' : ''));
  }
  if (process.env.WEBHOOK_INCOMING) {
    dbg(`Firing incoming webhook: ${process.env.WEBHOOK_INCOMING}`);
    postWebhook(process.env.WEBHOOK_INCOMING, { from: msg.from, body: msg.body, type: msg.type, timestamp: msg.timestamp });
  }
});

client.on('message_create', async (msg) => {
  dbg(`message_create: type=${msg.type} fromMe=${msg.fromMe} from=${msg.from} body="${(msg.body||'').slice(0,60)}"`);
  if (!msg.fromMe) return;
  if (msg.isStatus || isFilteredChat(msg.from || '')) return;
  const isText = msg.type === 'chat' || msg.type === 'text';
  const isImage = msg.type === 'image' || msg.type === 'sticker';
  if (!isText && !isImage) { dbg(`message_create: skipping type=${msg.type}`); return; }
  if (msg.__logged) return;
  const chat = await msg.getChat().catch(() => null);
  if (!chat) return;
  const chatId = chat.id._serialized;
  if (isFilteredChat(chatId)) return;
  upsertChat(chatId, { name: chat.name || msg.to.replace('@c.us', ''), phone: chat.id.user, isGroup: chat.isGroup });
  let type = 'text', mediaFile = null;
  if (isImage) {
    type = 'photo';
    if (DOWNLOAD_MEDIA) mediaFile = await downloadWAMedia(msg, msg.id._serialized);
  }
  addMsg(chatId, {
    id: msg.id._serialized,
    body: msg.body || '',
    type, mediaFile,
    timestamp: msg.timestamp * 1000,
    fromMe: true,
    contact: 'Ich',
    ack: msg.ack || 1,
  });
});

client.on('message_reaction', (reaction) => {
  const msgId = reaction.msgId?._serialized;
  if (!msgId) return;
  const senderId = reaction.senderId?._serialized || String(reaction.senderId || '');
  const emoji = reaction.reaction || '';
  dbg(`message_reaction: msgId=${msgId} sender=${senderId} emoji="${emoji}"`);
  for (const msgs of messagesByChatId.values()) {
    const msg = msgs.find(m => m.id === msgId);
    if (msg) {
      if (!msg.reactions) msg.reactions = {};
      for (const e of Object.keys(msg.reactions)) {
        msg.reactions[e] = msg.reactions[e].filter(s => s !== senderId);
        if (!msg.reactions[e].length) delete msg.reactions[e];
      }
      if (emoji) {
        if (!msg.reactions[emoji]) msg.reactions[emoji] = [];
        if (!msg.reactions[emoji].includes(senderId)) msg.reactions[emoji].push(senderId);
      }
      break;
    }
  }
});

client.on('message_ack', (msg, ack) => {
  dbg(`message_ack: ${msg.id._serialized} ack=${ack}`);
  const msgs = messagesByChatId.get(msg.to);
  if (msgs) {
    const stored = msgs.find(m => m.id === msg.id._serialized);
    if (stored) { stored.ack = ack; return; }
  }
  // Fallback: Gruppen-Chats haben andere chatId-Struktur
  for (const list of messagesByChatId.values()) {
    const stored = list.find(m => m.id === msg.id._serialized);
    if (stored) { stored.ack = ack; break; }
  }
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

function sendHANotification(chatId, senderName, body) {
  if (!HA_NOTIFY) return;
  const token = process.env.HA_TOKEN;
  if (!token) {
    console.warn('[WARN] HA_NOTIFICATIONS: ha_token in der Add-on-Konfiguration setzen');
    return;
  }
  const safeId = chatId.replace(/[^a-zA-Z0-9]/g, '_');
  const preview = (body || '').length > 200 ? body.slice(0, 200) + '…' : (body || '');
  const payload = JSON.stringify(HA_PRIVACY ? {
    title: 'WhatsApp',
    message: 'Neue Nachricht',
    notification_id: 'whatsapp_new_message',
  } : {
    title: `WhatsApp: ${senderName}`,
    message: preview || '📷 Foto',
    notification_id: `whatsapp_${safeId}`,
  });
  console.log(`[INFO] HA notification: WhatsApp${HA_PRIVACY ? '' : `: ${senderName}`}`);
  const req = http.request('http://homeassistant:8123/api/services/persistent_notification/create', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(payload),
    },
  }, (res) => {
    res.resume();
    if (res.statusCode === 200) {
      dbg('HA notification OK (HTTP 200)');
    } else {
      console.warn(`[WARN] HA notification returned HTTP ${res.statusCode}`);
    }
  });
  req.on('error', e => console.warn('[WARN] HA notification request error:', e.message));
  req.write(payload);
  req.end();
}

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
    dbg(`Sending message to ${jid}: "${message.slice(0,60)}${message.length>60?'…':''}"`);
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
      ack: 1,
    });
    res.json({ success: true, id: result.id._serialized });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

async function reinitClient() {
  status = 'initializing';
  qrCodeDataUrl = null;
  connectedPhone = null;
  try { await client.destroy(); } catch(e) {}
  // Remove Chromium lock files before reinit
  ['SingletonLock', 'SingletonCookie', 'SingletonSocket'].forEach(f => {
    try { rmSync(path.join(SESSION_CHROMIUM_DIR, f), { force: true }); } catch(e) {}
  });
  setTimeout(() => {
    client.initialize().catch(err => {
      lastError = String(err?.message || err);
      status = 'error';
      console.error('[ERROR] Reinit failed:', lastError);
    });
  }, 1500);
}

app.post('/api/logout', async (req, res) => {
  res.json({ success: true });
  try { await client.logout(); } catch(e) {}
  // Clear session so QR is shown on next init (not auto-reconnect)
  try { rmSync(SESSION_CHROMIUM_DIR, { recursive: true, force: true }); } catch(e) {}
  console.log('[INFO] Logged out — reinitializing…');
  await reinitClient();
});

app.get('/api/media/:filename', (req, res) => {
  const { filename } = req.params;
  if (!/^[\w.-]+$/.test(filename)) return res.status(400).end();
  const filePath = `${MEDIA_DIR}/${filename}`;
  if (!existsSync(filePath)) return res.status(404).end();
  const ext = filename.split('.').pop();
  const mime = ext === 'webp' ? 'image/webp' : ext === 'png' ? 'image/png' : 'image/jpeg';
  res.setHeader('Content-Type', mime);
  res.setHeader('Cache-Control', 'max-age=86400');
  res.sendFile(filePath);
});

function getDirSize(dir) {
  let total = 0;
  try {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = `${dir}/${entry.name}`;
      if (entry.isDirectory()) total += getDirSize(full);
      else if (entry.isFile()) { try { total += fs.statSync(full).size; } catch (e) {} }
    }
  } catch (e) {}
  return total;
}

app.get('/api/storage', (req, res) => {
  const bytes = getDirSize('/data');
  res.json({ bytes, mb: (bytes / (1024 * 1024)).toFixed(1) });
});

app.post('/api/reset', async (req, res) => {
  res.json({ success: true });
  try { rmSync(SESSION_CHROMIUM_DIR, { recursive: true, force: true }); } catch(e) {}
  console.log('[INFO] Session reset — reinitializing…');
  await reinitClient();
});

app.post('/api/react', async (req, res) => {
  const { msgId, reaction } = req.body;
  if (!msgId) return res.status(400).json({ error: 'msgId required' });
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  try {
    const msg = await client.getMessageById(msgId);
    if (!msg) return res.status(404).json({ error: 'Message not found' });
    await msg.react(reaction || '');
    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/reactions/:chatId', (req, res) => {
  const msgs = getChatMsgs(req.params.chatId);
  const result = {};
  for (const m of msgs) {
    if (m.reactions && Object.keys(m.reactions).length) result[m.id] = m.reactions;
  }
  res.json(result);
});

app.get('/api/presence/:chatId', async (req, res) => {
  const { chatId } = req.params;
  if (status !== 'connected') return res.json({ lastSeen: null });
  try {
    if (chatId.endsWith('@g.us')) {
      const chat = await client.getChatById(chatId);
      return res.json({ isGroup: true, memberCount: chat.participants?.length || 0 });
    }

    // Resolve @lid → @c.us JID via WWebJS.getContact
    const cusJid = await client.pupPage.evaluate(async (jid) => {
      try {
        const c = window.WWebJS?.getContact ? await window.WWebJS.getContact(jid) : null;
        return c?.id?._serialized || null;
      } catch(e) { return null; }
    }, chatId);
    dbg(`presence ${chatId} cusJid=${cusJid}`);

    // Node.js side: check client API for presence methods
    const clientPresenceMethods = Object.getOwnPropertyNames(Object.getPrototypeOf(client))
      .filter(k => /pres|last.*seen|subscribe/i.test(k));
    dbg('client presence methods:', clientPresenceMethods.join(',') || 'none');

    const jids = [...new Set([chatId, cusJid].filter(Boolean))];
    const result = await client.pupPage.evaluate(async (jids) => {
      const out = { lastSeen: null, dbg: {} };

      // 1. Direct Store.Presence access + scan window for store-like globals
      out.dbg.storeExists = !!window.Store;
      const storeGlobals = Object.getOwnPropertyNames(window).filter(k =>
        /store|presence/i.test(k) && k !== 'Store' && typeof window[k] === 'object' && window[k]
      );
      out.dbg.storeGlobals = storeGlobals;
      // Try window.Store and any store-like globals for Presence
      for (const storeName of ['Store', ...storeGlobals]) {
        const s = window[storeName];
        if (s?.Presence) {
          for (const j of jids) {
            try {
              const p = await s.Presence.get(j);
              if (p?.lastSeen != null) { out.lastSeen = p.lastSeen; out.dbg.src = storeName + '.Presence'; return out; }
            } catch(e) {}
          }
        }
      }

      // 2. WWebJS.getChat — serialize the chat model and inspect ALL keys
      for (const j of jids) {
        try {
          const chat = window.WWebJS?.getChat ? await window.WWebJS.getChat(j) : null;
          if (chat && typeof chat === 'object') {
            const allKeys = Object.keys(chat);
            const presKeys = allKeys.filter(k => /last|seen|pres|online|status|avail/i.test(k));
            const presData = {};
            for (const k of presKeys) { try { presData[k] = chat[k]; } catch(e) {} }
            out.dbg['chat_' + j] = { totalKeys: allKeys.length, presKeys, presData };
            // Check nested contact object
            if (chat.contact && typeof chat.contact === 'object') {
              const ck = Object.keys(chat.contact);
              const cpk = ck.filter(k => /last|seen|pres|online|status|avail/i.test(k));
              const cpd = {};
              for (const k of cpk) { try { cpd[k] = chat.contact[k]; } catch(e) {} }
              out.dbg['chatContact_' + j] = { totalKeys: ck.length, presKeys: cpk, presData: cpd };
              if (chat.contact.lastSeen != null) {
                out.lastSeen = chat.contact.lastSeen; out.dbg.src = 'chat.contact.lastSeen'; return out;
              }
            }
          } else {
            out.dbg['chat_' + j] = null;
          }
        } catch(e) { out.dbg['chat_' + j] = 'err:' + e.message.slice(0, 60); }
      }

      // 3. Monkeypatch Object.prototype.toJSON to capture raw contact model from WWebJS.getContact
      //    (getContact works and presumably calls contact.toJSON() internally)
      for (const j of jids) {
        try {
          const capturedModels = [];
          const hadToJSON = Object.prototype.hasOwnProperty('toJSON');
          const origToJSON = Object.prototype.toJSON;
          Object.prototype.toJSON = function() {
            capturedModels.push(this);
            return Object.assign({}, this);
          };
          try { await window.WWebJS.getContact(j); } catch(e) {}
          if (hadToJSON) Object.prototype.toJSON = origToJSON; else delete Object.prototype.toJSON;

          for (let i = 0; i < capturedModels.length; i++) {
            const m = capturedModels[i];
            const ownKeys = Object.getOwnPropertyNames(m);
            const presKeys = ownKeys.filter(k => /last|seen|pres|online|status|avail/i.test(k));
            if (presKeys.length > 0 || i === 0) {
              const presData = {};
              for (const k of presKeys) { try { presData[k] = m[k]; } catch(e) {} }
              out.dbg['toJSON_' + i + '_' + j] = { ctor: m?.constructor?.name, ownKeyCount: ownKeys.length, presKeys, presData };
            }
          }
          out.dbg['toJSONCnt_' + j] = capturedModels.length;
        } catch(e) { out.dbg['toJSONErr_' + j] = e.message.slice(0, 60); }
      }

      // 4. requireLazy subscription + read (last resort, 5s timeout)
      const lazyResult = await new Promise((resolve) => {
        let resolved = false;
        const done = (val) => { if (!resolved) { resolved = true; resolve(val ?? null); } };
        setTimeout(() => done(null), 5000);
        const tryLazy = (name, fn) => { try { window.requireLazy([name], fn); } catch(e) {} };
        const readPresence = () => {
          for (const storeName of ['ContactStore', 'ContactPresenceStore', 'PresenceStore']) {
            tryLazy(storeName, (store) => {
              if (resolved) return;
              for (const j of jids) {
                const c = store?.get?.(j) || store?.getContact?.(j) || store?.find?.(j);
                if (c?.lastSeen != null) { done(c.lastSeen); return; }
                if (c?.presence?.lastSeen != null) { done(c.presence.lastSeen); return; }
              }
            });
          }
        };
        for (const name of ['PresenceUtils', 'WAWebPresenceUtils', 'PresenceActions', 'PresenceSubscribeUtils']) {
          tryLazy(name, (mod) => {
            for (const j of jids) {
              try { mod?.sendPresenceSubscribe?.(j); } catch(e) {}
              try { mod?.subscribe?.(j); } catch(e) {}
              try { mod?.subscribePresence?.(j); } catch(e) {}
            }
          });
        }
        setTimeout(readPresence, 2000);
        setTimeout(readPresence, 4000);
      });
      if (lazyResult != null) { out.lastSeen = lazyResult; out.dbg.src = 'requireLazy'; }

      return out;
    }, jids);

    dbg(`presence ${chatId}: lastSeen=${result.lastSeen} src=${result.dbg?.src}`);
    dbg('presence dbg:', JSON.stringify(result.dbg));
    res.json({ lastSeen: result.lastSeen ?? null });
  } catch (e) {
    console.error('[ERROR] presence:', e.message);
    res.json({ lastSeen: null });
  }
});

app.post('/api/fetch-media/:chatId', async (req, res) => {
  const { chatId } = req.params;
  const limit = Math.min(parseInt(req.query.limit || '20', 10), 50);
  if (!DOWNLOAD_MEDIA) return res.status(400).json({ error: 'download_media not enabled' });
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  const msgs = getChatMsgs(chatId);
  const pending = msgs.filter(m => m.type === 'photo' && !m.mediaFile).slice(-limit);
  res.json({ total: pending.length });
  if (!pending.length) return;
  (async () => {
    let count = 0;
    for (const stored of pending) {
      try {
        const fullMsg = await client.getMessageById(stored.id);
        if (fullMsg) {
          const file = await downloadWAMedia(fullMsg, stored.id);
          if (file) { stored.mediaFile = file; count++; }
        }
      } catch (e) {
        dbg(`fetch-media: error for ${stored.id}: ${e.message}`);
      }
      await new Promise(r => setTimeout(r, 600));
    }
    console.log(`[INFO] fetch-media: ${count}/${pending.length} Fotos geladen für ${chatId}`);
  })();
});

app.delete('/api/messages/:chatId/:msgId', async (req, res) => {
  const { chatId, msgId } = req.params;
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  try {
    dbg(`Deleting message ${msgId} in chat ${chatId}`);
    const msg = await client.getMessageById(msgId);
    await msg.delete(true);
    const msgs = messagesByChatId.get(chatId);
    if (msgs) {
      const idx = msgs.findIndex(m => m.id === msgId);
      if (idx !== -1) { msgs.splice(idx, 1); seenIds.delete(msgId); }
    }
    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── Web UI ────────────────────────────────────────────────────────────────────

app.get('/', (req, res) => {
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.send(`<!DOCTYPE html>
<html lang="de" class="${DARK_MODE ? 'dark' : 'light'}">
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
    .storage-info { font-size: 12px; color: #8696a0; white-space: nowrap; }
    .logout-btn {
      background: none; border: none; color: #8696a0;
      font-size: 20px; cursor: pointer; padding: 4px; line-height: 1;
    }
    .logout-btn:hover { color: #f15c5c; }
    .photo-toggle-btn {
      background: none; border: 1px solid #8696a0; color: #e9edef;
      padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 12px; opacity: 0.55;
    }
    .photo-toggle-btn:hover { opacity: 0.8; }
    .photo-toggle-btn.active { opacity: 1; background: rgba(37,211,102,0.15); border-color: #25d366; color: #25d366; }
    .scroll-btn { background: none; border: 1px solid #8696a0; color: #e9edef; padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 14px; opacity: 0.55; line-height: 1; }
    .scroll-btn:hover { opacity: 0.8; }
    .photo-placeholder { display: none; }
    body.hide-photos .msg-img { display: none !important; }
    body.hide-photos .photo-placeholder { display: inline; }

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
    .chat-time { font-size: 11px; color: #8696a0; white-space: nowrap; }
    .unread-dot { width: 10px; height: 10px; background: #25d366; border-radius: 50%; }
    html.light .unread-dot { background: #128c7e; }
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
    #ch-lastseen { font-size: 12px; color: #8696a0; margin-top: 1px; }
    #fetch-media-btn { margin-left: auto; background: none; border: 1px solid rgba(134,150,160,0.5); color: #8696a0; padding: 5px 10px; border-radius: 6px; cursor: pointer; font-size: 12px; flex-shrink: 0; white-space: nowrap; }
    #fetch-media-btn:hover { border-color: #25d366; color: #25d366; }
    #fetch-media-btn:disabled { opacity: 0.4; cursor: default; border-color: rgba(134,150,160,0.3); color: #8696a0; }

    #messages {
      flex: 1; overflow-y: auto; padding: 12px 16px;
      display: flex; flex-direction: column; gap: 1px;
    }
    #messages::-webkit-scrollbar { width: 5px; }
    #messages::-webkit-scrollbar-thumb { background: #2a3942; border-radius: 3px; }

    .bubble-wrap { display: flex; flex-direction: column; margin: 1px 0; width: 100%; }
    .bubble-wrap.out { align-items: flex-end; }
    .bubble-wrap.in  { align-items: flex-start; }
    .contact-name { font-size: 11px; color: #8696a0; margin-bottom: 2px; padding: 0 4px; }
    .bubble {
      max-width: 65%; padding: 6px 10px 8px; border-radius: 7.5px;
      font-size: 14px; line-height: 1.45; word-break: break-word;
    }
    .bubble-row-inner { display: flex; align-items: center; gap: 6px; }
    .bubble-wrap.out .bubble-row-inner { width: 100%; justify-content: flex-end; }
    .bubble-wrap.out .del-btn { order: -1; }
    .del-btn { display: none; background: none; border: none; cursor: pointer; font-size: 15px; padding: 4px 6px; line-height: 1; border-radius: 6px; flex-shrink: 0; color: rgba(233,237,239,0.6); }
    .bubble-row-inner:hover .del-btn { display: block; }
    html.light .del-btn { color: rgba(0,0,0,0.4); }
    .del-btn:hover { color: #f15c5c !important; }
    .react-btn { display: none; background: none; border: none; cursor: pointer; font-size: 16px; padding: 4px; line-height: 1; border-radius: 50%; color: rgba(233,237,239,0.55); flex-shrink: 0; }
    .bubble-row-inner:hover .react-btn { display: inline-flex; align-items: center; }
    html.light .react-btn { color: rgba(0,0,0,0.35); }
    .react-btn:hover { background: rgba(134,150,160,0.18); color: #e9edef; }
    html.light .react-btn:hover { color: #111; }
    #reaction-picker { position: fixed; z-index: 300; border-radius: 28px; padding: 6px 10px; display: none; gap: 2px; box-shadow: 0 2px 16px rgba(0,0,0,0.3); }
    html.dark #reaction-picker { background: #233038; border: 1px solid #2a3942; }
    html.light #reaction-picker { background: #fff; border: 1px solid #d9dbdf; }
    #reaction-picker button { background: none; border: none; font-size: 24px; cursor: pointer; padding: 3px 4px; border-radius: 50%; line-height: 1; transition: transform 0.12s; }
    #reaction-picker button:hover { transform: scale(1.4); }
    .reactions-bar { display: flex; flex-wrap: wrap; gap: 3px; padding: 3px 2px 0; }
    .bubble-wrap.out .reactions-bar { justify-content: flex-end; }
    .reaction-badge { display: inline-flex; align-items: center; gap: 2px; border-radius: 10px; padding: 2px 7px; font-size: 13px; cursor: pointer; border: 1px solid transparent; user-select: none; line-height: 1.5; }
    html.dark .reaction-badge { background: #233038; border-color: #2a3942; color: #e9edef; }
    html.light .reaction-badge { background: #f0f2f5; border-color: #d9dbdf; color: #111; }
    .reaction-badge.own { border-color: #25d366; }
    html.dark .reaction-badge.own { background: rgba(37,211,102,0.12); }
    html.light .reaction-badge.own { background: rgba(37,211,102,0.1); }
    .reaction-badge:hover { opacity: 0.8; }
    .bubble-wrap.out .bubble { background: #005c4b; border-top-right-radius: 0; }
    .bubble-wrap.in  .bubble { background: #202c33; border-top-left-radius: 0; }
    .bubble.bubble-photo { padding: 0; overflow: hidden; }
    .bubble.bubble-photo .time { display: block; padding: 2px 8px 4px; text-align: right; }
    .bubble.bubble-photo .caption { padding: 4px 10px 0; }
    .bubble .time {
      font-size: 10px; color: rgba(134,150,160,0.85);
      float: right; margin-left: 8px; margin-top: 2px; white-space: nowrap;
    }
    .msg-ack { font-size: 12px; margin-left: 2px; vertical-align: middle; }
    .ack-1, .ack-2 { color: rgba(134,150,160,0.85); }
    .ack-3 { color: #53bdeb; }
    html.light .ack-1, html.light .ack-2 { color: rgba(0,0,0,0.4); }
    html.light .ack-3 { color: #0a84ff; }
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
      border-top: 1px solid #2a3942; flex-shrink: 0; position: relative;
    }
    #emoji-picker { display: none; position: absolute; bottom: 100%; left: 0; right: 0; background: #202c33; border-top: 1px solid #2a3942; padding: 8px 12px; max-height: 200px; overflow-y: auto; z-index: 20; box-shadow: 0 -2px 8px rgba(0,0,0,0.2); }
    #emoji-picker.open { display: block; }
    .emoji-grid { display: flex; flex-wrap: wrap; gap: 2px; }
    #send-bar .emoji-btn { background: none; border: none; font-size: 22px; cursor: pointer; padding: 3px 5px; border-radius: 6px; line-height: 1; width: auto; height: auto; }
    #send-bar .emoji-btn:hover { background: #2a3942; }
    #send-bar #emoji-toggle { background: none; border: none; font-size: 20px; cursor: pointer; padding: 6px; border-radius: 50%; flex-shrink: 0; line-height: 1; color: #8696a0; width: auto; height: auto; }
    #send-bar #emoji-toggle:hover { background: rgba(255,255,255,0.08); }
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

    /* Back button (mobile only) */
    #back-btn {
      display: none; background: none; border: none;
      color: #e9edef; font-size: 22px; cursor: pointer; padding: 4px 8px 4px 0;
      line-height: 1; flex-shrink: 0;
    }

    /* ── Mobile responsive ── */
    @media (max-width: 768px) {
      #sidebar { width: 100%; max-width: 100%; border-right: none; }
      #chat-panel { display: none; }
      #back-btn { display: block; }
      /* When a chat is open: hide sidebar, show chat panel */
      body.chat-open #sidebar { display: none; }
      body.chat-open #chat-panel { display: flex; }
    }

    /* Overlays */
    .overlay {
      position: fixed; inset: 0; background: #111b21; z-index: 100;
      display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 20px;
    }
    .overlay p { color: #8696a0; font-size: 14px; text-align: center; line-height: 1.7; }
    .overlay h2 { font-size: 20px; }
    #qr-overlay img { background: #fff; padding: 16px; border-radius: 12px; max-width: 280px; }

    html.light body { background: #f0f2f5; color: #111; }
    html.light .overlay { background: #f0f2f5; }
    html.light .overlay p { color: #555; }
    html.light .topbar { background: #075e54; }
    html.light #sidebar { background: #fff; border-color: #e0e0e0; }
    html.light #sidebar-header { background: #f0f2f5; border-color: #e0e0e0; }
    html.light #search { background: #f5f5f5; color: #111; }
    html.light #search::placeholder { color: #999; }
    html.light .chat-item { border-color: #f5f5f5; }
    html.light .chat-item:hover { background: #f5f5f5; }
    html.light .chat-item.active { background: #e9edf5; }
    html.light .chat-name { color: #111; }
    html.light .chat-preview { color: #999; }
    html.light .chat-time { color: #999; }
    html.light .no-chats { color: #777; }
    html.light #chat-panel { background: #e5ddd5; }
    html.light #chat-header { background: #075e54; border-color: #075e54; }
    html.light #ch-name { color: #fff; }
    html.light #ch-phone { color: rgba(255,255,255,0.75); }
    html.light #ch-lastseen { color: rgba(255,255,255,0.75); }
    html.light #welcome { color: #555; }
    html.light .bubble-wrap.in .bubble { background: #fff; color: #111; }
    html.light .bubble-wrap.out .bubble { background: #dcf8c6; color: #111; }
    html.light .bubble .time { color: rgba(0,0,0,0.4); }
    html.light .date-sep { color: #666; background: rgba(225,245,254,0.92); }
    html.light .contact-name { color: #666; }
    html.light .empty-msg { color: #777; }
    html.light #send-bar { background: #f0f2f5; border-color: #e0e0e0; }
    html.light #msg-input { background: #fff; color: #111; }
    html.light #msg-input::placeholder { color: #999; }
    html.light #emoji-picker { background: #fff; border-color: #e0e0e0; }
    html.light #send-bar .emoji-btn:hover { background: #f0f2f5; }
    html.light #send-bar #emoji-toggle { color: #555; }
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
    <span class="storage-info" id="storage-info"></span>
    ${DOWNLOAD_MEDIA ? '<button id="photo-toggle" class="photo-toggle-btn active" onclick="togglePhotos()">Fotos AN</button>' : ''}
    <button class="scroll-btn" onclick="scrollMsgs('top')" title="Nach oben">↑</button>
    <button class="scroll-btn" onclick="scrollMsgs('bottom')" title="Nach unten">↓</button>
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
        <button id="back-btn" onclick="closeChat()" title="Zurück">&#8592;</button>
        <div class="avatar" id="ch-avatar"></div>
        <div>
          <div id="ch-name"></div>
          <div id="ch-phone"></div>
          <div id="ch-lastseen"></div>
        </div>
        ${DOWNLOAD_MEDIA ? '<button id="fetch-media-btn" onclick="fetchMedia()" title="Letzte 20 Fotos herunterladen">📥 Fotos nachladen</button>' : ''}
      </div>
      <div id="messages" style="display:none;"></div>
      <div id="send-bar" style="display:none;">
        <div id="emoji-picker"><div class="emoji-grid" id="emoji-grid"></div></div>
        <button id="emoji-toggle" onclick="toggleEmojiPicker(event)" title="Emoji">😊</button>
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
    let lastSeenTime = {};
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
    async function loadStorage() {
      try {
        const d = await fetch('api/storage').then(r => r.json());
        const el = document.getElementById('storage-info');
        if (el) el.textContent = '💾 ' + d.mb + ' MB';
      } catch(e) {}
    }
    loadStorage();
    setInterval(loadStorage, 60000);

    function scrollMsgs(dir) {
      const el = document.getElementById('messages');
      if (!el) return;
      el.scrollTop = dir === 'top' ? 0 : el.scrollHeight;
    }

    function togglePhotos() {
      const hiding = !document.body.classList.contains('hide-photos');
      document.body.classList.toggle('hide-photos', hiding);
      const btn = document.getElementById('photo-toggle');
      if (btn) { btn.classList.toggle('active', !hiding); btn.textContent = hiding ? 'Fotos AUS' : 'Fotos AN'; }
      localStorage.setItem('wa-hide-photos', hiding ? '1' : '');
    }
    if (localStorage.getItem('wa-hide-photos')) {
      document.body.classList.add('hide-photos');
      const btn = document.getElementById('photo-toggle');
      if (btn) { btn.classList.remove('active'); btn.textContent = 'Fotos AUS'; }
    }

    function ackMark(ack) {
      if (ack >= 3) return '<span class="msg-ack ack-3">✓✓</span>';
      if (ack === 2) return '<span class="msg-ack ack-2">✓✓</span>';
      if (ack === 1) return '<span class="msg-ack ack-1">✓</span>';
      return '';
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

        const meta = document.createElement('div');
        meta.style.cssText = 'display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0;';
        const time = document.createElement('div');
        time.className = 'chat-time';
        time.textContent = chat.lastTime ? fmtChatTime(chat.lastTime) : '';
        meta.appendChild(time);
        if (chat.id !== selectedChatId && chat.lastTime > (lastSeenTime[chat.id] || 0)) {
          const dot = document.createElement('div');
          dot.className = 'unread-dot';
          meta.appendChild(dot);
        }

        item.appendChild(av); item.appendChild(info); item.appendChild(meta);
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
      document.body.classList.add('chat-open'); // mobile: show chat panel

      const av = document.getElementById('ch-avatar');
      av.style.background = avatarColor(chat.name);
      av.textContent = avatarInitials(chat.name);
      document.getElementById('ch-name').textContent = chat.name;
      const ph = chat.phone || '';
      document.getElementById('ch-phone').textContent = /^\d{7,15}$/.test(ph) ? '+' + ph : '';
      document.getElementById('ch-lastseen').textContent = '';
      fetchPresence(chat.id);

      lastSeenTime[chat.id] = chat.lastTime || Date.now();
      renderChatList(allChats);
      msgList.innerHTML = '';
      lastMsgTime[chat.id] = 0;
      atBottom = true;
      await loadMessages(chat.id);
    }

    function closeChat() {
      document.body.classList.remove('chat-open'); // mobile: back to chat list
      selectedChatId = null;
      selectedChatPhone = null;
      document.querySelectorAll('.chat-item').forEach(el => el.classList.remove('active'));
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
        wrap.dataset.msgid = m.id;
        if (!m.fromMe && m.contact) {
          const n = document.createElement('div');
          n.className = 'contact-name';
          n.textContent = m.contact;
          wrap.appendChild(n);
        }
        const bub = document.createElement('div');
        bub.className = 'bubble';
        const ack = m.fromMe ? ackMark(m.ack || 0) : '';
        if (m.type === 'photo' && m.mediaFile) {
          bub.classList.add('bubble-photo');
          const ph = document.createElement('span');
          ph.className = 'photo-placeholder'; ph.textContent = '📷 Foto';
          bub.appendChild(ph);
          const img = document.createElement('img');
          img.className = 'msg-img';
          img.src = 'api/media/' + encodeURIComponent(m.mediaFile);
          img.style.cssText = 'max-width:240px;max-height:300px;display:block;cursor:pointer;width:100%;';
          img.loading = 'lazy';
          img.addEventListener('click', function() { this.style.maxWidth = this.style.maxWidth === 'none' ? '240px' : 'none'; });
          bub.appendChild(img);
          if (m.body) { const cap = document.createElement('div'); cap.className = 'caption'; cap.textContent = m.body; bub.appendChild(cap); }
          const t = document.createElement('span'); t.className = 'time'; t.innerHTML = fmtTime(m.timestamp) + ack; bub.appendChild(t);
        } else {
          bub.innerHTML = esc(m.body || (m.type === 'photo' ? '📷 Foto' : '')) + '<span class="time">' + fmtTime(m.timestamp) + ack + '</span>';
        }
        const bri = document.createElement('div');
        bri.className = 'bubble-row-inner';
        bri.appendChild(bub);
        const delBtn = document.createElement('button');
        delBtn.className = 'del-btn';
        delBtn.title = 'Löschen';
        delBtn.textContent = '✕';
        delBtn.dataset.msgid = m.id;
        bri.appendChild(delBtn);
        const reactBtn = document.createElement('button');
        reactBtn.className = 'react-btn';
        reactBtn.title = 'Reagieren';
        reactBtn.textContent = '😊';
        reactBtn.dataset.msgid = m.id;
        bri.appendChild(reactBtn);
        wrap.appendChild(bri);
        if (m.reactions && Object.keys(m.reactions).length) {
          const bar = document.createElement('div');
          bar.className = 'reactions-bar';
          const myJid = myPhone ? myPhone + '@c.us' : null;
          for (const [emoji, senders] of Object.entries(m.reactions)) {
            if (!senders.length) continue;
            const isOwn = myJid ? senders.includes(myJid) : false;
            const badge = document.createElement('span');
            badge.className = 'reaction-badge' + (isOwn ? ' own' : '');
            badge.textContent = emoji + (senders.length > 1 ? ' ' + senders.length : '');
            badge.onclick = () => toggleReaction(m.id, emoji, isOwn);
            bar.appendChild(badge);
          }
          wrap.appendChild(bar);
        }
        msgList.appendChild(wrap);
        if (m.timestamp > (lastMsgTime[selectedChatId] || 0)) {
          lastMsgTime[selectedChatId] = m.timestamp;
        }
      });
      if (atBottom) msgList.scrollTop = msgList.scrollHeight;
    }

    function fmtLastSeen(ts) {
      const d = new Date(ts > 1e10 ? ts : ts * 1000);
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const yesterday = new Date(today.getTime() - 86400000);
      const day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
      const time = d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
      if (day.getTime() === today.getTime()) return 'heute um ' + time;
      if (day.getTime() === yesterday.getTime()) return 'gestern um ' + time;
      return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }) + '. um ' + time;
    }

    async function fetchPresence(chatId) {
      const el = document.getElementById('ch-lastseen');
      if (!el) return;
      el.textContent = '';

      const tryFetch = async () => {
        if (chatId !== selectedChatId) return true; // chat changed, stop
        try {
          const d = await fetch('api/presence/' + encodeURIComponent(chatId)).then(r => r.json());
          if (chatId !== selectedChatId) return true;
          if (d.isGroup) {
            el.textContent = d.memberCount ? d.memberCount + ' Mitglieder' : '';
            return true;
          } else if (d.lastSeen) {
            el.textContent = 'Zuletzt gesehen ' + fmtLastSeen(d.lastSeen);
            return true;
          }
          return false;
        } catch(e) { return false; }
      };

      if (await tryFetch()) return;
      // WhatsApp presence subscription takes a few seconds — retry
      setTimeout(async () => { if (!await tryFetch()) setTimeout(tryFetch, 5000); }, 3000);
    }

    async function reloadMessages(chatId) {
      if (!chatId || chatId !== selectedChatId) return;
      try {
        const msgs = await fetch('api/messages?chat=' + encodeURIComponent(chatId)).then(r => r.json());
        msgList.innerHTML = '';
        lastMsgTime[chatId] = 0;
        atBottom = true;
        if (msgs.length) renderMessages(msgs, chatId);
        lastMsgTime[chatId] = msgs.reduce((max, m) => Math.max(max, m.timestamp), 0);
      } catch(e) {}
    }

    async function fetchMedia() {
      const btn = document.getElementById('fetch-media-btn');
      if (!btn || !selectedChatId) return;
      btn.disabled = true;
      btn.textContent = '⏳ Lade…';
      try {
        const d = await fetch('api/fetch-media/' + encodeURIComponent(selectedChatId), { method: 'POST' }).then(r => r.json());
        if (!d.total) {
          btn.textContent = '✓ Alle geladen';
          setTimeout(() => { btn.disabled = false; btn.textContent = '📥 Fotos nachladen'; }, 2500);
          return;
        }
        btn.textContent = '⏳ ' + d.total + ' Fotos…';
        let polls = 0;
        const iv = setInterval(async () => {
          polls++;
          await reloadMessages(selectedChatId);
          if (polls >= 20) {
            clearInterval(iv);
            btn.disabled = false;
            btn.textContent = '📥 Fotos nachladen';
          }
        }, 2000);
      } catch(e) {
        btn.disabled = false;
        btn.textContent = '📥 Fotos nachladen';
      }
    }

    async function pollMessages() {
      if (currentStatus !== 'connected' || !selectedChatId) return;
      await loadMessages(selectedChatId);
    }

    async function pollChats() {
      if (currentStatus !== 'connected') return;
      try {
        const chats = await fetch('api/chats').then(r => r.json());
        chats.forEach(c => {
          if (!(c.id in lastSeenTime)) lastSeenTime[c.id] = c.lastTime || 0;
          else if (c.id === selectedChatId) lastSeenTime[c.id] = c.lastTime || lastSeenTime[c.id];
        });
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

    async function deleteMsg(chatId, msgId) {
      try {
        await fetch('api/messages/' + encodeURIComponent(chatId) + '/' + encodeURIComponent(msgId), {method:'DELETE'});
        for (const bri of msgList.querySelectorAll('.bubble-row-inner')) {
          if (bri.querySelector('.del-btn')?.dataset?.msgid === msgId) {
            bri.closest('.bubble-wrap')?.remove();
            break;
          }
        }
      } catch(e) {}
    }
    msgList.addEventListener('click', e => {
      const del = e.target.closest('.del-btn');
      if (del) { deleteMsg(selectedChatId, del.dataset.msgid); return; }
      const react = e.target.closest('.react-btn');
      if (react) { openReactionPicker(react, react.dataset.msgid); return; }
    });

    function showSpinner(msg) {
      document.getElementById('spinner-overlay').style.display = 'flex';
      document.getElementById('spinner-text').textContent = msg || 'Starte neu…';
      document.getElementById('topbar').style.display = 'none';
      document.getElementById('main').style.display = 'none';
      document.getElementById('qr-overlay').style.display = 'none';
      currentStatus = ''; // force refresh() to pick up new status
    }

    async function logout() {
      showSpinner('Abgemeldet — lade QR-Code…');
      await fetch('api/logout', { method: 'POST' }).catch(() => {});
    }

    async function resetSession() {
      showSpinner('Session gelöscht — lade QR-Code…');
      await fetch('api/reset', { method: 'POST' }).catch(() => {});
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

        if (s.phone && !myPhone) myPhone = s.phone;
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
    setInterval(pollReactions, 5000);

    // ── Reactions ──────────────────────────────────────────────────────────────
    const REACTION_EMOJIS = ['👍','❤️','😂','😮','😢','🙏'];
    let pickerTargetMsgId = null;
    let myPhone = null;

    const reactionPicker = document.createElement('div');
    reactionPicker.id = 'reaction-picker';
    reactionPicker.style.display = 'none';
    REACTION_EMOJIS.forEach(e => {
      const btn = document.createElement('button');
      btn.textContent = e;
      btn.title = e;
      btn.onclick = () => reactTo(e);
      reactionPicker.appendChild(btn);
    });
    document.body.appendChild(reactionPicker);

    document.addEventListener('click', ev => {
      if (!ev.target.closest('#reaction-picker') && !ev.target.closest('.react-btn')) {
        reactionPicker.style.display = 'none';
        pickerTargetMsgId = null;
      }
    });

    function openReactionPicker(btn, msgId) {
      pickerTargetMsgId = msgId;
      reactionPicker.style.display = 'flex';
      // Position above the trigger button
      const r = btn.getBoundingClientRect();
      reactionPicker.style.top = '-9999px';
      reactionPicker.style.left = '-9999px';
      requestAnimationFrame(() => {
        const pw = reactionPicker.offsetWidth || 220;
        const ph = reactionPicker.offsetHeight || 52;
        let top = r.top - ph - 8;
        if (top < 4) top = r.bottom + 8;
        let left = r.left + r.width / 2 - pw / 2;
        if (left < 4) left = 4;
        if (left + pw > window.innerWidth - 4) left = window.innerWidth - pw - 4;
        reactionPicker.style.top = top + 'px';
        reactionPicker.style.left = left + 'px';
      });
    }

    async function reactTo(emoji) {
      if (!pickerTargetMsgId) return;
      const msgId = pickerTargetMsgId;
      reactionPicker.style.display = 'none';
      pickerTargetMsgId = null;
      await fetch('api/react', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ msgId, reaction: emoji }),
      }).catch(() => {});
      setTimeout(pollReactions, 800);
    }

    async function toggleReaction(msgId, emoji, isOwn) {
      await fetch('api/react', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ msgId, reaction: isOwn ? '' : emoji }),
      }).catch(() => {});
      setTimeout(pollReactions, 800);
    }

    async function pollReactions() {
      if (!selectedChatId) return;
      try {
        const data = await fetch('api/reactions/' + encodeURIComponent(selectedChatId)).then(r => r.json());
        updateReactionsInDOM(data);
      } catch(e) {}
    }

    function updateReactionsInDOM(reactionsMap) {
      const myJid = myPhone ? myPhone + '@c.us' : null;
      for (const wrap of msgList.querySelectorAll('.bubble-wrap[data-msgid]')) {
        const msgId = wrap.dataset.msgid;
        const reactions = reactionsMap[msgId];
        let bar = wrap.querySelector('.reactions-bar');
        if (!reactions || !Object.keys(reactions).length) {
          if (bar) bar.remove();
          continue;
        }
        if (!bar) { bar = document.createElement('div'); bar.className = 'reactions-bar'; wrap.appendChild(bar); }
        bar.innerHTML = '';
        for (const [emoji, senders] of Object.entries(reactions)) {
          if (!senders.length) continue;
          const isOwn = myJid ? senders.includes(myJid) : false;
          const badge = document.createElement('span');
          badge.className = 'reaction-badge' + (isOwn ? ' own' : '');
          badge.title = isOwn ? 'Klicken zum Entfernen' : 'Klicken zum Reagieren';
          badge.textContent = emoji + (senders.length > 1 ? ' ' + senders.length : '');
          badge.onclick = () => toggleReaction(msgId, emoji, isOwn);
          bar.appendChild(badge);
        }
      }
    }
  </script>
</body>
</html>`);
});

// ── Start ─────────────────────────────────────────────────────────────────────

fs.mkdirSync(MEDIA_DIR, { recursive: true });

const PORT = parseInt(process.env.PORT || '3000', 10);
app.listen(PORT, () => console.log(`[INFO] Web UI running on port ${PORT}`));
