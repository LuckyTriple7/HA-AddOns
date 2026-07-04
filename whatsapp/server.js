'use strict';
const _logBuffer = [];
const _LOG_MAX = 300;
(function () {
  const _ts = () => new Date().toISOString().slice(0, 19).replace('T', ' ');
  const _levelMap = { log: 'INFO', warn: 'WARN', error: 'ERROR' };
  ['log','warn','error'].forEach(m => {
    const orig = console[m].bind(console);
    console[m] = (...a) => {
      let level = _levelMap[m] || 'INFO';
      let msg;
      if (a.length && typeof a[0] === 'string') {
        const match = a[0].match(/^(\[(INFO|WARN|ERROR|DEBUG)\])(.*)/s);
        if (match) {
          level = match[2];
          const rest = match[3].trimStart();
          msg = `[${level}] [${_ts()}]${rest ? ' ' + rest : ''}`;
          orig(msg, ...a.slice(1));
        } else {
          msg = `[${level}] [${_ts()}] ${a[0]}`;
          orig(msg, ...a.slice(1));
        }
      } else {
        msg = `[${level}] [${_ts()}]`;
        orig(msg, ...a);
      }
      _logBuffer.push({ ts: Date.now(), level, msg: msg + (a.length > 1 ? ' ' + a.slice(1).map(x => typeof x === 'object' ? JSON.stringify(x) : String(x)).join(' ') : '') });
      if (_logBuffer.length > _LOG_MAX) _logBuffer.shift();
    };
  });
})();

function _logSilent(level, msg) {
  _logBuffer.push({ ts: Date.now(), level: level || 'DEBUG', msg: '[' + (level||'DEBUG') + '] ' + msg });
  if (_logBuffer.length > _LOG_MAX) _logBuffer.shift();
}

const { Client, NoAuth, MessageMedia, Location } = require('whatsapp-web.js');
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

const rateLimit = require('express-rate-limit');
const deleteRateLimit = rateLimit({ windowMs: 60_000, limit: 30 });
// Einmal beim Start erzeugen — express-rate-limit verbietet das Anlegen im
// Request-Handler (ERR_ERL_CREATED_IN_REQUEST_HANDLER)
const mutatingRateLimit = rateLimit({ windowMs: 60_000, limit: 200 });

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
// Hinter dem HA-Ingress-Reverse-Proxy (genau ein Hop) — sonst warnt
// express-rate-limit über das X-Forwarded-For-Header (ERR_ERL_UNEXPECTED_X_FORWARDED_FOR)
app.set('trust proxy', 1);
app.use(express.json());
app.use((req, res, next) => {
  if (req.method === 'GET' || req.method === 'HEAD' || req.method === 'OPTIONS') return next();
  return mutatingRateLimit(req, res, next);
});
app.use((req, res, next) => {
  if (req.path === '/api/logs' || req.path.startsWith('/api/media/') || req.path === '/api/status') return next();
  const t0 = Date.now();
  res.on('finish', () => {
    _logSilent('DEBUG', `API ${req.method} ${req.path} → ${res.statusCode} (${Date.now()-t0}ms)`);
  });
  next();
});

let qrCodeDataUrl = null;
let status = 'initializing';
let connectedPhone = null;
let lastError = null;
let lastReceivedMsg = null; // { timestamp, iso, chatId, chatName, contact, preview }

const DARK_MODE = process.env.DARK_MODE !== 'false';
const DOWNLOAD_MEDIA = process.env.DOWNLOAD_MEDIA === 'true';
const MEDIA_MAX_MB = Math.max(parseInt(process.env.MEDIA_MAX_MB || '500', 10), 50);
const VIDEO_MAX_MB = Math.max(parseInt(process.env.VIDEO_MAX_MB || '50', 10), 1);
const KEEP_DELETED = process.env.KEEP_DELETED === 'true';
const DEBUG = process.env.DEBUG_MODE === 'true';
const HA_NOTIFY = process.env.HA_NOTIFICATIONS === 'true';
const HA_PRIVACY = process.env.HA_NOTIFICATIONS_PRIVACY === 'true';
const HA_NOTIFY_SKIP_GROUPS = process.env.HA_NOTIFICATIONS_SKIP_GROUPS === 'true';
// SUPERVISOR_TOKEN wird vom Supervisor automatisch injiziert (homeassistant_api: true) —
// kein manuell eingetragener Token mehr nötig.
const SUPERVISOR_TOKEN = process.env.SUPERVISOR_TOKEN || '';
function dbg(...args) { if (DEBUG) console.log('[DEBUG]', ...args); }
if (DEBUG) console.log('[DEBUG] Debug-Modus aktiv');
const MEDIA_DIR = '/config/media';
const INITIAL_CHATS = parseInt(process.env.INITIAL_CHATS || '30', 10);
const INITIAL_MESSAGES = parseInt(process.env.INITIAL_MESSAGES || '20', 10);
const WEBHOOK = process.env.WEBHOOK_INCOMING || '';
console.log('[INFO] ── Configuration ──────────────────────────────────');
console.log(`[INFO]   dark_mode              = ${DARK_MODE}`);
console.log(`[INFO]   download_media         = ${DOWNLOAD_MEDIA}`);
console.log(`[INFO]   media_max_mb           = ${MEDIA_MAX_MB}`);
console.log(`[INFO]   video_max_mb           = ${VIDEO_MAX_MB}`);
console.log(`[INFO]   keep_deleted           = ${KEEP_DELETED}`);
console.log(`[INFO]   debug_mode             = ${DEBUG}`);
console.log(`[INFO]   ha_notifications       = ${HA_NOTIFY}`);
console.log(`[INFO]   ha_notifications_priv  = ${HA_PRIVACY}`);
console.log(`[INFO]   ha_notify_skip_groups  = ${HA_NOTIFY_SKIP_GROUPS}`);
console.log(`[INFO]   home_assistant_api     = ${SUPERVISOR_TOKEN ? 'available' : 'not available'}`);
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
          type: m.type || 'text',
          preview: m.type === 'location' ? (m.locName ? '📍 ' + m.locName : '📍 Standort') : m.type === 'video' ? '📹 Video' : m.type === 'voice' ? '🎵 Sprachnachricht' : m.body || (m.type === 'photo' ? '📷 Foto' : m.type === 'document' ? `📄 ${m.filename || 'Dokument'}` : '[Medien]'),
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
    const preview = msg.type === 'location' ? (msg.locName ? '📍 ' + msg.locName : '📍 Standort') : msg.type === 'voice' ? '🎵 Sprachnachricht' : msg.type === 'video' ? '📹 Video' : msg.body || (msg.type === 'photo' ? '📷 Foto' : msg.type === 'document' ? '📄 ' + (msg.filename || 'Dokument') : '[Medien]');
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
    const mime = msg._data?.mimetype || '';
    const ext = msg.type === 'sticker' ? 'webp' : (msg.type === 'ptt' || msg.type === 'audio') ? 'ogg' : msg.type === 'video' ? (mime.includes('webm') ? 'webm' : 'mp4') : 'jpg';
    const filePath = path.resolve(MEDIA_DIR, `${safeId}.${ext}`);
    if (!filePath.startsWith(path.resolve(MEDIA_DIR) + path.sep)) return null;
    if (!existsSync(filePath)) {
      _logSilent('DEBUG', `downloadWAMedia: start ${safeId}.${ext} (${mime||'?'})`);
      const t0 = Date.now();
      const media = await msg.downloadMedia();
      if (media?.data) {
        fs.writeFileSync(filePath, Buffer.from(media.data, 'base64'));
        _logSilent('DEBUG', `downloadWAMedia: ok ${safeId}.${ext} ${(Buffer.from(media.data,'base64').length/1024).toFixed(1)}KB in ${Date.now()-t0}ms`);
        enforceMediaLimitThrottled(); // Speicherlimit auch beim Foto-/Auto-Download wahren
      } else {
        _logSilent('WARN', `downloadWAMedia: no data for ${safeId}.${ext}`);
      }
    } else {
      _logSilent('DEBUG', `downloadWAMedia: cached ${safeId}.${ext}`);
    }
    return existsSync(filePath) ? `${safeId}.${ext}` : null;
  } catch (e) {
    _logSilent('ERROR', `downloadWAMedia: failed ${msgId} — ${e.message}`);
    console.error('[ERROR] downloadWAMedia:', e.message);
    return null;
  }
}

// Lädt das Medium einer Nachricht im Hintergrund nach, wenn es zum Zeitpunkt
// der Erstellung noch nicht verfügbar war (typisch beim Weiterleiten: das
// message-Objekt aus message_create ist „stale" und liefert dauerhaft keine
// Daten — erst ein frisch via getMessageById geholtes Objekt funktioniert,
// genau wie nach einem Add-on-Neustart).
async function ensureMediaLater(chatId, msgId) {
  const delays = [1500, 2500, 4000, 6000, 8000, 10000, 12000];
  for (const d of delays) {
    await new Promise(r => setTimeout(r, d));
    const list = messagesByChatId.get(chatId);
    const stored = list && list.find(m => m.id === msgId);
    if (!stored || stored.mediaFile || stored.deleted) return; // schon da / weg / gelöscht
    try {
      const fresh = await client.getMessageById(msgId).catch(() => null);
      if (!fresh) continue;
      const file = await downloadWAMedia(fresh, msgId);
      if (file) {
        stored.mediaFile = file;
        stored.mediaUpdatedAt = Date.now();
        saveMsgs();
        _logSilent('INFO', `ensureMediaLater: media ready for ${msgId} after retry`);
        return;
      }
    } catch (e) { dbg('ensureMediaLater:', e.message); }
  }
  _logSilent('WARN', `ensureMediaLater: media still unavailable for ${msgId}`);
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
        const isLoc = msg.type === 'location';
        const isVid = msg.type === 'video';
        if (!isText && !isImage && !isPtt && !isLoc && !isVid) continue;
        if (!msg.body && !isImage && !isPtt && !isLoc && !isVid) continue;
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
          type: isImage ? 'photo' : isPtt ? 'voice' : isLoc ? 'location' : isVid ? 'video' : 'text',
          locLat: isLoc ? (msg.location?.latitude ?? null) : null,
          locLng: isLoc ? (msg.location?.longitude ?? null) : null,
          locName: isLoc ? (msg.location?.description || '') : '',
          videoSize: isVid ? (msg._data?.size || 0) : undefined,
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
        let cachedPhotos = 0, cachedVoice = 0, cachedVideo = 0;
        for (const [chatId, msgs] of messagesByChatId) {
          for (const m of msgs) {
            if (m.type === 'photo' || m.type === 'voice') {
              if (m.mediaFile) { if (m.type === 'photo') cachedPhotos++; else cachedVoice++; }
              else pending.push({ chatId, m });
            } else if (m.type === 'video' && m.mediaFile) { cachedVideo++; }
          }
        }
        const cachedTotal = cachedPhotos + cachedVoice + cachedVideo;
        if (cachedTotal) {
          const parts = [];
          if (cachedPhotos) parts.push(cachedPhotos + ' photo(s)');
          if (cachedVoice)  parts.push(cachedVoice  + ' voice message(s)');
          if (cachedVideo)  parts.push(cachedVideo  + ' video(s)');
          console.log(`[INFO] ${cachedTotal} media file(s) on disk: ${parts.join(', ')}`);
        }
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
  const isLocation = msg.type === 'location';
  const isVideo = msg.type === 'video';
  if (!isText && !isImage && !isDocument && !isPtt && !isLocation && !isVideo) { dbg(`Skipping unsupported type: ${msg.type}`); return; }
  if (!msg.body && !isImage && !isDocument && !isPtt && !isLocation && !isVideo) return;
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
  let type = 'text', mediaFile = null, filename = null, locLat = null, locLng = null, locName = '';
  if (isImage) {
    type = 'photo';
    if (DOWNLOAD_MEDIA) mediaFile = await downloadWAMedia(msg, msg.id._serialized);
  } else if (isDocument) {
    type = 'document';
    filename = msg._data?.filename || msg.filename || 'Dokument';
  } else if (isPtt) {
    type = 'voice';
    mediaFile = await downloadWAMedia(msg, msg.id._serialized);
  } else if (isLocation) {
    type = 'location';
    locLat = msg.location?.latitude ?? null;
    locLng = msg.location?.longitude ?? null;
    locName = msg.location?.description || '';
  } else if (isVideo) {
    type = 'video';
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
    locLat, locLng, locName,
    videoSize: isVideo ? (msg._data?.size || 0) : undefined,
    timestamp: msg.timestamp * 1000,
    fromMe: false,
    contact: contactName,
    isForwarded: !!msg.isForwarded,
    forwardingScore: msg.forwardingScore || 0,
    quotedMsg: quotedMsgData,
  });
  _logSilent('DEBUG', `msg_in: from=${contactName} chat=${chatId} type=${type}${msg.body?' body="'+msg.body.slice(0,60)+'"':''}`);
  // Foto ohne Medium (typisch beim Weiterleiten) im Hintergrund nachladen
  if (added && type === 'photo' && DOWNLOAD_MEDIA && !mediaFile) {
    ensureMediaLater(chatId, msg.id._serialized);
  }
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
        preview: type === 'location' ? (locName ? '📍 ' + locName : '📍 Standort') : type === 'video' ? '📹 Video' : type === 'voice' ? '🎵 Sprachnachricht' : msg.body || (type === 'photo' ? '📷 Foto' : type === 'document' ? `📄 ${filename || 'Dokument'}` : '[Medien]'),
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
  const isVideo = msg.type === 'video';
  if (!isText && !isImage && !isDocument && !isVideo) { dbg(`message_create: skipping type=${msg.type}`); return; }
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
  } else if (isVideo) {
    type = 'video';
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
    videoSize: isVideo ? (msg._data?.size || 0) : undefined,
    timestamp: msg.timestamp * 1000,
    fromMe: true,
    contact: 'Ich',
    ack: msg.ack || 1,
    isForwarded: !!msg.isForwarded,
    forwardingScore: msg.forwardingScore || 0,
    quotedMsg: quotedMsgDataOut,
  });
  // Foto ohne Medium (typisch beim Weiterleiten) im Hintergrund nachladen
  if (type === 'photo' && DOWNLOAD_MEDIA && !mediaFile) {
    ensureMediaLater(chatId, msg.id._serialized);
  }
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
  const ackNames = {1:'sent',2:'received',3:'read',4:'played'};
  _logSilent('DEBUG', `message_ack: ${msg.id._serialized} → ${ackNames[ack]||ack}`);
  const msgs = messagesByChatId.get(msg.to);
  if (msgs) {
    const stored = msgs.find(m => m.id === msg.id._serialized);
    if (stored) { stored.ack = ack; stored.ackUpdatedAt = Date.now(); return; }
  }
  for (const list of messagesByChatId.values()) {
    const stored = list.find(m => m.id === msg.id._serialized);
    if (stored) { stored.ack = ack; stored.ackUpdatedAt = Date.now(); break; }
  }
});

client.on('call', (call) => {
  _logSilent('INFO', `Incoming call from ${call.from} — type=${call.isVideo?'video':'audio'} id=${call.id}`);
});

client.on('group_join', (notification) => {
  _logSilent('INFO', `group_join: ${notification.chatId} — ${notification.recipientIds?.join(', ')}`);
});

client.on('group_leave', (notification) => {
  _logSilent('INFO', `group_leave: ${notification.chatId} — ${notification.recipientIds?.join(', ')}`);
});

