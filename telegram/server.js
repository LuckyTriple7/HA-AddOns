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
const express = require('express');
const http = require('http');
const { TelegramClient, Api } = require('telegram');
const { StringSession } = require('telegram/sessions');
const { NewMessage, Raw } = require('telegram/events');
const { CustomFile } = require('telegram/client/uploads');
const fs = require('fs');
const multer = require('multer');
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 64 * 1024 * 1024 } });

const app = express();
app.use(express.json());

const PORT = parseInt(process.env.PORT || '3000', 10);
const API_ID = parseInt(process.env.API_ID || '0', 10);
const API_HASH = process.env.API_HASH || '';
const PHONE_NUMBER = process.env.PHONE_NUMBER || '';
const WEBHOOK_INCOMING = process.env.WEBHOOK_INCOMING || '';
const DARK_MODE = process.env.DARK_MODE !== 'false';
const DOWNLOAD_MEDIA = process.env.DOWNLOAD_MEDIA === 'true';
const MEDIA_MAX_MB = Math.max(parseInt(process.env.MEDIA_MAX_MB || '500', 10), 50);
const FETCH_LIMIT = Math.min(Math.max(parseInt(process.env.FETCH_LIMIT || '50', 10), 1), 300);
const DEBUG = process.env.DEBUG_MODE === 'true';
const HA_NOTIFY = process.env.HA_NOTIFICATIONS === 'true';
const HA_PRIVACY = process.env.HA_NOTIFICATIONS_PRIVACY === 'true';
const HA_NOTIFY_SKIP_BOTS = process.env.HA_NOTIFY_SKIP_BOTS === 'true';
function dbg(...args) { if (DEBUG) console.log('[DEBUG]', ...args); }

const GRAMJS_VERSION = require('./node_modules/telegram/package.json').version;
console.log(`[INFO] GramJS (telegram) v${GRAMJS_VERSION}`);
console.log('[INFO] ── Configuration ──────────────────────────────────');
console.log(`[INFO]   api_id                 = ${API_ID ? 'set' : 'not set'}`);
console.log(`[INFO]   api_hash               = ${API_HASH ? 'set' : 'not set'}`);
console.log(`[INFO]   phone_number           = ${PHONE_NUMBER ? 'set' : 'not set'}`);
console.log(`[INFO]   dark_mode              = ${DARK_MODE}`);
console.log(`[INFO]   download_media         = ${DOWNLOAD_MEDIA}`);
console.log(`[INFO]   debug_mode             = ${DEBUG}`);
console.log(`[INFO]   ha_notifications       = ${HA_NOTIFY}`);
console.log(`[INFO]   ha_notifications_priv  = ${HA_PRIVACY}`);
console.log(`[INFO]   ha_notify_skip_bots    = ${HA_NOTIFY_SKIP_BOTS}`);
console.log(`[INFO]   ha_token               = ${process.env.HA_TOKEN ? 'set' : 'not set'}`);
console.log(`[INFO]   fetch_limit            = ${FETCH_LIMIT}`);
console.log(`[INFO]   webhook_incoming       = ${WEBHOOK_INCOMING ? WEBHOOK_INCOMING : 'not set'}`);
console.log('[INFO] ─────────────────────────────────────────────────────');

const SESSION_FILE = '/config/session.txt';
const CHATS_FILE = '/config/chats.json';
const MESSAGES_FILE = '/config/messages.json';
const MEDIA_DIR = '/config/media';
// ── State ─────────────────────────────────────────────────────────────────────

let status = 'starting'; // starting | awaiting_code | awaiting_password | connected | error
let lastError = '';
let lastReceivedMsg = null; // { timestamp, iso, chatId, chatName, contact, preview }
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

function getEntityType(entity) {
  if (!entity) return 'private';
  if (entity.bot === true) return 'bot';
  if (entity.className === 'Chat') return 'group';
  if (entity.className === 'Channel') return entity.megagroup ? 'group' : 'channel';
  return 'private';
}

function addMsg(chatId, msg) {
  if (seenMsgIds.has(msg.id)) { dbg(`addMsg: duplicate skipped ${msg.id}`); return false; }
  seenMsgIds.add(msg.id);
  dbg(`addMsg: chatId=${chatId} fromMe=${msg.fromMe} type=${msg.type||'text'} body="${(msg.body||'').slice(0,60)}"`);
  if (!messagesByChatId.has(chatId)) messagesByChatId.set(chatId, []);
  const msgs = messagesByChatId.get(chatId);
  msgs.push(msg);
  msgs.sort((a, b) => a.timestamp - b.timestamp);
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
      const attrs = rawMsg.media.document?.attributes || [];
      const isVoice = attrs.some(a => a.className === 'DocumentAttributeAudio' && a.voice);
      const isVideo = !isVoice && (attrs.some(a => a.className === 'DocumentAttributeVideo') || mime.startsWith('video/'));
      if (isVoice) {
        ext = 'ogg';
      } else if (isVideo) {
        const fileSize = rawMsg.media.document?.size || 0;
        if (fileSize > 50 * 1024 * 1024) return null; // max 50 MB
        ext = mime === 'video/webm' ? 'webm' : mime === 'video/ogg' ? 'ogv' : 'mp4';
      } else if (mime.startsWith('image/')) {
        ext = mime === 'image/webp' ? 'webp' : mime === 'image/png' ? 'png' : 'jpg';
      } else {
        return null;
      }
    } else if (mediaClass !== 'MessageMediaPhoto') {
      return null;
    }
    const filePath = `${MEDIA_DIR}/${safeId}.${ext}`;
    if (!fs.existsSync(filePath)) {
      enforceMediaLimit();
      const buf = await client.downloadMedia(rawMsg, { workers: 1 });
      if (buf) fs.writeFileSync(filePath, buf);
    }
    return fs.existsSync(filePath) ? `${safeId}.${ext}` : null;
  } catch (e) {
    console.error('[ERROR] downloadMedia:', e.message);
    return null;
  }
}

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
    title: 'Telegram',
    message: 'Neue Nachricht',
    notification_id: 'telegram_new_message',
  } : {
    title: `Telegram: ${senderName}`,
    message: preview || '📷 Foto',
    notification_id: `telegram_${safeId}`,
  });
  console.log(`[INFO] HA notification: Telegram${HA_PRIVACY ? '' : `: ${senderName}`}`);
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

async function processMessage(rawMsg, chatId, chatName, source = 'unknown') {
  const hasText = !!(rawMsg.message);
  const hasMedia = rawMsg.media && rawMsg.media.className && rawMsg.media.className !== 'MessageMediaEmpty';
  dbg(`processMessage [${source}]: chatId=${chatId} id=${rawMsg.id} fromMe=${rawMsg.out} class=${rawMsg.className||'?'} action=${rawMsg.action?.className||'none'} hasText=${hasText} hasMedia=${hasMedia} body="${(rawMsg.message||'').slice(0,60)}"`);
  if (!hasText && !hasMedia) { dbg(`processMessage [${source}]: skipping — no text and no media`); return; }

  const fromMe = rawMsg.out || false;
  const ts = (rawMsg.date || 0) * 1000;
  const msgId = `${chatId}_${rawMsg.id}`;

  if (seenMsgIds.has(msgId)) { dbg(`processMessage [${source}]: duplicate skipped ${msgId}`); return; }
  seenMsgIds.add(msgId);

  let type = 'text';
  let mediaFile = null;
  if (hasMedia) {
    const mc = rawMsg.media?.className;
    const attrs = rawMsg.media?.document?.attributes || [];
    const isVoice = mc === 'MessageMediaDocument' && attrs.some(a => a.className === 'DocumentAttributeAudio' && a.voice);
    const isImage = !isVoice && (mc === 'MessageMediaPhoto' ||
      (mc === 'MessageMediaDocument' && rawMsg.media.document?.mimeType?.startsWith('image/')));
    const isVideo = !isVoice && !isImage && mc === 'MessageMediaDocument' &&
      rawMsg.media.document?.mimeType?.startsWith('video/');
    if (isVoice) {
      type = 'voice';
      if (DOWNLOAD_MEDIA) mediaFile = await downloadMedia(rawMsg, msgId);
    } else if (isImage) {
      type = 'photo';
      if (DOWNLOAD_MEDIA) mediaFile = await downloadMedia(rawMsg, msgId);
    } else if (isVideo) {
      type = 'video';
      if (DOWNLOAD_MEDIA) mediaFile = await downloadMedia(rawMsg, msgId);
    }
  }

  const body = rawMsg.message || (type === 'photo' && !mediaFile ? '📷 Foto' : type === 'video' ? '📹 Video' : '');
  const preview = body || (type === 'photo' ? '📷 Foto' : '[Medien]');

  const msgReactions = {};
  let msgMyReaction = null;
  for (const r of (rawMsg.reactions?.results || [])) {
    const em = r.reaction?.emoticon;
    if (em && r.count > 0) msgReactions[em] = r.count;
  }
  for (const rr of (rawMsg.reactions?.recentReactions || [])) {
    if (rr.self) { msgMyReaction = rr.reaction?.emoticon || null; break; }
  }

  if (!messagesByChatId.has(chatId)) messagesByChatId.set(chatId, []);
  const msgs = messagesByChatId.get(chatId);
  let quotedMsg = null;
  if (rawMsg.replyTo?.replyToMsgId) {
    const qId = `${chatId}_${rawMsg.replyTo.replyToMsgId}`;
    const qStored = messagesByChatId.get(chatId)?.find(m => m.id === qId);
    if (qStored) quotedMsg = { body: (qStored.body || '').slice(0, 100), contact: qStored.fromMe ? 'Ich' : (chatMap.get(chatId)?.name || chatId) };
  }
  const msgObj = { id: msgId, from: fromMe ? myId : chatId, body, type, mediaFile, timestamp: ts, fromMe, ack: fromMe ? 1 : 0, quotedMsg };
  if (Object.keys(msgReactions).length) msgObj.reactions = msgReactions;
  if (msgMyReaction) msgObj.myReaction = msgMyReaction;
  msgs.push(msgObj);
  msgs.sort((a, b) => a.timestamp - b.timestamp);

  if (!chatMap.has(chatId)) {
    chatMap.set(chatId, { id: chatId, name: chatName, phone: '', lastMsg: preview, lastTime: ts });
  } else {
    const chat = chatMap.get(chatId);
    if (ts >= (chat.lastTime || 0)) { chat.lastMsg = preview; chat.lastTime = ts; }
  }
  scheduleSave();

  if (!fromMe && source === 'NewMessage') {
    const isBot = chatMap.get(chatId)?.isBot;
    const skipBot = HA_NOTIFY_SKIP_BOTS && isBot;
    dbg(`HA-Notification check [${source}]: msgId=${msgId} isBot=${isBot} skipBot=${skipBot} body="${(body||'').slice(0,60)}"`);
    if (!skipBot) {
      lastReceivedMsg = {
        timestamp: ts,
        iso: new Date(ts).toISOString(),
        chatId,
        chatName,
        contact: chatName,
        type,
        preview,
      };
      sendHANotification(chatId, chatName, body || (type === 'photo' ? '📷 Foto' : ''));
    }
  }
  if (WEBHOOK_INCOMING && !fromMe) {
    dbg(`Firing incoming webhook: ${WEBHOOK_INCOMING}`);
    fetch(WEBHOOK_INCOMING, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from: chatId, name: chatName, message: body || '[Foto]', type, timestamp: ts }),
    }).catch(() => {});
  }
}

async function loadDialogs() {
  if (status !== 'connected') return;
  try {
    const dialogs = await Promise.race([
      client.getDialogs({ limit: 50 }),
      new Promise((_, reject) => setTimeout(() => reject(new Error('timeout after 15s')), 15000)),
    ]);
    for (const dialog of dialogs) {
      if (!dialog.entity) continue;
      const entity = dialog.entity;
      const chatId = getEntityId(entity);
      const name = getEntityName(entity);
      peerMap.set(chatId, entity);
      const isBot = entity.bot === true;
      const chatType = getEntityType(entity);
      if (!chatMap.has(chatId) || !chatMap.get(chatId).lastTime) {
        chatMap.set(chatId, {
          id: chatId, name, phone: '',
          lastMsg: dialog.message?.message || '',
          lastTime: (dialog.message?.date || 0) * 1000,
          isBot, chatType,
        });
      } else {
        const c = chatMap.get(chatId);
        c.isBot = isBot;
        c.chatType = chatType;
      }
    }
    scheduleSave();
  } catch (e) { console.error('[ERROR] loadDialogs:', e.message); }
}

