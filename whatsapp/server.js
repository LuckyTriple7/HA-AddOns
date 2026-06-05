'use strict';
(function () {
  const _ts = () => new Date().toISOString().slice(0, 19).replace('T', ' ');
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

const { Client, NoAuth, MessageMedia } = require('whatsapp-web.js');
const multer = require('multer');
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 64 * 1024 * 1024 } });
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
const WA_VERSION = require('./node_modules/whatsapp-web.js/package.json').version;
console.log(`[INFO] whatsapp-web.js v${WA_VERSION}`);
console.log(`[INFO] Using Chromium: ${CHROMIUM}`);

// ── State ─────────────────────────────────────────────────────────────────────

const app = express();
app.use(express.json());

let qrCodeDataUrl = null;
let status = 'initializing';
let connectedPhone = null;
let lastError = null;
let lastReceivedMsg = null; // { timestamp, iso, chatId, chatName, contact, preview }

const DARK_MODE = process.env.DARK_MODE !== 'false';
const DOWNLOAD_MEDIA = process.env.DOWNLOAD_MEDIA === 'true';
const KEEP_DELETED = process.env.KEEP_DELETED === 'true';
const DEBUG = process.env.DEBUG_MODE === 'true';
const HA_NOTIFY = process.env.HA_NOTIFICATIONS === 'true';
const HA_PRIVACY = process.env.HA_NOTIFICATIONS_PRIVACY === 'true';
const HA_NOTIFY_SKIP_GROUPS = process.env.HA_NOTIFICATIONS_SKIP_GROUPS === 'true';
function dbg(...args) { if (DEBUG) console.log('[DEBUG]', ...args); }
if (DEBUG) console.log('[DEBUG] Debug-Modus aktiv');
const MEDIA_DIR = '/config/media';
const INITIAL_CHATS = parseInt(process.env.INITIAL_CHATS || '30', 10);
const INITIAL_MESSAGES = parseInt(process.env.INITIAL_MESSAGES || '20', 10);
const WEBHOOK = process.env.WEBHOOK_INCOMING || '';
console.log('[INFO] ── Configuration ──────────────────────────────────');
console.log(`[INFO]   dark_mode              = ${DARK_MODE}`);
console.log(`[INFO]   download_media         = ${DOWNLOAD_MEDIA}`);
console.log(`[INFO]   keep_deleted           = ${KEEP_DELETED}`);
console.log(`[INFO]   debug_mode             = ${DEBUG}`);
console.log(`[INFO]   ha_notifications       = ${HA_NOTIFY}`);
console.log(`[INFO]   ha_notifications_priv  = ${HA_PRIVACY}`);
console.log(`[INFO]   ha_notify_skip_groups  = ${HA_NOTIFY_SKIP_GROUPS}`);
console.log(`[INFO]   ha_token               = ${process.env.HA_TOKEN ? 'set' : 'not set'}`);
console.log(`[INFO]   initial_chats          = ${INITIAL_CHATS}`);
console.log(`[INFO]   initial_messages       = ${INITIAL_MESSAGES}`);
console.log(`[INFO]   webhook_incoming       = ${WEBHOOK ? WEBHOOK : 'not set'}`);
console.log('[INFO] ─────────────────────────────────────────────────────');
const chatMap = new Map();          // chatId -> { id, name, phone, lastMsg, lastTime, isGroup }
const messagesByChatId = new Map(); // chatId -> Message[]
const seenIds = new Set();

const CHATS_FILE = '/config/chats.json';
const MESSAGES_FILE = '/config/messages.json';
const REACTIONS_FILE = '/config/reactions.json';
const reactionsCache = new Map(); // msgId -> { emoji: [senderJid, ...] }

// Eigene Reaktionen werden unabhängig von JID-Formaten getrackt.
// Format: { msgId: emoji } — kein JID-Vergleich nötig.
const OWN_REACTIONS_FILE = '/config/ownreactions.json';
let myReactions = new Map(); // msgId -> emoji (leer = keine eigene Reaktion)

function normalizeJid(jid) {
  const m = String(jid).match(/^(\d+)/);
  return m ? m[1] + '@c.us' : '';
}

try {
  if (existsSync(REACTIONS_FILE)) {
    const data = JSON.parse(fs.readFileSync(REACTIONS_FILE, 'utf8'));
    for (const [msgId, reactions] of Object.entries(data)) {
      const clean = {};
      for (const [emoji, senders] of Object.entries(reactions)) {
        const deduped = [...new Set(senders.map(normalizeJid))].filter(Boolean);
        if (deduped.length) clean[emoji] = deduped;
      }
      if (Object.keys(clean).length) reactionsCache.set(msgId, clean);
    }
    console.log(`[INFO] Loaded reactions for ${reactionsCache.size} messages from disk`);
  }
} catch (e) { console.error('[ERROR] loadReactions:', e.message); }

try {
  if (existsSync(OWN_REACTIONS_FILE)) {
    const data = JSON.parse(fs.readFileSync(OWN_REACTIONS_FILE, 'utf8'));
    myReactions = new Map(Object.entries(data));
    console.log(`[INFO] Loaded own reactions for ${myReactions.size} messages from disk`);
  }
} catch (e) { console.error('[ERROR] loadOwnReactions:', e.message); }

try {
  if (existsSync(CHATS_FILE)) {
    const data = JSON.parse(fs.readFileSync(CHATS_FILE, 'utf8'));
    for (const chat of data) chatMap.set(chat.id, chat);
    console.log(`[INFO] Loaded ${chatMap.size} chats from disk`);
  }
} catch (e) { console.error('[ERROR] loadChats:', e.message); }

try {
  if (existsSync(MESSAGES_FILE)) {
    const data = JSON.parse(fs.readFileSync(MESSAGES_FILE, 'utf8'));
    let total = 0;
    for (const [chatId, msgs] of Object.entries(data)) {
      messagesByChatId.set(chatId, msgs);
      for (const m of msgs) { seenIds.add(m.id); applyReactionsToMsg(m); }
      total += msgs.length;
    }
    console.log(`[INFO] Loaded ${total} messages from disk`);
  }
} catch (e) { console.error('[ERROR] loadMessages:', e.message); }

try {
  let best = null;
  for (const [chatId, msgs] of messagesByChatId.entries()) {
    const chat = chatMap.get(chatId);
    if (HA_NOTIFY_SKIP_GROUPS && chat?.isGroup) continue;
    for (const m of msgs) {
      if (!m.fromMe && !m.deleted && (!best || m.timestamp > best.timestamp)) {
        best = {
          timestamp: m.timestamp,
          iso: new Date(m.timestamp).toISOString(),
          chatId,
          chatName: chat?.name || chatId,
          contact: m.contact || '',
          preview: m.body || (m.type === 'photo' ? '📷 Foto' : m.type === 'document' ? `📄 ${m.filename || 'Dokument'}` : '[Medien]'),
        };
      }
    }
  }
  if (best) lastReceivedMsg = best;
} catch (e) { console.error('[ERROR] lastReceivedMsg init:', e.message); }

let reactionsSaveTimer = null;
function saveReactions() {
  if (reactionsSaveTimer) clearTimeout(reactionsSaveTimer);
  reactionsSaveTimer = setTimeout(() => {
    try {
      fs.writeFileSync(REACTIONS_FILE, JSON.stringify(Object.fromEntries(reactionsCache)));
      fs.writeFileSync(OWN_REACTIONS_FILE, JSON.stringify(Object.fromEntries(myReactions)));
    } catch (e) { console.error('[ERROR] saveReactions:', e.message); }
  }, 3000);
}

let msgsSaveTimer = null;
function saveMsgs() {
  if (msgsSaveTimer) clearTimeout(msgsSaveTimer);
  msgsSaveTimer = setTimeout(() => {
    try {
      fs.writeFileSync(CHATS_FILE, JSON.stringify([...chatMap.values()]));
      const msgsObj = {};
      for (const [chatId, msgs] of messagesByChatId.entries()) msgsObj[chatId] = msgs;
      fs.writeFileSync(MESSAGES_FILE, JSON.stringify(msgsObj));
    } catch (e) { console.error('[ERROR] saveMsgs:', e.message); }
  }, 3000);
}

function applyReactionsToMsg(msg) {
  const saved = reactionsCache.get(msg.id);
  if (saved && Object.keys(saved).length) msg.reactions = { ...saved };
}

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
  applyReactionsToMsg(msg);
  msgs.push(msg);
  msgs.sort((a, b) => a.timestamp - b.timestamp);
  const chat = chatMap.get(chatId);
  if (chat && msg.timestamp >= (chat.lastTime || 0)) {
    const preview = msg.body || (msg.type === 'photo' ? '📷 Foto' : msg.type === 'document' ? '📄 ' + (msg.filename || 'Dokument') : msg.type === 'voice' ? '🎵 Sprachnachricht' : '[Medien]');
    chat.lastMsg = preview.length > 60 ? preview.slice(0, 60) + '…' : preview;
    chat.lastTime = msg.timestamp;
    chat.lastFromMe = !!msg.fromMe;
  }
  saveMsgs();
  return true;
}

async function downloadWAMedia(msg, msgId) {
  try {
    const safeId = msgId.replace(/[^a-zA-Z0-9]/g, '_');
    const ext = msg.type === 'sticker' ? 'webp' : (msg.type === 'ptt' || msg.type === 'audio') ? 'ogg' : 'jpg';
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
      '--disk-cache-size=52428800',
      '--media-cache-size=52428800',
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
  _reconnecting = false;
  _intentionalDisconnect = false;
  connectedPhone = (client.info?.wid?.user || '').replace(/:\d+$/, '') || null;
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
        const isPtt = msg.type === 'ptt' || msg.type === 'audio';
        if (!isText && !isImage && !isPtt) continue;
        if (!msg.body && !isImage && !isPtt) continue;
        let contactName = msg.fromMe ? 'Ich' : (chat.name || chat.id.user);
        if (!msg.fromMe && chat.isGroup) {
          const c = await msg.getContact().catch(() => null);
          contactName = c?.name || c?.pushname || msg.author?.replace('@c.us', '') || contactName;
        }
        let quotedMsg = null;
        if (msg.hasQuotedMsg) {
          try {
            const q = await msg.getQuotedMessage();
            if (q) quotedMsg = {
              body: (q.body || '').slice(0, 100),
              type: q.type,
              contact: q.fromMe ? 'Ich' : (q._data?.notifyName || (q.from || '').replace('@c.us', '')),
            };
          } catch(e) { dbg('getQuotedMessage:', e.message); }
        }
        addMsg(chatId, {
          id: msg.id._serialized,
          body: msg.body || '',
          type: isImage ? 'photo' : isPtt ? 'voice' : 'text',
          mediaFile: null,
          timestamp: msg.timestamp * 1000,
          fromMe: msg.fromMe,
          contact: contactName,
          ack: msg.ack || 0,
          isForwarded: !!msg.isForwarded,
          forwardingScore: msg.forwardingScore || 0,
          quotedMsg,
        });
      }
    }
    const total = [...messagesByChatId.values()].reduce((s, a) => s + a.length, 0);
    console.log(`[INFO] Loaded ${total} messages from ${recent.length} chats`);
    saveMsgs();

    if (DOWNLOAD_MEDIA) {
      (async () => {
        const pending = [];
        let cached = 0;
        for (const [chatId, msgs] of messagesByChatId) {
          for (const m of msgs.filter(m => m.type === 'photo' || m.type === 'voice')) {
            if (m.mediaFile) cached++;
            else pending.push({ chatId, m });
          }
        }
        if (cached) console.log(`[INFO] ${cached} media file(s) already on disk — no download needed`);
        if (!pending.length) return;
        console.log(`[INFO] Auto-downloading media for ${pending.length} message(s) in background…`);
        let count = 0;
        for (const { m } of pending) {
          try {
            const fullMsg = await client.getMessageById(m.id);
            if (fullMsg) {
              const file = await downloadWAMedia(fullMsg, m.id);
              if (file) { m.mediaFile = file; count++; }
            }
          } catch (e) { dbg(`auto-media: error for ${m.id}: ${e.message}`); }
          await new Promise(r => setTimeout(r, 600));
        }
        console.log(`[INFO] Auto-download complete: ${count}/${pending.length} media file(s) downloaded`);
        if (count) saveMsgs();
      })();
    }
  } catch (err) {
    console.warn('[WARN] Could not load recent messages:', err.message);
  }
});