client.on('contact_changed', (msg, oldId, newId, isContact) => {
  _logSilent('INFO', `contact_changed: ${oldId} → ${newId} isContact=${isContact}`);
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
  if (!SUPERVISOR_TOKEN) {
    console.warn('[WARN] HA_NOTIFICATIONS: SUPERVISOR_TOKEN not available (homeassistant_api missing?)');
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
  const req = http.request('http://supervisor/core/api/services/persistent_notification/create', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${SUPERVISOR_TOKEN}`,
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
  res.json(since_ts ? msgs.filter(m => m.timestamp > since_ts || (m.deletedAt && m.deletedAt > since_ts) || (m.ackUpdatedAt && m.ackUpdatedAt > since_ts) || (m.mediaUpdatedAt && m.mediaUpdatedAt > since_ts)) : msgs);
});

app.post('/api/send', async (req, res) => {
  const { to, message, mentions, displayBody } = req.body;
  if (!to || !message) return res.status(400).json({ error: 'to and message required' });
  if (status !== 'connected') return res.status(503).json({ error: `Not connected (status: ${status})` });
  try {
    const jid = formatNumber(to);
    dbg(`Sending message to ${jid}: "${message.slice(0,60)}${message.length>60?'…':''}"`);
    // Erwähnungen: Body enthält @<nummer>, mentions = Liste der JIDs
    const opts = {};
    if (Array.isArray(mentions) && mentions.length) {
      opts.mentions = mentions.filter(m => typeof m === 'string' && m.endsWith('@c.us')).slice(0, 100);
    }
    const result = await client.sendMessage(jid, message, opts);
    result.__logged = true;
    const targetChatId = jid;
    if (!chatMap.has(targetChatId)) {
      upsertChat(targetChatId, { name: to.replace('@c.us', '').replace('@g.us', ''), phone: to.replace('@c.us', '').replace('@g.us', '') });
    }
    addMsg(targetChatId, {
      id: result.id._serialized,
      body: message, // enthält @<nummer>; das Frontend löst zu @Name auf (wie bei eingehenden)
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

// Gruppenmitglieder (für @-Erwähnungen) — JID, Nummer und Anzeigename
app.get('/api/participants/:chatId', async (req, res) => {
  const chatId = req.params.chatId;
  if (!chatId.endsWith('@g.us')) return res.json([]);
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  try {
    const chat = await client.getChatById(chatId);
    const parts = (chat && chat.participants) || [];
    const myUser = (connectedPhone || '').replace(/:\d+$/, '');
    const out = [];
    for (const p of parts) {
      const jid = p.id?._serialized;
      const number = p.id?.user;
      if (!jid || !number || number === myUser) continue; // sich selbst nicht erwähnen
      let name = number;
      const c = await client.getContactById(jid).catch(() => null);
      if (c) name = c.name || c.pushname || c.verifiedName || c.shortName || number;
      out.push({ jid, number, name });
    }
    out.sort((a, b) => a.name.localeCompare(b.name));
    res.json(out);
  } catch (e) {
    res.status(500).json({ error: e.message });
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
      const filePath = path.resolve(MEDIA_DIR, `${safeId}.${ext}`);
      if (!filePath.startsWith(path.resolve(MEDIA_DIR) + path.sep)) return res.status(400).json({ error: 'Invalid path' });
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
    } else {
      _logSilent('INFO', `Keep-alive OK — state=${state} chats=${chatMap.size} msgs=${[...messagesByChatId.values()].reduce((s,a)=>s+a.length,0)}`);
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
  const filePath = path.resolve(MEDIA_DIR, filename);
  if (!filePath.startsWith(path.resolve(MEDIA_DIR) + path.sep)) return res.status(400).end();
  if (!existsSync(filePath)) return res.status(404).end();
  const ext = filename.split('.').pop();
  const mime = ext === 'webp' ? 'image/webp' : ext === 'png' ? 'image/png' : ext === 'ogg' ? 'audio/ogg' : ext === 'mp3' ? 'audio/mpeg' : 'image/jpeg';
  res.setHeader('Content-Type', mime);
  // Dateiname leitet sich aus der stabilen Message-ID ab → Inhalt ändert sich nie
  res.setHeader('Cache-Control', 'public, max-age=86400, immutable');
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

// Gedrosselt: höchstens alle 30 s das ganze Media-Verzeichnis scannen, damit
// häufige Downloads den Event-Loop nicht belasten.
let _lastMediaEnforce = 0;
function enforceMediaLimitThrottled() {
  const now = Date.now();
  if (now - _lastMediaEnforce < 30000) return;
  _lastMediaEnforce = now;
  try { enforceMediaLimit(); } catch (e) { console.error('[ERROR] enforceMediaLimit:', e.message); }
}

function enforceMediaLimit() {
  const limitBytes = MEDIA_MAX_MB * 1024 * 1024;
  const targetBytes = limitBytes * 0.8;
  let current = 0, files = [];
  try {
    for (const f of fs.readdirSync(MEDIA_DIR)) {
      const fp = `${MEDIA_DIR}/${f}`;
      try { const st = fs.statSync(fp); files.push({ fp, size: st.size, mtime: st.mtimeMs }); current += st.size; } catch(e) {}
    }
  } catch(e) { return; }
  if (current <= limitBytes) return;
  files.sort((a, b) => a.mtime - b.mtime);
  let freed = 0;
  for (const f of files) {
    if (current - freed <= targetBytes) break;
    try { fs.unlinkSync(f.fp); freed += f.size; console.log(`[INFO] Media-Limit: gelöscht ${f.fp} (${(f.size/1024/1024).toFixed(1)} MB)`); } catch(e) {}
  }
}

// Speicher-Scan ist ein rekursiver Sync-Walk über /config — kurz cachen, damit
// häufige Aufrufe den Event-Loop nicht blockieren.
let _storageCache = null;
const STORAGE_CACHE_MS = 15000;
app.get('/api/storage', (req, res) => {
  if (_storageCache && Date.now() - _storageCache.ts < STORAGE_CACHE_MS) {
    return res.json(_storageCache.data);
  }
  const bytes = getDirSize('/config');
  const mediaBytes = getDirSize(MEDIA_DIR);
  const mediaMb = mediaBytes / 1024 / 1024;
  const data = {
    bytes, mb: (bytes / 1024 / 1024).toFixed(1),
    mediaMb: mediaMb.toFixed(1),
    limitMb: MEDIA_MAX_MB,
    mediaPct: Math.round((mediaMb / MEDIA_MAX_MB) * 100),
  };
  _storageCache = { ts: Date.now(), data };
  res.json(data);
});

app.get('/api/logs', (req, res) => {
  const since = parseInt(req.query.since || '0', 10);
  res.json(since ? _logBuffer.filter(e => e.ts > since) : _logBuffer);
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
  const isEn = (req.query.lang || 'de') === 'en';
  const loc = isEn ? 'en-GB' : 'de-DE';
  const chat = chatMap.get(chatId);
  const msgs = messagesByChatId.get(chatId) || [];
  const chatName = chat ? (chat.name || chatId) : chatId;
  const escH = s => String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const exportDate = new Date().toLocaleString(loc, { day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit' });
  const meLabel = isEn ? 'Me' : 'Du';
  const exportedLabel = isEn ? 'Exported on' : 'Exportiert am';
  const messagesLabel = isEn ? 'messages' : 'Nachrichten';
  let lastDate = '';
  const msgsHtml = msgs.map(m => {
    const tsMs = Number(m.timestamp) > 1e12 ? Number(m.timestamp) : Number(m.timestamp) * 1000;
    const d = new Date(tsMs);
    const dateStr = d.toLocaleDateString(loc, { weekday:'long', day:'2-digit', month:'long', year:'numeric' });
    const time = d.toLocaleTimeString(loc, { hour:'2-digit', minute:'2-digit' });
    let sep = '';
    if (dateStr !== lastDate) { sep = `<div class="day-sep">${escH(dateStr)}</div>`; lastDate = dateStr; }
    let content = '';
    if (m.type === 'video') {
      content = `<span style="opacity:0.6">📹 ${isEn ? 'Video' : 'Video'}</span>`;
      if (m.body) content += `<div style="margin-top:4px">${escH(m.body)}</div>`;
    } else if (m.type === 'location' && m.locLat != null) {
      const mapsUrl = `https://maps.google.com/?q=${m.locLat},${m.locLng}`;
      const label = m.locName || `${parseFloat(m.locLat).toFixed(4)}, ${parseFloat(m.locLng).toFixed(4)}`;
      content = `<a href="${mapsUrl}" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:6px;text-decoration:none;color:inherit"><span>📍</span><span style="text-decoration:underline">${escH(label)}</span></a>`;
    } else if (m.type === 'voice') {
      content = `<span style="opacity:0.6">🎵 ${isEn ? 'Voice message' : 'Sprachnachricht'}</span>`;
    } else if (m.mediaFile && m.type === 'photo') {
      const fp = `${MEDIA_DIR}/${m.mediaFile}`;
      if (fs.existsSync(fp)) {
        const ext = m.mediaFile.split('.').pop().toLowerCase();
        const mime = ext==='png'?'image/png':ext==='webp'?'image/webp':ext==='gif'?'image/gif':'image/jpeg';
        content = `<img src="data:${mime};base64,${fs.readFileSync(fp).toString('base64')}" style="max-width:280px;max-height:280px;border-radius:6px;display:block;">`;
      } else { content = isEn ? '📷 Photo' : '📷 Foto'; }
      if (m.body) content += `<div style="margin-top:4px">${escH(m.body)}</div>`;
    } else if (m.type === 'document' && m.filename) {
      content = `<div style="display:flex;align-items:center;gap:8px"><span style="font-size:22px">📄</span><span style="font-weight:500">${escH(m.filename)}</span></div>`;
      if (m.body) content += `<div style="margin-top:4px">${escH(m.body)}</div>`;
    } else {
      content = escH(m.body||'').replace(/\n/g,'<br>');
    }
    const sender = m.fromMe ? meLabel : escH(chatName);
    return `${sep}<div class="msg ${m.fromMe?'out':'in'}"><div class="bubble"><div class="meta"><span class="sender">${sender}</span><span class="time">${time}</span></div><div class="content">${content}</div></div></div>`;
  }).join('\n');
  const html = `<!DOCTYPE html><html lang="${isEn?'en':'de'}"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Chat: ${escH(chatName)}</title><style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#e5ddd5;min-height:100vh;padding:16px}h1{text-align:center;font-size:18px;color:#333;padding:12px 0 4px}.export-info{text-align:center;font-size:12px;color:#888;margin-bottom:16px}.day-sep{text-align:center;margin:12px 0;font-size:12px;color:#666;background:rgba(255,255,255,.6);border-radius:8px;display:inline-block;padding:2px 10px;width:100%}.msg{display:flex;margin:3px 0}.msg.in{justify-content:flex-start}.msg.out{justify-content:flex-end}.bubble{max-width:70%;padding:7px 10px;border-radius:8px;font-size:14px;line-height:1.45;word-break:break-word}.msg.in .bubble{background:#fff;border-bottom-left-radius:2px}.msg.out .bubble{background:#d9fdd3;border-bottom-right-radius:2px}.meta{display:flex;justify-content:space-between;gap:8px;margin-bottom:3px;font-size:12px}.sender{font-weight:600;color:#25D366}.msg.out .sender{color:#128c7e}.time{color:#999;flex-shrink:0}@media print{body{background:#fff}.msg.out .bubble{background:#e8f5e9}}</style></head><body><h1>${escH(chatName)}</h1><p class="export-info">${exportedLabel} ${exportDate} &bull; ${msgs.length} ${messagesLabel}</p>${msgsHtml}</body></html>`;
  const fname = `whatsapp_${chatName.replace(/[^a-zA-Z0-9_-]/g,'_').slice(0,40)}_${new Date().toISOString().slice(0,10)}.html`;
  res.setHeader('Content-Type','text/html; charset=utf-8');
  res.setHeader('Content-Disposition',`attachment; filename="${fname}"`);
  res.send(html);
});