async function fetchMessages(chatId, limit = FETCH_LIMIT) {
  try {
    let entity = peerMap.get(chatId);
    if (!entity) { await loadDialogs(); entity = peerMap.get(chatId); }
    if (!entity) return;
    const msgs = await client.getMessages(entity, { limit });
    const chatName = chatMap.get(chatId)?.name || chatId;
    for (const msg of msgs) processMessage(msg, chatId, chatName, 'fetchMessages');
  } catch (e) { console.error(`[ERROR] fetchMessages(${chatId}):`, e.message); }
}

async function startClient() {
  if (!API_ID || !API_HASH || !PHONE_NUMBER) {
    status = 'error';
    lastError = 'Please set api_id, api_hash and phone_number in the add-on configuration';
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
        dbg(`NewMessage event: id=${msg.id} class=${msg.className||'?'} action=${msg.action?.className||'none'} fromMe=${msg.out} reactions=${msg.reactions?.results?.length||0} body="${(msg.message||'').slice(0,60)}"`);
        const chat = await msg.getChat();
        const chatId = getEntityId(chat);
        const chatName = getEntityName(chat);
        if (!peerMap.has(chatId)) peerMap.set(chatId, chat);
        if (chatMap.has(chatId)) {
          const c = chatMap.get(chatId);
          c.isBot = chat.bot === true;
          c.chatType = getEntityType(chat);
        }
        await processMessage(msg, chatId, chatName, 'NewMessage');
      } catch (e) { dbg(`NewMessage handler error: ${e.message}`); }
    }, new NewMessage({}));

    client.addEventHandler((update) => {
      const peer = update.peer;
      const chatId = String(peer?.userId || peer?.chatId || peer?.channelId || '');
      if (!chatId) return;

      if (update.className === 'UpdateReadHistoryOutbox') {
        const maxId = update.maxId;
        const msgs = messagesByChatId.get(chatId);
        if (!msgs) return;
        let changed = false;
        msgs.forEach(m => {
          if (!m.fromMe || m.ack >= 3) return;
          const rawId = parseInt(m.id.split('_').pop(), 10);
          if (rawId <= maxId) { m.ack = 3; changed = true; }
        });
        if (changed) dbg(`UpdateReadHistoryOutbox: chatId=${chatId} maxId=${update.maxId}`);
      }

      if (update.className === 'UpdateMessageReactions') {
        const msgId = `${chatId}_${update.msgId}`;
        const msgs = messagesByChatId.get(chatId);
        if (!msgs) return;
        const msg = msgs.find(m => m.id === msgId);
        if (!msg) return;
        const newReactions = {};
        for (const r of (update.reactions?.results || [])) {
          const emoticon = r.reaction?.emoticon;
          if (emoticon && r.count > 0) newReactions[emoticon] = r.count;
        }
        msg.reactions = newReactions;
        scheduleSave();
        dbg(`UpdateMessageReactions: ${msgId} → ${JSON.stringify(newReactions)}`);
      }
    }, new Raw({}));

    await loadDialogs();
    console.log(`[INFO] ${chatMap.size} dialogs loaded`);
    if (DEBUG) console.log('[DEBUG] Debug-Modus aktiv');
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

app.get('/api/stats', (req, res) => {
  const { chat: chatId } = req.query;
  if (!chatId) return res.json({});
  const msgs = messagesByChatId.get(chatId) || [];
  const sent = msgs.filter(m => m.fromMe).length;
  const received = msgs.filter(m => !m.fromMe).length;
  const photos = msgs.filter(m => m.type === 'photo').length;
  const first = msgs.length ? Math.min(...msgs.map(m => m.timestamp)) : null;
  res.json({ total: msgs.length, sent, received, photos, first });
});

app.get('/api/messages/:chatId', async (req, res) => {
  const { chatId } = req.params;
  if (req.query.refresh === '1' && status === 'connected') {
    const prevMsgs = messagesByChatId.get(chatId) || [];
    const savedReactions = new Map(prevMsgs.map(m => [m.id, { reactions: m.reactions, myReaction: m.myReaction }]));
    prevMsgs.forEach(m => seenMsgIds.delete(m.id));
    messagesByChatId.delete(chatId);
    await fetchMessages(chatId);
    for (const m of (messagesByChatId.get(chatId) || [])) {
      const saved = savedReactions.get(m.id);
      if (!saved) continue;
      if (!m.myReaction && saved.myReaction) m.myReaction = saved.myReaction;
      if ((!m.reactions || !Object.keys(m.reactions).length) && Object.keys(saved.reactions || {}).length) m.reactions = saved.reactions;
    }
    return res.json(messagesByChatId.get(chatId) || []);
  }
  const existing = messagesByChatId.get(chatId) || [];
  if (existing.length < FETCH_LIMIT && status === 'connected') {
    await fetchMessages(chatId);
    return res.json(messagesByChatId.get(chatId) || []);
  }
  res.json(existing);
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
    const d = new Date(m.timestamp);
    const dateStr = d.toLocaleDateString('de-DE', { weekday:'long', day:'2-digit', month:'long', year:'numeric' });
    const time = d.toLocaleTimeString('de-DE', { hour:'2-digit', minute:'2-digit' });
    let sep = '';
    if (dateStr !== lastDate) { sep = `<div class="day-sep">${escH(dateStr)}</div>`; lastDate = dateStr; }
    let content = '';
    if (m.type === 'voice' && m.mediaFile) {
      const fp = `${MEDIA_DIR}/${m.mediaFile}`;
      content = fs.existsSync(fp)
        ? `<audio controls style="min-width:200px;max-width:280px;width:100%" src="data:audio/ogg;base64,${fs.readFileSync(fp).toString('base64')}"></audio>`
        : '<span style="opacity:0.6">🎵 Sprachnachricht</span>';
    } else if (m.type === 'video' && m.mediaFile) {
      const fp = `${MEDIA_DIR}/${m.mediaFile}`;
      const ext = m.mediaFile.split('.').pop().toLowerCase();
      const vmime = ext==='webm'?'video/webm':ext==='ogv'?'video/ogg':'video/mp4';
      content = fs.existsSync(fp)
        ? `<video controls style="max-width:280px;max-height:280px;border-radius:6px;display:block" src="data:${vmime};base64,${fs.readFileSync(fp).toString('base64')}"></video>`
        : '<span style="opacity:0.6">📹 Video</span>';
      if (m.body) content += `<div style="margin-top:4px">${escH(m.body)}</div>`;
    } else if (m.type === 'photo' && m.mediaFile) {
      const fp = `${MEDIA_DIR}/${m.mediaFile}`;
      if (fs.existsSync(fp)) {
        const ext = m.mediaFile.split('.').pop().toLowerCase();
        const mime = ext==='png'?'image/png':ext==='webp'?'image/webp':'image/jpeg';
        content = `<img src="data:${mime};base64,${fs.readFileSync(fp).toString('base64')}" style="max-width:280px;max-height:280px;border-radius:6px;display:block;">`;
      } else { content = '📷 Foto'; }
      if (m.body) content += `<div style="margin-top:4px">${escH(m.body)}</div>`;
    } else if (m.type === 'document' && m.filename) {
      content = `<div style="display:flex;align-items:center;gap:8px"><span style="font-size:22px">📄</span><span style="font-weight:500">${escH(m.filename)}</span></div>`;
      if (m.body) content += `<div style="margin-top:4px">${escH(m.body)}</div>`;
    } else {
      content = escH(m.body||'').replace(/\n/g,'<br>');
    }
    const sender = m.fromMe ? 'Du' : escH(chatName);
    return `${sep}<div class="msg ${m.fromMe?'out':'in'}"><div class="bubble"><div class="meta"><span class="sender">${sender}</span><span class="time">${time}</span></div><div class="content">${content}</div></div></div>`;
  }).join('\n');
  const html = `<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Chat: ${escH(chatName)}</title><style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#1a2633;min-height:100vh;padding:16px;color:#e0e0e0}h1{text-align:center;font-size:18px;color:#fff;padding:12px 0 4px}.export-info{text-align:center;font-size:12px;color:#8696a0;margin-bottom:16px}.day-sep{text-align:center;margin:12px 0;font-size:12px;color:#8696a0;background:rgba(255,255,255,.06);border-radius:8px;display:inline-block;padding:2px 10px;width:100%}.msg{display:flex;margin:3px 0}.msg.in{justify-content:flex-start}.msg.out{justify-content:flex-end}.bubble{max-width:70%;padding:7px 10px;border-radius:8px;font-size:14px;line-height:1.45;word-break:break-word}.msg.in .bubble{background:#232e3c;border-bottom-left-radius:2px}.msg.out .bubble{background:#2b5278;border-bottom-right-radius:2px}.meta{display:flex;justify-content:space-between;gap:8px;margin-bottom:3px;font-size:12px}.sender{font-weight:600;color:#2AABEE}.msg.out .sender{color:#6ec6f5}.time{color:#8696a0;flex-shrink:0}@media print{body{background:#fff;color:#000}.msg.in .bubble{background:#f0f0f0}.msg.out .bubble{background:#d6eaf8}}</style></head><body><h1>${escH(chatName)}</h1><p class="export-info">Exportiert am ${exportDate} &bull; ${msgs.length} Nachrichten</p>${msgsHtml}</body></html>`;
  const fname = `telegram_${chatName.replace(/[^a-zA-Z0-9_-]/g,'_').slice(0,40)}_${new Date().toISOString().slice(0,10)}.html`;
  res.setHeader('Content-Type','text/html; charset=utf-8');
  res.setHeader('Content-Disposition',`attachment; filename="${fname}"`);
  res.send(html);
});