client.on('disconnected', (reason) => {
  status = 'disconnected';
  connectedPhone = null;
  lastError = reason;
  console.log(`[WARN] Disconnected: ${reason}`);
  setTimeout(() => doReconnect(`disconnected event: ${reason}`), 5000);
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
  const isDocument = msg.type === 'document';
  const isPtt = msg.type === 'ptt' || msg.type === 'audio';
  if (!isText && !isImage && !isDocument && !isPtt) { dbg(`Skipping unsupported type: ${msg.type}`); return; }
  if (!msg.body && !isImage && !isDocument && !isPtt) return;
  const chat = await msg.getChat().catch(() => null);
  const chatId = chat ? chat.id._serialized : msg.from;
  if (!chatId || isFilteredChat(chatId)) { dbg(`Skipping filtered chat: ${chatId}`); return; }
  const cachedChat = chatMap.get(chatId);
  if (!chat && !cachedChat) { dbg(`getChat() failed and chat unknown: ${chatId} — skipping`); return; }
  if (!chat) console.warn(`[WARN] getChat() failed for ${chatId} — using cached chat info`);
  const contact = await msg.getContact().catch(() => null);
  const contactName = contact?.name || contact?.pushname || msg.from.replace(/@[cg]\.us$/, '');
  upsertChat(chatId, {
    name: chat?.name || cachedChat?.name || contactName,
    phone: chat?.id.user || cachedChat?.phone || '',
    isGroup: chat?.isGroup ?? cachedChat?.isGroup ?? chatId.endsWith('@g.us'),
  });
  let type = 'text', mediaFile = null, filename = null;
  if (isImage) {
    type = 'photo';
    if (DOWNLOAD_MEDIA) mediaFile = await downloadWAMedia(msg, msg.id._serialized);
  } else if (isDocument) {
    type = 'document';
    filename = msg._data?.filename || msg.filename || 'Dokument';
  } else if (isPtt) {
    type = 'voice';
    mediaFile = await downloadWAMedia(msg, msg.id._serialized);
  }
  let quotedMsgData = null;
  if (msg.hasQuotedMsg) {
    try {
      const q = await msg.getQuotedMessage();
      if (q) quotedMsgData = {
        body: (q.body || '').slice(0, 100),
        type: q.type,
        contact: q.fromMe ? 'Ich' : (q._data?.notifyName || (q.from || '').replace('@c.us', '')),
      };
    } catch(e) { dbg('getQuotedMessage:', e.message); }
  }
  const added = addMsg(chatId, {
    id: msg.id._serialized,
    body: msg.body || '',
    type, mediaFile, filename,
    timestamp: msg.timestamp * 1000,
    fromMe: false,
    contact: contactName,
    isForwarded: !!msg.isForwarded,
    forwardingScore: msg.forwardingScore || 0,
    quotedMsg: quotedMsgData,
  });
  if (added) {
    const _ci = chatMap.get(chatId);
    const isGroup = _ci?.isGroup ?? chatId.endsWith('@g.us');
    const skipGroup = HA_NOTIFY_SKIP_GROUPS && isGroup;
    if (!skipGroup) {
      lastReceivedMsg = {
        timestamp: msg.timestamp * 1000,
        iso: new Date(msg.timestamp * 1000).toISOString(),
        chatId,
        chatName: _ci?.name || chatId,
        contact: contactName,
        type,
        preview: msg.body || (type === 'photo' ? '📷 Foto' : type === 'document' ? `📄 ${filename || 'Dokument'}` : type === 'voice' ? '🎵 Sprachnachricht' : '[Medien]'),
      };
      sendHANotification(chatId, contactName, msg.body || (type === 'photo' ? '📷 Foto' : ''));
    }
  }
  if (process.env.WEBHOOK_INCOMING) {
    dbg(`Firing incoming webhook: ${process.env.WEBHOOK_INCOMING}`);
    postWebhook(process.env.WEBHOOK_INCOMING, { from: msg.from, body: msg.body, type, timestamp: msg.timestamp });
  }
});

client.on('message_create', async (msg) => {
  dbg(`message_create: type=${msg.type} fromMe=${msg.fromMe} from=${msg.from} body="${(msg.body||'').slice(0,60)}"`);
  if (!msg.fromMe) return;
  if (msg.isStatus || isFilteredChat(msg.from || '')) return;
  const isText = msg.type === 'chat' || msg.type === 'text';
  const isImage = msg.type === 'image' || msg.type === 'sticker';
  const isDocument = msg.type === 'document';
  if (!isText && !isImage && !isDocument) { dbg(`message_create: skipping type=${msg.type}`); return; }
  if (msg.__logged) return;
  const chat = await msg.getChat().catch(() => null);
  if (!chat) return;
  const chatId = chat.id._serialized;
  if (isFilteredChat(chatId)) return;
  upsertChat(chatId, { name: chat.name || msg.to.replace('@c.us', ''), phone: chat.id.user, isGroup: chat.isGroup });
  let type = 'text', mediaFile = null, filename = null;
  if (isImage) {
    type = 'photo';
    if (DOWNLOAD_MEDIA) mediaFile = await downloadWAMedia(msg, msg.id._serialized);
  } else if (isDocument) {
    type = 'document';
    filename = msg._data?.filename || msg.filename || 'Dokument';
  }
  let quotedMsgDataOut = null;
  if (msg.hasQuotedMsg) {
    try {
      const q = await msg.getQuotedMessage();
      if (q) quotedMsgDataOut = {
        body: (q.body || '').slice(0, 100),
        type: q.type,
        contact: q.fromMe ? 'Ich' : (q._data?.notifyName || (q.from || '').replace('@c.us', '')),
      };
    } catch(e) { dbg('getQuotedMessage:', e.message); }
  }
  addMsg(chatId, {
    id: msg.id._serialized,
    body: msg.body || '',
    type, mediaFile, filename,
    timestamp: msg.timestamp * 1000,
    fromMe: true,
    contact: 'Ich',
    ack: msg.ack || 1,
    isForwarded: !!msg.isForwarded,
    forwardingScore: msg.forwardingScore || 0,
    quotedMsg: quotedMsgDataOut,
  });
});

client.on('message_reaction', (reaction) => {
  const msgId = reaction.msgId?._serialized;
  if (!msgId) return;
  const senderId = normalizeJid(reaction.senderId?._serialized || String(reaction.senderId || ''));
  if (!senderId) return;
  const emoji = reaction.reaction || '';
  dbg(`message_reaction: msgId=${msgId} sender=${senderId} emoji="${emoji}"`);

  function applyReaction(reactions) {
    for (const e of Object.keys(reactions)) {
      reactions[e] = reactions[e].filter(s => s !== senderId);
      if (!reactions[e].length) delete reactions[e];
    }
    if (emoji) {
      if (!reactions[emoji]) reactions[emoji] = [];
      if (!reactions[emoji].includes(senderId)) reactions[emoji].push(senderId);
    }
  }

  for (const msgs of messagesByChatId.values()) {
    const msg = msgs.find(m => m.id === msgId);
    if (msg) {
      if (!msg.reactions) msg.reactions = {};
      applyReaction(msg.reactions);
      dbg(`message_reaction: reactions[${msgId}] =`, JSON.stringify(msg.reactions));
      reactionsCache.set(msgId, { ...msg.reactions });
      saveReactions();
      break;
    }
  }
});

function markDeleted(msgId) {
  if (!msgId) return false;
  for (const msgs of messagesByChatId.values()) {
    const stored = msgs.find(m => m.id === msgId);
    if (stored && !stored.deleted) {
      stored.deleted = true;
      stored.deletedAt = Date.now();
      if (!KEEP_DELETED) stored.body = ''; // body erhalten wenn KEEP_DELETED=true
      saveMsgs();
      return true;
    }
  }
  return false;
}

client.on('message_revoke_everyone', (msg, revokedMsg) => {
  const idA = revokedMsg?.id?._serialized;
  const idB = msg?.id?._serialized;
  console.log(`[INFO] message_revoke_everyone: msg=${idB} revokedMsg=${idA}`);
  const found = markDeleted(idA) || markDeleted(idB);
  if (!found) console.log(`[WARN] message_revoke_everyone: no stored message matched`);
});

client.on('message_revoke_me', (msg) => {
  const msgId = msg?.id?._serialized;
  console.log(`[INFO] message_revoke_me: msg=${msgId}`);
  const found = markDeleted(msgId);
  if (!found) console.log(`[WARN] message_revoke_me: no stored message matched`);
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
    console.warn('[WARN] HA_NOTIFICATIONS: ha_token not set in add-on configuration');
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
  const myJid = connectedPhone ? normalizeJid(connectedPhone + '@c.us') : null;
  res.json({ status, phone: connectedPhone, myJid, error: lastError });
});

app.get('/api/qr', (req, res) => {
  if (!qrCodeDataUrl) return res.status(404).json({ error: 'No QR code available' });
  res.json({ qr: qrCodeDataUrl });
});

app.get('/api/chats', (req, res) => {
  const list = [...chatMap.values()].sort((a, b) => (b.lastTime || 0) - (a.lastTime || 0));
  res.json(list);
});

app.get('/api/stats', (req, res) => {
  const { chat: chatId } = req.query;
  if (!chatId) return res.json({});
  const msgs = getChatMsgs(chatId);
  const sent = msgs.filter(m => m.fromMe).length;
  const received = msgs.filter(m => !m.fromMe).length;
  const photos = msgs.filter(m => m.type === 'photo').length;
  const first = msgs.length ? Math.min(...msgs.map(m => m.timestamp)) : null;
  res.json({ total: msgs.length, sent, received, photos, first });
});