app.post('/api/messages/delete-batch', async (req, res) => {
  const { chatId, msgIds } = req.body;
  if (!chatId || !Array.isArray(msgIds) || !msgIds.length) return res.status(400).json({ error: 'chatId and msgIds required' });
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  let deleted = 0;
  for (const msgId of msgIds) {
    try {
      const msg = await client.getMessageById(msgId).catch(() => null);
      if (msg) { await msg.delete(true).catch(e => console.log(`[WARN] delete-batch: ${e.message}`)); deleted++; }
      const msgs = messagesByChatId.get(chatId);
      if (msgs) { const s = msgs.find(m => m.id === msgId); if (s) { s.deleted = true; s.body = ''; } }
      await new Promise(r => setTimeout(r, 400));
    } catch(e) { console.log(`[WARN] delete-batch error for ${msgId}: ${e.message}`); }
  }
  saveMsgs();
  res.json({ success: true, deleted });
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

app.post('/api/fetch-video', async (req, res) => {
  const { msgId, chatId } = req.body;
  if (!msgId || !chatId) return res.status(400).json({ error: 'msgId and chatId required' });
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  const stored = getChatMsgs(chatId).find(m => m.id === msgId);
  if (!stored) return res.status(404).json({ error: 'Message not found' });
  if (stored.mediaFile) return res.json({ success: true, mediaFile: stored.mediaFile });
  try {
    const waMsg = await client.getMessageById(msgId).catch(() => null);
    if (!waMsg) return res.status(404).json({ error: 'WA message not found' });
    const videoBytes = waMsg._data?.size || 0;
    if (videoBytes > VIDEO_MAX_MB * 1024 * 1024) return res.status(413).json({ error: `too_large`, maxMb: VIDEO_MAX_MB });
    enforceMediaLimit();
    const mediaFile = await downloadWAMedia(waMsg, msgId);
    if (!mediaFile) return res.status(500).json({ error: 'Download failed' });
    stored.mediaFile = mediaFile;
    saveMsgs();
    res.json({ success: true, mediaFile });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/delete-video', deleteRateLimit, async (req, res) => {
  const { msgId, chatId } = req.body;
  if (!msgId || !chatId) return res.status(400).json({ error: 'msgId and chatId required' });
  const stored = getChatMsgs(chatId).find(m => m.id === msgId);
  if (stored?.mediaFile) {
    try { fs.unlinkSync(`${MEDIA_DIR}/${stored.mediaFile}`); } catch(e) {}
    stored.mediaFile = null;
    saveMsgs();
  }
  res.json({ success: true });
});

app.post('/api/send-location', async (req, res) => {
  const { to, lat, lng, locName } = req.body;
  if (!to || lat == null || lng == null) return res.status(400).json({ error: 'to, lat, lng required' });
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  try {
    const loc = new Location(parseFloat(lat), parseFloat(lng), locName || '');
    const result = await client.sendMessage(to, loc);
    result.__logged = true;
    const ts = Date.now();
    addMsg(to, { id: result.id._serialized, body: '', type: 'location', locLat: parseFloat(lat), locLng: parseFloat(lng), locName: locName || '', timestamp: ts, fromMe: true });
    saveMsgs();
    res.json({ success: true });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/reply', async (req, res) => {
  const { quotedMsgId, chatId, message, mentions, displayBody } = req.body;
  if (!quotedMsgId || !chatId || !message) return res.status(400).json({ error: 'quotedMsgId, chatId and message required' });
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  try {
    const qMsg = await client.getMessageById(quotedMsgId);
    if (!qMsg) throw new Error('Quoted message not found');
    const opts = {};
    if (Array.isArray(mentions) && mentions.length) {
      opts.mentions = mentions.filter(m => typeof m === 'string' && m.endsWith('@c.us')).slice(0, 100);
    }
    const result = await qMsg.reply(message, undefined, opts);
    result.__logged = true;
    addMsg(chatId, {
      id: result.id._serialized,
      body: message, // @<nummer>; Frontend löst zu @Name auf
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
  promise.then(() => avatarPending.delete(chatId), () => avatarPending.delete(chatId));

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

app.get('/api/statuses-available', async (req, res) => {
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  try {
    const broadcasts = await client.getBroadcasts();
    const ids = broadcasts.filter(b => b.msgs && b.msgs.length).map(b => b.id._serialized);
    res.json({ ids });
  } catch(e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/status/:chatId', async (req, res) => {
  const chatId = req.params.chatId;
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  try {
    const broadcast = await client.getBroadcastById(chatId).catch(() => null);
    const raw = broadcast?.msgs || [];
    const msgs = [];
    for (const m of raw) {
      const isImage = m.type === 'image';
      const isVideo = m.type === 'video';
      let mediaFile = null;
      if (DOWNLOAD_MEDIA && (isImage || isVideo) && m.hasMedia) {
        mediaFile = await downloadWAMedia(m, m.id._serialized || m.id.id).catch(() => null);
      }
      msgs.push({
        id: m.id._serialized || m.id.id,
        type: isImage ? 'photo' : isVideo ? 'video' : 'text',
        body: m.body || '',
        timestamp: m.timestamp * 1000,
        mediaFile,
      });
    }
    res.json({ msgs });
  } catch(e) {
    res.status(500).json({ error: e.message });
  }
});

// ── Web UI ────────────────────────────────────────────────────────────────────
const _SVG = {
  moon:       '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
  sun:        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>',
  disk:       '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;flex-shrink:0"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>',
  imageOn:    '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>',
  imageOff:   '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>',
  trash:      '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>',
  chevUp:     '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg>',
  chevDown:   '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>',
  chevLeft:   '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>',
  download:   '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
  x:          '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  smile:      '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>',
  paperclip:  '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>',
  pin:        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>',
  doc:        '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
};

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
      padding: 4px 8px; border-radius: 6px; cursor: pointer; opacity: 0.55; line-height: 1;
      display: inline-flex; align-items: center; justify-content: center;
    }
    .photo-toggle-btn:hover { opacity: 0.8; }
    .photo-toggle-btn.active { opacity: 1; background: rgba(60,219,124,0.15); border-color: #3cdb7c; color: #3cdb7c; }
    .scroll-btn { background: none; border: 1px solid #8696a0; color: #e9edef; padding: 4px 8px; border-radius: 6px; cursor: pointer; opacity: 0.55; line-height: 1; display: inline-flex; align-items: center; justify-content: center; }
    .scroll-btn:hover { opacity: 0.8; }
    .photo-placeholder { display: none; }
    body.hide-photos .msg-img { display: none !important; }
    body.hide-photos .photo-placeholder { display: inline; }
    body.hide-photos video { display: none !important; }
    body.hide-photos .wa-video-placeholder { display: none !important; }

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
    .avatar.has-status { box-shadow: 0 0 0 2px #25D366; animation: statusPulse 2s ease-in-out infinite; }
    @keyframes statusPulse {
      0%, 100% { box-shadow: 0 0 0 2px #25D366; }
      50% { box-shadow: 0 0 0 2px #25D366, 0 0 0 5px rgba(37,211,102,0.4); }
    }
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
    .contact-modal-status { display: none; flex-direction: column; gap: 8px; width: 100%; max-height: 240px; overflow-y: auto; }
    .contact-modal-status.has-items { display: flex; }
    .status-label { font-size: 12px; font-weight: 600; opacity: 0.6; }
    .status-item { border-radius: 8px; padding: 6px; display: flex; flex-direction: column; gap: 4px; }
    html.dark .status-item { background: rgba(255,255,255,0.05); }
    html.light .status-item { background: rgba(0,0,0,0.05); }
    .status-item img, .status-item video { max-width: 100%; max-height: 180px; border-radius: 6px; display: block; cursor: zoom-in; }
    .status-item .status-text { font-size: 13px; word-break: break-word; }
    .status-item .status-time { font-size: 11px; color: #8696a0; }
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
    #msg-search-btn { background: none; border: 1px solid rgba(134,150,160,0.5); color: #8696a0; padding: 5px 8px; border-radius: 6px; cursor: pointer; flex-shrink: 0; line-height: 1; display: inline-flex; align-items: center; margin-left: auto; }
    #msg-search-btn:hover { border-color: #3cdb7c; color: #3cdb7c; }
    #msg-search-btn.active { border-color: #3cdb7c; color: #3cdb7c; }
    html.light #msg-search-btn:hover, html.light #msg-search-btn.active { border-color: #25d366; color: #25d366; }
    #export-btn, #spam-delete-btn { background: none; border: 1px solid rgba(134,150,160,0.5); color: #8696a0; padding: 5px 8px; border-radius: 6px; cursor: pointer; flex-shrink: 0; line-height: 1; display: inline-flex; align-items: center; justify-content: center; }
    #export-btn:hover { border-color: #3cdb7c; color: #3cdb7c; }
    #spam-delete-btn:hover { border-color: #f15c5c; color: #f15c5c; }
    #spam-delete-btn:disabled { opacity: 0.4; cursor: default; }
    #delete-mode-btn { background: none; border: 1px solid rgba(134,150,160,0.5); color: #8696a0; padding: 5px 8px; border-radius: 6px; cursor: pointer; flex-shrink: 0; line-height: 1; display: inline-flex; align-items: center; justify-content: center; transition: color 0.15s, border-color 0.15s; }
    #delete-mode-btn:hover { border-color: #f15c5c; color: #f15c5c; }
    #delete-mode-btn.active { border-color: #f15c5c; color: #f15c5c; }
    #messages.delete-mode .bubble-wrap { cursor: pointer; }
    #messages.delete-mode .del-btn, #messages.delete-mode .react-btn, #messages.delete-mode .fwd-btn, #messages.delete-mode .reply-btn { display: none !important; }
    .bubble-wrap.selected .bubble { background: rgba(231,76,60,0.18) !important; outline: 1px solid rgba(231,76,60,0.45); border-radius: 8px; }
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
    .reply-btn { opacity:0; pointer-events:none; background:none; border:none; cursor:pointer; font-size:15px; padding:4px 6px; line-height:1; border-radius:6px; flex-shrink:0; color:rgba(233,237,239,0.6); }
    .bubble-row-inner:hover .reply-btn { opacity:1; pointer-events:auto; }
    html.light .reply-btn { color:rgba(0,0,0,0.4); }
    .bubble-wrap.out .react-btn, .bubble-wrap.out .fwd-btn, .bubble-wrap.out .reply-btn { order: -1; }
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
    #attach-icon { flex-shrink:0; display:flex; align-items:center; justify-content:center; color:#8696a0; }
    #attach-cancel { background:none; border:none; color:#8696a0; cursor:pointer; line-height:1; padding:4px; flex-shrink:0; display:inline-flex; align-items:center; justify-content:center; }
    #attach-cancel:hover { color:#e9edef; }
    #send-bar #attach-btn, #send-bar #location-btn { background:none; border:none; cursor:pointer; padding:6px; border-radius:50%; flex-shrink:0; line-height:1; color:#8696a0; width:auto; height:auto; display:inline-flex; align-items:center; justify-content:center; }
    #send-bar #attach-btn:hover, #send-bar #location-btn:hover { background:rgba(255,255,255,0.08); }
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
    #reply-close { background:none; border:none; color:#8696a0; cursor:pointer; line-height:1; padding:4px; flex-shrink:0; display:inline-flex; align-items:center; justify-content:center; }
    #reply-close:hover { color:#e9edef; }

    #msg-search-bar {
      display: none; align-items: center; gap: 8px;
      background: #202c33; padding: 6px 12px; border-bottom: 1px solid #2a3942; flex-shrink: 0;
    }
    #msg-search-bar.open { display: flex; }
    #msg-search-input {
      flex: 1; background: #2a3942; border: none; border-radius: 6px;
      padding: 6px 10px; color: #e9edef; font-size: 13px; outline: none; font-family: inherit;
    }
    #msg-search-input::placeholder { color: #8696a0; }
    #msg-search-nav { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
    #msg-search-count { font-size: 12px; color: #8696a0; min-width: 40px; text-align: center; }
    .msg-search-nav-btn { background: none; border: none; color: #8696a0; cursor: pointer; padding: 4px 6px; line-height: 1; border-radius: 4px; display: inline-flex; align-items: center; justify-content: center; }
    .msg-search-nav-btn:hover { color: #e9edef; background: rgba(255,255,255,0.08); }
    .msg-search-nav-btn:disabled { opacity: 0.3; cursor: default; }
    #msg-search-close { background: none; border: none; color: #8696a0; cursor: pointer; padding: 4px; line-height: 1; display: inline-flex; align-items: center; justify-content: center; }
    #msg-search-close:hover { color: #e9edef; }
    .msg-highlight { background: rgba(255,214,0,0.35) !important; border-radius: 3px; }
    .msg-highlight-active { background: rgba(255,165,0,0.55) !important; }
    html.light #msg-search-bar { background: #075e54; border-color: #056b4e; }
    html.light #msg-search-input { background: rgba(255,255,255,0.2); color: #fff; }
    html.light #msg-search-input::placeholder { color: rgba(255,255,255,0.6); }
    html.light .msg-search-nav-btn, html.light #msg-search-close { color: rgba(255,255,255,0.7); }
    html.light .msg-search-nav-btn:hover, html.light #msg-search-close:hover { color: #fff; }

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
    .react-btn { opacity: 0; pointer-events: none; background: none; border: none; cursor: pointer; font-size: 16px; padding: 4px; line-height: 1; border-radius: 50%; color: rgba(233,237,239,0.55); flex-shrink: 0; display: inline-flex; align-items: center; }
    .bubble-row-inner:hover .react-btn { opacity: 1; pointer-events: auto; }
    html.light .react-btn { color: rgba(0,0,0,0.35); }
    .react-btn:hover { background: rgba(134,150,160,0.18); color: #e9edef; }
    html.light .react-btn:hover { color: #111; }
    .fwd-btn { opacity: 0; pointer-events: none; background: none; border: none; cursor: pointer; font-size: 15px; padding: 4px 6px; line-height: 1; border-radius: 6px; flex-shrink: 0; color: rgba(233,237,239,0.6); }
    .bubble-row-inner:hover .fwd-btn { opacity: 1; pointer-events: auto; }
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
    .bubble.bubble-photo { padding: 0; overflow: hidden; max-width: 280px; }
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
    #emoji-picker { display: none; flex-direction: column; position: absolute; bottom: 100%; left: 0; right: 0; background: #202c33; border-top: 1px solid #2a3942; padding: 8px 10px; height: 280px; z-index: 20; box-shadow: 0 -2px 8px rgba(0,0,0,0.2); }
    #emoji-picker.open { display: flex; }
    #emoji-search { width: 100%; box-sizing: border-box; padding: 6px 10px; margin-bottom: 6px; border: none; border-radius: 8px; background: #2a3942; color: #e9edef; font-size: 14px; outline: none; flex: 0 0 auto; }
    #emoji-search::placeholder { color: #8696a0; }
    #emoji-tabs { display: flex; gap: 2px; overflow-x: auto; flex: 0 0 auto; margin-bottom: 6px; scrollbar-width: none; }
    #emoji-tabs::-webkit-scrollbar { display: none; }
    #emoji-tabs .emoji-tab { background: none; border: none; width: auto; height: auto; font-size: 20px; cursor: pointer; padding: 4px 6px; border-radius: 8px; line-height: 1; opacity: 0.55; flex: 0 0 auto; }
    #emoji-tabs .emoji-tab:hover { background: #2a3942; }
    #emoji-tabs .emoji-tab.active { opacity: 1; background: #2a3942; }
    .emoji-grid { display: flex; flex-wrap: wrap; gap: 2px; align-content: flex-start; overflow-y: auto; flex: 1 1 auto; }
    .emoji-empty { color: #8696a0; font-size: 13px; padding: 12px; }
    #send-bar .emoji-btn { background: none; border: none; font-size: 22px; cursor: pointer; padding: 3px 5px; border-radius: 6px; line-height: 1; width: auto; height: auto; }
    #send-bar .emoji-btn:hover { background: #2a3942; }
    #send-bar #emoji-toggle { background: none; border: none; cursor: pointer; padding: 6px; border-radius: 50%; flex-shrink: 0; line-height: 1; color: #8696a0; width: auto; height: auto; display: inline-flex; align-items: center; justify-content: center; }
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
      color: #e9edef; cursor: pointer; padding: 4px 8px 4px 0; align-items: center; justify-content: center;
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
      /* Chat-Header-Buttons kleiner */
      #export-btn, #spam-delete-btn, #delete-mode-btn, #msg-search-btn { padding: 4px 5px; }
      /* Send-Bar kompakter */
      #send-bar { padding: 6px 8px; gap: 4px; }
      #send-bar #emoji-toggle, #send-bar #attach-btn, #send-bar #location-btn { font-size: 17px; padding: 4px; }
      #msg-input { padding: 7px 10px; min-height: 36px; }
    }

    /* Overlays */
    .overlay {
      position: fixed; inset: 0; background: #111b21; z-index: 100;
      display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 20px;
    }
    .overlay p { color: #8696a0; font-size: 14px; text-align: center; line-height: 1.7; }
    .overlay h2 { font-size: 20px; }
    #qr-overlay img { background: #fff; padding: 16px; border-radius: 12px; max-width: 280px; }

    #mention-dropdown { position: fixed; z-index: 200; background: #233138; border: 1px solid rgba(255,255,255,0.12); border-radius: 10px; max-height: 240px; overflow-y: auto; box-shadow: 0 6px 20px rgba(0,0,0,0.45); padding: 4px 0; }
    .mention-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; cursor: pointer; font-size: 14px; color: #e9edef; }
    .mention-item.active, .mention-item:hover { background: #2a3942; }
    .mention-av { width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; color: #fff; background: #5b6b7a; flex-shrink: 0; }
    .mention-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .mention-ref { color: #53bdeb; font-weight: 500; }
    html.light .mention-ref { color: #1f7aad; }
    html.light #mention-dropdown { background: #fff; border-color: #ddd; }
    html.light .mention-item { color: #111; }
    html.light .mention-item.active, html.light .mention-item:hover { background: #f0f2f5; }

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
    html.light #emoji-search { background: #f0f2f5; color: #111; }
    html.light #emoji-search::placeholder { color: #999; }
    html.light #emoji-tabs .emoji-tab:hover { background: #f0f2f5; }
    html.light #emoji-tabs .emoji-tab.active { background: #e9edef; }
    html.light #send-bar .emoji-btn:hover { background: #f0f2f5; }
    html.light #send-bar #emoji-toggle { color: #555; }

    /* ── Offline-Banner ── */
    #offline-banner { display:none; position:fixed; inset:0; z-index:800; background:rgba(0,0,0,0.72); backdrop-filter:blur(4px); -webkit-backdrop-filter:blur(4px); flex-direction:column; align-items:center; justify-content:center; gap:14px; }
    .ob-icon { font-size:44px; animation:ob-pulse 1.8s ease-in-out infinite; }
    .ob-title { font-size:16px; font-weight:600; color:#e9edef; }
    .ob-sub { font-size:13px; color:#8696a0; }
    .ob-reload { background:#2a3942; border:1px solid #3d5259; color:#e9edef; border-radius:8px; padding:8px 22px; font-size:13px; cursor:pointer; margin-top:4px; }
    .ob-reload:hover { background:#3d5259; border-color:#5a7a87; }
    @keyframes ob-pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
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
    <h1 ondblclick="waConsoleToggle()" style="cursor:default;user-select:none;" title="Doppelklick: Console">WhatsApp</h1>
    <button id="theme-btn" onclick="toggleTheme()" title="Dark / Light Mode" style="background:none;border:none;cursor:pointer;padding:4px;line-height:1;flex-shrink:0;opacity:0.75;display:inline-flex;align-items:center;justify-content:center;color:#8696a0;"></button>
    <div class="status-dot connected" id="status-dot" data-i18n-title="statusConnected" title="Verbunden"></div>
    <span class="storage-info" id="storage-info"></span>
    ${DOWNLOAD_MEDIA ? `<button id="photo-toggle" class="photo-toggle-btn active" onclick="togglePhotos()" data-i18n-title="photosOn" title="Medien AN">${_SVG.imageOn}</button>` : ''}
    ${DOWNLOAD_MEDIA ? `<button class="scroll-btn" onclick="cleanupMedia()" data-i18n-title="btnCleanup" title="Verwaiste Mediendateien löschen">${_SVG.trash}</button>` : ''}
    <button class="scroll-btn" onclick="scrollMsgs('top')" data-i18n-title="btnScrollUp" title="Nach oben">${_SVG.chevUp}</button>
    <button class="scroll-btn" onclick="scrollMsgs('bottom')" data-i18n-title="btnScrollDown" title="Nach unten">${_SVG.chevDown}</button>
    <button id="lang-btn" class="scroll-btn" onclick="switchLang()" title="Sprache / Language" style="font-size:13px;padding:0 8px;font-weight:500;">DE</button>
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
        <button id="back-btn" onclick="closeChat()" data-i18n-title="btnBack" title="Zurück">${_SVG.chevLeft}</button>
        <div class="avatar" id="ch-avatar"></div>
        <div id="ch-info">
          <div id="ch-name"></div>
          <div id="ch-phone"></div>
          <div id="ch-stats"></div>
        </div>
        <button id="msg-search-btn" onclick="toggleMsgSearch()" data-i18n-title="ttMsgSearch" title="Nachrichten durchsuchen"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg></button>
        <button id="export-btn" onclick="exportChat()" data-i18n-title="ttExport" title="Chat exportieren">${_SVG.download}</button>
        <button id="spam-delete-btn" onclick="deleteSpam()" data-i18n-title="ttSpamDelete" title="Häufig weitergeleitete Nachrichten löschen">${_SVG.trash}</button>
        <button id="delete-mode-btn" onclick="toggleDeleteMode()" title="Nachrichten löschen">${_SVG.x}</button>
      </div>
      <div id="msg-search-bar">
        <input id="msg-search-input" type="text" data-i18n-pl="msgSearchPlaceholder" placeholder="Suchen…" oninput="onMsgSearchInput(this.value)" onkeydown="if(event.key==='Escape')closeMsgSearch();">
        <div id="msg-search-nav">
          <button class="msg-search-nav-btn" id="msg-search-prev" onclick="stepMsgSearch(-1)" title="Vorheriger">${_SVG.chevUp}</button>
          <span id="msg-search-count"></span>
          <button class="msg-search-nav-btn" id="msg-search-next" onclick="stepMsgSearch(1)" title="Nächster">${_SVG.chevDown}</button>
        </div>
        <button id="msg-search-close" onclick="closeMsgSearch()">${_SVG.x}</button>
      </div>
      <div id="messages" style="display:none;"></div>
      <div id="reply-bar">
        <div class="reply-bar-content">
          <div id="reply-bar-sender"></div>
          <div id="reply-bar-text"></div>
        </div>
        <button id="reply-close" onclick="clearReply()">${_SVG.x}</button>
      </div>
      <div id="attach-bar">
        <div class="attach-preview">
          <img id="attach-thumb" alt="">
          <span id="attach-icon">${_SVG.doc}</span>
          <div class="attach-info">
            <span id="attach-name"></span>
            <span id="attach-size"></span>
          </div>
        </div>
        <button id="attach-cancel" onclick="clearAttach()">${_SVG.x}</button>
      </div>
      <div id="send-bar" style="display:none;">
        <input type="file" id="file-input" style="display:none;" onchange="onFileSelected(event)">
        <div id="emoji-picker">
          <input id="emoji-search" type="text" data-i18n-pl="emojiSearch" placeholder="Suchen…" oninput="onEmojiSearch(this.value)">
          <div id="emoji-tabs"></div>
          <div class="emoji-grid" id="emoji-grid"></div>
        </div>
        <div style="display:flex;align-items:center;gap:0;flex-shrink:0;">
          <button id="emoji-toggle" onclick="toggleEmojiPicker(event)" data-i18n-title="btnEmoji" title="Emoji">${_SVG.smile}</button>
          <button id="attach-btn" onclick="document.getElementById('file-input').click()" data-i18n-title="btnAttach" title="Datei anhängen">${_SVG.paperclip}</button>
          <button id="location-btn" onclick="openLocationModal()" data-i18n-title="btnLocation" title="Standort senden">${_SVG.pin}</button>
        </div>
        <textarea id="msg-input" rows="1" data-i18n-pl="msgInput" placeholder="Nachricht…"
          onkeydown="onMsgInputKeydown(event)"
          oninput="autoResize(this);onMentionInput(this)"></textarea>
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
      <div class="contact-modal-status" id="contact-modal-status"></div>
      <button class="contact-modal-close" onclick="closeContactModal()" data-i18n="btnClose">Schließen</button>
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
  <div id="location-modal" onclick="if(event.target===this)closeLocationModal()" style="display:none;position:fixed;inset:0;z-index:400;background:rgba(0,0,0,0.6);align-items:center;justify-content:center;">
    <div style="background:#202c33;border-radius:12px;padding:20px;width:min(340px,92%);display:flex;flex-direction:column;gap:10px;box-shadow:0 8px 32px rgba(0,0,0,0.5);">
      <h3 style="font-size:15px;font-weight:600;color:#e9edef;margin:0" data-i18n="locModalTitle">📍 Standort senden</h3>
      <button onclick="useGPSLocation()" style="background:#2a3942;border:none;color:#3cdb7c;padding:8px 12px;border-radius:8px;cursor:pointer;font-size:14px;text-align:left;" data-i18n="locUseGPS">📡 Aktuelle Position</button>
      <input id="loc-lat" type="number" step="any" placeholder="Breitengrad (z.B. 48.137)" style="background:#2a3942;border:none;color:#e9edef;padding:8px 10px;border-radius:8px;font-size:14px;outline:none;" data-i18n-pl="locLat">
      <input id="loc-lng" type="number" step="any" placeholder="Längengrad (z.B. 11.575)" style="background:#2a3942;border:none;color:#e9edef;padding:8px 10px;border-radius:8px;font-size:14px;outline:none;" data-i18n-pl="locLng">
      <input id="loc-name" type="text" placeholder="Name (optional)" style="background:#2a3942;border:none;color:#e9edef;padding:8px 10px;border-radius:8px;font-size:14px;outline:none;" data-i18n-pl="locNameLbl">
      <div style="display:flex;gap:8px;margin-top:4px;">
        <button onclick="closeLocationModal()" style="flex:1;background:#2a3942;border:none;color:#8696a0;padding:8px;border-radius:8px;cursor:pointer;font-size:14px;" data-i18n="locCancel">Abbrechen</button>
        <button onclick="sendLocationMsg()" style="flex:1;background:#00a884;border:none;color:#fff;padding:8px;border-radius:8px;cursor:pointer;font-size:14px;font-weight:600;" data-i18n="locSend">Senden</button>
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

  <div id="offline-banner">
    <div class="ob-icon">📡</div>
    <div class="ob-title" data-i18n="offlineTitle">Verbindung unterbrochen</div>
    <div class="ob-sub" data-i18n="offlineSub">Stelle Verbindung wieder her…</div>
    <button class="ob-reload" onclick="window.location.reload()" data-i18n="offlineReload">Neu laden</button>
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
        photosOn:'Medien AN', photosOff:'Medien AUS', btnCleanup:'Verwaiste Mediendateien löschen',
        btnScrollUp:'Nach oben', btnScrollDown:'Nach unten', btnLogout:'Abmelden',
        filterAll:'Alle', filterPrivate:'Privat', filterGroups:'Gruppen',
        searchChats:'🔍  Chats durchsuchen…', loadingChats:'Lade Chats…',
        welcomeMsg:'Wähle einen Chat aus der Liste', noChats:'Keine Chats',
        btnBack:'Zurück',
        ttExport:'Chat als HTML exportieren', ttSpamDelete:'Häufig weitergeleitete Nachrichten löschen', btnSpamDelete:'Spam löschen',
        ttMsgSearch:'Nachrichten durchsuchen', msgSearchPlaceholder:'Suchen…', msgSearchNoResult:'Keine Treffer',
        deleteMode:'Nachrichten löschen', deleteModeCancel:'Abbrechen', deleteConfirm:(n)=>n+(n===1?' Nachricht':' Nachrichten')+' wirklich löschen?',
        btnEmoji:'Emoji', btnAttach:'Datei anhängen', btnLocation:'Standort senden', msgInput:'Nachricht…', attachCaption:'Bildunterschrift (optional)…', btnSend:'Senden',
        emojiSearch:'Suchen…', emojiNone:'Keine Treffer', emojiRecent:'Zuletzt', emojiCatSmileys:'Smileys & Personen', emojiCatAnimals:'Tiere & Natur', emojiCatFood:'Essen & Trinken', emojiCatActivity:'Aktivitäten', emojiCatTravel:'Reisen & Orte', emojiCatObjects:'Objekte', emojiCatSymbols:'Symbole', emojiCatFlags:'Flaggen',
        locModalTitle:'📍 Standort senden', locLat:'Breitengrad', locLng:'Längengrad', locNameLbl:'Name (optional)', locUseGPS:'📡 Aktuelle Position', locSend:'Senden', locCancel:'Abbrechen', locGPSErr:'GPS nicht verfügbar', locLabel:'Standort',
        videoDownload:'⬇ Video herunterladen', videoTooBig:'📹 Video — zu groß (max ${VIDEO_MAX_MB} MB)',
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
        offlineTitle:'Verbindung unterbrochen', offlineSub:'Stelle Verbindung wieder her…', offlineReload:'Neu laden',
        btnClose:'Schließen', statusUpdates:'Status',
      },
      en: {
        spinnerConnecting:'Connecting to WhatsApp…', btnReset:'Reset Session',
        statusConnected:'Connected', statusQR:'Scan QR', statusAuth:'Authenticating…',
        statusInit:'Starting…', statusDisc:'Disconnected', statusAuthFail:'Auth error', statusError:'Error',
        photosOn:'Media ON', photosOff:'Media OFF', btnCleanup:'Delete orphaned media files',
        btnScrollUp:'Scroll up', btnScrollDown:'Scroll down', btnLogout:'Logout',
        filterAll:'All', filterPrivate:'Private', filterGroups:'Groups',
        searchChats:'🔍  Search chats…', loadingChats:'Loading chats…',
        welcomeMsg:'Select a chat from the list', noChats:'No chats',
        btnBack:'Back',
        ttExport:'Export chat as HTML', ttSpamDelete:'Delete frequently forwarded messages', btnSpamDelete:'Delete Spam',
        ttMsgSearch:'Search messages', msgSearchPlaceholder:'Search…', msgSearchNoResult:'No results',
        deleteMode:'Delete messages', deleteModeCancel:'Cancel', deleteConfirm:(n)=>'Really delete '+n+' message'+(n===1?'':'s')+'?',
        btnEmoji:'Emoji', btnAttach:'Attach file', btnLocation:'Send location', msgInput:'Message…', attachCaption:'Caption (optional)…', btnSend:'Send',
        emojiSearch:'Search…', emojiNone:'No results', emojiRecent:'Recent', emojiCatSmileys:'Smileys & People', emojiCatAnimals:'Animals & Nature', emojiCatFood:'Food & Drink', emojiCatActivity:'Activities', emojiCatTravel:'Travel & Places', emojiCatObjects:'Objects', emojiCatSymbols:'Symbols', emojiCatFlags:'Flags',
        locModalTitle:'📍 Send Location', locLat:'Latitude', locLng:'Longitude', locNameLbl:'Name (optional)', locUseGPS:'📡 Use current position', locSend:'Send', locCancel:'Cancel', locGPSErr:'GPS not available', locLabel:'Location',
        videoDownload:'⬇ Download video', videoTooBig:'📹 Video — too large (max ${VIDEO_MAX_MB} MB)',
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
        offlineTitle:'Connection lost', offlineSub:'Reconnecting…', offlineReload:'Reload',
        btnClose:'Close', statusUpdates:'Status',
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
      if (lb) lb.textContent = lang === 'de' ? 'DE' : 'EN';
      const ptb = document.getElementById('photo-toggle');
      if (ptb) ptb.title = document.body.classList.contains('hide-photos') ? t('photosOff') : t('photosOn');
    }
    function switchLang() {
      lang = lang === 'de' ? 'en' : 'de';
      localStorage.setItem('wa_lang', lang);
      applyLang();
    }
    function applyTheme() {
      var isDark = document.documentElement.classList.contains('dark');
      var btn = document.getElementById('theme-btn');
      if (btn) btn.innerHTML = isDark ? '${_SVG.sun}' : '${_SVG.moon}';
    }
    function toggleTheme() {
      var html = document.documentElement;
      var nowDark = html.classList.contains('dark');
      html.classList.toggle('dark', !nowDark);
      html.classList.toggle('light', nowDark);
      localStorage.setItem('wa_theme', nowDark ? 'light' : 'dark');
      applyTheme();
    }
    (function() {
      var saved = localStorage.getItem('wa_theme');
      if (saved) {
        document.documentElement.classList.remove('dark', 'light');
        document.documentElement.classList.add(saved);
      }
      applyTheme();
    })();
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
    let isDeleteMode = false;
    const selectedMsgs = new Set();
    function toggleDeleteMode() {
      if (!isDeleteMode) { enterDeleteMode(); return; }
      if (selectedMsgs.size > 0) confirmDeleteSelected(); else exitDeleteMode();
    }
    function enterDeleteMode() {
      isDeleteMode = true; selectedMsgs.clear(); updateDeleteBtn();
      document.getElementById('messages').classList.add('delete-mode');
    }
    function exitDeleteMode() {
      isDeleteMode = false; selectedMsgs.clear();
      document.querySelectorAll('#messages .bubble-wrap.selected').forEach(function(w){ w.classList.remove('selected'); });
      updateDeleteBtn();
      document.getElementById('messages').classList.remove('delete-mode');
    }
    function updateDeleteBtn() {
      var btn = document.getElementById('delete-mode-btn');
      if (!btn) return;
      var n = selectedMsgs.size;
      if (!isDeleteMode) { btn.innerHTML = '${_SVG.x}'; btn.classList.remove('active'); btn.title = t('deleteMode'); }
      else if (n === 0) { btn.innerHTML = '${_SVG.x}'; btn.classList.add('active'); btn.title = t('deleteModeCancel'); }
      else { btn.innerHTML = n + ' ${_SVG.trash}'; btn.classList.add('active'); btn.title = tf('deleteConfirm', n); }
    }
    async function confirmDeleteSelected() {
      var n = selectedMsgs.size;
      if (!confirm(tf('deleteConfirm', n))) return;
      var chatId = selectedChatId;
      var ids = Array.from(selectedMsgs);
      exitDeleteMode();
      await fetch('api/messages/delete-batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chatId: chatId, msgIds: ids })
      });
      await reloadMessages(chatId);
    }
    function openLocationModal() {
      document.getElementById('loc-lat').value = '';
      document.getElementById('loc-lng').value = '';
      document.getElementById('loc-name').value = '';
      document.getElementById('location-modal').style.display = 'flex';
      document.getElementById('loc-lat').focus();
    }
    function closeLocationModal() { document.getElementById('location-modal').style.display = 'none'; }
    function useGPSLocation() {
      if (!navigator.geolocation) { alert(t('locGPSErr')); return; }
      navigator.geolocation.getCurrentPosition(function(pos) {
        document.getElementById('loc-lat').value = pos.coords.latitude.toFixed(6);
        document.getElementById('loc-lng').value = pos.coords.longitude.toFixed(6);
      }, function() { alert(t('locGPSErr')); });
    }
    async function sendLocationMsg() {
      var lat = parseFloat(document.getElementById('loc-lat').value);
      var lng = parseFloat(document.getElementById('loc-lng').value);
      var name = document.getElementById('loc-name').value.trim();
      if (isNaN(lat) || isNaN(lng)) return;
      closeLocationModal();
      try {
        await fetch('api/send-location', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ to: selectedChatId, lat: lat, lng: lng, locName: name }) });
        await reloadMessages(selectedChatId);
      } catch(e) { console.error('sendLocation:', e.message); }
    }
    async function fetchWAVideo(el) {
      const msgId = el.dataset.msgid;
      const chatId = el.dataset.chatid || selectedChatId;
      el.textContent = '⏳';
      el.style.pointerEvents = 'none';
      try {
        const r = await fetch('api/fetch-video', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ msgId, chatId }) }).then(r => r.json());
        if (r.error === 'too_large') { el.textContent = t('videoTooBig'); el.style.textDecoration = 'none'; el.style.cursor = 'default'; el.onclick = null; return; }
        if (r.success) { await reloadMessages(selectedChatId); loadStorage(); }
        else { el.textContent = '❌'; }
      } catch(e) { el.textContent = '❌'; }
    }
    async function deleteWAVideo(msgId) {
      try {
        await fetch('api/delete-video', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ msgId, chatId: selectedChatId }) });
        await reloadMessages(selectedChatId);
        loadStorage();
      } catch(e) { console.error('deleteWAVideo:', e.message); }
    }
    let lastMsgTime = {};
    let allChats = [];
    let lastSeenTime = {};
    let _statusChatIds = new Set();
    async function pollStatuses() {
      if (document.hidden || currentStatus !== 'connected') return;
      try {
        const sd = await fetch('api/statuses-available').then(r => r.json());
        _statusChatIds = new Set(sd.ids || []);
        renderChatList(allChats);
      } catch(e) {}
    }
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
    function mentionName(num) {
      const list = _mentionParticipants[selectedChatId] || [];
      const p = list.find(x => x.number === num);
      if (p && p.name && p.name !== num) return p.name;
      return '+' + num; // kein Name bekannt → wenigstens mit + formatieren
    }
    function formatText(s) {
      let html = String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');
      html = html.replace(/((https?:\\/\\/|www\\.)[^\\s<>"&]+)/gi, function(m) {
        let url = m.replace(/[.,!?;:)]+$/, '');
        const trail = m.slice(url.length);
        const href = url.startsWith('www.') ? 'https://' + url : url;
        return '<a href="' + href + '" target="_blank" rel="noopener noreferrer" style="color:#53bdeb;text-decoration:underline;">' + url + '</a>' + trail;
      });
      // Erwähnungen: @<nummer> → @Name (deckt eingehende wie eigene Nachrichten ab);
      // Lookbehind verhindert Treffer in URLs wie user@12345.com
      html = html.replace(/(?<!\\w)@(\\d{5,})/g, function(_m, num) {
        return '<span class="mention-ref">@' + esc(mentionName(num)) + '</span>';
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
        if (!el) return;
        el.innerHTML = '${_SVG.disk} ' + d.mb + ' MB';
        if (d.mediaMb !== undefined) {
          const autoAt = d.limitMb, autoTo = Math.round(d.limitMb * 0.8);
          el.title = lang === 'de'
            ? 'Gesamt /config: ' + d.mb + ' MB\\nMedienordner: ' + d.mediaMb + ' MB von ' + autoAt + ' MB (' + d.mediaPct + '%)\\nAuto-Delete startet bei ' + autoAt + ' MB, l\xF6scht auf ' + autoTo + ' MB'
            : 'Total /config: ' + d.mb + ' MB\\nMedia folder: ' + d.mediaMb + ' MB of ' + autoAt + ' MB (' + d.mediaPct + '%)\\nAuto-delete starts at ' + autoAt + ' MB, cleans to ' + autoTo + ' MB';
        }
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
      if (btn) { btn.classList.toggle('active', !hiding); btn.innerHTML = hiding ? '${_SVG.imageOff}' : '${_SVG.imageOn}'; btn.title = hiding ? t('photosOff') : t('photosOn'); }
      localStorage.setItem('wa-hide-photos', hiding ? '1' : '');
    }
    if (localStorage.getItem('wa-hide-photos')) {
      document.body.classList.add('hide-photos');
      const btn = document.getElementById('photo-toggle');
      if (btn) { btn.classList.remove('active'); btn.innerHTML = '${_SVG.imageOff}'; btn.title = t('photosOff'); }
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

    // ── Emoji-Picker mit Kategorien, Suche & „Zuletzt verwendet" ─────────────────
    const EMOJI_RECENT_KEY = 'wa_emoji_recent';
    const EMOJI_CAT_ICON = { recent:'🕐', smileys:'😀', animals:'🐻', food:'🍔', activity:'⚽', travel:'🚗', objects:'💡', symbols:'❤️', flags:'🏳️' };
    const EMOJI_CAT_I18N = { recent:'emojiRecent', smileys:'emojiCatSmileys', animals:'emojiCatAnimals', food:'emojiCatFood', activity:'emojiCatActivity', travel:'emojiCatTravel', objects:'emojiCatObjects', symbols:'emojiCatSymbols', flags:'emojiCatFlags' };
    const EMOJI_CATS = [
      { key:'smileys', items:[
        ['😀','grinsen grin happy'],['😃','freuen smiley'],['😄','lachen happy'],['😁','strahlen beam'],['😆','laugh lol'],['😅','schwitzen sweat lachen'],['🤣','rofl rolling lachen'],['😂','lachen tränen joy'],['🙂','lächeln slight'],['🙃','upside kopf'],['😉','zwinkern wink'],['😊','froh blush'],['😇','engel halo angel'],['🥰','verliebt love herzen'],['😍','herzaugen heart eyes love'],['🤩','begeistert star struck'],['😘','kuss kiss'],['😗','küssen kiss'],['☺️','lächeln relaxed'],['😚','kuss closed'],['😙','kuss smiling'],['🥲','träne happy tear'],['😋','lecker yum'],['😛','zunge tongue'],['😜','zwinkern zunge wink'],['🤪','albern zany verrückt'],['😝','zunge squint'],['🤑','geld money mund'],['🤗','umarmen hug'],['🤭','kichern giggle hand'],['🤫','psst shush leise'],['🤔','nachdenken think denken'],['🤐','reißverschluss zipper'],['🤨','augenbraue raised skeptisch'],['😐','neutral'],['😑','ausdruckslos expressionless'],['😶','sprachlos no mouth'],['😏','schmunzeln smirk'],['😒','genervt unamused'],['🙄','augen rollen eyeroll'],['😬','grimasse grimace'],['🤥','lüge lying'],['😌','zufrieden relieved'],['😔','nachdenklich pensive traurig'],['😪','müde sleepy'],['🤤','sabbern drool'],['😴','schlafen sleep zzz'],['😷','maske mask krank'],['🤒','fieber krank thermometer'],['🤕','verletzt bandage'],['🤢','übel nauseated'],['🤮','kotzen vomit erbrechen'],['🤧','niesen sneeze'],['🥵','heiß hot schwitzen'],['🥶','kalt cold frieren'],['🥴','benommen woozy betrunken'],['😵','schwindel dizzy'],['🤯','explodiert mind blown schock'],['🤠','cowboy'],['🥳','party feiern hut'],['😎','sonnenbrille cool'],['🤓','nerd brille'],['🧐','monokel'],['😕','verwirrt confused'],['😟','besorgt worried'],['🙁','traurig frown'],['☹️','traurig frown'],['😮','überrascht open mouth'],['😯','still hushed'],['😲','erstaunt astonished'],['😳','errötet flushed peinlich'],['🥺','bettelnd pleading puppy'],['😦','stirnrunzeln frowning'],['😧','angst anguished'],['😨','ängstlich fearful'],['😰','schweiß angst anxious'],['😥','enttäuscht sad'],['😢','weinen cry traurig'],['😭','heulen sob weinen'],['😱','schrei scream angst'],['😖','verzweifelt confounded'],['😣','ausdauer persevere'],['😞','enttäuscht disappointed'],['😓','niedergeschlagen downcast'],['😩','müde weary'],['😫','erschöpft tired'],['🥱','gähnen yawn müde'],['😤','dampf triumph wütend'],['😡','wütend rage rot'],['😠','sauer angry'],['🤬','fluchen swearing'],['😈','teufel devil lächeln'],['👿','imp böse teufel'],['💀','totenkopf skull'],['☠️','totenkopf skull gefahr'],['💩','kacke poop haufen'],['🤡','clown'],['👹','oger ogre'],['👺','goblin'],['👻','geist ghost halloween'],['👽','alien ufo'],['👾','monster invader'],['🤖','roboter robot'],['😺','katze grin cat'],['😸','katze freude cat'],['😹','katze tränen cat'],['😻','katze verliebt cat love'],['😼','katze schmunzeln cat'],['😽','katze kuss cat'],['🙀','katze schock cat'],['😿','katze weinen cat'],['😾','katze schmollen cat'],
        ['👋','winken wave hallo'],['🤚','hand raised'],['🖐️','hand fingers'],['✋','stop hand'],['🖖','vulkan spock'],['👌','okay ok perfekt'],['🤌','finger pinched italienisch'],['🤏','wenig pinch klein'],['✌️','victory peace sieg'],['🤞','daumen drücken crossed glück'],['🤟','love you finger'],['🤘','rock metal'],['🤙','ruf mich call'],['👈','links left'],['👉','rechts right'],['👆','hoch up'],['🖕','mittelfinger'],['👇','runter down'],['☝️','zeigefinger up'],['👍','daumen hoch thumbsup gut like'],['👎','daumen runter thumbsdown dislike'],['✊','faust fist'],['👊','schlag punch faust'],['🤛','faust links'],['🤜','faust rechts'],['👏','klatschen clap applaus'],['🙌','hände hoch raised feiern'],['👐','offene hände open'],['🤲','handflächen palms'],['🤝','handschlag handshake deal'],['🙏','danke beten pray bitte'],['✍️','schreiben writing'],['💅','nägel nails'],['🤳','selfie'],['💪','muskel muscle stark'],
        ['👶','baby'],['🧒','kind child'],['👦','junge boy'],['👧','mädchen girl'],['🧑','person'],['👨','mann man'],['👩','frau woman'],['🧓','senior alt'],['👴','opa grandpa'],['👵','oma grandma'],['🙅','nein no'],['🙆','okay ja'],['💁','info desk hand'],['🙋','melden hand frage'],['🙇','verbeugen bow sorry'],['🤦','facepalm'],['🤷','schulterzucken shrug keine ahnung'],['👮','polizist police'],['🕵️','detektiv spy'],['💂','wache guard'],['👷','bauarbeiter worker helm'],['🤴','prinz prince'],['👸','prinzessin princess'],['👳','turban'],['🧕','kopftuch'],['🤵','smoking tuxedo'],['👰','braut bride'],['🤰','schwanger pregnant'],['🤱','stillen'],['👼','engel baby angel'],['🎅','weihnachtsmann santa'],['🤶','weihnachtsfrau'],['🦸','held hero'],['🦹','schurke villain'],['🧙','zauberer mage'],['🧚','fee fairy'],['🧛','vampir vampire'],['🧜','meerjungfrau mermaid'],['🧝','elf'],['🧞','dschinn genie'],['🧟','zombie'],['💆','massage'],['💇','friseur haircut'],['🚶','gehen walk'],['🏃','rennen run'],['💃','tänzerin dancer'],['🕺','tänzer dancing'],['🧘','yoga meditation'],['🛀','baden bath'],['👭','frauen hand'],['👫','paar hand couple'],['👬','männer hand'],['💏','kuss paar couple'],['💑','liebe paar couple'],['👪','familie family'],['🗣️','sprechen speaking'],['👤','silhouette'],['👥','silhouetten'],['👣','fußspuren footprints'],
      ]},
      { key:'animals', items:[
        ['🐶','hund dog'],['🐱','katze cat'],['🐭','maus mouse'],['🐹','hamster'],['🐰','hase rabbit bunny'],['🦊','fuchs fox'],['🐻','bär bear'],['🐼','panda'],['🐨','koala'],['🐯','tiger'],['🦁','löwe lion'],['🐮','kuh cow'],['🐷','schwein pig'],['🐽','schweinenase pig'],['🐸','frosch frog'],['🐵','affe monkey'],['🙈','nichts sehen affe monkey'],['🙉','nichts hören affe monkey'],['🙊','nichts sagen affe monkey'],['🐒','affe monkey'],['🐔','huhn chicken'],['🐧','pinguin penguin'],['🐦','vogel bird'],['🐤','küken chick'],['🐣','schlüpfen hatch küken'],['🦆','ente duck'],['🦅','adler eagle'],['🦉','eule owl'],['🦇','fledermaus bat'],['🐺','wolf'],['🐗','wildschwein boar'],['🐴','pferd horse'],['🦄','einhorn unicorn'],['🐝','biene bee'],['🐛','raupe caterpillar'],['🦋','schmetterling butterfly'],['🐌','schnecke snail'],['🐞','marienkäfer ladybug'],['🐜','ameise ant'],['🦗','grille cricket'],['🕷️','spinne spider'],['🕸️','spinnennetz web'],['🦂','skorpion scorpion'],['🐢','schildkröte turtle'],['🐍','schlange snake'],['🦎','eidechse lizard'],['🦖','t-rex dino'],['🦕','dino dinosaurier'],['🐙','krake octopus'],['🦑','tintenfisch squid'],['🦐','garnele shrimp'],['🦀','krabbe crab'],['🐡','kugelfisch fish'],['🐠','fisch tropical'],['🐟','fisch fish'],['🐬','delfin dolphin'],['🐳','wal whale'],['🦈','hai shark'],['🐊','krokodil crocodile'],['🐆','leopard'],['🦓','zebra'],['🦍','gorilla'],['🦧','orang utan'],['🐘','elefant elephant'],['🦛','nilpferd hippo'],['🦏','nashorn rhino'],['🐪','kamel camel'],['🦒','giraffe'],['🦘','känguru kangaroo'],['🐂','stier ox'],['🐄','kuh cow'],['🐑','schaf sheep'],['🦙','lama'],['🐐','ziege goat'],['🦌','hirsch deer'],['🐕','hund dog'],['🐩','pudel poodle'],['🐈','katze cat'],['🐓','hahn rooster'],['🦃','truthahn turkey'],['🦚','pfau peacock'],['🦜','papagei parrot'],['🦢','schwan swan'],['🦩','flamingo'],['🕊️','taube dove frieden'],['🦝','waschbär raccoon'],['🦨','stinktier skunk'],['🦦','otter'],['🦥','faultier sloth'],['🐀','ratte rat'],['🐿️','eichhörnchen squirrel'],['🦔','igel hedgehog'],
        ['🌵','kaktus cactus'],['🎄','tannenbaum christmas tree'],['🌲','baum tree tanne'],['🌳','laubbaum tree'],['🌴','palme palm'],['🌱','setzling sprout'],['🌿','kräuter herb'],['☘️','klee shamrock'],['🍀','glücksklee clover vierblättrig'],['🎍','bambus'],['🍃','blätter leaves wind'],['🍂','laub fallen herbst'],['🍁','ahorn maple'],['🌾','reis ähre'],['🌷','tulpe tulip'],['🌹','rose'],['🥀','welke rose'],['🌺','hibiskus hibiscus'],['🌸','kirschblüte blossom'],['🌼','blume flower'],['🌻','sonnenblume sunflower'],['🌞','sonne sun gesicht'],['🌝','mond face moon'],['🌛','mond sichel moon'],['🌜','mond moon'],['🌚','neumond moon'],['🌕','vollmond full moon'],['🌙','mond crescent moon'],['⭐','stern star'],['🌟','glitzerstern star'],['✨','funkeln sparkles glitzer'],['⚡','blitz lightning'],['☄️','komet comet'],['💫','schwindel star dizzy'],['🔥','feuer fire'],['🌪️','tornado wirbel'],['🌈','regenbogen rainbow'],['☀️','sonne sun'],['⛅','wolke sonne cloud'],['☁️','wolke cloud'],['🌧️','regen rain'],['⛈️','gewitter storm'],['❄️','schneeflocke snowflake'],['☃️','schneemann snowman'],['⛄','schneemann snowman'],['💨','dampf wind'],['💧','tropfen drop wasser'],['💦','schweiß sweat tropfen'],['☔','regenschirm umbrella'],['🌊','welle wave meer'],['🌍','erde europa earth globus'],['🌎','erde amerika earth'],['🌏','erde asien earth'],
      ]},
      { key:'food', items:[
        ['🍏','apfel grün apple'],['🍎','apfel rot apple'],['🍐','birne pear'],['🍊','orange mandarine'],['🍋','zitrone lemon'],['🍌','banane banana'],['🍉','wassermelone melon'],['🍇','trauben grapes'],['🍓','erdbeere strawberry'],['🫐','blaubeere blueberry'],['🍈','melone melon'],['🍒','kirsche cherry'],['🍑','pfirsich peach'],['🥭','mango'],['🍍','ananas pineapple'],['🥥','kokosnuss coconut'],['🥝','kiwi'],['🍅','tomate tomato'],['🍆','aubergine eggplant'],['🥑','avocado'],['🥦','brokkoli broccoli'],['🥬','salat lettuce'],['🥒','gurke cucumber'],['🌶️','chili pepper scharf'],['🌽','mais corn'],['🥕','karotte carrot'],['🧄','knoblauch garlic'],['🧅','zwiebel onion'],['🥔','kartoffel potato'],['🥐','croissant'],['🥯','bagel'],['🍞','brot bread'],['🥖','baguette'],['🥨','brezel pretzel'],['🧀','käse cheese'],['🥚','ei egg'],['🍳','spiegelei fried egg'],['🧈','butter'],['🥞','pfannkuchen pancakes'],['🧇','waffel waffle'],['🥓','speck bacon'],['🥩','steak fleisch meat'],['🍗','hähnchen drumstick chicken'],['🍖','fleisch meat'],['🌭','hotdog'],['🍔','burger hamburger'],['🍟','pommes fries'],['🍕','pizza'],['🥪','sandwich'],['🥙','döner wrap kebab'],['🧆','falafel'],['🌮','taco'],['🌯','burrito'],['🥗','salat salad'],['🥘','pfanne paella'],['🍝','spaghetti pasta nudeln'],['🍜','ramen nudeln noodles suppe'],['🍲','eintopf stew suppe'],['🍛','curry reis'],['🍣','sushi'],['🍱','bento box'],['🥟','teigtasche dumpling'],['🍤','garnele tempura shrimp'],['🍚','reis rice'],['🍘','reiscracker'],['🍥','fischkuchen'],['🍡','dango spieß'],['🍧','eis shaved'],['🍨','eis icecream becher'],['🍦','softeis icecream'],['🥧','kuchen pie'],['🧁','cupcake muffin'],['🍰','kuchen cake torte'],['🎂','geburtstag birthday cake torte'],['🍮','pudding flan'],['🍭','lutscher lollipop'],['🍬','bonbon candy süßigkeit'],['🍫','schokolade chocolate'],['🍿','popcorn'],['🍩','donut'],['🍪','keks cookie'],['🌰','kastanie chestnut'],['🥜','erdnuss peanut'],['🍯','honig honey'],['🥛','milch milk'],['🍼','babyflasche bottle'],['☕','kaffee coffee tee'],['🍵','tee tea grün'],['🧃','saftpäckchen juice'],['🥤','softdrink cola becher'],['🧋','bubble tea'],['🍶','sake'],['🍺','bier beer'],['🍻','prost beers'],['🥂','sekt champagne anstoßen'],['🍷','wein wine rotwein'],['🥃','whisky'],['🍸','cocktail martini'],['🍹','tropisch drink cocktail'],['🧉','mate'],['🍾','champagner sekt flasche'],['🥄','löffel spoon'],['🍴','besteck fork messer'],['🍽️','teller plate essen'],['🥢','stäbchen chopsticks'],['🧂','salz salt'],
      ]},
      { key:'activity', items:[
        ['⚽','fußball soccer'],['🏀','basketball'],['🏈','football'],['⚾','baseball'],['🥎','softball'],['🎾','tennis'],['🏐','volleyball'],['🏉','rugby'],['🥏','frisbee'],['🎱','billard pool'],['🪀','jojo yoyo'],['🏓','tischtennis pingpong'],['🏸','badminton'],['🏒','eishockey hockey'],['🏑','feldhockey hockey'],['🥍','lacrosse'],['🏏','cricket'],['🥅','tor goal netz'],['⛳','golf flag'],['🪁','drachen kite'],['🏹','bogen archery pfeil'],['🎣','angeln fishing'],['🤿','tauchen diving maske'],['🥊','boxhandschuh boxing'],['🥋','kampfsport judo karate'],['🛹','skateboard'],['🛼','rollschuh skate'],['🛷','schlitten sled'],['⛸️','schlittschuh skate'],['🥌','curling'],['🎿','ski'],['⛷️','skifahren ski'],['🏂','snowboard'],['🏋️','hantel gewichtheben weight'],['🤼','ringen wrestle'],['🤸','turnen cartwheel'],['⛹️','dribbeln basketball'],['🤺','fechten fencing'],['🏇','pferderennen horse'],['🧘','yoga meditation'],['🏄','surfen surf'],['🏊','schwimmen swim'],['🤽','wasserball waterpolo'],['🚣','rudern row boot'],['🧗','klettern climb'],['🚵','mountainbike bike'],['🚴','radfahren cycle bike'],['🏆','pokal trophy sieg'],['🥇','gold medaille first'],['🥈','silber medaille second'],['🥉','bronze medaille third'],['🏅','medaille medal'],['🎖️','orden military medaille'],['🎗️','schleife ribbon'],['🎫','ticket'],['🎟️','eintritt admission'],['🎪','zirkus circus zelt'],['🤹','jonglieren juggle'],['🎭','theater masken masks'],['🩰','ballett ballet'],['🎨','kunst palette malen art'],['🎬','film clapper klappe'],['🎤','mikrofon mic singen'],['🎧','kopfhörer headphone'],['🎼','noten music'],['🎹','klavier piano keyboard'],['🥁','trommel drum schlagzeug'],['🎷','saxofon sax'],['🎺','trompete trumpet'],['🎸','gitarre guitar'],['🪕','banjo'],['🎻','geige violin'],['🎲','würfel dice'],['♟️','schach chess'],['🎯','dartscheibe target ziel'],['🎳','bowling'],['🎮','gamepad controller zocken'],['🕹️','joystick'],['🎰','spielautomat slot'],['🧩','puzzle'],['🎉','party tada konfetti'],['🎊','konfetti ball'],['🎈','luftballon balloon'],['🎁','geschenk gift present'],['🎀','schleife bow'],['🪄','zauberstab wand magie'],['🎆','feuerwerk fireworks'],['🎇','wunderkerze sparkler'],['🧨','böller firecracker'],['🎃','kürbis halloween pumpkin'],['🎏','karpfen flag koi'],['🎐','windspiel'],['🧧','glücksgeld red envelope'],
      ]},
      { key:'travel', items:[
        ['🚗','auto car'],['🚕','taxi'],['🚙','suv jeep auto'],['🚌','bus'],['🏎️','rennwagen racing auto'],['🚓','polizeiauto police'],['🚑','krankenwagen ambulance'],['🚒','feuerwehr fire truck'],['🚐','van bus'],['🚚','lkw truck'],['🚛','sattelschlepper truck'],['🚜','traktor tractor'],['🛴','roller scooter tret'],['🚲','fahrrad bike'],['🛵','motorroller scooter'],['🏍️','motorrad motorcycle'],['🚨','sirene light alarm'],['🚀','rakete rocket'],['🛸','ufo'],['🛰️','satellit satellite'],['🚁','hubschrauber helicopter'],['✈️','flugzeug plane fliegen'],['🛫','start takeoff'],['🛬','landung landing'],['🛩️','kleinflugzeug plane'],['💺','sitz seat'],['🚂','dampflok locomotive zug'],['🚄','schnellzug bullet train'],['🚅','shinkansen zug'],['🚆','zug train'],['🚇','u-bahn metro subway'],['🚉','bahnhof station'],['🚊','straßenbahn tram'],['🚝','einschienenbahn monorail'],['🚞','bergbahn zug'],['🚋','tram waggon'],['🚎','oberleitungsbus trolley'],['🚢','schiff ship'],['⛴️','fähre ferry'],['🛳️','kreuzfahrt cruise schiff'],['🛥️','motorboot boot'],['🚤','schnellboot speedboat'],['⛵','segelboot sailboat'],['🛶','kanu canoe'],['⚓','anker anchor'],['⛽','tankstelle fuel benzin'],['🚧','baustelle construction'],['🚦','ampel traffic light'],['🚥','ampel traffic'],['🗺️','landkarte map karte'],['🗿','moai statue'],['🗽','freiheitsstatue liberty'],['🗼','turm tokyo tower'],['🏰','schloss castle'],['🏯','burg japan castle'],['🏟️','stadion stadium'],['🎡','riesenrad ferris wheel'],['🎢','achterbahn rollercoaster'],['🎠','karussell carousel'],['⛲','brunnen fountain'],['⛱️','sonnenschirm beach'],['🏖️','strand beach'],['🏝️','insel island'],['🏜️','wüste desert'],['🌋','vulkan volcano'],['⛰️','berg mountain'],['🏔️','schneeberg mountain'],['🗻','fuji berg'],['🏕️','camping zelt tent'],['⛺','zelt tent'],['🏠','haus house'],['🏡','haus garten home'],['🏘️','häuser houses'],['🏗️','baustelle building crane'],['🏭','fabrik factory'],['🏢','bürogebäude office'],['🏬','kaufhaus mall'],['🏥','krankenhaus hospital'],['🏦','bank'],['🏨','hotel'],['🏪','kiosk store laden'],['🏫','schule school'],['⛪','kirche church'],['🕌','moschee mosque'],['🕍','synagoge synagogue'],['🛕','tempel temple'],['⛩️','schrein shrine torii'],['🌁','nebel foggy'],['🌃','nacht stadt night city'],['🏙️','skyline city stadt'],['🌆','sonnenuntergang dusk stadt'],['🌇','sonnenaufgang sunrise'],['🌉','brücke bridge nacht'],['🌌','milchstraße galaxy sterne'],['🌠','sternschnuppe shooting star'],
      ]},
      { key:'objects', items:[
        ['⌚','uhr watch armbanduhr'],['📱','handy phone smartphone'],['📲','handy pfeil call'],['💻','laptop notebook'],['⌨️','tastatur keyboard'],['🖥️','computer desktop pc'],['🖨️','drucker printer'],['🖱️','maus mouse computer'],['💽','minidisc'],['💾','diskette floppy speichern save'],['💿','cd'],['📀','dvd'],['📼','videokassette tape'],['📷','kamera camera foto'],['📸','kamera blitz camera'],['📹','videokamera camcorder'],['🎥','filmkamera movie'],['📽️','projektor projector'],['🎞️','filmrolle film'],['📞','telefon phone hörer'],['☎️','telefon phone'],['📟','pager'],['📠','fax'],['📺','fernseher tv'],['📻','radio'],['🎙️','mikrofon studio mic'],['🧭','kompass compass'],['⏱️','stoppuhr stopwatch'],['⏰','wecker alarm clock'],['⌛','sanduhr hourglass'],['⏳','sanduhr läuft hourglass'],['📡','satellitenschüssel antenna'],['🔋','batterie battery akku'],['🔌','stecker plug strom'],['💡','glühbirne idea bulb licht'],['🔦','taschenlampe flashlight'],['🕯️','kerze candle'],['🧯','feuerlöscher extinguisher'],['🛢️','ölfass barrel'],['💸','geld fliegt money'],['💵','dollar geld'],['💶','euro geld'],['💷','pfund pound'],['🪙','münze coin'],['💰','geldsack money bag'],['💳','kreditkarte card'],['💎','diamant gem juwel'],['⚖️','waage balance justice'],['🪜','leiter ladder'],['🧰','werkzeugkasten toolbox'],['🔧','schraubenschlüssel wrench'],['🔨','hammer'],['🛠️','werkzeug tools'],['⛏️','spitzhacke pick'],['🔩','schraube nut bolt'],['⚙️','zahnrad gear einstellung'],['🧱','ziegel brick mauer'],['⛓️','kette chain'],['🧲','magnet'],['🔫','wasserpistole gun pistole'],['💣','bombe bomb'],['🔪','messer knife'],['🗡️','dolch dagger'],['⚔️','schwerter swords'],['🛡️','schild shield'],['🚬','zigarette cigarette'],['⚰️','sarg coffin'],['🏺','amphore vase'],['🔮','glaskugel crystal ball'],['🧿','nazar amulett'],['💈','barbier pole'],['🔭','teleskop telescope'],['🔬','mikroskop microscope'],['🕳️','loch hole'],['💊','pille pill medizin'],['💉','spritze syringe impfung'],['🩸','blut blood'],['🩹','pflaster bandaid'],['🩺','stethoskop arzt'],['🌡️','thermometer fieber'],['🧬','dna'],['🦠','mikrobe virus'],['🧪','reagenzglas test tube'],['🧹','besen broom'],['🧺','korb basket wäsche'],['🧻','klopapier toilet roll'],['🚽','toilette wc klo'],['🚿','dusche shower'],['🛁','badewanne bath'],['🧼','seife soap'],['🪥','zahnbürste toothbrush'],['🧽','schwamm sponge'],['🪒','rasierer razor'],['🧴','lotion flasche'],['🔑','schlüssel key'],['🗝️','schlüssel alt key'],['🚪','tür door'],['🪑','stuhl chair'],['🛋️','sofa couch'],['🛏️','bett bed'],['🧸','teddy teddybär bear'],['🖼️','bild gemälde frame'],['🛍️','einkauf bags shopping'],['🛒','einkaufswagen cart'],['📦','paket box karton'],['📫','briefkasten mailbox'],['📜','schriftrolle scroll'],['📄','dokument document seite'],['📊','balkendiagramm chart'],['📈','steigend trend up chart'],['📉','fallend trend down chart'],['📋','klemmbrett clipboard'],['📌','pinnnadel pushpin'],['📍','ort location pin standort'],['📎','büroklammer clip'],['📏','lineal ruler'],['📐','geodreieck triangle'],['✂️','schere scissors'],['🗑️','papierkorb trash müll'],['🔒','schloss zu lock gesperrt'],['🔓','schloss auf unlock'],['📔','notizbuch notebook'],['📕','buch rot book'],['📗','buch grün book'],['📘','buch blau book'],['📙','buch orange book'],['📚','bücher books'],['📖','offenes buch open book lesen'],['🔖','lesezeichen bookmark'],['🏷️','etikett label tag'],['✏️','bleistift pencil'],['✒️','füller pen'],['🖊️','kugelschreiber pen'],['🖌️','pinsel brush'],['🖍️','wachsmalstift crayon'],['📝','notiz memo schreiben'],['🔍','lupe search suche'],['🔎','lupe rechts search'],
      ]},
      { key:'symbols', items:[
        ['❤️','herz rot heart liebe love'],['🧡','herz orange heart'],['💛','herz gelb heart'],['💚','herz grün heart'],['💙','herz blau heart'],['💜','herz lila heart'],['🖤','herz schwarz black heart'],['🤍','herz weiß white heart'],['🤎','herz braun brown heart'],['💔','gebrochenes herz broken heart'],['❣️','herz ausruf heart'],['💕','zwei herzen hearts'],['💞','kreisende herzen hearts'],['💓','pochendes herz heart'],['💗','wachsendes herz heart'],['💖','funkelndes herz sparkle heart'],['💘','herz pfeil cupid amor'],['💝','herz schleife heart gift'],['💟','herz deko heart'],['☮️','frieden peace'],['✝️','kreuz cross christlich'],['☪️','halbmond stern islam'],['🕉️','om hinduismus'],['✡️','davidstern judentum'],['☯️','yin yang'],['🛐','gebetsstätte worship'],['⛎','schlangenträger ophiuchus'],['♈','widder aries'],['♉','stier taurus'],['♊','zwilling gemini'],['♋','krebs cancer'],['♌','löwe leo'],['♍','jungfrau virgo'],['♎','waage libra'],['♏','skorpion scorpio'],['♐','schütze sagittarius'],['♑','steinbock capricorn'],['♒','wassermann aquarius'],['♓','fische pisces'],['⚛️','atom science'],['☢️','radioaktiv radioactive'],['☣️','biogefahr biohazard'],['✴️','stern acht star'],['❌','kreuz x falsch'],['⭕','kreis rot o'],['🛑','stopp stop'],['⛔','verboten no entry'],['🚫','verboten prohibited'],['💯','hundert hundred prozent'],['💢','wut anger zorn'],['♨️','heiße quelle hot spring'],['🔞','ab 18 adult'],['📵','kein handy no phone'],['❗','ausrufezeichen exclamation'],['❓','frage question fragezeichen'],['❔','frage weiß question'],['‼️','doppel ausruf exclamation'],['⁉️','ausruf frage interrobang'],['💲','dollar zeichen'],['™️','trademark marke'],['©️','copyright'],['®️','registered'],['🔚','ende end'],['🔙','zurück back'],['🔛','an on'],['🔝','oben top'],['🔜','bald soon'],['✅','häkchen check grün ok'],['☑️','kästchen check'],['✔️','haken check'],['❎','kreuz grün cross'],['➕','plus addieren'],['➖','minus'],['➗','geteilt divide'],['✖️','mal multiply'],['♾️','unendlich infinity'],['🔘','radiobutton'],['🔱','dreizack trident'],['⚠️','warnung warning achtung'],['🔰','anfänger beginner'],['♻️','recycling recycle'],['✳️','stern grün asterisk'],['❇️','funkeln stern sparkle'],['🔴','roter kreis red circle'],['🟠','oranger kreis orange'],['🟡','gelber kreis yellow'],['🟢','grüner kreis green'],['🔵','blauer kreis blue'],['🟣','lila kreis purple'],['⚫','schwarzer kreis black'],['⚪','weißer kreis white'],['🟤','brauner kreis brown'],['🔺','dreieck rot hoch triangle'],['🔻','dreieck rot runter triangle'],['🔶','raute orange diamond'],['🔷','raute blau diamond'],['🟥','rotes quadrat red square'],['🟧','oranges quadrat'],['🟨','gelbes quadrat'],['🟩','grünes quadrat green'],['🟦','blaues quadrat blue'],['🟪','lila quadrat'],['⬛','großes schwarz black square'],['⬜','großes weiß white square'],['🟫','braunes quadrat'],
        ['⬆️','pfeil hoch up arrow'],['↗️','pfeil rechts oben arrow'],['➡️','pfeil rechts right arrow'],['↘️','pfeil rechts unten arrow'],['⬇️','pfeil runter down arrow'],['↙️','pfeil links unten arrow'],['⬅️','pfeil links left arrow'],['↖️','pfeil links oben arrow'],['↕️','pfeil hoch runter arrow'],['↔️','pfeil links rechts arrow'],['↩️','pfeil zurück arrow'],['↪️','pfeil weiter arrow'],['🔃','pfeile uhrzeiger reload'],['🔄','pfeile gegen refresh'],['🔀','mischen shuffle'],['🔁','wiederholen repeat loop'],['🔂','einmal wiederholen repeat'],['▶️','play abspielen'],['⏸️','pause'],['⏹️','stopp stop'],['⏺️','aufnahme record'],['⏭️','nächster next'],['⏮️','vorheriger previous'],['⏩','schneller fast forward'],['⏪','zurück rewind'],['🔼','dreieck hoch up'],['🔽','dreieck runter down'],
        ['0️⃣','null zero'],['1️⃣','eins one'],['2️⃣','zwei two'],['3️⃣','drei three'],['4️⃣','vier four'],['5️⃣','fünf five'],['6️⃣','sechs six'],['7️⃣','sieben seven'],['8️⃣','acht eight'],['9️⃣','neun nine'],['🔟','zehn ten'],['#️⃣','raute hash'],['*️⃣','stern asterisk'],['🔢','zahlen numbers'],['🔤','abc buchstaben letters'],
        ['🆗','ok okay'],['🆕','neu new'],['🆒','cool'],['🆙','up'],['🆓','gratis free'],['🛗','aufzug elevator lift'],['🚹','herren wc men'],['🚺','damen wc women'],['🚻','toilette restroom wc'],['♿','rollstuhl wheelchair'],['🅿️','parken parking'],['🚮','mülleimer litter'],['🔆','hell bright'],['🔅','dunkel dim'],['📶','signal empfang'],['🔈','lautsprecher leise speaker'],['🔉','lautsprecher mittel speaker'],['🔊','lautsprecher laut speaker'],['🔇','stumm mute'],['🔔','glocke bell benachrichtigung'],['🔕','glocke aus mute'],['📣','megafon megaphone'],['📢','lautsprecher announce'],['💬','sprechblase chat speech'],['💭','gedankenblase thought'],['🗯️','wutblase anger speech'],['♠️','pik spades karten'],['♥️','herz hearts karten'],['♦️','karo diamonds karten'],['♣️','kreuz clubs karten'],['🃏','joker karte'],['🀄','mahjong'],['🎴','spielkarte hanafuda'],
      ]},
      { key:'flags', items:[
        ['🏳️','weiße flagge white flag'],['🏴','schwarze flagge black flag'],['🏁','zielflagge checkered finish'],['🚩','dreiecksflagge red flag'],['🏳️‍🌈','regenbogenflagge pride rainbow'],['🏴‍☠️','piratenflagge pirate'],['🇩🇪','deutschland germany'],['🇦🇹','österreich austria'],['🇨🇭','schweiz switzerland'],['🇫🇷','frankreich france'],['🇮🇹','italien italy'],['🇪🇸','spanien spain'],['🇵🇹','portugal'],['🇬🇧','großbritannien uk england'],['🇮🇪','irland ireland'],['🇳🇱','niederlande netherlands holland'],['🇧🇪','belgien belgium'],['🇱🇺','luxemburg luxembourg'],['🇩🇰','dänemark denmark'],['🇸🇪','schweden sweden'],['🇳🇴','norwegen norway'],['🇫🇮','finnland finland'],['🇮🇸','island iceland'],['🇵🇱','polen poland'],['🇨🇿','tschechien czech'],['🇸🇰','slowakei slovakia'],['🇭🇺','ungarn hungary'],['🇬🇷','griechenland greece'],['🇹🇷','türkei turkey'],['🇷🇺','russland russia'],['🇺🇦','ukraine'],['🇺🇸','usa amerika america'],['🇨🇦','kanada canada'],['🇲🇽','mexiko mexico'],['🇧🇷','brasilien brazil'],['🇦🇷','argentinien argentina'],['🇯🇵','japan'],['🇨🇳','china'],['🇰🇷','südkorea korea'],['🇮🇳','indien india'],['🇦🇺','australien australia'],['🇳🇿','neuseeland new zealand'],['🇿🇦','südafrika south africa'],['🇪🇬','ägypten egypt'],['🇦🇪','emirate uae dubai'],['🇸🇦','saudi arabien saudi'],['🇮🇱','israel'],['🇪🇺','europa eu europe'],
      ]},
    ];

    let _emojiActiveCat = 'smileys';
    function emojiRecentList() { try { return JSON.parse(localStorage.getItem(EMOJI_RECENT_KEY) || '[]'); } catch(e) { return []; } }
    function pushEmojiRecent(emoji) {
      let list = emojiRecentList().filter(e => e !== emoji);
      list.unshift(emoji);
      if (list.length > 30) list = list.slice(0, 30);
      try { localStorage.setItem(EMOJI_RECENT_KEY, JSON.stringify(list)); } catch(e) {}
    }
    function emojiCatItems(key) {
      if (key === 'recent') return emojiRecentList().map(e => [e, '']);
      const c = EMOJI_CATS.find(c => c.key === key);
      return c ? c.items : [];
    }
    function renderEmojiGrid(items) {
      const grid = document.getElementById('emoji-grid');
      grid.innerHTML = '';
      if (!items.length) {
        const empty = document.createElement('div');
        empty.className = 'emoji-empty';
        empty.textContent = t('emojiNone');
        grid.appendChild(empty);
        return;
      }
      const frag = document.createDocumentFragment();
      for (const it of items) {
        const btn = document.createElement('button');
        btn.className = 'emoji-btn';
        btn.type = 'button';
        btn.textContent = it[0];
        btn.onclick = () => insertEmoji(it[0]);
        frag.appendChild(btn);
      }
      grid.appendChild(frag);
    }
    function setEmojiCat(key) {
      _emojiActiveCat = key;
      document.querySelectorAll('#emoji-tabs .emoji-tab').forEach(tab => tab.classList.toggle('active', tab.dataset.cat === key));
      renderEmojiGrid(emojiCatItems(key));
      const grid = document.getElementById('emoji-grid');
      if (grid) grid.scrollTop = 0;
    }
    function buildEmojiTabs() {
      const tabs = document.getElementById('emoji-tabs');
      if (!tabs) return;
      tabs.innerHTML = '';
      const keys = [];
      if (emojiRecentList().length) keys.push('recent');
      for (const c of EMOJI_CATS) keys.push(c.key);
      for (const key of keys) {
        const b = document.createElement('button');
        b.className = 'emoji-tab' + (key === _emojiActiveCat ? ' active' : '');
        b.type = 'button';
        b.dataset.cat = key;
        b.textContent = EMOJI_CAT_ICON[key];
        b.title = t(EMOJI_CAT_I18N[key]);
        b.onclick = (ev) => { ev.stopPropagation(); const s = document.getElementById('emoji-search'); if (s) s.value = ''; setEmojiCat(key); };
        tabs.appendChild(b);
      }
    }
    function onEmojiSearch(q) {
      q = (q || '').trim().toLowerCase();
      if (!q) { setEmojiCat(_emojiActiveCat); return; }
      document.querySelectorAll('#emoji-tabs .emoji-tab').forEach(tab => tab.classList.remove('active'));
      const seen = new Set();
      const hits = [];
      for (const c of EMOJI_CATS) {
        for (const it of c.items) {
          if (seen.has(it[0])) continue;
          if (it[0] === q || it[1].indexOf(q) !== -1) { hits.push(it); seen.add(it[0]); }
        }
      }
      renderEmojiGrid(hits);
    }

    function toggleEmojiPicker(evt) {
      evt.stopPropagation();
      const pk = document.getElementById('emoji-picker');
      const opening = !pk.classList.contains('open');
      pk.classList.toggle('open');
      if (opening) {
        const s = document.getElementById('emoji-search'); if (s) s.value = '';
        if (_emojiActiveCat === 'recent' && !emojiRecentList().length) _emojiActiveCat = 'smileys';
        buildEmojiTabs();
        setEmojiCat(_emojiActiveCat);
      }
    }

    function insertEmoji(emoji) {
      const inp = document.getElementById('msg-input');
      const start = inp.selectionStart;
      const end = inp.selectionEnd;
      inp.value = inp.value.slice(0, start) + emoji + inp.value.slice(end);
      inp.selectionStart = inp.selectionEnd = start + emoji.length;
      inp.focus();
      autoResize(inp);
      pushEmojiRecent(emoji);
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
          av.className = 'avatar' + (_statusChatIds.has(chat.id) ? ' has-status' : '');
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
      exitDeleteMode();
      clearReply();
      closeMsgSearch();
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
      _pendingMentions = []; hideMentionDropdown(); // Erwähnungen vom vorherigen Chat verwerfen
      if (isGroupChat(chat.id)) ensureParticipants(chat.id); // Namen für @-Auflösung vorladen
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
        // Stats nur neu laden, wenn tatsächlich neue Nachrichten kamen
        if (msgs.length) {
          renderMessages(msgs, chatId); pollReactions(); updateChatStats(chatId);
          // Kontaktliste links sofort aktualisieren (Vorschau + Sortierung),
          // statt bis zum nächsten pollChats-Intervall (10 s) zu warten — gilt für
          // empfangene wie gesendete Nachrichten im offenen Chat
          pollChats();
        }
      } catch(e) {}
    }

    function fillPhotoBubble(bub, m, ack) {
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
      img.style.cssText = 'width:100%;height:auto;max-height:360px;display:block;cursor:zoom-in;';
      img.loading = 'lazy';
      img.addEventListener('click', function(e) { e.stopPropagation(); openLightbox(this.src); });
      bub.appendChild(img);
      if (m.body) { const cap = document.createElement('div'); cap.className = 'caption'; cap.innerHTML = formatText(m.body); bub.appendChild(cap); }
      const timeEl = document.createElement('span'); timeEl.className = 'time'; timeEl.innerHTML = fmtTime(m.timestamp) + ack; bub.appendChild(timeEl);
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

        // Foto nachgeladen (z.B. nach Weiterleiten): Platzhalter-Bubble in-place
        // durch Bild ersetzen, statt eine doppelte Bubble zu erzeugen
        if (m.type === 'photo' && m.mediaFile) {
          const existingWrap = msgList.querySelector('.bubble-wrap[data-msgid="' + m.id + '"]');
          if (existingWrap && !existingWrap.querySelector('img.msg-img')) {
            const bub = existingWrap.querySelector('.bubble');
            if (bub) {
              bub.innerHTML = '';
              fillPhotoBubble(bub, m, m.fromMe ? ackMark(m.ack || 0) : '');
            }
            return;
          }
        }

        // ACK-Update: Häkchen in-place aktualisieren ohne Bubble neu zu erstellen
        if (m.fromMe && m.ackUpdatedAt) {
          const existingWrap = msgList.querySelector('.bubble-wrap[data-msgid="' + m.id + '"]');
          if (existingWrap) {
            const timeEl = existingWrap.querySelector('.time');
            if (timeEl) timeEl.innerHTML = fmtTime(m.timestamp) + ackMark(m.ack || 0);
            return;
          }
        }

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

        // Bubble schon im DOM (z.B. durch parallelen Poll nach sendMsg()
        // gleichzeitig mit dem 2s-Intervall) — keine doppelte Bubble erzeugen
        if (msgList.querySelector('.bubble-wrap[data-msgid="' + m.id + '"]')) return;

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
        } else if (m.type === 'video') {
          if (m.mediaFile) {
            const vSrc = 'api/media/' + encodeURIComponent(m.mediaFile);
            bub.innerHTML = '<div style="display:inline-flex;align-items:flex-end;gap:6px"><video controls style="max-width:280px;max-height:360px;display:block;border-radius:8px" src="' + vSrc + '"></video><button data-msgid="' + esc(m.id) + '" onclick="deleteWAVideo(this.dataset.msgid)" style="background:none;border:none;cursor:pointer;font-size:15px;opacity:0.55;padding:4px;flex-shrink:0;line-height:1" title="Video von Disk löschen">🗑️</button></div>' + (m.body ? '<div style="margin-top:4px;font-size:13px">' + esc(m.body) + '</div>' : '') + '<span class="time">' + fmtTime(m.timestamp) + ack + '</span>';
          } else {
            const sz = m.videoSize || 0;
            const mb = sz ? ' · ' + (sz/1024/1024).toFixed(1) + ' MB' : '';
            const tooBig = sz > ${VIDEO_MAX_MB}*1024*1024;
            bub.innerHTML = tooBig
              ? '<span style="opacity:0.5;cursor:default">' + t('videoTooBig') + mb + '</span><span class="time">' + fmtTime(m.timestamp) + ack + '</span>'
              : '<span class="wa-video-placeholder" data-msgid="' + esc(m.id) + '" data-chatid="' + esc(m.fromMe ? selectedChatId : m.from || selectedChatId) + '" onclick="fetchWAVideo(this)" style="cursor:pointer;opacity:0.85;text-decoration:underline">' + t('videoDownload') + mb + '</span><span class="time">' + fmtTime(m.timestamp) + ack + '</span>';
          }
        } else if (m.type === 'location' && m.locLat != null) {
          const mapsUrl = 'https://maps.google.com/?q=' + m.locLat + ',' + m.locLng;
          const label = m.locName || (m.locLat.toFixed(4) + ', ' + m.locLng.toFixed(4));
          bub.innerHTML = '<a href="' + mapsUrl + '" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:8px;text-decoration:none;color:inherit;"><span style="font-size:22px">📍</span><span style="font-size:13px;text-decoration:underline;opacity:0.9">' + esc(label) + '</span></a><span class="time" style="float:right;margin-top:4px">' + fmtTime(m.timestamp) + ack + '</span>';
        } else if (m.type === 'document') {
          bub.innerHTML = '<div class="bubble-document"><span class="doc-icon">📄</span><div class="doc-info"><span class="doc-name">' + esc(m.filename || 'Dokument') + '</span>' + (m.body ? '<div class="doc-caption">' + esc(m.body) + '</div>' : '') + '</div></div><span class="time" style="float:right;padding:0 0 4px;">' + fmtTime(m.timestamp) + ack + '</span>';
        } else if (m.type === 'voice') {
          const audioSrc = m.mediaFile ? 'api/media/' + encodeURIComponent(m.mediaFile) : '';
          bub.innerHTML = (audioSrc
            ? '<audio controls style="min-width:220px;max-width:300px;width:100%" src="' + audioSrc + '"></audio>'
            : '<span style="opacity:0.6">' + t('voiceMsg') + '</span>')
            + '<span class="time">' + fmtTime(m.timestamp) + ack + '</span>';
        } else if (m.type === 'photo' && m.mediaFile) {
          fillPhotoBubble(bub, m, ack);
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

    // ── Nachrichtensuche ────────────────────────────────────────────────────────
    let _searchMatches = [];
    let _searchIdx = -1;

    function toggleMsgSearch() {
      const bar = document.getElementById('msg-search-bar');
      if (bar.classList.contains('open')) { closeMsgSearch(); return; }
      bar.classList.add('open');
      document.getElementById('msg-search-btn').classList.add('active');
      const inp = document.getElementById('msg-search-input');
      inp.placeholder = t('msgSearchPlaceholder');
      inp.value = '';
      inp.focus();
      _searchMatches = [];
      _searchIdx = -1;
      document.getElementById('msg-search-count').textContent = '';
    }

    function closeMsgSearch() {
      document.getElementById('msg-search-bar').classList.remove('open');
      document.getElementById('msg-search-btn').classList.remove('active');
      document.getElementById('msg-search-input').value = '';
      clearMsgHighlights();
      _searchMatches = [];
      _searchIdx = -1;
    }

    function clearMsgHighlights() {
      document.querySelectorAll('.msg-highlight, .msg-highlight-active').forEach(el => {
        el.classList.remove('msg-highlight', 'msg-highlight-active');
      });
    }

    function onMsgSearchInput(query) {
      clearMsgHighlights();
      _searchMatches = [];
      _searchIdx = -1;
      const q = query.trim().toLowerCase();
      const countEl = document.getElementById('msg-search-count');
      if (!q) { countEl.textContent = ''; updateSearchNav(); return; }
      document.querySelectorAll('#messages .bubble').forEach(bub => {
        const text = bub.textContent.toLowerCase();
        if (text.includes(q)) {
          bub.classList.add('msg-highlight');
          _searchMatches.push(bub);
        }
      });
      if (_searchMatches.length) {
        _searchIdx = 0;
        activateSearchMatch();
      } else {
        countEl.textContent = t('msgSearchNoResult');
      }
      updateSearchNav();
    }

    function activateSearchMatch() {
      _searchMatches.forEach((b, i) => {
        b.classList.toggle('msg-highlight-active', i === _searchIdx);
        b.classList.toggle('msg-highlight', i !== _searchIdx);
      });
      _searchMatches[_searchIdx].scrollIntoView({ behavior: 'smooth', block: 'center' });
      document.getElementById('msg-search-count').textContent = (_searchIdx + 1) + ' / ' + _searchMatches.length;
    }

    function stepMsgSearch(dir) {
      if (!_searchMatches.length) return;
      _searchIdx = (_searchIdx + dir + _searchMatches.length) % _searchMatches.length;
      activateSearchMatch();
      updateSearchNav();
    }

    function updateSearchNav() {
      const has = _searchMatches.length > 0;
      document.getElementById('msg-search-prev').disabled = !has;
      document.getElementById('msg-search-next').disabled = !has;
    }

    function exportChat() {
      if (!selectedChatId) return;
      window.location.href = 'api/export/' + encodeURIComponent(selectedChatId) + '?lang=' + lang;
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
      if (btn) { btn.disabled = true; btn.innerHTML = t('spamDeleting'); }
      try {
        const r = await fetch('api/delete-batch/' + encodeURIComponent(selectedChatId), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids }),
        }).then(r => r.json());
        for (const wrap of wraps) wrap.remove();
        await pollChats();
        if (btn) { btn.innerHTML = tf('spamDeleted', r.deleted); setTimeout(() => { btn.innerHTML = '${_SVG.trash}'; }, 3000); }
      } catch(e) {
        if (btn) { btn.innerHTML = t('spamError'); setTimeout(() => { btn.innerHTML = '${_SVG.trash}'; }, 3000); }
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
      const statusEl = document.getElementById('contact-modal-status');
      // Reset
      picEl.innerHTML = '…'; picEl.style.background = '#2a3942';
      nameEl.textContent = '…'; pushnameEl.textContent = ''; numberEl.textContent = ''; aboutEl.textContent = '';
      statusEl.innerHTML = ''; statusEl.classList.remove('has-items');
      modal.classList.add('open');
      fetch('api/status/' + encodeURIComponent(chatId)).then(r => r.json()).then(sd => {
        if (!sd.msgs || !sd.msgs.length) return;
        statusEl.innerHTML = '<div class="status-label">' + esc(t('statusUpdates')) + '</div>' +
          sd.msgs.map(renderStatusItem).join('');
        statusEl.classList.add('has-items');
        statusEl.querySelectorAll('img.status-img').forEach(img => {
          img.addEventListener('click', () => openLightbox(img.src));
        });
      }).catch(() => {});
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
    function renderStatusItem(m) {
      const time = fmtDate(m.timestamp) + ', ' + fmtTime(m.timestamp);
      let inner;
      if (m.type === 'photo' && m.mediaFile) {
        inner = '<img class="status-img" src="api/media/' + encodeURIComponent(m.mediaFile) + '" loading="lazy">';
      } else if (m.type === 'video' && m.mediaFile) {
        inner = '<video controls src="api/media/' + encodeURIComponent(m.mediaFile) + '"></video>';
      } else if (m.body) {
        inner = '<div class="status-text">' + formatText(m.body) + '</div>';
      } else {
        return '';
      }
      return '<div class="status-item">' + inner + '<div class="status-time">' + esc(time) + '</div></div>';
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
      if (document.hidden || currentStatus !== 'connected' || !selectedChatId) return;
      await loadMessages(selectedChatId);
    }

    async function pollChats() {
      if (document.hidden || currentStatus !== 'connected') return;
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

    // ── @-Erwähnungen in Gruppen ───────────────────────────────────────────────
    let _mentionParticipants = {}; // chatId -> [{jid, number, name}]
    let _pendingMentions = [];     // bereits gewählte Erwähnungen [{name, number, jid}]
    let _mentionFiltered = [], _mentionSelIdx = 0, _mentionStart = -1, _mentionActive = false;

    function isGroupChat(chatId) {
      const c = allChats.find(x => x.id === chatId);
      return c ? !!c.isGroup : (chatId || '').endsWith('@g.us');
    }
    async function ensureParticipants(chatId) {
      if (_mentionParticipants[chatId]) return _mentionParticipants[chatId];
      try {
        const list = await fetch('api/participants/' + encodeURIComponent(chatId)).then(r => r.json());
        _mentionParticipants[chatId] = Array.isArray(list) ? list : [];
      } catch(e) { _mentionParticipants[chatId] = []; }
      return _mentionParticipants[chatId];
    }
    function getMentionDropdown() {
      let d = document.getElementById('mention-dropdown');
      if (!d) { d = document.createElement('div'); d.id = 'mention-dropdown'; d.style.display = 'none'; document.body.appendChild(d); }
      return d;
    }
    function hideMentionDropdown() {
      const d = document.getElementById('mention-dropdown');
      if (d) d.style.display = 'none';
      _mentionActive = false; _mentionStart = -1; _mentionFiltered = [];
    }
    async function onMentionInput(ta) {
      if (!selectedChatId || !isGroupChat(selectedChatId)) { hideMentionDropdown(); return; }
      const pos = ta.selectionStart;
      const before = ta.value.slice(0, pos);
      const m = before.match(/(?:^|\\s)@([^\\s@]*)$/);
      if (!m) { hideMentionDropdown(); return; }
      _mentionStart = pos - m[1].length - 1;
      const query = m[1].toLowerCase();
      const parts = await ensureParticipants(selectedChatId);
      if (selectedChatId && ta.selectionStart !== pos) return; // Cursor hat sich verschoben
      _mentionFiltered = parts.filter(p => (p.name||'').toLowerCase().includes(query) || (p.number||'').includes(query)).slice(0, 8);
      if (!_mentionFiltered.length) { hideMentionDropdown(); return; }
      _mentionSelIdx = 0;
      renderMentionDropdown();
    }
    function renderMentionDropdown() {
      const d = getMentionDropdown();
      d.innerHTML = _mentionFiltered.map((p, i) =>
        '<div class="mention-item' + (i === _mentionSelIdx ? ' active' : '') + '" data-i="' + i + '">' +
        '<span class="mention-av">' + esc((p.name || p.number || '?').charAt(0).toUpperCase()) + '</span>' +
        '<span class="mention-name">' + esc(p.name || p.number) + '</span></div>').join('');
      d.querySelectorAll('.mention-item').forEach(el => {
        el.addEventListener('mousedown', ev => { ev.preventDefault(); pickMention(parseInt(el.dataset.i, 10)); });
      });
      const bar = document.getElementById('send-bar').getBoundingClientRect();
      d.style.display = 'block';
      d.style.left = bar.left + 'px';
      d.style.width = bar.width + 'px';
      d.style.bottom = (window.innerHeight - bar.top + 4) + 'px';
      _mentionActive = true;
    }
    function pickMention(i) {
      const ta = document.getElementById('msg-input');
      const p = _mentionFiltered[i];
      if (!p || _mentionStart < 0) return;
      const pos = ta.selectionStart;
      const beforeTxt = ta.value.slice(0, _mentionStart);
      const afterTxt = ta.value.slice(pos);
      const token = '@' + (p.name || p.number);
      ta.value = beforeTxt + token + ' ' + afterTxt;
      const newPos = (beforeTxt + token + ' ').length;
      ta.setSelectionRange(newPos, newPos);
      if (!_pendingMentions.some(x => x.jid === p.jid)) _pendingMentions.push({ name: p.name || p.number, number: p.number, jid: p.jid });
      hideMentionDropdown();
      autoResize(ta);
      ta.focus();
    }
    function onMsgInputKeydown(event) {
      if (_mentionActive && _mentionFiltered.length) {
        if (event.key === 'ArrowDown') { event.preventDefault(); _mentionSelIdx = (_mentionSelIdx + 1) % _mentionFiltered.length; renderMentionDropdown(); return; }
        if (event.key === 'ArrowUp')   { event.preventDefault(); _mentionSelIdx = (_mentionSelIdx - 1 + _mentionFiltered.length) % _mentionFiltered.length; renderMentionDropdown(); return; }
        if (event.key === 'Enter' || event.key === 'Tab') { event.preventDefault(); pickMention(_mentionSelIdx); return; }
        if (event.key === 'Escape') { event.preventDefault(); hideMentionDropdown(); return; }
      }
      if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMsg(); }
    }
    // Ersetzt sichtbare @Name-Tokens durch @<nummer> und sammelt die JIDs
    function buildMentions(text) {
      const out = { text, mentions: [] };
      const sorted = [..._pendingMentions].sort((a, b) => (b.name||'').length - (a.name||'').length);
      for (const mn of sorted) {
        const token = '@' + mn.name;
        if (out.text.includes(token)) {
          out.text = out.text.split(token).join('@' + mn.number);
          if (!out.mentions.includes(mn.jid)) out.mentions.push(mn.jid);
        }
      }
      return out;
    }

    let _sending = false; // verhindert Doppelversand bei schnellem Doppel-Tap/Doppel-Enter
    async function sendMsg() {
      if (_sending) return;
      if (!selectedChatId) return;
      _sending = true;
      try {
        if (_attachFile) { await sendFile(); return; }
        const txt = document.getElementById('msg-input').value.trim();
        if (!txt) return;
        hideMentionDropdown();
        const quotedMsgId = _replyMsgId;
        clearReply();
        const built = buildMentions(txt);
        _pendingMentions = [];
        const endpoint = quotedMsgId ? 'api/reply' : 'api/send';
        const payload = quotedMsgId
          ? { quotedMsgId, chatId: selectedChatId, message: built.text, mentions: built.mentions, displayBody: txt }
          : { to: selectedChatId, message: built.text, mentions: built.mentions, displayBody: txt };
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
      finally { _sending = false; }
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
      if (isDeleteMode) {
        var wrap = e.target.closest('.bubble-wrap');
        if (wrap && wrap.dataset.msgid) {
          var id = wrap.dataset.msgid;
          if (selectedMsgs.has(id)) { selectedMsgs.delete(id); wrap.classList.remove('selected'); }
          else { selectedMsgs.add(id); wrap.classList.add('selected'); }
          updateDeleteBtn();
        }
        return;
      }
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

    let _offlineFails = 0;
    function showOfflineBanner() { document.getElementById('offline-banner').style.display = 'flex'; }
    function hideOfflineBanner() { document.getElementById('offline-banner').style.display = 'none'; }

    async function refresh() {
      try {
        const s = await fetch('api/status').then(r => r.json());
        _offlineFails = 0;
        if (navigator.onLine !== false) hideOfflineBanner();
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
          if (connected) { await pollChats(); pollStatuses(); }
        }
      } catch(e) {
        _offlineFails++;
        if (_offlineFails >= 3) showOfflineBanner();
      }
    }

    applyLang();
    if (!navigator.onLine) showOfflineBanner();
    refresh();
    // Intervalle pausieren, wenn der Tab im Hintergrund ist (spart Last/Requests);
    // visibilitychange unten aktualisiert sofort beim Zurückkehren
    setInterval(() => { if (!document.hidden) refresh(); }, 5000);
    setInterval(pollMessages, 2000);
    setInterval(pollChats, 10000);
    setInterval(pollStatuses, 30000);
    setInterval(pollReactions, 5000);

    // Mentions-Dropdown schließen, wenn außerhalb geklickt wird
    document.addEventListener('click', (e) => {
      if (!e.target.closest('#mention-dropdown') && e.target.id !== 'msg-input') hideMentionDropdown();
    });

    // Tab wird wieder sichtbar (Laptop aufgeklappt, Tab-Wechsel) → sofort aktualisieren
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState !== 'visible') return;
      refresh();
      pollChats();
      if (selectedChatId) loadMessages(selectedChatId);
    });
    // Netzwerk wieder da
    window.addEventListener('online', () => { _offlineFails = 0; refresh(); pollChats(); });
    // Netzwerk weg → Banner sofort zeigen
    window.addEventListener('offline', () => showOfflineBanner());

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
        if (isDeleteMode) { exitDeleteMode(); return; }
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
      if (document.hidden || !selectedChatId) return;
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
  <style>
    #wa-console{display:none;position:fixed;bottom:80px;right:20px;width:560px;height:340px;background:#0d1117;border:1px solid #30363d;border-radius:8px;z-index:9999;flex-direction:column;font-family:monospace;font-size:12px;box-shadow:0 8px 32px rgba(0,0,0,0.6);resize:both;overflow:hidden;min-width:320px;min-height:180px;}
    #wa-console.open{display:flex;}
    #wa-console-header{display:flex;align-items:center;justify-content:space-between;padding:5px 10px;background:#161b22;border-bottom:1px solid #30363d;flex-shrink:0;cursor:move;user-select:none;border-radius:7px 7px 0 0;}
    #wa-console-title{color:#8b949e;font-size:11px;font-weight:600;letter-spacing:.05em;}
    #wa-console-close{background:none;border:none;color:#8b949e;cursor:pointer;font-size:14px;padding:2px 6px;line-height:1;}
    #wa-console-close:hover{color:#f85149;}
    #wa-console-body{flex:1;overflow-y:auto;padding:6px 10px;line-height:1.6;}
    #wa-console-body::-webkit-scrollbar{width:5px;}#wa-console-body::-webkit-scrollbar-thumb{background:#30363d;border-radius:3px;}
    .wc-info{color:#3fb950;}.wc-warn{color:#d29922;}.wc-error{color:#f85149;}.wc-debug{color:#6e7681;}
    @media(max-width:767px){#wa-console{display:none!important;}}
  </style>
  <div id="wa-console">
    <div id="wa-console-header">
      <span id="wa-console-title">⬛ CONSOLE — WhatsApp</span>
      <button id="wa-console-close" onclick="waConsoleToggle()">✕</button>
    </div>
    <div id="wa-console-body"></div>
  </div>
  <script>
    (function(){
      var _open=false,_lastTs=0,_timer=null;
      var panel=document.getElementById('wa-console');
      var header=document.getElementById('wa-console-header');
      var body=document.getElementById('wa-console-body');
      // Drag
      var _dx=0,_dy=0,_dragging=false;
      header.addEventListener('mousedown',function(e){
        if(e.target===document.getElementById('wa-console-close'))return;
        _dragging=true;
        _dx=e.clientX-panel.offsetLeft;
        _dy=e.clientY-panel.offsetTop;
        e.preventDefault();
      });
      document.addEventListener('mousemove',function(e){
        if(!_dragging)return;
        var x=Math.max(0,Math.min(e.clientX-_dx,window.innerWidth-panel.offsetWidth));
        var y=Math.max(0,Math.min(e.clientY-_dy,window.innerHeight-panel.offsetHeight));
        panel.style.left=x+'px'; panel.style.top=y+'px';
        panel.style.right='auto'; panel.style.bottom='auto';
      });
      document.addEventListener('mouseup',function(){_dragging=false;});
      function waConsoleToggle(){
        if(window.innerWidth<768)return;
        _open=!_open;
        panel.classList.toggle('open',_open);
        if(_open){_poll();_timer=setInterval(_poll,2000);}
        else{clearInterval(_timer);_timer=null;}
      }
      window.waConsoleToggle=waConsoleToggle;
      function _cls(l){return l==='WARN'?'wc-warn':l==='ERROR'?'wc-error':l==='DEBUG'?'wc-debug':'wc-info';}
      async function _poll(){
        try{
          var entries=await fetch('api/logs?since='+_lastTs).then(function(r){return r.json();});
          if(!entries.length)return;
          var atBottom=body.scrollHeight-body.scrollTop-body.clientHeight<40;
          entries.forEach(function(e){
            _lastTs=Math.max(_lastTs,e.ts);
            var line=document.createElement('div');
            line.className=_cls(e.level);
            line.textContent=e.msg;
            body.appendChild(line);
          });
          if(atBottom)body.scrollTop=body.scrollHeight;
          if(body.children.length>600)for(var i=0;i<100;i++)body.removeChild(body.firstChild);
        }catch(e){}
      }
    })();
  </script>
</body>
</html>`);
});

// ── Start ─────────────────────────────────────────────────────────────────────

fs.mkdirSync(MEDIA_DIR, { recursive: true });

const PORT = parseInt(process.env.PORT || '17776', 10);
app.listen(PORT, () => console.log(`[INFO] Web UI running on port ${PORT}`));