app.post('/api/send', async (req, res) => {
  const { to, message } = req.body;
  if (!to || !message) return res.status(400).json({ error: 'to und message erforderlich' });
  if (status !== 'connected') return res.status(503).json({ error: 'Nicht verbunden' });
  try {
    let entity = peerMap.get(to);
    if (!entity) { await loadDialogs(); entity = peerMap.get(to); }
    if (!entity) return res.status(404).json({ error: 'Chat nicht gefunden' });

    dbg(`Sending message to ${to}: "${message.slice(0,60)}${message.length>60?'…':''}"`);
    const result = await client.sendMessage(entity, { message });
    const msgId = `${to}_${result.id}`;
    if (!seenMsgIds.has(msgId)) {
      seenMsgIds.add(msgId);
      const ts = Date.now();
      if (!messagesByChatId.has(to)) messagesByChatId.set(to, []);
      messagesByChatId.get(to).push({ id: msgId, from: myId, body: message, timestamp: ts, fromMe: true, ack: 1 });
      if (chatMap.has(to)) { chatMap.get(to).lastMsg = message; chatMap.get(to).lastTime = ts; }
      scheduleSave();
    }
    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/reply', async (req, res) => {
  const { to, message, replyToTgId } = req.body;
  if (!to || !message) return res.status(400).json({ error: 'to und message erforderlich' });
  if (status !== 'connected') return res.status(503).json({ error: 'Nicht verbunden' });
  try {
    let entity = peerMap.get(to);
    if (!entity) { await loadDialogs(); entity = peerMap.get(to); }
    if (!entity) return res.status(404).json({ error: 'Chat nicht gefunden' });
    const result = await client.sendMessage(entity, { message, replyTo: replyToTgId ? Number(replyToTgId) : undefined });
    const msgId = `${to}_${result.id}`;
    if (!seenMsgIds.has(msgId)) {
      seenMsgIds.add(msgId);
      const ts = Date.now();
      if (!messagesByChatId.has(to)) messagesByChatId.set(to, []);
      messagesByChatId.get(to).push({ id: msgId, from: myId, body: message, timestamp: ts, fromMe: true, ack: 1 });
      if (chatMap.has(to)) { chatMap.get(to).lastMsg = message; chatMap.get(to).lastTime = ts; }
      scheduleSave();
    }
    res.json({ success: true });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/forward', async (req, res) => {
  const { msgId, to } = req.body;
  if (!msgId || !to) return res.status(400).json({ error: 'msgId und to erforderlich' });
  if (status !== 'connected') return res.status(503).json({ error: 'Nicht verbunden' });
  try {
    const tgMsgId = parseInt(msgId.split('_').pop(), 10);
    const fromChatId = msgId.split('_').slice(0, -1).join('_');
    let fromEntity = peerMap.get(fromChatId);
    if (!fromEntity) { await loadDialogs(); fromEntity = peerMap.get(fromChatId); }
    let toEntity = peerMap.get(to);
    if (!toEntity) { await loadDialogs(); toEntity = peerMap.get(to); }
    if (!fromEntity || !toEntity) return res.status(404).json({ error: 'Chat nicht gefunden' });
    await client.forwardMessages(toEntity, { messages: [tgMsgId], fromPeer: fromEntity });
    res.json({ success: true });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/send-media', upload.single('file'), async (req, res) => {
  const { to, caption } = req.body;
  if (!to || !req.file) return res.status(400).json({ error: 'to und file erforderlich' });
  if (status !== 'connected') return res.status(503).json({ error: 'Nicht verbunden' });
  try {
    let entity = peerMap.get(to);
    if (!entity) { await loadDialogs(); entity = peerMap.get(to); }
    if (!entity) return res.status(404).json({ error: 'Chat nicht gefunden' });

    const { originalname, mimetype, buffer } = req.file;
    const isImg = mimetype.startsWith('image/');
    const safeName = originalname.replace(/[^a-zA-Z0-9._-]/g, '_');

    const result = await client.sendFile(entity, {
      file: new CustomFile(safeName, buffer.length, '', buffer),
      caption: caption || '',
      forceDocument: !isImg,
    });

    const msgId = `${to}_${result.id}`;
    if (!seenMsgIds.has(msgId)) {
      seenMsgIds.add(msgId);
      const ts = Date.now();
      let mediaFile = null;
      if (isImg && DOWNLOAD_MEDIA) {
        const fname = `${ts}_${safeName}`;
        fs.writeFileSync(`${MEDIA_DIR}/${fname}`, buffer);
        mediaFile = fname;
      }
      const msgObj = isImg
        ? { id: msgId, from: myId, body: caption || '', type: 'photo', mediaFile, timestamp: ts, fromMe: true, ack: 1 }
        : { id: msgId, from: myId, body: caption || '', type: 'document', filename: safeName, timestamp: ts, fromMe: true, ack: 1 };
      if (!messagesByChatId.has(to)) messagesByChatId.set(to, []);
      messagesByChatId.get(to).push(msgObj);
      if (chatMap.has(to)) {
        chatMap.get(to).lastMsg = caption || (isImg ? '📷 Foto' : safeName);
        chatMap.get(to).lastTime = ts;
      }
      scheduleSave();
    }

    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.delete('/api/messages/:chatId/:msgId', async (req, res) => {
  const { chatId, msgId } = req.params;
  if (status !== 'connected') return res.status(503).json({ error: 'Nicht verbunden' });
  try {
    let entity = peerMap.get(chatId);
    if (!entity) { await loadDialogs(); entity = peerMap.get(chatId); }
    if (!entity) return res.status(404).json({ error: 'Chat nicht gefunden' });
    const rawId = parseInt(msgId.split('_').pop(), 10);
    dbg(`Deleting message ${msgId} (rawId=${rawId}) in chat ${chatId}`);
    await client.deleteMessages(entity, [rawId], { revoke: true });
    const msgs = messagesByChatId.get(chatId);
    if (msgs) {
      const idx = msgs.findIndex(m => m.id === msgId);
      if (idx !== -1) { msgs.splice(idx, 1); seenMsgIds.delete(msgId); scheduleSave(); }
    }
    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/react', async (req, res) => {
  const { msgId, reaction } = req.body;
  if (!msgId) return res.status(400).json({ error: 'msgId erforderlich' });
  if (status !== 'connected') return res.status(503).json({ error: 'Nicht verbunden' });
  try {
    const parts = msgId.split('_');
    const rawId = parseInt(parts[parts.length - 1], 10);
    const chatId = parts.slice(0, -1).join('_');
    let entity = peerMap.get(chatId);
    if (!entity) { await loadDialogs(); entity = peerMap.get(chatId); }
    if (!entity) return res.status(404).json({ error: 'Chat nicht gefunden' });
    const reactionList = reaction ? [new Api.ReactionEmoji({ emoticon: reaction })] : [];
    await client.invoke(new Api.messages.SendReaction({ peer: entity, msgId: rawId, reaction: reactionList }));
    const msgs = messagesByChatId.get(chatId);
    if (msgs) {
      const msg = msgs.find(m => m.id === msgId);
      if (msg) {
        if (!msg.reactions) msg.reactions = {};
        const prev = msg.myReaction;
        if (prev) { msg.reactions[prev] = Math.max(0, (msg.reactions[prev] || 1) - 1); if (!msg.reactions[prev]) delete msg.reactions[prev]; }
        msg.myReaction = reaction || null;
        if (reaction) msg.reactions[reaction] = (msg.reactions[reaction] || 0) + 1;
        scheduleSave();
      }
    }
    res.json({ success: true });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/reactions/:chatId', (req, res) => {
  const msgs = messagesByChatId.get(req.params.chatId) || [];
  const result = {};
  for (const m of msgs) {
    if ((m.reactions && Object.keys(m.reactions).length) || m.myReaction) {
      result[m.id] = { reactions: m.reactions || {}, myReaction: m.myReaction || null };
    }
  }
  res.json(result);
});

app.get('/api/last-received', (req, res) => {
  const { chat: chatId } = req.query;
  if (chatId) {
    const msgs = (messagesByChatId.get(chatId) || []).filter(m => !m.fromMe && !m.deleted);
    if (!msgs.length) return res.json(null);
    const last = msgs[msgs.length - 1];
    const chat = chatMap.get(chatId);
    return res.json({
      timestamp: last.timestamp,
      iso: new Date(last.timestamp).toISOString(),
      chatId,
      chatName: chat?.name || chatId,
      contact: chat?.name || chatId,
      type: last.type || 'text',
      preview: last.body || (last.type === 'photo' ? '📷 Foto' : last.type === 'video' ? '📹 Video' : last.type === 'voice' ? '🎵 Sprachnachricht' : '[Medien]'),
    });
  }
  res.json(lastReceivedMsg);
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

// ── Keep-alive: erkennt silent TCP-Drops und reconnectet automatisch ──────────
let _reconnecting = false;
setInterval(async () => {
  if (status !== 'connected' || _reconnecting) return;
  try {
    await Promise.race([
      client.getMe(),
      new Promise((_, reject) => setTimeout(() => reject(new Error('ping timeout')), 10000)),
    ]);
  } catch (e) {
    if (status !== 'connected') return; // zwischenzeitlich geändert
    console.warn('[WARN] Keep-alive fehlgeschlagen (%s) — reconnecting…', e.message);
    _reconnecting = true;
    status = 'starting';
    try { await client.disconnect(); } catch (_) {}
    try {
      await client.connect();
      const me = await client.getMe();
      myId   = String(me.id);
      myName = getEntityName(me);
      status = 'connected';
      _reconnecting = false;
      console.log('[INFO] Reconnected als %s', myName);
      await loadDialogs();
    } catch (err) {
      console.error('[ERROR] Reconnect fehlgeschlagen: %s', err.message);
      status = 'error';
      lastError = err.message;
      _reconnecting = false;
    }
  }
}, 30000);

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

function enforceMediaLimit() {
  const limitBytes = MEDIA_MAX_MB * 1024 * 1024;
  const targetBytes = limitBytes * 0.8; // auf 80% des Limits zurückschneiden
  let current = 0;
  let files = [];
  try {
    for (const f of fs.readdirSync(MEDIA_DIR)) {
      const fp = `${MEDIA_DIR}/${f}`;
      try {
        const st = fs.statSync(fp);
        files.push({ fp, size: st.size, mtime: st.mtimeMs });
        current += st.size;
      } catch(e) {}
    }
  } catch(e) { return; }
  if (current <= limitBytes) return;
  // Älteste zuerst löschen
  files.sort((a, b) => a.mtime - b.mtime);
  let freed = 0;
  for (const f of files) {
    if (current - freed <= targetBytes) break;
    try { fs.unlinkSync(f.fp); freed += f.size; console.log(`[INFO] Media-Limit: gelöscht ${f.fp} (${(f.size/1024/1024).toFixed(1)} MB)`); } catch(e) {}
  }
  console.log(`[INFO] Media-Limit: ${(freed/1024/1024).toFixed(1)} MB freigegeben (Limit: ${MEDIA_MAX_MB} MB)`);
}

app.get('/api/storage', (req, res) => {
  const bytes = getDirSize('/config');
  const mediaBytes = getDirSize(MEDIA_DIR);
  const mediaMb = mediaBytes / 1024 / 1024;
  res.json({
    bytes, mb: (bytes / 1024 / 1024).toFixed(1),
    mediaMb: mediaMb.toFixed(1),
    limitMb: MEDIA_MAX_MB,
    mediaPct: Math.round((mediaMb / MEDIA_MAX_MB) * 100),
  });
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

app.get('/api/media/:filename', (req, res) => {
  const { filename } = req.params;
  if (!/^[\w.-]+$/.test(filename)) return res.status(400).end();
  const filePath = `${MEDIA_DIR}/${filename}`;
  if (!fs.existsSync(filePath)) return res.status(404).end();
  const ext = filename.split('.').pop();
  const mime = ext==='webp'?'image/webp':ext==='png'?'image/png':ext==='ogg'?'audio/ogg':ext==='mp4'?'video/mp4':ext==='webm'?'video/webm':ext==='ogv'?'video/ogg':'image/jpeg';
  res.setHeader('Content-Type', mime);
  res.setHeader('Cache-Control', 'max-age=86400');
  res.sendFile(filePath);
});

// ── Avatar + Kontaktinfo ──────────────────────────────────────────────────────

const tgAvatarCache   = new Map(); // chatId → { buf: Buffer|null, ts: number }
const tgAvatarPending = new Map(); // chatId → Promise

app.get('/api/avatar/:chatId', async (req, res) => {
  const chatId = req.params.chatId;
  const cached = tgAvatarCache.get(chatId);
  if (cached !== undefined && Date.now() - cached.ts < 3600000) {
    if (!cached.buf) return res.status(404).end();
    res.setHeader('Content-Type', 'image/jpeg');
    res.setHeader('Cache-Control', 'public, max-age=3600');
    return res.send(cached.buf);
  }
  if (status !== 'connected') return res.status(503).end();
  if (tgAvatarPending.has(chatId)) {
    try {
      const buf = await tgAvatarPending.get(chatId);
      if (!buf) return res.status(404).end();
      res.setHeader('Content-Type', 'image/jpeg'); res.setHeader('Cache-Control', 'public, max-age=3600');
      return res.send(buf);
    } catch { return res.status(404).end(); }
  }
  const promise = (async () => {
    let entity = peerMap.get(chatId);
    if (!entity) { await loadDialogs(); entity = peerMap.get(chatId); }
    if (!entity) throw new Error('not found');
    const buf = await client.downloadProfilePhoto(entity, { isBig: false });
    return (buf && buf.length) ? buf : null;
  })();
  tgAvatarPending.set(chatId, promise);
  promise.finally(() => tgAvatarPending.delete(chatId));
  try {
    const buf = await promise;
    tgAvatarCache.set(chatId, { buf: buf || null, ts: Date.now() });
    if (!buf) return res.status(404).end();
    res.setHeader('Content-Type', 'image/jpeg'); res.setHeader('Cache-Control', 'public, max-age=3600');
    res.send(buf);
  } catch(e) {
    tgAvatarCache.set(chatId, { buf: null, ts: Date.now() });
    res.status(404).end();
  }
});

app.get('/api/contact/:chatId', async (req, res) => {
  const chatId = req.params.chatId;
  if (status !== 'connected') return res.status(503).json({ error: 'Not connected' });
  try {
    let entity = peerMap.get(chatId);
    if (!entity) { await loadDialogs(); entity = peerMap.get(chatId); }
    if (!entity) return res.status(404).json({ error: 'Not found' });
    let bio = '';
    try {
      if (entity.className === 'User') {
        const full = await client.invoke(new Api.users.GetFullUser({ id: entity }));
        bio = full.fullUser?.about || '';
      } else if (entity.className === 'Channel' || entity.className === 'Chat') {
        const full = await client.invoke(new Api.channels.GetFullChannel({ channel: entity })).catch(() => null);
        bio = full?.fullChat?.about || '';
      }
    } catch(e) {}
    const picBuf = await client.downloadProfilePhoto(entity, { isBig: false }).catch(() => null);
    const name = entity.firstName ? [entity.firstName, entity.lastName].filter(Boolean).join(' ') : (entity.title || chatId);
    res.json({
      id: chatId,
      name,
      firstName: entity.firstName || '',
      lastName: entity.lastName || '',
      username: entity.username || '',
      phone: entity.phone || '',
      about: bio,
      hasProfilePic: !!(picBuf && picBuf.length),
      chatType: entity.className === 'Channel' ? (entity.megagroup ? 'group' : 'channel') : entity.className === 'Chat' ? 'group' : 'private',
    });
  } catch(e) { res.status(500).json({ error: e.message }); }
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
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>Telegram</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; height: var(--app-height, 100dvh); display: flex; flex-direction: column; overflow: hidden; }

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
#storage-info { font-size: 12px; opacity: 0.6; white-space: nowrap; }
#logout-btn, #topbar-back { background: none; border: none; color: rgba(255,255,255,0.5); cursor: pointer; padding: 6px; line-height: 1; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
#logout-btn:hover { color: #f15c5c; }
#topbar-back { display: none; }
#topbar-back:hover { color: rgba(255,255,255,0.9); }
#photo-toggle { background: transparent; border: 1px solid rgba(255,255,255,0.3); color: #fff; padding: 5px 8px; border-radius: 6px; cursor: pointer; font-size: 16px; opacity: 0.55; line-height: 1; }
#photo-toggle:hover { background: rgba(255,255,255,0.1); opacity: 0.8; }
#photo-toggle.active { opacity: 1; background: rgba(255,255,255,0.22); border-color: rgba(255,255,255,0.8); }
.scroll-btn { background: transparent; border: 1px solid rgba(255,255,255,0.3); color: #fff; padding: 5px 10px; border-radius: 6px; cursor: pointer; font-size: 15px; opacity: 0.55; line-height: 1; }
.scroll-btn:hover { background: rgba(255,255,255,0.1); opacity: 0.8; }
#refresh-btn { display: none; background: transparent; border: 1px solid rgba(255,255,255,0.3); color: #fff; padding: 5px 8px; border-radius: 6px; cursor: pointer; font-size: 16px; opacity: 0.55; line-height: 1; }
#refresh-btn:hover { background: rgba(255,255,255,0.1); opacity: 0.8; }
#export-btn { background: none; border: 1px solid rgba(255,255,255,0.3); color: rgba(255,255,255,0.7); padding: 4px 8px; border-radius: 6px; cursor: pointer; font-size: 14px; flex-shrink: 0; }
#export-btn:hover { border-color: #fff; color: #fff; }
#refresh-btn.spinning { animation: spin 0.7s linear infinite; opacity: 1; }
@keyframes spin { to { transform: rotate(360deg); } }
.photo-placeholder { display: none; }
body.hide-photos .msg-img { display: none !important; }
body.hide-photos .photo-placeholder { display: inline; }

/* ── Main layout ── */
#main { display: none; flex: 1; overflow: hidden; }

/* ── Sidebar ── */
#sidebar { width: 360px; min-width: 260px; display: flex; flex-direction: column; flex-shrink: 0; }
html.dark #sidebar { background: #232E3C; border-right: 1px solid #1A2432; }
html.light #sidebar { background: #fff; border-right: 1px solid #e0e0e0; }
#search-wrap { padding: 8px 12px; }
html.dark #search-wrap { border-bottom: 1px solid #1A2432; }
html.light #search-wrap { border-bottom: 1px solid #e0e0e0; }
#chat-filter { display:flex; padding:4px 8px; gap:4px; flex-shrink:0; }
html.dark #chat-filter { background:#232E3C; border-bottom:1px solid #1A2432; }
html.light #chat-filter { background:#fff; border-bottom:1px solid #e0e0e0; }
.filter-tab { flex:1; background:none; border:none; border-radius:16px; padding:5px 4px; font-size:11px; cursor:pointer; transition:background 0.12s,color 0.12s; white-space:nowrap; }
html.dark .filter-tab { color:#6B7B8D; }
html.light .filter-tab { color:#999; }
html.dark .filter-tab:hover { background:rgba(255,255,255,0.06); color:#C1C9D4; }
html.light .filter-tab:hover { background:rgba(0,0,0,0.05); color:#222; }
html.dark .filter-tab.active { background:#17212B; color:#C1C9D4; font-weight:500; }
html.light .filter-tab.active { background:#e8f0fe; color:#2563eb; font-weight:500; }
.avatar.type-group { font-size:22px; }
.avatar.type-channel { font-size:22px; }
.avatar.type-bot { font-size:22px; }
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
.avatar { width: 46px; height: 46px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 17px; color: #fff; flex-shrink: 0; position: relative; overflow: hidden; }
.avatar img[data-avatar] { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; border-radius: 50%; display: block; }
#contact-modal { display: none; position: fixed; inset: 0; z-index: 450; background: rgba(0,0,0,0.65); align-items: center; justify-content: center; }
#contact-modal.open { display: flex; }
.contact-modal-box { border-radius: 16px; padding: 28px 24px 20px; max-width: 320px; width: 90%; display: flex; flex-direction: column; align-items: center; gap: 10px; box-shadow: 0 8px 32px rgba(0,0,0,0.5); }
html.dark .contact-modal-box { background: #232E3C; }
html.light .contact-modal-box { background: #fff; }
.contact-modal-pic { width: 96px; height: 96px; border-radius: 50%; overflow: hidden; display: flex; align-items: center; justify-content: center; font-size: 36px; font-weight: 700; color: #fff; flex-shrink: 0; margin-bottom: 4px; }
.contact-modal-pic img { width: 100%; height: 100%; object-fit: cover; display: block; }
.contact-modal-name { font-size: 18px; font-weight: 600; text-align: center; }
html.dark .contact-modal-name { color: #fff; }
html.light .contact-modal-name { color: #111; }
.contact-modal-sub { font-size: 13px; color: #6B7B8D; text-align: center; }
.contact-modal-number { font-size: 14px; color: #2AABEE; font-weight: 500; }
.contact-modal-about { font-size: 13px; color: #6B7B8D; text-align: center; max-width: 260px; word-break: break-word; }
.contact-modal-close { margin-top: 10px; border: none; border-radius: 8px; padding: 8px 28px; font-size: 14px; cursor: pointer; }
html.dark .contact-modal-close { background: #2B3A4A; color: #C1C9D4; }
html.light .contact-modal-close { background: #f0f2f5; color: #111; }
.contact-modal-close:hover { opacity: 0.8; }
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
.unread-dot { width: 10px; height: 10px; border-radius: 50%; background: #2AABEE; }

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
#ch-name { font-size: 16px; font-weight: 600; color: #fff; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#ch-stats { font-size: 11px; color: rgba(255,255,255,0.6); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#messages { flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 2px; display: none; }
.bubble { max-width: 100%; padding: 8px 12px; border-radius: 10px; font-size: 14px; line-height: 1.45; word-break: break-word; }
.bubble.in { border-bottom-left-radius: 2px; }
.bubble.out { border-bottom-right-radius: 2px; }
.bubble-stack { display: flex; flex-direction: column; max-width: 80%; }
.bubble-row { display: flex; }
.bubble-row.out { justify-content: flex-end; }
.bubble-row.in { justify-content: flex-start; }
.bubble-row-inner { display: flex; align-items: flex-end; gap: 6px; }
.bubble-row-inner .del-btn { order: -1; }
#lightbox { display: none; position: fixed; inset: 0; z-index: 500; background: rgba(0,0,0,0.88); cursor: zoom-out; align-items: center; justify-content: center; }
#lightbox.open { display: flex; }
#lightbox img { max-width: 92vw; max-height: 92vh; object-fit: contain; border-radius: 4px; box-shadow: 0 4px 32px rgba(0,0,0,0.6); cursor: default; }
#reaction-picker { position: fixed; z-index: 300; border-radius: 28px; padding: 6px 10px; display: none; gap: 2px; box-shadow: 0 2px 16px rgba(0,0,0,0.3); }
html.dark #reaction-picker { background: #232E3C; border: 1px solid #1A2432; }
html.light #reaction-picker { background: #fff; border: 1px solid #d9dbdf; }
#reaction-picker button { background: none; border: none; font-size: 24px; cursor: pointer; padding: 3px 4px; border-radius: 50%; line-height: 1; transition: transform 0.12s; }
#reaction-picker button:hover { transform: scale(1.4); }
.react-btn { display: none; background: none; border: none; cursor: pointer; font-size: 15px; padding: 4px 5px; line-height: 1; border-radius: 50%; flex-shrink: 0; }
.bubble-row:hover .react-btn { display: block; }
html.dark .react-btn { color: rgba(193,201,212,0.5); }
html.light .react-btn { color: rgba(0,0,0,0.35); }
html.dark .react-btn:hover { color: #C1C9D4; }
html.light .react-btn:hover { color: #111; }
.reactions-bar { display: flex; flex-wrap: wrap; gap: 3px; padding: 3px 2px 0; }
.reaction-badge { display: inline-flex; align-items: center; gap: 2px; border-radius: 10px; padding: 2px 7px; font-size: 13px; cursor: pointer; border: 1px solid transparent; user-select: none; line-height: 1.5; }
html.dark .reaction-badge { background: #1A2432; border-color: #2B3A4A; color: #C1C9D4; }
html.light .reaction-badge { background: #f0f2f5; border-color: #d9dbdf; color: #111; }
.reaction-badge.own { border-color: #2AABEE; }
html.dark .reaction-badge.own { background: rgba(42,171,238,0.12); }
html.light .reaction-badge.own { background: rgba(42,171,238,0.1); }
.reaction-badge:hover { opacity: 0.8; }
.bubble.photo-bubble { padding: 0; overflow: hidden; position: relative; }
.bubble.photo-bubble .bubble-time { position: absolute; bottom: 3px; right: 5px; background: rgba(0,0,0,0.45); color: rgba(255,255,255,0.95) !important; border-radius: 8px; padding: 0 5px; float: none; margin: 0; }
.bubble.photo-bubble .msg-ack { color: rgba(255,255,255,0.95) !important; }
.bubble-doc { display: flex; align-items: center; gap: 10px; padding: 4px 0; }
.bubble-doc .doc-icon { font-size: 28px; flex-shrink: 0; line-height: 1; }
.bubble-doc .doc-name { font-size: 13px; word-break: break-all; font-weight: 500; }
.photo-caption { padding: 4px 10px 4px; }
.del-btn { display: none; background: none; border: none; cursor: pointer; font-size: 15px; padding: 4px 6px; line-height: 1; border-radius: 6px; flex-shrink: 0; }
.bubble-row:hover .del-btn { display: block; }
html.dark .del-btn { color: rgba(193,201,212,0.6); }
html.light .del-btn { color: rgba(0,0,0,0.4); }
.del-btn:hover { color: #e74c3c !important; }
.fwd-btn, .reply-btn { display: none; background: none; border: none; cursor: pointer; font-size: 15px; padding: 4px 6px; line-height: 1; border-radius: 6px; flex-shrink: 0; }
.bubble-row:hover .fwd-btn, .bubble-row:hover .reply-btn { display: block; }
html.dark .fwd-btn, html.dark .reply-btn { color: rgba(193,201,212,0.5); }
html.light .fwd-btn, html.light .reply-btn { color: rgba(0,0,0,0.35); }
.fwd-btn:hover { color: #2AABEE !important; }
.reply-btn:hover { color: #2AABEE !important; }
.quoted-block { border-left: 3px solid #2AABEE; background: rgba(42,171,238,0.08); border-radius: 4px; padding: 4px 8px; margin-bottom: 5px; overflow: hidden; }
.quoted-sender { font-size: 11px; font-weight: 600; color: #2AABEE; margin-bottom: 1px; }
.quoted-text { font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
html.dark .quoted-text { color: rgba(193,201,212,0.7); }
html.light .quoted-text { color: rgba(0,0,0,0.55); }
#reply-bar { display: none; border-left: 3px solid #2AABEE; padding: 6px 16px; align-items: center; gap: 10px; flex-shrink: 0; }
html.dark #reply-bar { background: #1a2533; }
html.light #reply-bar { background: #e8f4fb; }
#reply-bar.active { display: flex; }
.reply-bar-content { flex: 1; overflow: hidden; }
#reply-bar-sender { font-size: 11px; font-weight: 600; color: #2AABEE; }
#reply-bar-text { font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
html.dark #reply-bar-text { color: #8696a0; }
html.light #reply-bar-text { color: #666; }
#reply-close { background: none; border: none; color: #8696a0; cursor: pointer; font-size: 16px; line-height: 1; padding: 4px; flex-shrink: 0; }
#reply-close:hover { color: #e74c3c; }
#fwd-modal { display: none; position: fixed; inset: 0; z-index: 400; background: rgba(0,0,0,0.6); align-items: center; justify-content: center; }
#fwd-modal.open { display: flex; }
.fwd-modal-box { border-radius: 12px; padding: 20px; max-width: 400px; width: 92%; max-height: 70vh; display: flex; flex-direction: column; box-shadow: 0 8px 32px rgba(0,0,0,0.5); }
html.dark .fwd-modal-box { background: #232E3C; }
html.light .fwd-modal-box { background: #fff; }
.fwd-modal-box h3 { font-size: 15px; font-weight: 600; margin-bottom: 12px; }
html.dark .fwd-modal-box h3 { color: #fff; }
html.light .fwd-modal-box h3 { color: #111; }
#fwd-search { width: 100%; border: none; border-radius: 8px; padding: 8px 12px; font-size: 14px; outline: none; margin-bottom: 10px; }
html.dark #fwd-search { background: #17212B; color: #C1C9D4; }
html.light #fwd-search { background: #f0f2f5; color: #111; }
#fwd-search::placeholder { color: #6B7B8D; }
#fwd-chat-list { flex: 1; overflow-y: auto; }
.fwd-chat-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; cursor: pointer; border-radius: 8px; }
html.dark .fwd-chat-item:hover { background: #2B3A4A; }
html.light .fwd-chat-item:hover { background: #f0f2f5; }
.fwd-chat-item-name { font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
html.dark .fwd-chat-item-name { color: #C1C9D4; }
html.light .fwd-chat-item-name { color: #111; }
.fwd-modal-cancel { margin-top: 12px; border: none; border-radius: 8px; padding: 8px 18px; font-size: 14px; cursor: pointer; width: 100%; }
html.dark .fwd-modal-cancel { background: #2B3A4A; color: #C1C9D4; }
html.light .fwd-modal-cancel { background: #e0e0e0; color: #111; }
.fwd-modal-cancel:hover { opacity: 0.8; }
html.dark .bubble.in { background: #182533; color: #C1C9D4; }
html.dark .bubble.out { background: #2B5278; color: #fff; }
html.light .bubble.in { background: #fff; color: #222; }
html.light .bubble.out { background: #EEFFDE; color: #222; }
.bubble-time { font-size: 11px; float: right; margin-left: 8px; margin-top: 2px; white-space: nowrap; }
html.dark .bubble-time { color: rgba(193,201,212,0.6); }
html.light .bubble-time { color: rgba(0,0,0,0.35); }
.msg-ack { font-size: 11px; margin-left: 2px; }
.ack-1 { color: rgba(193,201,212,0.6); }
.ack-3 { color: #2AABEE; }
html.light .ack-1 { color: rgba(0,0,0,0.35); }
html.light .ack-3 { color: #0284C7; }
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
#input-bar #attach-btn { background: none; border: none; font-size: 20px; cursor: pointer; padding: 6px; border-radius: 50%; flex-shrink: 0; width: auto; height: auto; line-height: 1; }
html.dark #input-bar #attach-btn { color: #6B7B8D; }
html.light #input-bar #attach-btn { color: #888; }
#input-bar #attach-btn:hover { background: rgba(0,0,0,0.08); }
#attach-bar { display: none; align-items: center; gap: 10px; padding: 6px 16px; font-size: 13px; border-top: 1px solid transparent; }
#attach-bar.visible { display: flex; }
html.dark #attach-bar { background: #1A2432; border-color: #1A2432; color: #C1C9D4; }
html.light #attach-bar { background: #e8eef4; border-color: #d0d8e0; color: #333; }
#attach-bar .attach-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#attach-bar .attach-clear { background: none; border: none; cursor: pointer; font-size: 16px; color: #e74c3c; padding: 2px 6px; border-radius: 4px; flex-shrink: 0; }
#file-input { display: none; }

/* ── Mobile ── */
@media (max-width: 768px) {
  #sidebar { width: 100%; border-right: none; }
  #chat-panel { display: none; }
  #back-btn { display: none !important; }
  body.chat-open #sidebar { display: none; }
  body.chat-open #chat-panel { display: flex; }
  #lang-btn { display: none !important; }
  #topbar { gap: 6px; }
  #topbar .uname { display: none; }
  #ch-stats { white-space: normal; font-size: 10px; overflow: visible; text-overflow: unset; }
  body.chat-open #topbar h1 { display: none; }
  body.chat-open #topbar-back { display: inline-flex; margin-right: auto; }
}
#logout-modal { display:none; position:fixed; inset:0; z-index:500; background:rgba(0,0,0,0.6); align-items:center; justify-content:center; }
#logout-modal.open { display:flex; }
.logout-modal-box { background:#232E3C; border-radius:12px; padding:24px; max-width:360px; width:90%; box-shadow:0 8px 32px rgba(0,0,0,0.5); }
html.light .logout-modal-box { background:#fff; }
.logout-modal-box p { color:#e9edef; font-size:14px; line-height:1.6; margin-bottom:20px; }
html.light .logout-modal-box p { color:#111; }
.logout-modal-actions { display:flex; justify-content:flex-end; gap:10px; }
.logout-modal-actions button { padding:8px 18px; border-radius:8px; border:none; font-size:14px; cursor:pointer; }
.logout-modal-no { background:#2a3942; color:#e9edef; }
html.light .logout-modal-no { background:#e0e0e0; color:#111; }
.logout-modal-no:hover { background:#3d5259; }
.logout-modal-yes { background:#f15c5c; color:#fff; }
.logout-modal-yes:hover { background:#d94444; }
</style>
</head>
<body>

<div id="overlay-spinner" class="overlay">
  <div class="tg-logo">✈️</div>
  <div class="spinner"></div>
  <p id="spinner-text" data-i18n="spinnerConnect">Verbinde mit Telegram…</p>
</div>

<div id="overlay-code" class="overlay" style="display:none">
  <div class="tg-logo">✈️</div>
  <h2 data-i18n="codeTitle">Code eingeben</h2>
  <p data-i18n="codeInstr">Telegram hat einen Code an deine App oder per SMS gesendet.</p>
  <div class="auth-box">
    <input class="auth-input" id="code-input" type="text" inputmode="numeric" maxlength="8" placeholder="12345">
    <div class="auth-error" id="code-error"></div>
    <button class="auth-btn" onclick="submitCode()" data-i18n="btnConfirm">Bestätigen</button>
  </div>
</div>

<div id="overlay-password" class="overlay" style="display:none">
  <div class="tg-logo">✈️</div>
  <h2 data-i18n="pwTitle">2-Faktor-Passwort</h2>
  <p data-i18n="pwInstr">Dein Konto ist durch ein Cloud-Passwort geschützt.</p>
  <div class="auth-box">
    <input class="auth-input text" id="pw-input" type="password" placeholder="Passwort">
    <div class="auth-error" id="pw-error"></div>
    <button class="auth-btn" onclick="submitPassword()" data-i18n="btnConfirm">Bestätigen</button>
  </div>
</div>

<div id="overlay-error" class="overlay" style="display:none">
  <div class="tg-logo">✈️</div>
  <h2 data-i18n="overlayErrorTitle">Fehler</h2>
  <p id="error-text"></p>
  <button class="auth-btn" style="max-width:220px;margin-top:8px" onclick="reconnect()" data-i18n="btnReconnect">Erneut verbinden</button>
</div>

<div id="topbar">
  <button id="topbar-back" onclick="closeChat()" title="Zurück"><svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><polyline points="15 18 9 12 15 6"/></svg></button>
  <h1>Telegram</h1>
  <span class="uname" id="my-name"></span>
  <span id="storage-info"></span>
  ${DOWNLOAD_MEDIA ? '<button id="photo-toggle" class="active" onclick="togglePhotos()" data-i18n-title="photosOn" title="Fotos AN">📷</button>' : ''}
  ${DOWNLOAD_MEDIA ? '<button class="scroll-btn" onclick="cleanupMedia()" data-i18n-title="cleanupTitle" title="Verwaiste Mediendateien löschen">🗑️</button>' : ''}
  <button id="refresh-btn" onclick="refreshChat()" data-i18n-title="btnReload" title="Chat neu laden">↺</button>
  <button class="scroll-btn" onclick="scrollMsgs(\'top\')" data-i18n-title="btnScrollUp" title="Nach oben">↑</button>
  <button class="scroll-btn" onclick="scrollMsgs(\'bottom\')" data-i18n-title="btnScrollDown" title="Nach unten">↓</button>
  <button id="lang-btn" class="scroll-btn" onclick="switchLang()" title="Sprache / Language" style="font-size:14px;padding:0 6px;">🌐 DE</button>
  <button id="logout-btn" onclick="confirmLogout()" data-i18n-title="btnLogout" title="Abmelden"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg></button>
</div>

<div id="main">
  <div id="sidebar">
    <div id="search-wrap">
      <input id="search-input" type="text" placeholder="Suchen…" data-i18n-pl="searchPlaceholder" oninput="filterChats()">
    </div>
    <div id="chat-filter">
      <button class="filter-tab active" data-filter="all" onclick="setFilter('all')" data-i18n="filterAll">Alle</button>
      <button class="filter-tab" data-filter="private" onclick="setFilter('private')" data-i18n="filterPrivate">Privat</button>
      <button class="filter-tab" data-filter="group" onclick="setFilter('group')" data-i18n="filterGroups">Gruppen</button>
      <button class="filter-tab" data-filter="channel" onclick="setFilter('channel')" data-i18n="filterChannels">Kanäle</button>
      <button class="filter-tab" data-filter="bot" onclick="setFilter('bot')" data-i18n="filterBots">Bots</button>
    </div>
    <div id="chat-list"></div>
  </div>
  <div id="chat-panel">
    <div id="no-chat-wrap" data-i18n="noChatSelected">Wähle einen Chat aus der Liste</div>
    <div id="chat-header">
      <button id="back-btn" onclick="closeChat()">&#8592;</button>
      <div class="avatar" id="ch-avatar" style="width:36px;height:36px;font-size:14px;background:#2AABEE">?</div>
      <div style="flex:1;overflow:hidden">
        <div id="ch-name">–</div>
        <div id="ch-stats"></div>
      </div>
      <button id="export-btn" onclick="exportChat()" data-i18n-title="ttExport" title="Chat exportieren">💾</button>
    </div>
    <div id="messages"></div>
    <div id="reply-bar">
      <div class="reply-bar-content">
        <div id="reply-bar-sender"></div>
        <div id="reply-bar-text"></div>
      </div>
      <button id="reply-close" onclick="clearReply()">✕</button>
    </div>
    <div id="attach-bar">
      <span>📎</span>
      <span class="attach-name" id="attach-name"></span>
      <button class="attach-clear" onclick="clearAttach()" title="Entfernen">✕</button>
    </div>
    <div id="input-bar">
      <div id="emoji-picker"><div class="emoji-grid" id="emoji-grid"></div></div>
      <input type="file" id="file-input" onchange="onFileSelected(this)">
      <button id="emoji-toggle" onclick="toggleEmojiPicker(event)" data-i18n-title="emojiTitle" title="Emoji">😊</button>
      <button id="attach-btn" onclick="document.getElementById('file-input').click()" data-i18n-title="attachTitle" title="Datei anhängen">📎</button>
      <textarea id="msg-input" rows="1" placeholder="Nachricht…" data-i18n-pl="msgPlaceholder" onkeydown="handleKey(event)" oninput="autoResize(this)"></textarea>
      <button id="send-btn" onclick="sendMsg()">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="white"><path d="M2 21l21-9L2 3v7l15 2-15 2v7z"/></svg>
      </button>
    </div>
  </div>
</div>

<script>
    (function() {
      function setAppHeight() {
        var h = window.visualViewport ? window.visualViewport.height : window.innerHeight;
        document.documentElement.style.setProperty('--app-height', h + 'px');
      }
      if (window.visualViewport) window.visualViewport.addEventListener('resize', setAppHeight);
      window.addEventListener('resize', setAppHeight);
      setAppHeight();
    })();

const LANG = {
  de: {
    spinnerConnect: 'Verbinde mit Telegram…', spinnerLogout: 'Abmelden…',
    codeTitle: 'Code eingeben',
    codeInstr: 'Telegram hat einen Code an deine App oder per SMS gesendet.',
    pwTitle: '2-Faktor-Passwort', pwInstr: 'Dein Konto ist durch ein Cloud-Passwort geschützt.',
    btnConfirm: 'Bestätigen', overlayErrorTitle: 'Fehler', btnReconnect: 'Erneut verbinden',
    unknownError: 'Unbekannter Fehler',
    photosOn: 'Fotos AN', photosOff: 'Fotos AUS',
    cleanupTitle: 'Verwaiste Mediendateien löschen',
    btnReload: 'Chat neu laden', btnScrollUp: 'Nach oben', btnScrollDown: 'Nach unten', ttExport: 'Chat als HTML exportieren',
    filterAll: 'Alle', filterPrivate: 'Privat', filterGroups: 'Gruppen', filterChannels: 'Kanäle', filterBots: 'Bots',
    btnLogout: 'Abmelden', logoutConfirmMsg: 'Möchtest du dich wirklich abmelden?', btnYes: 'Ja', btnNo: 'Nein',
    searchPlaceholder: 'Suchen…',
    noChatSelected: 'Wähle einen Chat aus der Liste', noMessages: 'Noch keine Nachrichten',
    emojiTitle: 'Emoji', msgPlaceholder: 'Nachricht…', attachTitle: 'Datei anhängen',
    btnDelete: 'Löschen', btnReact: 'Reagieren', reactionRemove: 'Klicken zum Entfernen',
    cleanupConfirm: 'Verwaiste Mediendateien löschen (nicht mehr referenzierte Fotos)?',
    cleanupSuccess: (c, mb) => c + ' Datei(en) gelöscht, ' + mb + ' MB freigegeben.',
    cleanupError: (e) => 'Fehler beim Cleanup: ' + e,
    statsMsg: 'Nachrichten', statsSince: 'seit',
  },
  en: {
    spinnerConnect: 'Connecting to Telegram…', spinnerLogout: 'Logging out…',
    codeTitle: 'Enter code',
    codeInstr: 'Telegram sent a code to your app or via SMS.',
    pwTitle: '2-Factor Password', pwInstr: 'Your account is protected by a cloud password.',
    btnConfirm: 'Confirm', overlayErrorTitle: 'Error', btnReconnect: 'Reconnect',
    unknownError: 'Unknown error',
    photosOn: 'Photos ON', photosOff: 'Photos OFF',
    cleanupTitle: 'Delete orphaned media files',
    btnReload: 'Reload chat', btnScrollUp: 'Scroll up', btnScrollDown: 'Scroll down', ttExport: 'Export chat as HTML',
    filterAll: 'All', filterPrivate: 'Private', filterGroups: 'Groups', filterChannels: 'Channels', filterBots: 'Bots',
    btnLogout: 'Log out', logoutConfirmMsg: 'Do you really want to log out?', btnYes: 'Yes', btnNo: 'No',
    searchPlaceholder: 'Search…',
    noChatSelected: 'Select a chat from the list', noMessages: 'No messages yet',
    emojiTitle: 'Emoji', msgPlaceholder: 'Message…', attachTitle: 'Attach file',
    btnDelete: 'Delete', btnReact: 'React', reactionRemove: 'Click to remove',
    cleanupConfirm: 'Delete orphaned media files (photos no longer referenced)?',
    cleanupSuccess: (c, mb) => c + ' file(s) deleted, ' + mb + ' MB freed.',
    cleanupError: (e) => 'Cleanup error: ' + e,
    statsMsg: 'messages', statsSince: 'since',
  },
};
const _browserLang = (navigator.language || '').toLowerCase().startsWith('de') ? 'de' : 'en';
let lang = localStorage.getItem('tg_lang') || _browserLang;
function t(key) { const v = LANG[lang][key]; return (typeof v === 'function' || v === undefined) ? (LANG.de[key] || key) : v; }
function tf(key, ...args) { const v = LANG[lang][key]; return typeof v === 'function' ? v(...args) : (LANG.de[key] ? LANG.de[key](...args) : key); }
function locale() { return lang === 'de' ? 'de-DE' : 'en-GB'; }
function applyLang() {
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll('[data-i18n-pl]').forEach(el => { el.placeholder = t(el.dataset.i18nPl); });
  document.querySelectorAll('[data-i18n-title]').forEach(el => { el.title = t(el.dataset.i18nTitle); });
  const lb = document.getElementById('lang-btn');
  if (lb) lb.textContent = lang === 'de' ? '🌐 DE' : '🌐 EN';
  const ptb = document.getElementById('photo-toggle');
  if (ptb) ptb.title = ptb.classList.contains('active') ? t('photosOn') : t('photosOff');
}
function switchLang() {
  lang = lang === 'de' ? 'en' : 'de';
  localStorage.setItem('tg_lang', lang);
  applyLang();
}

const BASE = location.pathname.replace(/\\/+$/, '');

// ── Avatar-System ─────────────────────────────────────────────────────────────
const _avatarState = new Map();
const _avatarUrl   = new Map();
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
    if (!_avatarState.has(chat.id)) _avatarQueue.push(chat.id);
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
      _avatarState.set(chatId, 'loaded'); _avatarUrl.set(chatId, img.src);
      document.querySelectorAll('[data-avid="'+chatId+'"]').forEach(el => applyAvatar(el, chatId));
      _avatarActive--; drainAvatarQueue();
    };
    img.onerror = () => { _avatarState.set(chatId, 'failed'); _avatarActive--; drainAvatarQueue(); };
    img.src = api('/api/avatar/' + encodeURIComponent(chatId));
  }
}

let currentStatus = '';
let selectedChatId = null;
let allChats = [];
let lastSeenTime = {};
let lastMsgCount = {};

function api(p) { return BASE + p; }

const COLORS = ['#E17076','#F28C28','#8ECC44','#2AABEE','#7B68EE','#E84393','#00BCD4','#FF8C00'];
function avatarColor(s) { let h=0; for(const c of String(s)) h=(h*31+c.charCodeAt(0))&0xffff; return COLORS[h%COLORS.length]; }
function avatarInitial(s) { return (String(s||'?')).charAt(0).toUpperCase(); }

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts), now = new Date();
  if (d.toDateString()===now.toDateString()) return d.toLocaleTimeString(locale(),{hour:'2-digit',minute:'2-digit'});
  return d.toLocaleDateString(locale(),{day:'2-digit',month:'2-digit'});
}
function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
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

function scrollMsgs(dir) {
  const el = document.getElementById('messages');
  if (!el) return;
  el.scrollTop = dir === 'top' ? 0 : el.scrollHeight;
}

async function loadStorage() {
  try {
    const d = await fetch(api('/api/storage')).then(r => r.json());
    const el = document.getElementById('storage-info');
    if (!el) return;
    el.textContent = '💾 ' + d.mb + ' MB';
    if (d.mediaMb !== undefined) {
      const autoAt = d.limitMb, autoTo = Math.round(d.limitMb * 0.8);
      el.title = lang === 'de'
        ? \`Gesamt /config: \${d.mb} MB\nMedienordner: \${d.mediaMb} MB von \${autoAt} MB (\${d.mediaPct}%)\nAuto-Delete startet bei \${autoAt} MB → löscht auf \${autoTo} MB\`
        : \`Total /config: \${d.mb} MB\nMedia folder: \${d.mediaMb} MB of \${autoAt} MB (\${d.mediaPct}%)\nAuto-delete starts at \${autoAt} MB → cleans to \${autoTo} MB\`;
    }
  } catch(e) {}
}
loadStorage();
setInterval(loadStorage, 60000);

function togglePhotos() {
  const hiding = !document.body.classList.contains('hide-photos');
  document.body.classList.toggle('hide-photos', hiding);
  const btn = document.getElementById('photo-toggle');
  if (btn) { btn.classList.toggle('active', !hiding); btn.textContent = hiding ? '🚫' : '📷'; btn.title = hiding ? t('photosOff') : t('photosOn'); }
  localStorage.setItem('tg-hide-photos', hiding ? '1' : '');
}
if (localStorage.getItem('tg-hide-photos')) {
  document.body.classList.add('hide-photos');
  const btn = document.getElementById('photo-toggle');
  if (btn) { btn.classList.remove('active'); btn.textContent = '🚫'; btn.title = t('photosOff'); }
}

async function cleanupMedia() {
  if (!confirm(t('cleanupConfirm'))) return;
  try {
    const d = await fetch(api('/api/cleanup-media'), { method: 'POST' }).then(r => r.json());
    alert(tf('cleanupSuccess', d.deleted, d.freedMb));
    loadStorage();
  } catch(e) { alert(tf('cleanupError', e.message)); }
}

function ackMark(ack) {
  if (!ack) return '';
  const cls = ack >= 3 ? 'ack-3' : 'ack-1';
  return \`<span class="msg-ack \${cls}">\${ack >= 3 ? '✓✓' : '✓'}</span>\`;
}

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
      document.getElementById('error-text').textContent = d.error || t('unknownError');
    } else if (d.status==='connected') {
      document.getElementById('topbar').style.display = 'flex';
      document.getElementById('main').style.display = 'flex';
      document.getElementById('my-name').textContent = d.name || '';
      document.getElementById('my-name').title = d.id || '';
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

function confirmLogout() {
  document.getElementById('logout-modal').classList.add('open');
  applyLang();
}
function closeLogoutModal() {
  document.getElementById('logout-modal').classList.remove('open');
}
async function logout() {
  closeLogoutModal();
  currentStatus = '';
  document.getElementById('topbar').style.display = 'none';
  document.getElementById('main').style.display = 'none';
  document.getElementById('overlay-spinner').style.display = 'flex';
  document.getElementById('spinner-text').textContent = t('spinnerLogout');
  await fetch(api('/api/logout'),{method:'POST'}).catch(()=>{});
}

// ── Chats ──────────────────────────────────────────────────────────────────────
async function loadChats() {
  try {
    const chats = await fetch(api('/api/chats')).then(r=>r.json());
    chats.forEach(c => {
      if (!(c.id in lastSeenTime)) lastSeenTime[c.id] = c.lastTime || 0;
      else if (c.id === selectedChatId) lastSeenTime[c.id] = c.lastTime || lastSeenTime[c.id];
    });
    allChats = chats;
    renderChats(chats);
    if (selectedChatId) loadMessages(selectedChatId);
  } catch(e) {}
}
setInterval(loadChats, 5000);

let currentFilter = 'all';
function setFilter(f) {
  currentFilter = f;
  document.querySelectorAll('.filter-tab').forEach(btn => btn.classList.toggle('active', btn.dataset.filter === f));
  renderChats(allChats);
}

function chatAvatar(c) {
  const type = c.chatType || (c.isBot ? 'bot' : 'private');
  const avid = \`data-avid="\${escHtml(c.id)}"\`;
  if (type === 'group')   return \`<div class="avatar type-group" \${avid} style="background:#2b5278">👥</div>\`;
  if (type === 'channel') return \`<div class="avatar type-channel" \${avid} style="background:#1e6b8c">📢</div>\`;
  if (type === 'bot')     return \`<div class="avatar type-bot" \${avid} style="background:#4a3f8c">🤖</div>\`;
  return \`<div class="avatar" \${avid} style="background:\${avatarColor(c.name||c.id)}">\${avatarInitial(c.name||c.id)}</div>\`;
}

function renderChats(chats) {
  const q = document.getElementById('search-input').value.toLowerCase();
  const filtered = chats.filter(c => {
    if (q && !(c.name||'').toLowerCase().includes(q)) return false;
    const type = c.chatType || (c.isBot ? 'bot' : 'private');
    if (currentFilter !== 'all' && type !== currentFilter) return false;
    return true;
  });
  document.getElementById('chat-list').innerHTML = filtered.map(c => \`
    <div class="chat-item\${c.id===selectedChatId?' active':''}" data-id="\${escHtml(c.id)}" onclick="openChatById(this.dataset.id)">
      \${chatAvatar(c)}
      <div class="chat-info">
        <div class="chat-name">\${escHtml(c.name||c.id)}</div>
        <div class="chat-preview">\${escHtml(c.lastMsg||'')}</div>
      </div>
      <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0;">
        <div class="chat-time">\${formatTime(c.lastTime)}</div>
        \${c.id!==selectedChatId&&c.lastTime>(lastSeenTime[c.id]||0)?'<div class="unread-dot"></div>':''}
      </div>
    </div>
  \`).join('');
  // Gecachte Avatare sofort anwenden, Rest nachgelagert
  document.querySelectorAll('[data-avid]').forEach(el => {
    const id = el.getAttribute('data-avid');
    if (_avatarState.get(id) === 'loaded') applyAvatar(el, id);
  });
  setTimeout(() => queueAvatars(filtered), 300);
}

function filterChats() { renderChats(allChats); }

function openChatById(id) { const c = allChats.find(c=>c.id===id); if(c) openChat(c); }

function openChat(chat) {
  selectedChatId = chat.id;
  lastSeenTime[chat.id] = chat.lastTime || Date.now();
  lastMsgCount[chat.id] = 0;
  document.body.classList.add('chat-open');
  document.getElementById('no-chat-wrap').style.display = 'none';
  document.getElementById('chat-header').style.display = 'flex';
  document.getElementById('messages').style.display = 'flex';
  document.getElementById('input-bar').style.display = 'flex';
  document.getElementById('refresh-btn').style.display = 'inline-block';
  clearAttach();
  document.getElementById('ch-name').textContent = chat.name || chat.id;
  document.getElementById('ch-stats').textContent = '';
  const av = document.getElementById('ch-avatar');
  av.onclick = null; av.style.cursor = '';
  av.querySelectorAll('img[data-avatar]').forEach(i => i.remove());
  const type = chat.chatType || (chat.isBot ? 'bot' : 'private');
  if (type === 'group')        { av.textContent = '👥'; av.style.background = '#2b5278'; av.style.fontSize = '22px'; }
  else if (type === 'channel') { av.textContent = '📢'; av.style.background = '#1e6b8c'; av.style.fontSize = '22px'; }
  else if (type === 'bot')     { av.textContent = '🤖'; av.style.background = '#4a3f8c'; av.style.fontSize = '22px'; }
  else { av.textContent = avatarInitial(chat.name||chat.id); av.style.background = avatarColor(chat.name||chat.id); av.style.fontSize = ''; }
  av.setAttribute('data-avid', chat.id);
  if (_avatarState.get(chat.id) === 'loaded') applyAvatar(av, chat.id);
  else queueAvatars([chat]);
  av.onclick = () => openContactInfo(chat.id, chat.name);
  av.style.cursor = 'pointer';
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
  document.getElementById('refresh-btn').style.display = 'none';
  clearAttach();
}

function exportChat() {
  if (!selectedChatId) return;
  window.location.href = api('/api/export/' + encodeURIComponent(selectedChatId));
}

async function refreshChat() {
  if (!selectedChatId) return;
  const btn = document.getElementById('refresh-btn');
  btn.classList.add('spinning');
  try {
    const msgs = await fetch(api('/api/messages/'+encodeURIComponent(selectedChatId)+'?refresh=1')).then(r=>r.json());
    renderMessages(msgs);
  } catch(e) {}
  btn.classList.remove('spinning');
}

async function loadMessages(chatId) {
  if (!chatId) return;
  try {
    const msgs = await fetch(api('/api/messages/'+encodeURIComponent(chatId))).then(r=>r.json());
    renderMessages(msgs);
    if (window.pollReactions) window.pollReactions();
    updateChatStats(chatId);
  } catch(e) {}
}

async function updateChatStats(chatId) {
  if (chatId !== selectedChatId) return;
  try {
    const s = await fetch(api('/api/stats?chat='+encodeURIComponent(chatId))).then(r=>r.json());
    const sinceStr = s.first ? new Date(s.first).toLocaleDateString(locale()) : '';
    const photoStr = s.photos ? '  📷 ' + s.photos : '';
    document.getElementById('ch-stats').textContent =
      s.total + ' ' + t('statsMsg') + '  ↑ ' + s.sent + '  ↓ ' + s.received + photoStr + (sinceStr ? '  ' + t('statsSince') + ' ' + sinceStr : '');
  } catch(e) {}
}

function renderMessages(msgs) {
  const el = document.getElementById('messages');
  if (!msgs||!msgs.length) { el.innerHTML='<div style="text-align:center;padding:24px;opacity:0.5">'+t('noMessages')+'</div>'; return; }
  const wasAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  const prevCount = lastMsgCount[selectedChatId] || 0;
  lastMsgCount[selectedChatId] = msgs.length;
  let lastDate='';
  el.innerHTML = msgs.map(m => {
    const d=new Date(m.timestamp);
    const dateStr=d.toLocaleDateString(locale(),{day:'2-digit',month:'2-digit',year:'numeric'});
    let sep='';
    if(dateStr!==lastDate){sep=\`<div class="day-sep">\${dateStr}</div>\`;lastDate=dateStr;}
    const time=d.toLocaleTimeString(locale(),{hour:'2-digit',minute:'2-digit'});
    let content='';
    const isPhoto = m.type==='photo'&&m.mediaFile;
    const isDoc = m.type==='document'&&m.filename;
    const isVoice = m.type==='voice';
    const isVideo = m.type==='video';
    const quotedHtml = m.quotedMsg ? \`<div class="quoted-block"><div class="quoted-sender">\${escHtml(m.quotedMsg.contact||'')}</div><div class="quoted-text">\${escHtml(m.quotedMsg.body||'')}</div></div>\` : '';
    if(isVoice){
      content = m.mediaFile
        ? \`<audio controls style="min-width:220px;max-width:300px;width:100%" src="\${BASE}/api/media/\${encodeURIComponent(m.mediaFile)}"></audio>\`
        : '<span style="opacity:0.6">🎵 Sprachnachricht</span>';
    } else if(isVideo){
      content = m.mediaFile
        ? \`<video controls style="max-width:320px;max-height:400px;display:block;border-radius:8px" src="\${BASE}/api/media/\${encodeURIComponent(m.mediaFile)}"></video>\`
        : '<span style="opacity:0.6">📹 Video</span>';
      if(m.body) content+=\`<div style="margin-top:4px;font-size:13px">\${formatText(m.body)}</div>\`;
    } else if(isPhoto){
      content=\`<span class="photo-placeholder">📷 Foto</span><img class="msg-img" src="\${BASE}/api/media/\${encodeURIComponent(m.mediaFile)}" style="max-width:320px;max-height:400px;display:block;cursor:zoom-in" loading="lazy" onclick="event.stopPropagation();openLightbox(this.src)">\`;
      if(m.body) content+=\`<div class="photo-caption">\${formatText(m.body)}</div>\`;
    } else if(isDoc){
      content=\`<div class="bubble-doc"><span class="doc-icon">📄</span><span class="doc-name">\${escHtml(m.filename)}</span></div>\`;
      if(m.body) content+=\`<div style="margin-top:4px;font-size:13px">\${formatText(m.body)}</div>\`;
    } else {
      content=formatText(m.body);
    }
    const ack = m.fromMe ? ackMark(m.ack || 0) : '';
    const reactBadges = m.reactions ? Object.entries(m.reactions).filter(function(e){return e[1]>0;}).map(function(e){var em=e[0],cnt=e[1],own=m.myReaction===em;return '<span class="reaction-badge'+(own?' own':'')+'" data-emoji="'+em+'" data-own="'+own+'">'+em+(cnt>1?' '+cnt:'')+'</span>';}).join('') : '';
    const reactBar = reactBadges ? '<div class="reactions-bar">'+reactBadges+'</div>' : '';
    const chatForReply = allChats.find(c=>c.id===selectedChatId);
    const replyContact = m.fromMe ? 'Ich' : (chatForReply?.name||selectedChatId||'');
    const replyPreview = escHtml((m.body||(m.type==='voice'?'🎵 Sprachnachricht':m.type==='photo'?'📷 Foto':m.type==='video'?'📹 Video':'')).slice(0,60));
    const tgMsgRawId = m.id.split('_').pop();
    return sep+\`<div class="bubble-row \${m.fromMe?'out':'in'}" data-msgid="\${escHtml(m.id)}" data-chatid="\${escHtml(selectedChatId)}"><div class="bubble-row-inner"><div class="bubble-stack"><div class="bubble \${m.fromMe?'out':'in'}\${isPhoto?' photo-bubble':''}">\${quotedHtml}\${content}<span class="bubble-time">\${time}\${ack}</span></div>\${reactBar}</div><button class="react-btn"\${reactBadges?' style="display:none"':''} title="\${t('btnReact')}">😊</button><button class="fwd-btn" data-msgid="\${escHtml(m.id)}" title="Weiterleiten">↪</button><button class="reply-btn" data-msgid="\${escHtml(m.id)}" data-contact="\${escHtml(replyContact)}" data-preview="\${replyPreview}" data-tgid="\${tgMsgRawId}" title="Antworten">↩</button><button class="del-btn" title="\${t('btnDelete')}">✕</button></div></div>\`;
  }).join('');
  if (wasAtBottom || msgs.length > prevCount) el.scrollTop = el.scrollHeight;
}

let _attachFile = null;
let _replyMsgId = null, _replyTgId = null, _replyContact = null, _replyPreview = null;

function setReply(msgId, contact, preview, tgId) {
  _replyMsgId = msgId; _replyTgId = tgId; _replyContact = contact; _replyPreview = preview;
  document.getElementById('reply-bar-sender').textContent = contact;
  document.getElementById('reply-bar-text').textContent = preview;
  document.getElementById('reply-bar').classList.add('active');
  document.getElementById('msg-input').focus();
}
function clearReply() {
  _replyMsgId = null; _replyTgId = null; _replyContact = null; _replyPreview = null;
  document.getElementById('reply-bar').classList.remove('active');
}

async function openContactInfo(chatId, fallbackName) {
  const modal = document.getElementById('contact-modal');
  const picEl = document.getElementById('contact-modal-pic');
  const nameEl = document.getElementById('contact-modal-name');
  const subEl  = document.getElementById('contact-modal-sub');
  const numEl  = document.getElementById('contact-modal-number');
  const aboutEl = document.getElementById('contact-modal-about');
  picEl.innerHTML = '…'; picEl.style.background = '#2B3A4A';
  nameEl.textContent = '…'; subEl.textContent = ''; numEl.textContent = ''; aboutEl.textContent = '';
  modal.classList.add('open');
  try {
    const data = await fetch(api('/api/contact/' + encodeURIComponent(chatId))).then(r => r.json());
    const name = data.name || fallbackName || chatId;
    nameEl.textContent = name;
    subEl.textContent = data.username ? '@' + data.username : '';
    numEl.textContent = data.phone ? '+' + data.phone : '';
    aboutEl.textContent = data.about || '';
    picEl.textContent = '';
    if (data.hasProfilePic) {
      const cached = _avatarState.get(chatId);
      if (cached === 'loaded') {
        picEl.style.background = 'none';
        const img = document.createElement('img'); img.src = _avatarUrl.get(chatId);
        picEl.appendChild(img);
      } else {
        picEl.style.background = avatarColor(name); picEl.textContent = avatarInitial(name);
        const img = new Image();
        img.onload = () => {
          picEl.style.background = 'none'; picEl.textContent = '';
          const i2 = document.createElement('img'); i2.src = img.src; picEl.appendChild(i2);
          _avatarState.set(chatId, 'loaded'); _avatarUrl.set(chatId, img.src);
        };
        img.src = api('/api/avatar/' + encodeURIComponent(chatId));
      }
    } else {
      picEl.style.background = avatarColor(name); picEl.textContent = avatarInitial(name);
    }
  } catch(e) {
    nameEl.textContent = fallbackName || chatId;
    picEl.style.background = avatarColor(fallbackName || chatId);
    picEl.textContent = avatarInitial(fallbackName || chatId);
  }
}
function closeContactModal() { document.getElementById('contact-modal').classList.remove('open'); }

let _fwdMsgId = null;
function openFwdModal(msgId) {
  _fwdMsgId = msgId;
  document.getElementById('fwd-search').value = '';
  renderFwdList(allChats);
  document.getElementById('fwd-modal').classList.add('open');
  setTimeout(() => document.getElementById('fwd-search').focus(), 50);
}
function closeFwdModal() { document.getElementById('fwd-modal').classList.remove('open'); _fwdMsgId = null; }
function filterFwdChats() {
  const q = document.getElementById('fwd-search').value.toLowerCase();
  renderFwdList(q ? allChats.filter(c=>(c.name||'').toLowerCase().includes(q)) : allChats);
}
function renderFwdList(chats) {
  const list = document.getElementById('fwd-chat-list');
  list.innerHTML = chats.map(c => {
    const bg = avatarColor(c.name||c.id);
    return \`<div class="fwd-chat-item" onclick="forwardTo('\${escHtml(c.id)}')"><div class="avatar" style="width:34px;height:34px;font-size:13px;background:\${bg};flex-shrink:0">\${avatarInitial(c.name||c.id)}</div><div class="fwd-chat-item-name">\${escHtml(c.name||c.id)}</div></div>\`;
  }).join('');
}
async function forwardTo(chatId) {
  const msgId = _fwdMsgId;
  closeFwdModal();
  if (!msgId) return;
  try {
    await fetch(api('/api/forward'), { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ msgId, to: chatId }) });
  } catch(e) { console.error('Forward error:', e.message); }
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

function attachFile(file) {
  if (!file) return;
  _attachFile = file;
  document.getElementById('attach-name').textContent = file.name + ' (' + formatFileSize(file.size) + ')';
  document.getElementById('attach-bar').classList.add('visible');
}

function onFileSelected(input) {
  attachFile(input.files[0]);
  input.value = '';
}

function clearAttach() {
  _attachFile = null;
  document.getElementById('attach-bar').classList.remove('visible');
  document.getElementById('attach-name').textContent = '';
}

async function sendFile(chatId, caption) {
  const fd = new FormData();
  fd.append('to', chatId);
  fd.append('caption', caption || '');
  fd.append('file', _attachFile, _attachFile.name);
  clearAttach();
  await fetch(api('/api/send-media'), { method: 'POST', body: fd });
}

async function sendMsg() {
  if (!selectedChatId) return;
  const inp = document.getElementById('msg-input');
  const text = inp.value.trim();
  if (_attachFile) {
    inp.value = ''; inp.style.height = '';
    try {
      await sendFile(selectedChatId, text);
      await loadMessages(selectedChatId);
      await loadChats();
    } catch(e) {}
    return;
  }
  if (!text) return;
  const replyId = _replyMsgId, replyTgId = _replyTgId;
  clearReply();
  inp.value=''; inp.style.height='';
  try {
    const endpoint = replyId ? api('/api/reply') : api('/api/send');
    const payload = replyId
      ? { to: selectedChatId, message: text, replyToTgId: replyTgId }
      : { to: selectedChatId, message: text };
    await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    await loadMessages(selectedChatId);
    await loadChats();
  } catch(e) {}
}

function handleKey(e) { if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMsg();} }
function autoResize(el) { el.style.height='auto'; el.style.height=Math.min(el.scrollHeight,120)+'px'; }

async function deleteMsg(chatId, msgId) {
  try {
    await fetch(api('/api/messages/'+encodeURIComponent(chatId)+'/'+encodeURIComponent(msgId)), {method:'DELETE'});
    await loadMessages(chatId);
  } catch(e) {}
}
document.getElementById('messages').addEventListener('click', e => {
  const del = e.target.closest('.del-btn');
  if (del) { const row = del.closest('.bubble-row'); if (row) deleteMsg(row.dataset.chatid, row.dataset.msgid); return; }
  const fwd = e.target.closest('.fwd-btn');
  if (fwd) { openFwdModal(fwd.dataset.msgid); return; }
  const rpl = e.target.closest('.reply-btn');
  if (rpl) { setReply(rpl.dataset.msgid, rpl.dataset.contact, rpl.dataset.preview, rpl.dataset.tgid); return; }
});

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

document.getElementById('msg-input').addEventListener('paste', function(e) {
  var items = (e.clipboardData && e.clipboardData.items) || [];
  for (var i = 0; i < items.length; i++) {
    if (items[i].type.indexOf('image/') === 0) {
      e.preventDefault();
      var blob = items[i].getAsFile();
      var ext = items[i].type.split('/')[1].replace('jpeg', 'jpg');
      attachFile(new File([blob], 'bild.' + ext, { type: items[i].type }));
      return;
    }
  }
});

// ── Reactions ─────────────────────────────────────────────────────────────────
(function(){
  const REACTION_EMOJIS = ['👍','👎','❤️','🔥','😂','😮','😢','🙏'];
  let pickerTargetMsgId = null;

  const picker = document.createElement('div');
  picker.id = 'reaction-picker';
  REACTION_EMOJIS.forEach(e => {
    const btn = document.createElement('button');
    btn.textContent = e; btn.title = e;
    btn.onclick = () => reactTo(e);
    picker.appendChild(btn);
  });
  document.body.appendChild(picker);

  document.addEventListener('click', ev => {
    if (!ev.target.closest('#reaction-picker') && !ev.target.closest('.react-btn')) {
      picker.style.display = 'none'; pickerTargetMsgId = null;
    }
  });

  document.getElementById('messages').addEventListener('click', ev => {
    const badge = ev.target.closest('.reaction-badge[data-emoji]');
    if (badge) {
      const row = badge.closest('.bubble-row');
      if (row) window.toggleReaction(row.dataset.msgid, badge.dataset.emoji, badge.dataset.own === 'true');
      return;
    }
    const btn = ev.target.closest('.react-btn');
    if (!btn) return;
    ev.stopPropagation();
    const row = btn.closest('.bubble-row');
    if (!row) return;
    const msgId = row.dataset.msgid;
    if (pickerTargetMsgId === msgId) { picker.style.display = 'none'; pickerTargetMsgId = null; return; }
    pickerTargetMsgId = msgId;
    picker.style.display = 'flex';
    picker.style.top = '-9999px'; picker.style.left = '-9999px';
    requestAnimationFrame(() => {
      const r = btn.getBoundingClientRect();
      const pw = picker.offsetWidth || 220, ph = picker.offsetHeight || 52;
      let top = r.top - ph - 8; if (top < 4) top = r.bottom + 8;
      let left = r.left + r.width / 2 - pw / 2;
      if (left < 4) left = 4;
      if (left + pw > window.innerWidth - 4) left = window.innerWidth - pw - 4;
      picker.style.top = top + 'px'; picker.style.left = left + 'px';
    });
  });

  async function reactTo(emoji) {
    if (!pickerTargetMsgId) return;
    const msgId = pickerTargetMsgId;
    picker.style.display = 'none'; pickerTargetMsgId = null;
    await fetch(api('/api/react'), {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ msgId, reaction: emoji }),
    }).catch(() => {});
    setTimeout(pollReactions, 600);
  }

  window.toggleReaction = async function(msgId, emoji, isOwn) {
    await fetch(api('/api/react'), {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ msgId, reaction: isOwn ? '' : emoji }),
    }).catch(() => {});
    setTimeout(pollReactions, 600);
  };

  async function pollReactions() {
    if (!selectedChatId) return;
    try {
      const data = await fetch(api('/api/reactions/'+encodeURIComponent(selectedChatId))).then(r=>r.json());
      updateReactionsInDOM(data);
    } catch(e) {}
  }
  window.pollReactions = pollReactions;
  setInterval(() => { if (selectedChatId) pollReactions(); }, 4000);

  function updateReactionsInDOM(map) {
    for (const row of document.querySelectorAll('#messages .bubble-row[data-msgid]')) {
      const msgId = row.dataset.msgid;
      const entry = map[msgId];
      let bar = row.querySelector('.reactions-bar');
      const reactBtn = row.querySelector('.react-btn');
      if (!entry || !Object.keys(entry.reactions).length) {
        if (bar) bar.remove();
        if (reactBtn) reactBtn.style.display = '';
        continue;
      }
      if (!bar) { bar = document.createElement('div'); bar.className = 'reactions-bar'; (row.querySelector('.bubble-stack') || row).appendChild(bar); }
      bar.innerHTML = '';
      for (const [emoji, count] of Object.entries(entry.reactions)) {
        if (!count) continue;
        const isOwn = entry.myReaction === emoji;
        const badge = document.createElement('span');
        badge.className = 'reaction-badge' + (isOwn ? ' own' : '');
        badge.title = isOwn ? t('reactionRemove') : emoji;
        badge.textContent = emoji + (count > 1 ? ' ' + count : '');
        badge.onclick = () => window.toggleReaction(msgId, emoji, isOwn);
        bar.appendChild(badge);
      }
      if (reactBtn) reactBtn.style.display = 'none';
    }
  }
})();

applyLang();

// Lightbox
(function(){
  const lb=document.createElement('div'); lb.id='lightbox';
  const lbImg=document.createElement('img'); lb.appendChild(lbImg);
  document.body.appendChild(lb);
  window.openLightbox=function(src){lbImg.src=src;lb.classList.add('open');};
  lb.addEventListener('click',()=>lb.classList.remove('open'));
  lbImg.addEventListener('click',e=>e.stopPropagation());
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape'){
      lb.classList.remove('open');
      document.getElementById('contact-modal')?.classList.remove('open');
    }
  });
})();
</script>
<div id="contact-modal" onclick="if(event.target===this)closeContactModal()">
  <div class="contact-modal-box">
    <div class="contact-modal-pic" id="contact-modal-pic"></div>
    <div class="contact-modal-name" id="contact-modal-name">…</div>
    <div class="contact-modal-sub" id="contact-modal-sub"></div>
    <div class="contact-modal-number" id="contact-modal-number"></div>
    <div class="contact-modal-about" id="contact-modal-about"></div>
    <button class="contact-modal-close" onclick="closeContactModal()">Schließen</button>
  </div>
</div>
<div id="fwd-modal">
  <div class="fwd-modal-box">
    <h3>↪ Weiterleiten an…</h3>
    <input type="text" id="fwd-search" placeholder="🔍 Chat suchen…" oninput="filterFwdChats()">
    <div id="fwd-chat-list"></div>
    <button class="fwd-modal-cancel" onclick="closeFwdModal()">Abbrechen</button>
  </div>
</div>
<div id="logout-modal">
  <div class="logout-modal-box">
    <p data-i18n="logoutConfirmMsg">Möchtest du dich wirklich abmelden?</p>
    <div class="logout-modal-actions">
      <button class="logout-modal-no" data-i18n="btnNo" onclick="closeLogoutModal()">Nein</button>
      <button class="logout-modal-yes" data-i18n="btnYes" onclick="logout()">Ja</button>
    </div>
  </div>
</div>
</body>
</html>`;
}

process.on('unhandledRejection', (reason) => {
  console.error('[ERROR] Unhandled:', reason?.message || reason);
});

fs.mkdirSync(MEDIA_DIR, { recursive: true });
loadFromDisk();
try {
  let best = null;
  for (const [chatId, msgs] of messagesByChatId.entries()) {
    const chat = chatMap.get(chatId);
    if (HA_NOTIFY_SKIP_BOTS && chat?.isBot) continue;
    for (const m of msgs) {
      if (!m.fromMe && !m.deleted && (!best || m.timestamp > best.timestamp)) {
        best = {
          timestamp: m.timestamp,
          iso: new Date(m.timestamp).toISOString(),
          chatId,
          chatName: chat?.name || chatId,
          contact: chat?.name || chatId,
          preview: m.body || (m.type === 'photo' ? '📷 Foto' : m.type === 'video' ? '📹 Video' : '[Medien]'),
        };
      }
    }
  }
  if (best) lastReceivedMsg = best;
} catch (e) { console.error('[ERROR] lastReceivedMsg init:', e.message); }
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