app.get('/api/messages', (req, res) => {
  const { chat: chatId, since } = req.query;
  if (!chatId) return res.json([]);
  const msgs = getChatMsgs(chatId);
  const since_ts = parseInt(since || '0', 10);
  res.json(since_ts ? msgs.filter(m => m.timestamp > since_ts || (m.deletedAt && m.deletedAt > since_ts)) : msgs);
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

app.post('/api/send-media', upload.single('file'), async (req, res) => {
  const { to, caption } = req.body;
  if (!to || !req.file) return res.status(400).json({ error: 'to and file required' });
  if (status !== 'connected') return res.status(503).json({ error: `Not connected (status: ${status})` });
  try {
    const jid = formatNumber(to);
    const mime = req.file.mimetype;
    const origName = req.file.originalname;
    const data = req.file.buffer.toString('base64');
    const media = new MessageMedia(mime, data, origName);
    const isImg = mime.startsWith('image/');
    const result = await client.sendMessage(jid, media, caption ? { caption } : {});
    result.__logged = true;
    let mediaFile = null;
    if (isImg) {
      const safeId = result.id._serialized.replace(/[^a-zA-Z0-9]/g, '_');
      const ext = mime === 'image/png' ? 'png' : mime === 'image/webp' ? 'webp' : 'jpg';
      const filePath = `${MEDIA_DIR}/${safeId}.${ext}`;
      fs.writeFileSync(filePath, req.file.buffer);
      mediaFile = `${safeId}.${ext}`;
    }
    if (!chatMap.has(jid)) {
      upsertChat(jid, { name: to.replace(/@[cg]\.us$/, ''), phone: to.replace(/@[cg]\.us$/, '') });
    }
    addMsg(jid, {
      id: result.id._serialized,
      body: caption || '',
      type: isImg ? 'photo' : 'document',
      mediaFile,
      filename: isImg ? null : origName,
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

let _reconnecting = false;
let _intentionalDisconnect = false;

async function doReconnect(reason) {
  if (_reconnecting || _intentionalDisconnect) return;
  _reconnecting = true;
  status = 'initializing';
  connectedPhone = null;
  console.warn('[WARN] Auto-reconnect: %s', reason);
  try { await client.destroy(); } catch (e) {}
  ['SingletonLock', 'SingletonCookie', 'SingletonSocket'].forEach(f => {
    try { rmSync(path.join(SESSION_CHROMIUM_DIR, f), { force: true }); } catch(e) {}
  });
  client.initialize().catch(err => {
    lastError = String(err?.message || err);
    status = 'error';
    _reconnecting = false;
    console.error('[ERROR] Auto-reconnect failed:', lastError);
  });
}

// Keep-alive: erkennt hängende Puppeteer-Instanzen alle 10 Minuten
setInterval(async () => {
  if (status !== 'connected' || _reconnecting) return;
  try {
    const state = await client.getState();
    if (state !== 'CONNECTED') {
      console.warn('[WARN] State check: state=%s — reconnecting…', state);
      doReconnect('state check: ' + state);
    }
  } catch (e) {
    console.warn('[WARN] State check failed (%s) — reconnecting…', e.message);
    doReconnect('state check error: ' + e.message);
  }
}, 600000);

async function reinitClient() {
  _intentionalDisconnect = true;
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
  _intentionalDisconnect = true;
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
  const mime = ext === 'webp' ? 'image/webp' : ext === 'png' ? 'image/png' : ext === 'ogg' ? 'audio/ogg' : ext === 'mp3' ? 'audio/mpeg' : 'image/jpeg';
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
  const bytes = getDirSize('/config');
  res.json({ bytes, mb: (bytes / (1024 * 1024)).toFixed(1) });
});

app.post('/api/cleanup-media', (req, res) => {
  try {
    const referenced = new Set();
    for (const msgs of messagesByChatId.values())
      for (const m of msgs)
        if (m.mediaFile) referenced.add(m.mediaFile);
    const files = fs.readdirSync(MEDIA_DIR);
    let count = 0, freed = 0;
    for (const f of files) {
      if (!referenced.has(f)) {
        const fp = `${MEDIA_DIR}/${f}`;
        try { freed += fs.statSync(fp).size; fs.unlinkSync(fp); count++; } catch(e) {}
      }
    }
    res.json({ deleted: count, freedMb: (freed / (1024 * 1024)).toFixed(1) });
  } catch(e) { res.status(500).json({ error: e.message }); }
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
    dbg(`/api/react: sent reaction="${reaction||''}" for msgId=${msgId}`);
    // Eigene Reaktion explizit tracken — kein JID-Vergleich nötig
    if (reaction) { myReactions.set(msgId, reaction); } else { myReactions.delete(msgId); }
    saveReactions();
    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/reactions/:chatId', (req, res) => {
  const msgs = getChatMsgs(req.params.chatId);
  const result = {};
  for (const m of msgs) {
    if (!m.reactions || !Object.keys(m.reactions).length) continue;
    const ownEmoji = myReactions.get(m.id) || null;
    const entry = {};
    for (const [emoji, senders] of Object.entries(m.reactions)) {
      if (!senders.length) continue;
      entry[emoji] = { count: senders.length, own: emoji === ownEmoji };
    }
    if (Object.keys(entry).length) result[m.id] = entry;
  }
  res.json(result);
});


app.get('/api/last-received', (req, res) => {
  const { chat: chatId } = req.query;
  if (chatId) {
    const msgs = getChatMsgs(chatId);
    const received = msgs.filter(m => !m.fromMe && !m.deleted);
    if (!received.length) return res.json(null);
    const last = received[received.length - 1];
    const chat = chatMap.get(chatId);
    return res.json({
      timestamp: last.timestamp,
      iso: new Date(last.timestamp).toISOString(),
      chatId,
      chatName: chat?.name || chatId,
      contact: last.contact || '',
      type: last.type || 'text',
      preview: last.body || (last.type === 'photo' ? '📷 Foto' : last.type === 'document' ? `📄 ${last.filename || 'Dokument'}` : last.type === 'voice' ? '🎵 Sprachnachricht' : '[Medien]'),
    });
  }
  res.json(lastReceivedMsg);
});

app.get('/api/export/:chatId', (req, res) => {
  const chatId = decodeURIComponent(req.params.chatId);
  const chat = chatMap.get(chatId);
  const msgs = messagesByChatId.get(chatId) || [];
  const chatName = chat ? (chat.name || chatId) : chatId;
  const escH = s => String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const exportDate = new Date().toLocaleString('de-DE', { day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit' });
  let lastDate = '';
  const msgsHtml = msgs.map(m => {
    const tsMs = Number(m.timestamp) > 1e12 ? Number(m.timestamp) : Number(m.timestamp) * 1000;
    const d = new Date(tsMs);
    const dateStr = d.toLocaleDateString('de-DE', { weekday:'long', day:'2-digit', month:'long', year:'numeric' });
    const time = d.toLocaleTimeString('de-DE', { hour:'2-digit', minute:'2-digit' });
    let sep = '';
    if (dateStr !== lastDate) { sep = `<div class="day-sep">${escH(dateStr)}</div>`; lastDate = dateStr; }
    let content = '';
    if (m.mediaFile) {
      const fp = `${MEDIA_DIR}/${m.mediaFile}`;
      if (fs.existsSync(fp)) {
        const ext = m.mediaFile.split('.').pop().toLowerCase();
        const mime = ext==='png'?'image/png':ext==='webp'?'image/webp':ext==='gif'?'image/gif':'image/jpeg';
        content = `<img src="data:${mime};base64,${fs.readFileSync(fp).toString('base64')}" style="max-width:280px;max-height:280px;border-radius:6px;display:block;">`;
      } else { content = '📷 Foto'; }
      if (m.body) content += `<div style="margin-top:4px">${escH(m.body)}</div>`;
    } else if (m.type === 'voice') {
      content = m.mediaFile
        ? '<audio controls style="min-width:220px;max-width:300px;width:100%" src="api/media/' + escH(m.mediaFile) + '"></audio>'
        : '<span style="opacity:0.6">🎵 Sprachnachricht</span>';
    } else if (m.type === 'document' && m.filename) {
      content = `<div style="display:flex;align-items:center;gap:8px"><span style="font-size:22px">📄</span><span style="font-weight:500">${escH(m.filename)}</span></div>`;
      if (m.body) content += `<div style="margin-top:4px">${escH(m.body)}</div>`;
    } else {
      content = escH(m.body||'').replace(/\n/g,'<br>');
    }
    const sender = m.fromMe ? 'Du' : escH(chatName);
    return `${sep}<div class="msg ${m.fromMe?'out':'in'}"><div class="bubble"><div class="meta"><span class="sender">${sender}</span><span class="time">${time}</span></div><div class="content">${content}</div></div></div>`;
  }).join('\n');
  const html = `<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Chat: ${escH(chatName)}</title><style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#e5ddd5;min-height:100vh;padding:16px}h1{text-align:center;font-size:18px;color:#333;padding:12px 0 4px}.export-info{text-align:center;font-size:12px;color:#888;margin-bottom:16px}.day-sep{text-align:center;margin:12px 0;font-size:12px;color:#666;background:rgba(255,255,255,.6);border-radius:8px;display:inline-block;padding:2px 10px;width:100%}.msg{display:flex;margin:3px 0}.msg.in{justify-content:flex-start}.msg.out{justify-content:flex-end}.bubble{max-width:70%;padding:7px 10px;border-radius:8px;font-size:14px;line-height:1.45;word-break:break-word}.msg.in .bubble{background:#fff;border-bottom-left-radius:2px}.msg.out .bubble{background:#d9fdd3;border-bottom-right-radius:2px}.meta{display:flex;justify-content:space-between;gap:8px;margin-bottom:3px;font-size:12px}.sender{font-weight:600;color:#25D366}.msg.out .sender{color:#128c7e}.time{color:#999;flex-shrink:0}@media print{body{background:#fff}.msg.out .bubble{background:#e8f5e9}}</style></head><body><h1>${escH(chatName)}</h1><p class="export-info">Exportiert am ${exportDate} &bull; ${msgs.length} Nachrichten</p>${msgsHtml}</body></html>`;
  const fname = `whatsapp_${chatName.replace(/[^a-zA-Z0-9_-]/g,'_').slice(0,40)}_${new Date().toISOString().slice(0,10)}.html`;
  res.setHeader('Content-Type','text/html; charset=utf-8');
  res.setHeader('Content-Disposition',`attachment; filename="${fname}"`);
  res.send(html);
});

app.delete('/api/messages/:chatId/:msgId', async (req, res) => {
  const { chatId, msgId } = req.params;
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  try {
    dbg(`Deleting message ${msgId} in chat ${chatId}`);
    const msg = await client.getMessageById(msgId).catch(() => null);
    if (msg) await msg.delete(true).catch(e => console.log(`[WARN] delete(true) failed: ${e.message}`));
    const msgs = messagesByChatId.get(chatId);
    if (msgs) {
      const stored = msgs.find(m => m.id === msgId);
      if (stored) { stored.deleted = true; stored.body = ''; saveMsgs(); }
    }
    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/reply', async (req, res) => {
  const { quotedMsgId, chatId, message } = req.body;
  if (!quotedMsgId || !chatId || !message) return res.status(400).json({ error: 'quotedMsgId, chatId and message required' });
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  try {
    const qMsg = await client.getMessageById(quotedMsgId);
    if (!qMsg) throw new Error('Quoted message not found');
    const result = await qMsg.reply(message);
    result.__logged = true;
    addMsg(chatId, {
      id: result.id._serialized,
      body: message,
      timestamp: Date.now(),
      fromMe: true,
      contact: 'Ich',
      ack: 1,
    });
    res.json({ success: true, id: result.id._serialized });
  } catch(e) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/forward', async (req, res) => {
  const { msgId, to } = req.body;
  if (!msgId || !to) return res.status(400).json({ error: 'msgId and to required' });
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  try {
    const msg = await client.getMessageById(msgId);
    if (!msg) return res.status(404).json({ error: 'Message not found' });
    const chat = await client.getChatById(to);
    await msg.forward(chat);
    res.json({ success: true });
  } catch(e) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/delete-batch/:chatId', async (req, res) => {
  const { chatId } = req.params;
  const { ids } = req.body;
  if (!Array.isArray(ids) || !ids.length) return res.json({ deleted: 0, failed: 0 });
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  let deleted = 0, failed = 0;
  for (const msgId of ids) {
    try {
      const msg = await client.getMessageById(msgId);
      if (msg) await msg.delete(true);
      const list = messagesByChatId.get(chatId);
      if (list) {
        const idx = list.findIndex(m => m.id === msgId);
        if (idx !== -1) { list.splice(idx, 1); seenIds.delete(msgId); }
      }
      deleted++;
    } catch(e) {
      dbg(`delete-batch: failed for ${msgId}: ${e.message}`);
      failed++;
    }
  }
  // Vorschautext in der Chat-Liste aktualisieren
  const remaining = messagesByChatId.get(chatId) || [];
  const chat = chatMap.get(chatId);
  if (chat) {
    if (remaining.length) {
      const last = remaining[remaining.length - 1];
      const preview = last.body || (last.type === 'photo' ? '📷 Foto' : '[Medien]');
      chat.lastMsg = preview.length > 60 ? preview.slice(0, 60) + '…' : preview;
      chat.lastTime = last.timestamp;
    } else {
      chat.lastMsg = '';
    }
  }
  console.log(`[INFO] Spam-Löschung: ${deleted}/${ids.length} gelöscht in Chat ${chatId}`);
  res.json({ deleted, failed });
});

// ── Avatar + Kontaktinfo ──────────────────────────────────────────────────────

const avatarCache = new Map();    // chatId → { buf: Buffer, ts: number }
const avatarPending = new Map();  // chatId → Promise (dedup parallel requests)

app.get('/api/avatar/:chatId', async (req, res) => {
  const chatId = req.params.chatId;
  const cached = avatarCache.get(chatId);
  if (cached !== undefined && Date.now() - cached.ts < 3600000) {
    if (!cached.buf) return res.status(404).end(); // cached "no pic"
    res.setHeader('Content-Type', 'image/jpeg');
    res.setHeader('Cache-Control', 'public, max-age=3600');
    return res.send(cached.buf);
  }
  if (status !== 'connected') return res.status(503).end();

  // Dedup: if another request for this chatId is already in-flight, wait for it
  if (avatarPending.has(chatId)) {
    try {
      const buf = await avatarPending.get(chatId);
      res.setHeader('Content-Type', 'image/jpeg');
      res.setHeader('Cache-Control', 'public, max-age=3600');
      return res.send(buf);
    } catch { return res.status(404).end(); }
  }

  const promise = (async () => {
    const contact = await client.getContactById(chatId);
    const picUrl = await contact.getProfilePicUrl();
    if (!picUrl) throw new Error('no pic');
    const r = await fetch(picUrl);
    if (!r.ok) throw new Error('fetch failed');
    const buf = Buffer.from(await r.arrayBuffer());
    avatarCache.set(chatId, { buf, ts: Date.now() });
    return buf;
  })();

  avatarPending.set(chatId, promise);
  promise.finally(() => avatarPending.delete(chatId));

  try {
    const buf = await promise;
    res.setHeader('Content-Type', 'image/jpeg');
    res.setHeader('Cache-Control', 'public, max-age=3600');
    res.send(buf);
  } catch(e) {
    avatarCache.set(chatId, { buf: null, ts: Date.now() }); // Mark as no-pic so we don't retry immediately
    res.status(404).end();
  }
});

app.get('/api/contact/:chatId', async (req, res) => {
  const chatId = req.params.chatId;
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  try {
    const contact = await client.getContactById(chatId);
    const picUrl = await contact.getProfilePicUrl().catch(() => null);
    const about = await contact.getAbout().catch(() => null);
    const rawId = contact.id?.user || chatId.split('@')[0];
    const number = /^\d{6,15}$/.test(rawId) ? rawId : '';
    const savedName = contact.name || contact.shortName || '';
    const waName = contact.pushname || '';
    res.json({
      id: chatId,
      name: savedName || waName || rawId,
      savedName,
      waName,
      number,
      about: about || '',
      isMyContact: contact.isMyContact || false,
      hasProfilePic: !!picUrl,
    });
  } catch(e) {
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
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>WhatsApp</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #111b21; color: #e9edef;
      height: var(--app-height, 100dvh); display: flex; flex-direction: column; overflow: hidden;
    }

    /* Top bar */
    .topbar {
      background: #202c33; padding: 10px 16px;
      display: flex; align-items: center; gap: 12px;
      border-bottom: 1px solid #2a3942; flex-shrink: 0; height: 56px;
    }
    .topbar h1 { font-size: 16px; font-weight: 600; flex: 1; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .status-dot.connected { background: #3cdb7c; }
    .status-dot.waiting   { background: #f0a500; }
    .status-dot.error, .status-dot.disconnected { background: #f15c5c; }
    .status-dot.initializing { background: #8696a0; }
    .storage-info { font-size: 12px; color: #8696a0; white-space: nowrap; }
    .logout-btn, #topbar-back {
      background: none; border: none; color: #8696a0;
      cursor: pointer; padding: 6px; line-height: 1;
      display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
    }
    .logout-btn:hover { color: #f15c5c; }
    #topbar-back { display: none; }
    #topbar-back:hover { color: #e9edef; }
    .photo-toggle-btn {
      background: none; border: 1px solid #8696a0; color: #e9edef;
      padding: 4px 8px; border-radius: 6px; cursor: pointer; font-size: 16px; opacity: 0.55; line-height: 1;
    }
    .photo-toggle-btn:hover { opacity: 0.8; }
    .photo-toggle-btn.active { opacity: 1; background: rgba(60,219,124,0.15); border-color: #3cdb7c; color: #3cdb7c; }
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
    #chat-filter { display:flex; background:#202c33; border-bottom:1px solid #2a3942; padding:4px 8px; gap:4px; flex-shrink:0; }
    .filter-tab { flex:1; background:none; border:none; border-radius:16px; padding:5px 6px; font-size:12px; color:#8696a0; cursor:pointer; transition:background 0.12s,color 0.12s; white-space:nowrap; }
    .filter-tab:hover { background:rgba(134,150,160,0.15); color:#e9edef; }
    .filter-tab.active { background:#2a3942; color:#e9edef; font-weight:500; }
    html.light #chat-filter { background:#f0f2f5; border-color:#e0e0e0; }
    html.light .filter-tab { color:#999; }
    html.light .filter-tab:hover { background:rgba(0,0,0,0.06); color:#111; }
    html.light .filter-tab.active { background:#e0e0e0; color:#111; }
    .avatar.group-avatar { background:#25D366 !important; font-size:22px; }
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
      position: relative; overflow: hidden;
    }
    .avatar img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; border-radius: 50%; display: block; }
    #contact-modal { display: none; position: fixed; inset: 0; z-index: 450; background: rgba(0,0,0,0.65); align-items: center; justify-content: center; }
    #contact-modal.open { display: flex; }
    .contact-modal-box { border-radius: 16px; padding: 28px 24px 20px; max-width: 320px; width: 90%; display: flex; flex-direction: column; align-items: center; gap: 10px; box-shadow: 0 8px 32px rgba(0,0,0,0.5); }
    html.dark .contact-modal-box { background: #202c33; }
    html.light .contact-modal-box { background: #fff; }
    .contact-modal-pic { width: 96px; height: 96px; border-radius: 50%; overflow: hidden; display: flex; align-items: center; justify-content: center; font-size: 36px; font-weight: 700; color: #fff; flex-shrink: 0; margin-bottom: 4px; }
    .contact-modal-pic img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .contact-modal-name { font-size: 18px; font-weight: 600; text-align: center; }
    html.dark .contact-modal-name { color: #e9edef; }
    html.light .contact-modal-name { color: #111; }
    .contact-modal-pushname { font-size: 13px; color: #8696a0; }
    .contact-modal-number { font-size: 14px; color: #00a884; font-weight: 500; }
    .contact-modal-about { font-size: 13px; color: #8696a0; text-align: center; max-width: 260px; word-break: break-word; }
    .contact-modal-close { margin-top: 10px; border: none; border-radius: 8px; padding: 8px 28px; font-size: 14px; cursor: pointer; }
    html.dark .contact-modal-close { background: #2a3942; color: #e9edef; }
    html.light .contact-modal-close { background: #f0f2f5; color: #111; }
    .contact-modal-close:hover { opacity: 0.8; }
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
    .unread-dot { width: 10px; height: 10px; background: #3cdb7c; border-radius: 50%; }
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
    #ch-info { flex: 1; min-width: 0; }
    #ch-name { font-size: 15px; font-weight: 600; }
    #ch-phone { font-size: 12px; color: #8696a0; }
    #ch-stats { font-size: 11px; color: #8696a0; margin-top: 2px; white-space: nowrap; }
    #export-btn, #spam-delete-btn { background: none; border: 1px solid rgba(134,150,160,0.5); color: #8696a0; padding: 5px 8px; border-radius: 6px; cursor: pointer; font-size: 15px; flex-shrink: 0; line-height: 1; }
    #export-btn { margin-left: auto; }
    #export-btn:hover { border-color: #3cdb7c; color: #3cdb7c; }
    #spam-delete-btn:hover { border-color: #f15c5c; color: #f15c5c; }
    #spam-delete-btn:disabled { opacity: 0.4; cursor: default; }
    #spam-modal, #logout-modal { display:none; position:fixed; inset:0; z-index:400; background:rgba(0,0,0,0.6); align-items:center; justify-content:center; }
    #spam-modal.open, #logout-modal.open { display:flex; }
    .spam-modal-box { background:#202c33; border-radius:12px; padding:24px; max-width:360px; width:90%; box-shadow:0 8px 32px rgba(0,0,0,0.5); }
    .spam-modal-box p { color:#e9edef; font-size:14px; line-height:1.6; margin-bottom:20px; }
    .spam-modal-actions { display:flex; justify-content:flex-end; gap:10px; }
    .spam-modal-actions button { padding:8px 18px; border-radius:8px; border:none; font-size:14px; cursor:pointer; }
    .spam-modal-cancel { background:#2a3942; color:#e9edef; }
    .spam-modal-cancel:hover { background:#3d5259; }
    .spam-modal-confirm { background:#f15c5c; color:#fff; }
    .spam-modal-confirm:hover { background:#d94444; }
    .reply-btn { display:none; background:none; border:none; cursor:pointer; font-size:15px; padding:4px 6px; line-height:1; border-radius:6px; flex-shrink:0; color:rgba(233,237,239,0.6); }
    .bubble-row-inner:hover .reply-btn { display:block; }
    html.light .reply-btn { color:rgba(0,0,0,0.4); }
    .reply-btn:hover { color:#3cdb7c !important; }
    .quoted-block { border-left:3px solid #3cdb7c; background:rgba(0,0,0,0.25); border-radius:4px; padding:4px 8px; margin-bottom:6px; overflow:hidden; }
    .bubble-wrap.out .quoted-block { border-left-color:rgba(255,255,255,0.4); background:rgba(0,0,0,0.2); }
    .quoted-sender { font-size:11px; font-weight:600; color:#3cdb7c; margin-bottom:1px; }
    .bubble-wrap.out .quoted-sender { color:rgba(255,255,255,0.85); }
    .quoted-text { font-size:12px; color:rgba(233,237,239,0.88); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    html.light .quoted-text { color:rgba(0,0,0,0.65); }
    html.light .quoted-block { background:rgba(0,0,0,0.08); }
    #reply-bar { display:none; background:#1a2530; border-left:3px solid #3cdb7c; border-top:1px solid #2a3942; padding:6px 16px; align-items:center; gap:10px; flex-shrink:0; }
    #reply-bar.active { display:flex; }
    #attach-bar { display:none; background:#1a2530; border-top:1px solid #2a3942; padding:8px 16px; align-items:center; gap:10px; flex-shrink:0; }
    #attach-bar.active { display:flex; }
    .attach-preview { display:flex; align-items:center; gap:10px; flex:1; min-width:0; overflow:hidden; }
    #attach-thumb { width:48px; height:48px; object-fit:cover; border-radius:6px; flex-shrink:0; display:none; }
    .attach-info { flex:1; min-width:0; }
    #attach-name { font-size:13px; color:#e9edef; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:block; }
    #attach-size { font-size:11px; color:#8696a0; }
    #attach-icon { font-size:28px; flex-shrink:0; }
    #attach-cancel { background:none; border:none; color:#8696a0; cursor:pointer; font-size:16px; line-height:1; padding:4px; flex-shrink:0; }
    #attach-cancel:hover { color:#e9edef; }
    #send-bar #attach-btn { background:none; border:none; font-size:20px; cursor:pointer; padding:6px; border-radius:50%; flex-shrink:0; line-height:1; color:#8696a0; width:auto; height:auto; }
    #send-bar #attach-btn:hover { background:rgba(255,255,255,0.08); }
    .bubble-deleted { font-style:italic; color:rgba(233,237,239,0.75); font-size:13px; padding:2px 0; }
    .bubble-deleted .del-icon { margin-right:5px; opacity:0.9; }
    html.light .bubble-deleted { color:rgba(0,0,0,0.55); }
    .deleted-notice { display:block; font-size:11px; font-style:italic; color:rgba(233,237,239,0.6); margin-top:5px; padding-top:4px; border-top:1px solid rgba(233,237,239,0.12); }
    html.light .deleted-notice { color:rgba(0,0,0,0.45); border-top-color:rgba(0,0,0,0.1); }
    .bubble-document { display:flex; align-items:center; gap:10px; padding:6px 10px 8px; }
    .bubble-document .doc-icon { font-size:26px; flex-shrink:0; }
    .bubble-document .doc-info { flex:1; min-width:0; }
    .bubble-document .doc-name { font-size:13px; font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:block; }
    .bubble-document .doc-caption { font-size:12px; color:rgba(233,237,239,0.7); margin-top:2px; }
    .reply-bar-content { flex:1; overflow:hidden; }
    #reply-bar-sender { font-size:11px; font-weight:600; color:#3cdb7c; }
    #reply-bar-text { font-size:12px; color:#8696a0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    #reply-close { background:none; border:none; color:#8696a0; cursor:pointer; font-size:16px; line-height:1; padding:4px; flex-shrink:0; }
    #reply-close:hover { color:#e9edef; }

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
    .bubble-row-inner { display: flex; align-items: center; gap: 6px; width: 100%; }
    .bubble-wrap.out .bubble-row-inner { justify-content: flex-end; }
    .bubble-wrap.out .del-btn,
    .bubble-wrap.in  .del-btn { order: -1; }
    .del-btn { display: none; background: none; border: none; cursor: pointer; font-size: 15px; padding: 4px 6px; line-height: 1; border-radius: 6px; flex-shrink: 0; color: rgba(233,237,239,0.6); }
    .bubble-row-inner:hover .del-btn { display: block; }
    html.light .del-btn { color: rgba(0,0,0,0.4); }
    .del-btn:hover { color: #f15c5c !important; }
    .react-btn { display: none; background: none; border: none; cursor: pointer; font-size: 16px; padding: 4px; line-height: 1; border-radius: 50%; color: rgba(233,237,239,0.55); flex-shrink: 0; }
    .bubble-row-inner:hover .react-btn { display: inline-flex; align-items: center; }
    html.light .react-btn { color: rgba(0,0,0,0.35); }
    .react-btn:hover { background: rgba(134,150,160,0.18); color: #e9edef; }
    html.light .react-btn:hover { color: #111; }
    .fwd-btn { display: none; background: none; border: none; cursor: pointer; font-size: 15px; padding: 4px 6px; line-height: 1; border-radius: 6px; flex-shrink: 0; color: rgba(233,237,239,0.6); }
    .bubble-row-inner:hover .fwd-btn { display: block; }
    html.light .fwd-btn { color: rgba(0,0,0,0.4); }
    .fwd-btn:hover { color: #3cdb7c !important; }
    #fwd-modal { display:none; position:fixed; inset:0; z-index:400; background:rgba(0,0,0,0.6); align-items:center; justify-content:center; }
    #fwd-modal.open { display:flex; }
    .fwd-modal-box { background:#202c33; border-radius:12px; padding:20px; max-width:400px; width:92%; max-height:70vh; display:flex; flex-direction:column; box-shadow:0 8px 32px rgba(0,0,0,0.5); }
    .fwd-modal-box h3 { font-size:15px; font-weight:600; margin-bottom:12px; color:#e9edef; }
    #fwd-search { width:100%; background:#2a3942; border:none; border-radius:8px; padding:8px 12px; color:#e9edef; font-size:14px; outline:none; margin-bottom:10px; }
    #fwd-search::placeholder { color:#8696a0; }
    #fwd-chat-list { flex:1; overflow-y:auto; }
    .fwd-chat-item { display:flex; align-items:center; gap:10px; padding:8px 12px; cursor:pointer; border-radius:8px; }
    .fwd-chat-item:hover { background:#2a3942; }
    .fwd-modal-cancel { margin-top:12px; background:#2a3942; color:#e9edef; border:none; border-radius:8px; padding:8px 18px; font-size:14px; cursor:pointer; width:100%; }
    .fwd-modal-cancel:hover { background:#3d5259; }
    #lightbox { display: none; position: fixed; inset: 0; z-index: 500; background: rgba(0,0,0,0.88); cursor: zoom-out; align-items: center; justify-content: center; }
    #lightbox.open { display: flex; }
    #lightbox img { max-width: 92vw; max-height: 92vh; object-fit: contain; border-radius: 4px; box-shadow: 0 4px 32px rgba(0,0,0,0.6); cursor: default; }
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
    .reaction-badge.own { border-color: #3cdb7c; }
    html.dark .reaction-badge.own { background: rgba(60,219,124,0.12); }
    html.light .reaction-badge.own { background: rgba(60,219,124,0.1); }
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
    .forwarded-label { font-size: 11px; font-style: italic; display: block; margin-bottom: 3px; color: #8696a0; }
    .forwarded-label.frequent { color: #f15c5c; font-weight: 500; }

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
      background: #3cdb7c; border: none; border-radius: 50%;
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
      #back-btn { display: none !important; }
      body.chat-open #sidebar { display: none; }
      body.chat-open #chat-panel { display: flex; }
      #lang-btn { display: none !important; }
      .topbar { gap: 6px; }
      #ch-stats { white-space: normal; font-size: 10px; }
      body.chat-open .topbar h1 { display: none; }
      body.chat-open .topbar .status-dot { display: none; }
      body.chat-open #topbar-back { display: inline-flex; margin-right: auto; }
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
    html.light #ch-stats { color: rgba(255,255,255,0.65); }
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
    <p id="spinner-text" data-i18n="spinnerConnecting">Verbinde mit WhatsApp…</p>
    <button onclick="resetSession()" data-i18n="btnReset" style="
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
    <button id="topbar-back" onclick="closeChat()" data-i18n-title="btnBack" title="Zurück"><svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><polyline points="15 18 9 12 15 6"/></svg></button>
    <h1>WhatsApp</h1>
    <div class="status-dot connected" id="status-dot" data-i18n-title="statusConnected" title="Verbunden"></div>
    <span class="storage-info" id="storage-info"></span>
    ${DOWNLOAD_MEDIA ? '<button id="photo-toggle" class="photo-toggle-btn active" onclick="togglePhotos()" data-i18n-title="photosOn" title="Fotos AN">📷</button>' : ''}
    ${DOWNLOAD_MEDIA ? '<button class="scroll-btn" onclick="cleanupMedia()" data-i18n-title="btnCleanup" title="Verwaiste Mediendateien löschen">🗑️</button>' : ''}
    <button class="scroll-btn" onclick="scrollMsgs('top')" data-i18n-title="btnScrollUp" title="Nach oben">↑</button>
    <button class="scroll-btn" onclick="scrollMsgs('bottom')" data-i18n-title="btnScrollDown" title="Nach unten">↓</button>
    <button id="lang-btn" class="scroll-btn" onclick="switchLang()" title="Sprache / Language" style="font-size:14px;padding:0 6px;">🌐 DE</button>
    <button class="logout-btn" data-i18n-title="btnLogout" title="Abmelden" onclick="confirmLogout()"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg></button>
  </div>

  <div id="main" style="display:none;">

    <div id="sidebar">
      <div id="sidebar-header">
        <input type="text" id="search" data-i18n-pl="searchChats" placeholder="🔍  Chats durchsuchen…" oninput="filterChats()">
      </div>
      <div id="chat-filter">
        <button class="filter-tab active" data-filter="all" onclick="setFilter('all')" data-i18n="filterAll">Alle</button>
        <button class="filter-tab" data-filter="private" onclick="setFilter('private')" data-i18n="filterPrivate">Privat</button>
        <button class="filter-tab" data-filter="groups" onclick="setFilter('groups')" data-i18n="filterGroups">Gruppen</button>
      </div>
      <div id="chat-list"><div class="no-chats" data-i18n="loadingChats">Lade Chats…</div></div>
    </div>

    <div id="chat-panel">
      <div id="welcome">
        <div class="icon">💬</div>
        <p data-i18n="welcomeMsg">Wähle einen Chat aus der Liste</p>
      </div>
      <div id="chat-header" style="display:none;">
        <button id="back-btn" onclick="closeChat()" data-i18n-title="btnBack" title="Zurück">&#8592;</button>
        <div class="avatar" id="ch-avatar"></div>
        <div id="ch-info">
          <div id="ch-name"></div>
          <div id="ch-phone"></div>
          <div id="ch-stats"></div>
        </div>
        <button id="export-btn" onclick="exportChat()" data-i18n-title="ttExport" title="Chat exportieren">💾</button>
        <button id="spam-delete-btn" onclick="deleteSpam()" data-i18n-title="ttSpamDelete" title="Häufig weitergeleitete Nachrichten löschen">🗑️</button>
      </div>
      <div id="messages" style="display:none;"></div>
      <div id="reply-bar">
        <div class="reply-bar-content">
          <div id="reply-bar-sender"></div>
          <div id="reply-bar-text"></div>
        </div>
        <button id="reply-close" onclick="clearReply()">✕</button>
      </div>
      <div id="attach-bar">
        <div class="attach-preview">
          <img id="attach-thumb" alt="">
          <span id="attach-icon">📄</span>
          <div class="attach-info">
            <span id="attach-name"></span>
            <span id="attach-size"></span>
          </div>
        </div>
        <button id="attach-cancel" onclick="clearAttach()">✕</button>
      </div>
      <div id="send-bar" style="display:none;">
        <input type="file" id="file-input" style="display:none;" onchange="onFileSelected(event)">
        <div id="emoji-picker"><div class="emoji-grid" id="emoji-grid"></div></div>
        <button id="emoji-toggle" onclick="toggleEmojiPicker(event)" data-i18n-title="btnEmoji" title="Emoji">😊</button>
        <button id="attach-btn" onclick="document.getElementById('file-input').click()" data-i18n-title="btnAttach" title="Datei anhängen">📎</button>
        <textarea id="msg-input" rows="1" data-i18n-pl="msgInput" placeholder="Nachricht…"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMsg();}"
          oninput="autoResize(this)"></textarea>
        <button onclick="sendMsg()" data-i18n-title="btnSend" title="Senden">➤</button>
      </div>
    </div>

  </div>

  <div id="contact-modal" onclick="if(event.target===this)closeContactModal()">
    <div class="contact-modal-box">
      <div class="contact-modal-pic" id="contact-modal-pic"></div>
      <div class="contact-modal-name" id="contact-modal-name">…</div>
      <div class="contact-modal-pushname" id="contact-modal-pushname"></div>
      <div class="contact-modal-number" id="contact-modal-number"></div>
      <div class="contact-modal-about" id="contact-modal-about"></div>
      <button class="contact-modal-close" onclick="closeContactModal()">Schließen</button>
    </div>
  </div>

  <div id="fwd-modal">
    <div class="fwd-modal-box">
      <h3 data-i18n="fwdTitle">↪ Weiterleiten an…</h3>
      <input type="text" id="fwd-search" data-i18n-pl="searchForward" placeholder="🔍 Chat suchen…" oninput="filterFwdChats()">
      <div id="fwd-chat-list"></div>
      <button class="fwd-modal-cancel" data-i18n="btnCancel" onclick="closeFwdModal()">Abbrechen</button>
    </div>
  </div>

  <div id="spam-modal">
    <div class="spam-modal-box">
      <p id="spam-modal-text"></p>
      <div class="spam-modal-actions">
        <button class="spam-modal-cancel" data-i18n="btnCancel" onclick="closeSpamModal()">Abbrechen</button>
        <button class="spam-modal-confirm" data-i18n="btnDeleteYes" onclick="confirmDeleteSpam()">Ja, löschen</button>
      </div>
    </div>
  </div>
  <div id="logout-modal">
    <div class="spam-modal-box">
      <p data-i18n="logoutConfirmMsg">Möchtest du dich wirklich abmelden?</p>
      <div class="spam-modal-actions">
        <button class="spam-modal-cancel" data-i18n="btnNo" onclick="closeLogoutModal()">Nein</button>
        <button class="spam-modal-confirm" data-i18n="btnYes" onclick="logout()">Ja</button>
      </div>
    </div>
  </div>

  <script>
    // Fix für Android WebViews: setzt --app-height auf die tatsächlich sichtbare Höhe
    // (visualViewport.height exkludiert Navigationsleiste und Tastatur)
    (function() {
      function setAppHeight() {
        var h = window.visualViewport ? window.visualViewport.height : window.innerHeight;
        document.documentElement.style.setProperty('--app-height', h + 'px');
      }
      if (window.visualViewport) window.visualViewport.addEventListener('resize', setAppHeight);
      window.addEventListener('resize', setAppHeight);
      setAppHeight();
    })();

    // ── i18n ────────────────────────────────────────────────────────────────────
    const LANG = {
      de: {
        spinnerConnecting:'Verbinde mit WhatsApp…', btnReset:'Session zurücksetzen',
        statusConnected:'Verbunden', statusQR:'QR scannen', statusAuth:'Authentifiziert…',
        statusInit:'Starte…', statusDisc:'Getrennt', statusAuthFail:'Auth-Fehler', statusError:'Fehler',
        photosOn:'Fotos AN', photosOff:'Fotos AUS', btnCleanup:'Verwaiste Mediendateien löschen',
        btnScrollUp:'Nach oben', btnScrollDown:'Nach unten', btnLogout:'Abmelden',
        filterAll:'Alle', filterPrivate:'Privat', filterGroups:'Gruppen',
        searchChats:'🔍  Chats durchsuchen…', loadingChats:'Lade Chats…',
        welcomeMsg:'Wähle einen Chat aus der Liste', noChats:'Keine Chats',
        btnBack:'Zurück',
        ttExport:'Chat als HTML exportieren', ttSpamDelete:'Häufig weitergeleitete Nachrichten löschen', btnSpamDelete:'🗑️ Spam löschen',
        btnEmoji:'Emoji', btnAttach:'Datei anhängen', msgInput:'Nachricht…', attachCaption:'Bildunterschrift (optional)…', btnSend:'Senden',
        fwdTitle:'↪ Weiterleiten an…', searchForward:'🔍 Chat suchen…',
        btnCancel:'Abbrechen', btnDeleteYes:'Ja, löschen',
        logoutConfirmMsg:'Möchtest du dich wirklich abmelden?', btnYes:'Ja', btnNo:'Nein',
        today:'Heute', yesterday:'Gestern',
        photo:'📷 Foto', voiceMsg:'🎵 Sprachnachricht', mediaGeneric:'📎', media:'[Medien]', me:'Ich',
        forwarded:'↪ Weitergeleitet', frequentForwarded:'↪↪ Häufig weitergeleitet',
        msgDeleted:'Diese Nachricht wurde gelöscht',
        msgDeletedNotice:'🚫 Nachricht gelöscht',
        ttDelete:'Löschen', ttReact:'Reagieren', ttForward:'Weiterleiten', ttReply:'Antworten',
        ttRemoveReaction:'Klicken zum Entfernen', ttAddReaction:'Klicken zum Reagieren',
        cleanupConfirm:'Verwaiste Mediendateien löschen (nicht mehr referenzierte Fotos)?',
        cleanupDone:(d,m)=>d+' Datei(en) gelöscht, '+m+' MB freigegeben.',
        cleanupError:(e)=>'Fehler beim Cleanup: '+e,
        spamModal:(n)=>'In diesem Chat wurden '+n+' Nachricht'+(n===1?'':'en')+' häufig weitergeleitet. Soll ich diese jetzt löschen?',
        spinnerRestart:'Starte neu…', spinnerLogout:'Abgemeldet — lade QR-Code…',
        spinnerReset:'Session gelöscht — lade QR-Code…', spinnerDisconnect:'Abgemeldet — starte neu…',
        spamDeleting:'⏳ Lösche…', spamDeleted:(n)=>'✓ '+n+' gelöscht',
        spamError:'✗ Fehler', spamNone:'✓ Kein Spam',
        errSend:(e)=>'Fehler: '+e, errNetwork:'Netzwerkfehler', locale:'de-DE',
        statsMsg:'Nachrichten', statsSince:'seit',
      },
      en: {
        spinnerConnecting:'Connecting to WhatsApp…', btnReset:'Reset Session',
        statusConnected:'Connected', statusQR:'Scan QR', statusAuth:'Authenticating…',
        statusInit:'Starting…', statusDisc:'Disconnected', statusAuthFail:'Auth error', statusError:'Error',
        photosOn:'Photos ON', photosOff:'Photos OFF', btnCleanup:'Delete orphaned media files',
        btnScrollUp:'Scroll up', btnScrollDown:'Scroll down', btnLogout:'Logout',
        filterAll:'All', filterPrivate:'Private', filterGroups:'Groups',
        searchChats:'🔍  Search chats…', loadingChats:'Loading chats…',
        welcomeMsg:'Select a chat from the list', noChats:'No chats',
        btnBack:'Back',
        ttExport:'Export chat as HTML', ttSpamDelete:'Delete frequently forwarded messages', btnSpamDelete:'🗑️ Delete Spam',
        btnEmoji:'Emoji', btnAttach:'Attach file', msgInput:'Message…', attachCaption:'Caption (optional)…', btnSend:'Send',
        fwdTitle:'↪ Forward to…', searchForward:'🔍 Search chat…',
        btnCancel:'Cancel', btnDeleteYes:'Yes, delete',
        logoutConfirmMsg:'Do you really want to log out?', btnYes:'Yes', btnNo:'No',
        today:'Today', yesterday:'Yesterday',
        photo:'📷 Photo', voiceMsg:'🎵 Voice message', mediaGeneric:'📎', media:'[Media]', me:'Me',
        forwarded:'↪ Forwarded', frequentForwarded:'↪↪ Frequently forwarded',
        msgDeleted:'This message was deleted',
        msgDeletedNotice:'🚫 Message deleted',
        ttDelete:'Delete', ttReact:'React', ttForward:'Forward', ttReply:'Reply',
        ttRemoveReaction:'Click to remove', ttAddReaction:'Click to react',
        cleanupConfirm:'Delete orphaned media files (photos no longer referenced)?',
        cleanupDone:(d,m)=>d+' file(s) deleted, '+m+' MB freed.',
        cleanupError:(e)=>'Cleanup error: '+e,
        spamModal:(n)=>n+' message'+(n===1?'':'s')+' in this chat '+(n===1?'was':'were')+' frequently forwarded. Delete '+(n===1?'it':'them')+' now?',
        spinnerRestart:'Restarting…', spinnerLogout:'Logged out — loading QR code…',
        spinnerReset:'Session deleted — loading QR code…', spinnerDisconnect:'Disconnected — restarting…',
        spamDeleting:'⏳ Deleting…', spamDeleted:(n)=>'✓ '+n+' deleted',
        spamError:'✗ Error', spamNone:'✓ No spam',
        errSend:(e)=>'Error: '+e, errNetwork:'Network error', locale:'en-US',
        statsMsg:'messages', statsSince:'since',
      },
    };
    const _browserLang = (navigator.language || '').toLowerCase().startsWith('de') ? 'de' : 'en';
    let lang = localStorage.getItem('wa_lang') || _browserLang;
    function t(key) { const v = LANG[lang][key]; return (typeof v === 'function' || v === undefined) ? (LANG.de[key] || key) : v; }
    function tf(key, ...args) { const v = LANG[lang][key]; return typeof v === 'function' ? v(...args) : (LANG.de[key] ? LANG.de[key](...args) : key); }
    function applyLang() {
      document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
      document.querySelectorAll('[data-i18n-pl]').forEach(el => { el.placeholder = t(el.dataset.i18nPl); });
      document.querySelectorAll('[data-i18n-title]').forEach(el => { el.title = t(el.dataset.i18nTitle); });
      const lb = document.getElementById('lang-btn');
      if (lb) lb.textContent = lang === 'de' ? '🌐 DE' : '🌐 EN';
      const ptb = document.getElementById('photo-toggle');
      if (ptb) ptb.title = document.body.classList.contains('hide-photos') ? t('photosOff') : t('photosOn');
    }
    function switchLang() {
      lang = lang === 'de' ? 'en' : 'de';
      localStorage.setItem('wa_lang', lang);
      applyLang();
    }
    // ── Avatar-System: nachgelagert, max 2 parallel ──────────────────────────────
    const _avatarState = new Map(); // chatId → 'loading'|'loaded'|'failed'
    const _avatarUrl   = new Map(); // chatId → resolved img.src (absolute URL)
    const _avatarQueue = [];
    let   _avatarActive = 0;
    const AVATAR_CONCURRENCY = 2;

    function applyAvatar(avEl, chatId) {
      const src = _avatarUrl.get(chatId);
      if (!src || avEl.querySelector('img[data-avatar]')) return;
      const i = document.createElement('img');
      i.setAttribute('data-avatar', '1');
      i.src = src;
      avEl.textContent = '';
      avEl.style.background = 'none';
      avEl.appendChild(i);
    }

    function queueAvatars(chats) {
      for (const chat of chats) {
        if (!chat.isGroup && !_avatarState.has(chat.id)) {
          _avatarQueue.push(chat.id);
        }
      }
      drainAvatarQueue();
    }

    function drainAvatarQueue() {
      while (_avatarQueue.length && _avatarActive < AVATAR_CONCURRENCY) {
        const chatId = _avatarQueue.shift();
        if (_avatarState.has(chatId)) { drainAvatarQueue(); return; }
        _avatarActive++;
        _avatarState.set(chatId, 'loading');
        const img = new Image();
        img.onload = () => {
          _avatarState.set(chatId, 'loaded');
          _avatarUrl.set(chatId, img.src);
          document.querySelectorAll('[data-avid="' + chatId + '"]').forEach(el => applyAvatar(el, chatId));
          _avatarActive--;
          drainAvatarQueue();
        };
        img.onerror = () => {
          _avatarState.set(chatId, 'failed');
          _avatarActive--;
          drainAvatarQueue();
        };
        img.src = 'api/avatar/' + encodeURIComponent(chatId);
      }
    }
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

    const COLORS = ['#e67e22','#d35400','#27ae60','#34b7f1','#00bcd4','#9c27b0','#ff5722','#607d8b','#e91e63','#3f51b5'];
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
      return new Date(ts).toLocaleTimeString(t('locale'), { hour:'2-digit', minute:'2-digit' });
    }
    function fmtDate(ts) {
      const d = new Date(ts), now = new Date();
      if (d.toDateString() === now.toDateString()) return t('today');
      const y = new Date(now); y.setDate(now.getDate()-1);
      if (d.toDateString() === y.toDateString()) return t('yesterday');
      return d.toLocaleDateString(t('locale'));
    }
    function fmtChatTime(ts) {
      const d = new Date(ts), now = new Date();
      if (d.toDateString() === now.toDateString())
        return d.toLocaleTimeString(t('locale'), { hour:'2-digit', minute:'2-digit' });
      const y = new Date(now); y.setDate(now.getDate()-1);
      if (d.toDateString() === y.toDateString()) return t('yesterday');
      return d.toLocaleDateString(t('locale'), { day:'2-digit', month:'2-digit' });
    }
    function esc(s) {
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                      .replace(/\\n/g,'<br>');
    }
    function formatText(s) {
      let html = String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');
      html = html.replace(/((https?:\\/\\/|www\\.)[^\\s<>"&]+)/gi, function(m) {
        let url = m.replace(/[.,!?;:)]+$/, '');
        const trail = m.slice(url.length);
        const href = url.startsWith('www.') ? 'https://' + url : url;
        return '<a href="' + href + '" target="_blank" rel="noopener noreferrer" style="color:#53bdeb;text-decoration:underline;">' + url + '</a>' + trail;
      });
      return html;
    }
    function renderQuotedBlock(q) {
      const preview = q.body
        ? (q.body.length > 80 ? q.body.slice(0,80)+'…' : q.body)
        : (q.type==='image'||q.type==='photo' ? t('photo') : q.type==='ptt'||q.type==='audio' ? t('voiceMsg') : t('mediaGeneric'));
      return '<div class="quoted-block"><div class="quoted-sender">' + esc(q.contact||'') + '</div><div class="quoted-text">' + esc(preview) + '</div></div>';
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

    async function cleanupMedia() {
      if (!confirm(t('cleanupConfirm'))) return;
      try {
        const d = await fetch('api/cleanup-media', { method: 'POST' }).then(r => r.json());
        alert(tf('cleanupDone', d.deleted, d.freedMb));
        loadStorage();
      } catch(e) { alert(tf('cleanupError', e.message)); }
    }

    function scrollMsgs(dir) {
      const el = document.getElementById('messages');
      if (!el) return;
      el.scrollTop = dir === 'top' ? 0 : el.scrollHeight;
    }

    function togglePhotos() {
      const hiding = !document.body.classList.contains('hide-photos');
      document.body.classList.toggle('hide-photos', hiding);
      const btn = document.getElementById('photo-toggle');
      if (btn) { btn.classList.toggle('active', !hiding); btn.textContent = hiding ? '🚫' : '📷'; btn.title = hiding ? t('photosOff') : t('photosOn'); }
      localStorage.setItem('wa-hide-photos', hiding ? '1' : '');
    }
    if (localStorage.getItem('wa-hide-photos')) {
      document.body.classList.add('hide-photos');
      const btn = document.getElementById('photo-toggle');
      if (btn) { btn.classList.remove('active'); btn.textContent = '🚫'; btn.title = t('photosOff'); }
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

    let currentFilter = 'all';
    function setFilter(f) {
      currentFilter = f;
      document.querySelectorAll('.filter-tab').forEach(btn => btn.classList.toggle('active', btn.dataset.filter === f));
      renderChatList(allChats);
    }

    function renderChatList(chats) {
      const list = document.getElementById('chat-list');
      const q = document.getElementById('search').value.toLowerCase();
      const filtered = chats.filter(c => {
        if (q && !c.name.toLowerCase().includes(q)) return false;
        if (currentFilter === 'private') return !c.isGroup;
        if (currentFilter === 'groups') return !!c.isGroup;
        return true;
      });
      if (!filtered.length) {
        list.innerHTML = '<div class="no-chats">' + t('noChats') + '</div>';
        return;
      }
      list.innerHTML = '';
      for (const chat of filtered) {
        const item = document.createElement('div');
        item.className = 'chat-item' + (chat.id === selectedChatId ? ' active' : '');
        item.dataset.id = chat.id;
        item.onclick = () => openChat(chat);

        const av = document.createElement('div');
        if (chat.isGroup) {
          av.className = 'avatar group-avatar';
          av.textContent = '👥';
        } else {
          av.className = 'avatar';
          av.setAttribute('data-avid', chat.id);
          av.style.background = avatarColor(chat.name);
          av.textContent = avatarInitials(chat.name);
          if (_avatarState.get(chat.id) === 'loaded') applyAvatar(av, chat.id);
        }

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
        if (chat.id !== selectedChatId && !chat.lastFromMe && chat.lastTime > (lastSeenTime[chat.id] || 0)) {
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
      clearReply();
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
      av.onclick = null;
      av.style.cursor = '';
      av.querySelectorAll('img[data-avatar]').forEach(i => i.remove());
      if (chat.isGroup) {
        av.className = 'avatar group-avatar';
        av.textContent = '👥';
        av.style.background = '';
        av.removeAttribute('data-avid');
      } else {
        av.className = 'avatar';
        av.setAttribute('data-avid', chat.id);
        av.style.background = avatarColor(chat.name);
        av.textContent = avatarInitials(chat.name);
        if (_avatarState.get(chat.id) === 'loaded') applyAvatar(av, chat.id);
        else queueAvatars([chat]);
        av.onclick = () => openContactInfo(chat.id, chat.name);
        av.style.cursor = 'pointer';
      }
      document.getElementById('ch-name').textContent = chat.name;
      const ph = chat.phone || '';
      document.getElementById('ch-phone').textContent = /^\d{7,15}$/.test(ph) ? '+' + ph : '';

      lastSeenTime[chat.id] = chat.lastTime || Date.now();
      renderChatList(allChats);
      msgList.innerHTML = '';
      lastMsgTime[chat.id] = 0;
      atBottom = true;
      document.getElementById('ch-stats').textContent = '';
      await loadMessages(chat.id);
    }

    async function updateChatStats(chatId) {
      if (chatId !== selectedChatId) return;
      try {
        const s = await fetch('api/stats?chat=' + encodeURIComponent(chatId)).then(r => r.json());
        const sinceStr = s.first ? fmtDate(s.first) : '';
        const photoStr = s.photos ? '  📷 ' + s.photos : '';
        document.getElementById('ch-stats').textContent =
          s.total + ' ' + t('statsMsg') + '  ↑ ' + s.sent + '  ↓ ' + s.received + photoStr + (sinceStr ? '  ' + t('statsSince') + ' ' + sinceStr : '');
      } catch(e) {}
    }

    function closeChat() {
      document.body.classList.remove('chat-open'); // mobile: back to chat list
      selectedChatId = null;
      selectedChatPhone = null;
      document.querySelectorAll('.chat-item').forEach(el => el.classList.remove('active'));
      clearReply();
    }

    async function loadMessages(chatId) {
      if (!chatId) return;
      const since = lastMsgTime[chatId] || 0;
      try {
        const msgs = await fetch('api/messages?chat=' + encodeURIComponent(chatId) + '&since=' + since)
          .then(r => r.json());
        if (msgs.length) { renderMessages(msgs, chatId); pollReactions(); }
        updateChatStats(chatId);
      } catch(e) {}
    }

    function renderMessages(msgs, chatId) {
      if (chatId !== selectedChatId) return;
      if (!msgs.length) return;
      const noMsg = msgList.querySelector('.empty-msg');
      if (noMsg) noMsg.remove();

      let lastDate = msgList.querySelector('.date-sep:last-of-type')?.textContent || null;

      msgs.forEach(m => {
        // lastMsgTime mit deletedAt aktualisieren (deletedAt kann neuer sein als timestamp)
        const effectiveTs = (m.deleted && m.deletedAt) ? Math.max(m.timestamp, m.deletedAt) : m.timestamp;
        if (effectiveTs > (lastMsgTime[selectedChatId] || 0)) lastMsgTime[selectedChatId] = effectiveTs;

        // Gelöschte Nachrichten: vorhandenen Wrap in-place aktualisieren statt neu erstellen
        if (m.deleted) {
          const existingWrap = msgList.querySelector('.bubble-wrap[data-msgid="' + m.id + '"]');
          if (existingWrap) {
            const bub = existingWrap.querySelector('.bubble');
            if (bub && !bub.querySelector('.deleted-notice') && !bub.querySelector('.bubble-deleted')) {
              if (m.body) {
                const notice = document.createElement('span');
                notice.className = 'deleted-notice';
                notice.textContent = t('msgDeletedNotice');
                bub.appendChild(notice);
              } else {
                bub.innerHTML = '<span class="bubble-deleted"><span class="del-icon">🚫</span>' + t('msgDeleted') + '</span><span class="time">' + fmtTime(m.timestamp) + '</span>';
              }
              existingWrap.querySelectorAll('.del-btn,.react-btn,.fwd-btn,.reply-btn').forEach(b => b.style.display = 'none');
            }
            return;
          }
        }

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
        if (m.deleted && !m.body) {
          // Standard: Body ersetzt durch 🚫-Text (KEEP_DELETED=false)
          bub.innerHTML = '<span class="bubble-deleted"><span class="del-icon">🚫</span>' + t('msgDeleted') + '</span><span class="time">' + fmtTime(m.timestamp) + '</span>';
        } else if (m.type === 'document') {
          bub.innerHTML = '<div class="bubble-document"><span class="doc-icon">📄</span><div class="doc-info"><span class="doc-name">' + esc(m.filename || 'Dokument') + '</span>' + (m.body ? '<div class="doc-caption">' + esc(m.body) + '</div>' : '') + '</div></div><span class="time" style="float:right;padding:0 0 4px;">' + fmtTime(m.timestamp) + ack + '</span>';
        } else if (m.type === 'voice') {
          const audioSrc = m.mediaFile ? 'api/media/' + encodeURIComponent(m.mediaFile) : '';
          bub.innerHTML = (audioSrc
            ? '<audio controls style="min-width:220px;max-width:300px;width:100%" src="' + audioSrc + '"></audio>'
            : '<span style="opacity:0.6">' + t('voiceMsg') + '</span>')
            + '<span class="time">' + fmtTime(m.timestamp) + ack + '</span>';
        } else if (m.type === 'photo' && m.mediaFile) {
          bub.classList.add('bubble-photo');
          if (m.isForwarded) {
            const fwdEl = document.createElement('span');
            fwdEl.className = 'forwarded-label' + (m.forwardingScore >= 5 ? ' frequent' : '');
            fwdEl.textContent = m.forwardingScore >= 5 ? t('frequentForwarded') : t('forwarded');
            bub.appendChild(fwdEl);
          }
          if (m.quotedMsg) bub.insertAdjacentHTML('beforeend', renderQuotedBlock(m.quotedMsg));
          const ph = document.createElement('span');
          ph.className = 'photo-placeholder'; ph.textContent = t('photo');
          bub.appendChild(ph);
          const img = document.createElement('img');
          img.className = 'msg-img';
          img.src = 'api/media/' + encodeURIComponent(m.mediaFile);
          img.style.cssText = 'max-width:320px;max-height:400px;display:block;cursor:zoom-in;width:100%;';
          img.loading = 'lazy';
          img.addEventListener('click', function(e) { e.stopPropagation(); openLightbox(this.src); });
          bub.appendChild(img);
          if (m.body) { const cap = document.createElement('div'); cap.className = 'caption'; cap.innerHTML = formatText(m.body); bub.appendChild(cap); }
          const timeEl = document.createElement('span'); timeEl.className = 'time'; timeEl.innerHTML = fmtTime(m.timestamp) + ack; bub.appendChild(timeEl);
        } else {
          const fwdHtml = m.isForwarded
            ? '<span class="forwarded-label' + (m.forwardingScore >= 5 ? ' frequent' : '') + '">' + (m.forwardingScore >= 5 ? t('frequentForwarded') : t('forwarded')) + '</span>'
            : '';
          const quotedHtml = m.quotedMsg ? renderQuotedBlock(m.quotedMsg) : '';
          bub.innerHTML = fwdHtml + quotedHtml + formatText(m.body || (m.type === 'photo' ? t('photo') : '')) + '<span class="time">' + fmtTime(m.timestamp) + ack + '</span>';
        }
        // KEEP_DELETED-Modus: Badge unter dem originalen Inhalt
        if (m.deleted && m.body) {
          const notice = document.createElement('span');
          notice.className = 'deleted-notice';
          notice.textContent = t('msgDeletedNotice');
          bub.appendChild(notice);
        }
        const bri = document.createElement('div');
        bri.className = 'bubble-row-inner';
        bri.appendChild(bub);
        const delBtn = document.createElement('button');
        delBtn.className = 'del-btn';
        delBtn.title = t('ttDelete');
        delBtn.textContent = '✕';
        delBtn.dataset.msgid = m.id;
        if (m.deleted) delBtn.style.display = 'none';
        bri.appendChild(delBtn);
        const reactBtn = document.createElement('button');
        reactBtn.className = 'react-btn';
        reactBtn.title = t('ttReact');
        reactBtn.textContent = '😊';
        reactBtn.dataset.msgid = m.id;
        if (m.deleted) reactBtn.style.display = 'none';
        bri.appendChild(reactBtn);
        const fwdBtn = document.createElement('button');
        fwdBtn.className = 'fwd-btn';
        fwdBtn.title = t('ttForward');
        fwdBtn.textContent = '↪';
        fwdBtn.dataset.msgid = m.id;
        if (m.deleted) fwdBtn.style.display = 'none';
        bri.appendChild(fwdBtn);
        const replyBtn = document.createElement('button');
        replyBtn.className = 'reply-btn';
        replyBtn.title = t('ttReply');
        replyBtn.textContent = '↩';
        replyBtn.dataset.msgid = m.id;
        replyBtn.dataset.contact = m.fromMe ? t('me') : (m.contact || '');
        replyBtn.dataset.preview = (m.body || (m.type === 'photo' ? t('photo') : t('mediaGeneric'))).slice(0, 60);
        if (m.deleted) replyBtn.style.display = 'none';
        bri.appendChild(replyBtn);
        wrap.appendChild(bri);
        // Reaktions-Badges werden ausschließlich von updateReactionsInDOM gesetzt
        // (mit server-seitigem isOwn). Kein client-seitiger JID-Vergleich hier.
        msgList.appendChild(wrap);
        if (m.timestamp > (lastMsgTime[selectedChatId] || 0)) {
          lastMsgTime[selectedChatId] = m.timestamp;
        }
      });
      if (atBottom) msgList.scrollTop = msgList.scrollHeight;
    }

    async function reloadMessages(chatId) {
      if (!chatId || chatId !== selectedChatId) return;
      try {
        const msgs = await fetch('api/messages?chat=' + encodeURIComponent(chatId)).then(r => r.json());
        msgList.innerHTML = '';
        lastMsgTime[chatId] = 0;
        atBottom = true;
        if (msgs.length) { renderMessages(msgs, chatId); pollReactions(); }
        lastMsgTime[chatId] = msgs.reduce((max, m) => Math.max(max, m.timestamp), 0);
      } catch(e) {}
    }

    function exportChat() {
      if (!selectedChatId) return;
      window.location.href = 'api/export/' + encodeURIComponent(selectedChatId);
    }


    let _replyMsgId = null;

    function setReply(msgId, contact, preview) {
      _replyMsgId = msgId;
      document.getElementById('reply-bar-sender').textContent = contact;
      document.getElementById('reply-bar-text').textContent = preview;
      document.getElementById('reply-bar').classList.add('active');
      document.getElementById('msg-input').focus();
    }

    function clearReply() {
      _replyMsgId = null;
      document.getElementById('reply-bar').classList.remove('active');
    }

    let _spamDeleteIds = [];
    let _spamDeleteWraps = [];

    function openSpamModal(count, wraps, ids) {
      _spamDeleteIds = ids;
      _spamDeleteWraps = wraps;
      document.getElementById('spam-modal-text').textContent = tf('spamModal', count);
      document.getElementById('spam-modal').classList.add('open');
    }

    function closeSpamModal() {
      document.getElementById('spam-modal').classList.remove('open');
      _spamDeleteIds = [];
      _spamDeleteWraps = [];
    }

    async function confirmDeleteSpam() {
      const ids = _spamDeleteIds.slice();
      const wraps = _spamDeleteWraps.slice();
      closeSpamModal();
      const btn = document.getElementById('spam-delete-btn');
      if (btn) { btn.disabled = true; btn.textContent = t('spamDeleting'); }
      try {
        const r = await fetch('api/delete-batch/' + encodeURIComponent(selectedChatId), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids }),
        }).then(r => r.json());
        for (const wrap of wraps) wrap.remove();
        await pollChats();
        if (btn) { btn.textContent = tf('spamDeleted', r.deleted); setTimeout(() => { btn.textContent = t('btnSpamDelete'); }, 3000); }
      } catch(e) {
        if (btn) { btn.textContent = t('spamError'); setTimeout(() => { btn.textContent = t('btnSpamDelete'); }, 3000); }
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    async function deleteSpam() {
      if (!selectedChatId) return;
      const spamWraps = [...msgList.querySelectorAll('.bubble-wrap')].filter(w => w.querySelector('.forwarded-label.frequent'));
      const count = spamWraps.length;
      if (!count) {
        const btn = document.getElementById('spam-delete-btn');
        if (btn) { const orig = btn.textContent; btn.textContent = t('spamNone'); setTimeout(() => { btn.textContent = orig; }, 2000); }
        return;
      }
      openSpamModal(count, spamWraps, spamWraps.map(w => w.dataset.msgid).filter(Boolean));
    }

    let _fwdMsgId = null;

    function renderFwdChatList(chats) {
      const list = document.getElementById('fwd-chat-list');
      list.innerHTML = '';
      for (const chat of chats) {
        const item = document.createElement('div');
        item.className = 'fwd-chat-item';
        const av = document.createElement('div');
        av.className = 'avatar';
        av.style.cssText = 'width:36px;height:36px;font-size:13px;flex-shrink:0;';
        av.style.background = avatarColor(chat.name);
        av.textContent = avatarInitials(chat.name);
        const name = document.createElement('div');
        name.style.cssText = 'font-size:14px;color:#e9edef;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
        name.textContent = chat.name;
        item.appendChild(av);
        item.appendChild(name);
        item.onclick = () => forwardTo(chat.id);
        list.appendChild(item);
      }
    }

    function filterFwdChats() {
      const q = document.getElementById('fwd-search').value.toLowerCase();
      renderFwdChatList(q ? allChats.filter(c => c.name.toLowerCase().includes(q)) : allChats);
    }

    async function openContactInfo(chatId, fallbackName) {
      const modal = document.getElementById('contact-modal');
      const picEl = document.getElementById('contact-modal-pic');
      const nameEl = document.getElementById('contact-modal-name');
      const pushnameEl = document.getElementById('contact-modal-pushname');
      const numberEl = document.getElementById('contact-modal-number');
      const aboutEl = document.getElementById('contact-modal-about');
      // Reset
      picEl.innerHTML = '…'; picEl.style.background = '#2a3942';
      nameEl.textContent = '…'; pushnameEl.textContent = ''; numberEl.textContent = ''; aboutEl.textContent = '';
      modal.classList.add('open');
      try {
        const data = await fetch('api/contact/' + encodeURIComponent(chatId)).then(r => r.json());
        const name = data.name || fallbackName || chatId;
        nameEl.textContent = name;
        // Zeige WhatsApp-Profilname (waName) nur wenn er vom Telefonbuch-Namen abweicht
        if (data.waName && data.waName !== data.savedName) {
          pushnameEl.innerHTML = '<span style="font-size:11px;opacity:0.6">WhatsApp-Name</span><br>' + esc(data.waName);
        } else {
          pushnameEl.textContent = '';
        }
        numberEl.textContent = data.number ? '+' + data.number : '';
        aboutEl.textContent = data.about || '';
        picEl.textContent = '';
        picEl.removeAttribute('data-avid');
        if (data.hasProfilePic) {
          const cached = _avatarState.get(chatId);
          if (cached === 'loaded') {
            picEl.style.background = 'none';
            const img = document.createElement('img');
            img.src = _avatarUrl.get(chatId);
            picEl.appendChild(img);
          } else if (cached !== 'failed') {
            picEl.style.background = avatarColor(name);
            picEl.textContent = avatarInitials(name);
            picEl.setAttribute('data-avid', chatId);
            loadAvatar(chatId, picEl);
          } else {
            picEl.style.background = avatarColor(name);
            picEl.textContent = avatarInitials(name);
          }
        } else {
          picEl.style.background = avatarColor(name);
          picEl.textContent = avatarInitials(name);
        }
      } catch(e) {
        nameEl.textContent = fallbackName || chatId;
        picEl.style.background = avatarColor(fallbackName || chatId);
        picEl.textContent = avatarInitials(fallbackName || chatId);
      }
    }
    function closeContactModal() {
      document.getElementById('contact-modal').classList.remove('open');
    }

    function openFwdModal(msgId) {
      _fwdMsgId = msgId;
      document.getElementById('fwd-search').value = '';
      renderFwdChatList(allChats);
      document.getElementById('fwd-modal').classList.add('open');
      setTimeout(() => document.getElementById('fwd-search').focus(), 50);
    }

    function closeFwdModal() {
      document.getElementById('fwd-modal').classList.remove('open');
      _fwdMsgId = null;
    }

    async function forwardTo(chatId) {
      const msgId = _fwdMsgId;
      closeFwdModal();
      if (!msgId) return;
      try {
        const r = await fetch('api/forward', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ msgId, to: chatId }),
        }).then(r => r.json());
        if (!r.success) console.error('Forward failed:', r.error);
      } catch(e) {
        console.error('Forward error:', e.message);
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
        renderChatList(chats);           // 1. Kontakte sofort anzeigen (Initialen)
        setTimeout(() => queueAvatars(chats), 200); // 2. Avatare nachgelagert laden
      } catch(e) {}
    }

    let _attachFile = null;

    function formatFileSize(bytes) {
      if (bytes < 1024) return bytes + ' B';
      if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
      return (bytes / 1048576).toFixed(1) + ' MB';
    }

    function attachFile(file) {
      if (!file) return;
      _attachFile = file;
      const isImg = file.type.startsWith('image/');
      const icon = document.getElementById('attach-icon');
      const thumb = document.getElementById('attach-thumb');
      icon.style.display = isImg ? 'none' : 'block';
      if (isImg) {
        const reader = new FileReader();
        reader.onload = e => { thumb.src = e.target.result; thumb.style.display = 'block'; };
        reader.readAsDataURL(file);
      } else {
        thumb.style.display = 'none';
      }
      document.getElementById('attach-name').textContent = file.name;
      document.getElementById('attach-size').textContent = formatFileSize(file.size);
      document.getElementById('attach-bar').classList.add('active');
      document.getElementById('msg-input').placeholder = t('attachCaption');
      document.getElementById('msg-input').focus();
    }

    function onFileSelected(evt) {
      attachFile(evt.target.files[0]);
      evt.target.value = '';
    }

    function clearAttach() {
      _attachFile = null;
      document.getElementById('attach-bar').classList.remove('active');
      document.getElementById('attach-thumb').style.display = 'none';
      document.getElementById('attach-name').textContent = '';
      document.getElementById('attach-size').textContent = '';
      document.getElementById('msg-input').placeholder = t('msgInput');
    }

    async function sendFile() {
      if (!_attachFile || !selectedChatId) return;
      const caption = document.getElementById('msg-input').value.trim();
      const formData = new FormData();
      formData.append('to', selectedChatId);
      if (caption) formData.append('caption', caption);
      formData.append('file', _attachFile);
      clearAttach();
      document.getElementById('msg-input').value = '';
      document.getElementById('msg-input').style.height = 'auto';
      atBottom = true;
      try {
        const r = await fetch('api/send-media', { method: 'POST', body: formData }).then(r => r.json());
        if (r.success) {
          await pollMessages();
        } else {
          alert(tf('errSend', r.error));
        }
      } catch(e) { alert(t('errNetwork')); }
    }

    async function sendMsg() {
      if (!selectedChatId) return;
      if (_attachFile) { await sendFile(); return; }
      const txt = document.getElementById('msg-input').value.trim();
      if (!txt) return;
      const quotedMsgId = _replyMsgId;
      clearReply();
      try {
        const endpoint = quotedMsgId ? 'api/reply' : 'api/send';
        const payload = quotedMsgId
          ? { quotedMsgId, chatId: selectedChatId, message: txt }
          : { to: selectedChatId, message: txt };
        const r = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        }).then(r => r.json());
        if (r.success) {
          document.getElementById('msg-input').value = '';
          document.getElementById('msg-input').style.height = 'auto';
          atBottom = true;
          await pollMessages();
        } else {
          alert(tf('errSend', r.error));
        }
      } catch(e) { alert(t('errNetwork')); }
    }

    async function deleteMsg(chatId, msgId) {
      try {
        const r = await fetch('api/messages/' + encodeURIComponent(chatId) + '/' + encodeURIComponent(msgId), {method:'DELETE'});
        if (!r.ok) return;
        for (const bri of msgList.querySelectorAll('.bubble-row-inner')) {
          const btn = bri.querySelector('.del-btn');
          if (btn?.dataset?.msgid === msgId) {
            const bub = bri.querySelector('.bubble');
            if (bub) {
              bub.innerHTML = '<span class="bubble-deleted"><span class="del-icon">🚫</span>' + t('msgDeleted') + '</span><span class="time">' + bub.querySelector('.time')?.textContent + '</span>';
            }
            btn.style.display = 'none';
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
      const fwd = e.target.closest('.fwd-btn');
      if (fwd) { openFwdModal(fwd.dataset.msgid); return; }
      const reply = e.target.closest('.reply-btn');
      if (reply) { setReply(reply.dataset.msgid, reply.dataset.contact, reply.dataset.preview); return; }
    });

    function showSpinner(msg) {
      document.getElementById('spinner-overlay').style.display = 'flex';
      document.getElementById('spinner-text').textContent = msg || t('spinnerRestart');
      document.getElementById('topbar').style.display = 'none';
      document.getElementById('main').style.display = 'none';
      document.getElementById('qr-overlay').style.display = 'none';
      currentStatus = ''; // force refresh() to pick up new status
    }

    function confirmLogout() {
      document.getElementById('logout-modal').classList.add('open');
      applyI18n();
    }
    function closeLogoutModal() {
      document.getElementById('logout-modal').classList.remove('open');
    }
    async function logout() {
      closeLogoutModal();
      showSpinner(t('spinnerLogout'));
      await fetch('api/logout', { method: 'POST' }).catch(() => {});
    }

    async function resetSession() {
      showSpinner(t('spinnerReset'));
      await fetch('api/reset', { method: 'POST' }).catch(() => {});
    }

    async function refresh() {
      try {
        const s = await fetch('api/status').then(r => r.json());
        const dotLabel = ({
          connected: t('statusConnected'), waiting_for_scan: t('statusQR'),
          authenticated: t('statusAuth'), initializing: t('statusInit'),
          disconnected: t('statusDisc'), auth_failed: t('statusAuthFail'), error: t('statusError'),
        })[s.status] || s.status;
        const dot = document.getElementById('status-dot');
        dot.className = 'status-dot ' + (
          s.status === 'connected' ? 'connected' :
          s.status === 'waiting_for_scan' || s.status === 'authenticated' ? 'waiting' :
          s.status === 'initializing' ? 'initializing' : 'error'
        );
        dot.title = dotLabel;

        if (s.phone && !myPhone) myPhone = s.phone;
        if (s.myJid && !myJid) myJid = s.myJid;
        if (s.status !== currentStatus) {
          currentStatus = s.status;
          const connecting = s.status === 'initializing' || s.status === 'authenticated' || s.status === 'disconnected';
          document.getElementById('spinner-text').textContent =
            s.status === 'disconnected' ? t('spinnerDisconnect') : t('spinnerConnecting');
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

    applyLang();
    refresh();
    setInterval(refresh, 5000);
    setInterval(pollMessages, 2000);
    setInterval(pollChats, 10000);
    setInterval(pollReactions, 5000);

    // ── Reactions ──────────────────────────────────────────────────────────────
    const REACTION_EMOJIS = ['👍','❤️','😂','😮','😢','🙏'];
    let pickerTargetMsgId = null;
    let myPhone = null;
    let myJid = null;

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

    // Lightbox
    const lightbox = document.createElement('div');
    lightbox.id = 'lightbox';
    const lbImg = document.createElement('img');
    lightbox.appendChild(lbImg);
    document.body.appendChild(lightbox);
    function openLightbox(src) { lbImg.src = src; lightbox.classList.add('open'); }
    lightbox.addEventListener('click', () => lightbox.classList.remove('open'));
    lbImg.addEventListener('click', e => e.stopPropagation());
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        lightbox.classList.remove('open');
        document.getElementById('contact-modal')?.classList.remove('open');
      }
    });

    document.getElementById('msg-input').addEventListener('paste', e => {
      const items = e.clipboardData?.items ?? [];
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          e.preventDefault();
          const ext = item.type.split('/')[1].replace('jpeg', 'jpg');
          attachFile(new File([item.getAsFile()], 'bild.' + ext, { type: item.type }));
          return;
        }
      }
    });

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
      setTimeout(pollReactions, 1500);
    }

    async function toggleReaction(msgId, emoji, isOwn) {
      await fetch('api/react', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ msgId, reaction: isOwn ? '' : emoji }),
      }).catch(() => {});
      setTimeout(pollReactions, 1500);
    }

    async function pollReactions() {
      if (!selectedChatId) return;
      try {
        const data = await fetch('api/reactions/' + encodeURIComponent(selectedChatId)).then(r => r.json());
        updateReactionsInDOM(data);
      } catch(e) {}
    }

    function updateReactionsInDOM(reactionsMap) {
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
        for (const [emoji, { count, own }] of Object.entries(reactions)) {
          const badge = document.createElement('span');
          badge.className = 'reaction-badge' + (own ? ' own' : '');
          badge.title = own ? t('ttRemoveReaction') : t('ttAddReaction');
          badge.textContent = emoji + (count > 1 ? ' ' + count : '');
          badge.onclick = () => toggleReaction(msgId, emoji, own);
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

const PORT = parseInt(process.env.PORT || '17776', 10);
app.listen(PORT, () => console.log(`[INFO] Web UI running on port ${PORT}`));
