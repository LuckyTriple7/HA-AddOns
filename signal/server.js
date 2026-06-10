'use strict';
const _logBuffer = [];
const _LOG_MAX = 300;
function _logSilent(level, msg) {
  _logBuffer.push({ ts: Date.now(), level: level||'DEBUG', msg: '['+(level||'DEBUG')+'] '+msg });
  if (_logBuffer.length > _LOG_MAX) _logBuffer.shift();
}
(function () {
  const _ts = () => new Date().toISOString().slice(0, 19).replace('T', ' ');
  const _lmap = { log:'INFO', warn:'WARN', error:'ERROR' };
  ['log','warn','error'].forEach(m => {
    const orig = console[m].bind(console);
    console[m] = (...a) => {
      let level = _lmap[m]||'INFO', out;
      if (a.length && typeof a[0] === 'string') {
        const match = a[0].match(/^(\[(INFO|WARN|ERROR|DEBUG)\])(.*)/s);
        if (match) {
          level = match[2];
          const rest = match[3].trimStart();
          out = `[${level}] [${_ts()}]${rest?' '+rest:''}`;
          orig(out, ...a.slice(1));
        } else {
          out = `[${level}] [${_ts()}] ${a[0]}`;
          orig(out, ...a.slice(1));
        }
      } else { out = `[${level}] [${_ts()}]`; orig(out, ...a); }
      _logBuffer.push({ ts: Date.now(), level, msg: out+(a.length>1?' '+a.slice(1).map(x=>typeof x==='object'?JSON.stringify(x):String(x)).join(' '):'') });
      if (_logBuffer.length > _LOG_MAX) _logBuffer.shift();
    };
  });
})();
const express = require('express');
const fetch = require('node-fetch');
const QRCode = require('qrcode');
const fs = require('fs');
const path = require('path');
const multer = require('multer');
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 64 * 1024 * 1024 } });

const rateLimit = require('express-rate-limit');
const deleteRateLimit = rateLimit({ windowMs: 60_000, limit: 30 });
const cleanupRateLimit = rateLimit({ windowMs: 60_000, limit: 5 });

const app = express();
app.use(express.json());
app.use((req, res, next) => {
  if (req.method === 'GET' || req.method === 'HEAD' || req.method === 'OPTIONS') return next();
  return rateLimit({ windowMs: 60_000, limit: 200 })(req, res, next);
});
app.use((req, res, next) => {
  if (req.path === '/api/logs' || req.path.startsWith('/api/media/') || req.path === '/api/status') return next();
  const t0 = Date.now();
  res.on('finish', () => _logSilent('DEBUG', `API ${req.method} ${req.path} → ${res.statusCode} (${Date.now()-t0}ms)`));
  next();
});

const PORT = process.env.PORT || 3000;
const SIGNAL_API = process.env.SIGNAL_API_URL || 'http://localhost:8080';
const WEBHOOK_INCOMING = process.env.WEBHOOK_INCOMING || '';
let PHONE_NUMBER = process.env.PHONE_NUMBER || '';
const DARK_MODE = process.env.DARK_MODE === 'true';
const DEBUG = process.env.DEBUG_MODE === 'true';
const DOWNLOAD_MEDIA = process.env.DOWNLOAD_MEDIA === 'true';
const MEDIA_MAX_MB = Math.max(parseInt(process.env.MEDIA_MAX_MB || '500', 10), 50);
const HA_NOTIFY = process.env.HA_NOTIFICATIONS === 'true';
const HA_PRIVACY = process.env.HA_NOTIFICATIONS_PRIVACY === 'true';
const HA_TOKEN = process.env.HA_TOKEN || '';
const MEDIA_DIR = '/config/media/';
function dbg(...args) { if (DEBUG) console.log('[DEBUG]', ...args.map(a => (typeof a === 'object' ? JSON.stringify(a) : String(a)))); }
console.log('[INFO] ── Configuration ──────────────────────────────────');
console.log(`[INFO]   phone_number           = ${PHONE_NUMBER ? 'set' : 'not set'}`);
console.log(`[INFO]   signal_api_url         = ${SIGNAL_API}`);
console.log(`[INFO]   dark_mode              = ${DARK_MODE}`);
console.log(`[INFO]   download_media         = ${DOWNLOAD_MEDIA}`);
console.log(`[INFO]   media_max_mb           = ${MEDIA_MAX_MB}`);
console.log(`[INFO]   debug_mode             = ${DEBUG}`);
console.log(`[INFO]   ha_notifications       = ${HA_NOTIFY}`);
console.log(`[INFO]   ha_notifications_priv  = ${HA_PRIVACY}`);
console.log(`[INFO]   ha_token               = ${HA_TOKEN ? 'set' : 'not set'}`);
console.log(`[INFO]   webhook_incoming       = ${WEBHOOK_INCOMING ? WEBHOOK_INCOMING : 'not set'}`);
console.log('[INFO] ─────────────────────────────────────────────────────');

let status = 'starting'; // starting | not-linked | linked | error
let lastError = '';
let lastReceivedMsg = null; // { timestamp, iso, chatId, chatName, contact, preview }
let qrSvg = null;      // inline SVG if API returns text URI
let qrUri = null;      // raw sgnl:// URI (if API returns text)
let qrDataUrl = null;  // data URL if API returns image directly
let qrFetching = false;

const chatMap = new Map();           // chatId -> { id, name, phone, lastMsg, lastTime }
const messagesByChatId = new Map();  // chatId -> Message[]
const seenMsgIds = new Set();

const CHATS_FILE = '/config/chats.json';
const MESSAGES_FILE = '/config/messages.json';

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
      console.log('[INFO] Signal account linked');
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

  // Lesebestätigungen / Zustellbestätigungen
  const rm = env.receiptMessage;
  if (rm && Array.isArray(rm.timestamps) && rm.timestamps.length > 0) {
    const ackLevel = rm.isRead ? 2 : rm.isDelivery ? 1 : 0;
    if (ackLevel > 0) {
      dbg(`receiptMessage: ackLevel=${ackLevel} timestamps=${rm.timestamps.join(',')}`);
      for (const ts of rm.timestamps) updateMsgAck(ts, ackLevel);
      scheduleSave();
    }
    return;
  }

  // Sync-Nachrichten: vom eigenen Gerät (Handy) gesendete Nachrichten
  const sm = env.syncMessage?.sentMessage;

  let dm, chatId, isOwn, senderName;
  if (sm) {
    const dest = normPhone(sm.destinationNumber || sm.destination);
    if (!dest) { dbg('processEnvelope: syncMessage ohne Ziel, übersprungen'); return; }
    dm = { message: sm.message || '', timestamp: sm.timestamp, attachments: sm.attachments || [] };
    chatId = dest;
    isOwn = true;
    senderName = PHONE_NUMBER;
  } else {
    dm = env.dataMessage;
    const source = normPhone(env.sourceNumber || env.source);
    isOwn = source === PHONE_NUMBER;
    chatId = source;
    senderName = env.sourceName || source;
  }

  const hasText = !!(dm && dm.message);
  const hasAttachments = !!(dm && Array.isArray(dm.attachments) && dm.attachments.length > 0);
  dbg(`processEnvelope: isOwn=${isOwn} hasDataMessage=${!!dm} hasText=${hasText} hasAttachments=${hasAttachments} body="${(dm?.message||'').slice(0,60)}"`);
  if (!dm || !chatId || (!hasText && !hasAttachments)) { dbg(`processEnvelope: skipping — no dataMessage, chatId, or content`); return; }

  const msgId = `${isOwn ? PHONE_NUMBER : chatId}_${dm.timestamp}`;
  if (seenMsgIds.has(msgId)) { dbg(`processEnvelope: duplicate skipped ${msgId}`); return; }
  seenMsgIds.add(msgId);
  const isVoice = hasAttachments && dm.attachments.some(a => (a.contentType || '').startsWith('audio/'));
  const isVideo = !isVoice && hasAttachments && dm.attachments.some(a => (a.contentType || '').startsWith('video/'));
  const msgType = isVoice ? 'voice' : isVideo ? 'video' : hasAttachments ? 'photo' : 'text';
  const previewText = dm.message || (isVoice ? '🎵 Sprachnachricht' : isVideo ? '📹 Video' : hasAttachments ? '📷 Foto' : '');

  const attIds = hasAttachments
    ? dm.attachments.filter(a => a.id).map(a => ({ id: a.id, ct: a.contentType || 'image/jpeg' }))
    : undefined;
  const msgFrom = isOwn ? PHONE_NUMBER : chatId;
  let quotedMsg = null;
  if (dm.quote) {
    quotedMsg = {
      body: (dm.quote.text || dm.quote.message || '').slice(0, 100),
      contact: normPhone(dm.quote.author) === PHONE_NUMBER ? 'Ich' : (dm.quote.author || ''),
    };
  }
  const videoAtt = isVideo ? dm.attachments.find(a => (a.contentType || '').startsWith('video/')) : null;
  const videoSize = videoAtt ? (videoAtt.size || 0) : undefined;
  const msg = { id: msgId, from: msgFrom, body: dm.message || '', timestamp: dm.timestamp, fromMe: isOwn, type: msgType, attIds, videoSize, quotedMsg };

  if (DOWNLOAD_MEDIA && hasAttachments) {
    for (const att of dm.attachments) {
      if (att.id && !(att.contentType || '').startsWith('video/')) downloadAttachment(att.id, att.contentType || 'image/jpeg', msgId);
    }
  }

  _logSilent('DEBUG', `signal-cli msg: from=${senderName||chatId} type=${msgType} fromMe=${isOwn}${dm.message?' "'+dm.message.slice(0,60)+'"':''}`);
  if (!messagesByChatId.has(chatId)) messagesByChatId.set(chatId, []);
  messagesByChatId.get(chatId).push(msg);

  if (!chatMap.has(chatId)) {
    chatMap.set(chatId, { id: chatId, name: senderName, phone: chatId, lastMsg: previewText, lastTime: dm.timestamp, lastFromMe: isOwn });
  } else {
    const chat = chatMap.get(chatId);
    chat.lastMsg = previewText;
    chat.lastTime = dm.timestamp;
    chat.lastFromMe = isOwn;
    if (senderName && senderName !== chatId) chat.name = senderName;
  }

  scheduleSave();

  dbg(`processEnvelope: stored msgId=${msgId} fromMe=${isOwn}`);

  if (!isOwn) {
    lastReceivedMsg = {
      timestamp: dm.timestamp,
      iso: new Date(dm.timestamp).toISOString(),
      chatId,
      chatName: chatMap.get(chatId)?.name || senderName,
      contact: senderName,
      type: msgType,
      preview: previewText,
    };
    sendHANotification(senderName, dm.message || previewText);
  }

  if (WEBHOOK_INCOMING && !isOwn) {
    dbg('Firing incoming webhook');
    fetch(WEBHOOK_INCOMING, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from: chatId, name: senderName, message: dm.message || previewText, type: msgType, timestamp: dm.timestamp }),
    }).catch(() => {});
  }
}

let _pollCount = 0;
async function pollMessages() {
  if (status !== 'linked' || !PHONE_NUMBER) return;
  try {
    const r = await fetch(`${SIGNAL_API}/v1/receive/${encodeURIComponent(PHONE_NUMBER)}`, { timeout: 5000 });
    if (!r.ok) return;
    _pollCount++;
    if (_pollCount % 30 === 0) _logSilent('INFO', `signal-cli Keep-alive OK — API reachable chats=${chatMap.size} msgs=${[...messagesByChatId.values()].reduce((s,a)=>s+a.length,0)}`);
    const messages = await r.json();
    if (Array.isArray(messages) && messages.length > 0) {
      dbg(`pollMessages: received ${messages.length} envelope(s)`);
      _logSilent('INFO', `signal-cli /v1/receive: ${messages.length} envelope(s)`);
      messages.forEach(processEnvelope);
    }
  } catch (e) {}
}

async function downloadAttachment(attId, contentType, msgId) {
  try {
    const ext = contentType.includes('webm') ? 'webm' : contentType.startsWith('video/') ? 'mp4' : contentType.includes('ogg') ? 'ogg' : contentType.includes('aac') ? 'aac' : contentType.includes('mpeg') ? 'mp3' : contentType.includes('png') ? 'png' : contentType.includes('gif') ? 'gif' : contentType.includes('webp') ? 'webp' : 'jpg';
    const filename = `${msgId.replace(/[^a-zA-Z0-9_-]/g, '_')}.${ext}`;
    const filepath = path.resolve(MEDIA_DIR, filename);
    if (!filepath.startsWith(path.resolve(MEDIA_DIR) + path.sep)) return;
    if (fs.existsSync(filepath)) { updateMsgMedia(msgId, filename); scheduleSave(); return; }
    _logSilent('DEBUG', `signal-cli downloadAttachment: start ${filename}`);
    const _t0 = Date.now();
    const r = await fetch(`${SIGNAL_API}/v1/attachments/${encodeURIComponent(attId)}`, { timeout: 30000 });
    if (!r.ok) { console.warn(`[WARN] Attachment download failed: HTTP ${r.status}`); return; }
    const buf = await r.buffer();
    fs.writeFileSync(filepath, buf);
    _logSilent('DEBUG', `signal-cli downloadAttachment: ok ${filename} ${(buf.length/1024).toFixed(1)}KB in ${Date.now()-_t0}ms`);
    updateMsgMedia(msgId, filename);
    scheduleSave();
  } catch (e) {
    console.error('[ERROR] downloadAttachment:', e.message);
  }
}

function updateMsgMedia(msgId, filename) {
  for (const [, msgs] of messagesByChatId) {
    const msg = msgs.find(m => m.id === msgId);
    if (msg) { msg.mediaFile = filename; break; }
  }
}

function sendHANotification(senderName, body) {
  if (!HA_NOTIFY || !HA_TOKEN) {
    if (HA_NOTIFY && !HA_TOKEN) console.warn('[WARN] HA_NOTIFICATIONS: ha_token not set in add-on configuration');
    return;
  }
  const preview = (body || '').length > 200 ? body.slice(0, 200) + '…' : (body || '');
  const payload = JSON.stringify(HA_PRIVACY ? {
    title: 'Signal',
    message: 'Neue Nachricht',
    notification_id: 'signal_new_message',
  } : {
    title: `Signal: ${senderName}`,
    message: preview || '📷 Foto',
    notification_id: 'signal_new_message',
  });
  const http = require('http');
  const req = http.request('http://homeassistant:8123/api/services/persistent_notification/create', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${HA_TOKEN}`,
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(payload),
    },
  }, (res) => {
    res.resume();
    if (res.statusCode !== 200) console.warn(`[WARN] HA notification returned HTTP ${res.statusCode}`);
  });
  req.on('error', e => console.warn('[WARN] HA notification error:', e.message));
  req.write(payload);
  req.end();
  console.log('[INFO] HA notification: Signal sent');
}

function updateMsgAck(signalTs, ackLevel) {
  for (const msgs of messagesByChatId.values()) {
    for (const msg of msgs) {
      if (msg.signalTimestamp === signalTs && msg.fromMe) {
        if ((msg.ack || 0) < ackLevel) {
          msg.ack = ackLevel;
          dbg(`ACK updated: signalTs=${signalTs} → ack=${ackLevel}`);
        }
        return;
      }
    }
  }
  dbg(`ACK: kein Match für signalTs=${signalTs}`);
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

app.get('/api/messages/:chatId', (req, res) => {
  res.json(messagesByChatId.get(req.params.chatId) || []);
});

app.get('/api/last-received', (req, res) => {
  const { chat: chatId } = req.query;
  if (chatId) {
    const msgs = (messagesByChatId.get(chatId) || []).filter(m => !m.fromMe);
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
      preview: last.body || (last.type === 'video' ? '📹 Video' : last.type === 'photo' ? '📷 Foto' : last.type === 'voice' ? '🎵 Sprachnachricht' : '[Medien]'),
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
    const tsNum = Number(m.timestamp);
    const tsMs = tsNum > 1e12 ? tsNum : tsNum * 1000;
    const d = new Date(tsMs);
    const dateStr = d.toLocaleDateString(loc, { weekday:'long', day:'2-digit', month:'long', year:'numeric' });
    const time = d.toLocaleTimeString(loc, { hour:'2-digit', minute:'2-digit' });
    let sep = '';
    if (dateStr !== lastDate) { sep = `<div class="day-sep">${escH(dateStr)}</div>`; lastDate = dateStr; }
    let content = '';
    if (m.type === 'voice') {
      content = `<span style="opacity:0.6">🎵 ${isEn ? 'Voice message' : 'Sprachnachricht'}</span>`;
    } else if (m.mediaFile) {
      const fp = MEDIA_DIR + m.mediaFile;
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
  const html = `<!DOCTYPE html><html lang="${isEn?'en':'de'}"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Chat: ${escH(chatName)}</title><style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#e5ddd5;min-height:100vh;padding:16px}h1{text-align:center;font-size:18px;color:#333;padding:12px 0 4px}.export-info{text-align:center;font-size:12px;color:#888;margin-bottom:16px}.day-sep{text-align:center;margin:12px 0;font-size:12px;color:#666;background:rgba(255,255,255,.6);border-radius:8px;display:inline-block;padding:2px 10px;width:100%}.msg{display:flex;margin:3px 0}.msg.in{justify-content:flex-start}.msg.out{justify-content:flex-end}.bubble{max-width:70%;padding:7px 10px;border-radius:8px;font-size:14px;line-height:1.45;word-break:break-word}.msg.in .bubble{background:#fff;border-bottom-left-radius:2px}.msg.out .bubble{background:#d1e3ff;border-bottom-right-radius:2px}.meta{display:flex;justify-content:space-between;gap:8px;margin-bottom:3px;font-size:12px}.sender{font-weight:600;color:#3a76f0}.msg.out .sender{color:#2960d6}.time{color:#999;flex-shrink:0}@media print{body{background:#fff}.msg.out .bubble{background:#ddeeff}}</style></head><body><h1>${escH(chatName)}</h1><p class="export-info">${exportedLabel} ${exportDate} &bull; ${msgs.length} ${messagesLabel}</p>${msgsHtml}</body></html>`;
  const fname = `signal_${chatName.replace(/[^a-zA-Z0-9_-]/g,'_').slice(0,40)}_${new Date().toISOString().slice(0,10)}.html`;
  res.setHeader('Content-Type','text/html; charset=utf-8');
  res.setHeader('Content-Disposition',`attachment; filename="${fname}"`);
  res.send(html);
});

app.get('/api/media/:filename', (req, res) => {
  const filename = req.params.filename;
  if (!/^[\w.-]+$/.test(filename)) return res.status(400).send('Invalid filename');
  const filepath = path.resolve(MEDIA_DIR, filename);
  if (!filepath.startsWith(path.resolve(MEDIA_DIR) + path.sep)) return res.status(400).send('Invalid filename');
  if (!fs.existsSync(filepath)) return res.status(404).send('Not found');
  const ext = filename.split('.').pop().toLowerCase();
  const mime = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', gif: 'image/gif', webp: 'image/webp', ogg: 'audio/ogg', aac: 'audio/aac', mp3: 'audio/mpeg' };
  res.setHeader('Content-Type', mime[ext] || 'application/octet-stream');
  fs.createReadStream(filepath).pipe(res);
});

function enforceMediaLimit() {
  const limitBytes = MEDIA_MAX_MB * 1024 * 1024;
  const targetBytes = limitBytes * 0.8;
  let current = 0, files = [];
  try {
    for (const f of fs.readdirSync(MEDIA_DIR)) {
      const fp = `${MEDIA_DIR}${f}`;
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
  if (freed) console.log(`[INFO] Media-Limit: ${(freed/1024/1024).toFixed(1)} MB freigegeben (Limit: ${MEDIA_MAX_MB} MB)`);
}

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

app.get('/api/logs', (req, res) => {
  const since = parseInt(req.query.since || '0', 10);
  res.json(since ? _logBuffer.filter(e => e.ts > since) : _logBuffer);
});

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

app.post('/api/cleanup-media', cleanupRateLimit, (req, res) => {
  try {
    const referenced = new Set();
    for (const msgs of messagesByChatId.values())
      for (const m of msgs)
        if (m.mediaFile) referenced.add(m.mediaFile);
    const files = fs.readdirSync(MEDIA_DIR);
    let count = 0, freed = 0;
    for (const f of files) {
      if (!referenced.has(f)) {
        const fp = MEDIA_DIR + f;
        try { freed += fs.statSync(fp).size; fs.unlinkSync(fp); count++; } catch(e) {}
      }
    }
    res.json({ deleted: count, freedMb: (freed / (1024 * 1024)).toFixed(1) });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/fetch-video', async (req, res) => {
  const { msgId } = req.body;
  if (!msgId) return res.status(400).json({ error: 'msgId required' });
  let storedMsg = null;
  for (const msgs of messagesByChatId.values()) { storedMsg = msgs.find(m => m.id === msgId); if (storedMsg) break; }
  if (!storedMsg) return res.status(404).json({ error: 'Nachricht nicht gefunden' });
  if (storedMsg.mediaFile) return res.json({ success: true, mediaFile: storedMsg.mediaFile });
  if (!storedMsg.attIds || !storedMsg.attIds.length) return res.status(400).json({ error: 'Keine Anhang-IDs gespeichert' });
  try {
    const att = storedMsg.attIds.find(a => (a.ct || '').startsWith('video/')) || storedMsg.attIds[0];
    if (storedMsg.videoSize && storedMsg.videoSize > MEDIA_MAX_MB * 1024 * 1024) {
      return res.status(413).json({ error: `Video zu groß (${(storedMsg.videoSize/1024/1024).toFixed(1)} MB, max ${MEDIA_MAX_MB} MB)` });
    }
    await downloadAttachment(att.id, att.ct, msgId);
    if (!storedMsg.mediaFile) return res.status(500).json({ error: 'Download fehlgeschlagen' });
    res.json({ success: true, mediaFile: storedMsg.mediaFile });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/fetch-media/:chatId', async (req, res) => {
  if (!DOWNLOAD_MEDIA) return res.status(400).json({ error: 'download_media not enabled' });
  const msgs = messagesByChatId.get(req.params.chatId) || [];
  const pending = msgs.filter(m => !m.mediaFile && m.attIds && m.attIds.length > 0);
  res.json({ total: pending.length });
  (async () => {
    let count = 0;
    for (const m of pending) {
      for (const att of m.attIds) {
        await downloadAttachment(att.id, att.ct, m.id);
        if (m.mediaFile) count++;
      }
      await new Promise(r => setTimeout(r, 400));
    }
    console.log(`[INFO] fetch-media: ${count}/${pending.length} Fotos nachgeladen für ${req.params.chatId}`);
  })();
});

app.post('/api/poll', async (req, res) => {
  await pollMessages();
  res.json({ ok: true });
});

app.post('/api/send', async (req, res) => {
  const { to, message } = req.body;
  if (!to || !message) return res.status(400).json({ error: 'Missing to/message' });
  try {
    dbg(`Sending message: "${message.slice(0,60)}${message.length>60?'…':''}"`);
    const r = await fetch(`${SIGNAL_API}/v2/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, number: PHONE_NUMBER, recipients: [to] }),
      timeout: 10000,
    });
    const result = await r.json();
    if (!r.ok) return res.status(500).json({ error: result });

    const signalTs = Number(result.timestamp) > 0 ? Number(result.timestamp) : Date.now();
    const msgId = `${PHONE_NUMBER}_${signalTs}`;
    if (!seenMsgIds.has(msgId)) {
      seenMsgIds.add(msgId);
      const msg = { id: msgId, from: PHONE_NUMBER, body: message, timestamp: signalTs, fromMe: true, ack: 0, signalTimestamp: signalTs };
      if (!messagesByChatId.has(to)) messagesByChatId.set(to, []);
      messagesByChatId.get(to).push(msg);
      if (!chatMap.has(to)) {
        chatMap.set(to, { id: to, name: to, phone: to, lastMsg: message, lastTime: Date.now() });
      } else {
        const chat = chatMap.get(to);
        chat.lastMsg = message;
        chat.lastTime = Date.now();
        chat.lastFromMe = true;
      }
      scheduleSave();
    }
    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
});

app.post('/api/reply', async (req, res) => {
  const { to, message, quoteTimestamp, quoteAuthor, quoteBody } = req.body;
  if (!to || !message) return res.status(400).json({ error: 'Missing to/message' });
  try {
    const r = await fetch(`${SIGNAL_API}/v2/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, number: PHONE_NUMBER, recipients: [to], quote: { id: quoteTimestamp, author: quoteAuthor, message: quoteBody || '' } }),
      timeout: 10000,
    });
    const result = await r.json();
    if (!r.ok) return res.status(500).json({ error: result });
    const signalTs = Number(result.timestamp) > 0 ? Number(result.timestamp) : Date.now();
    const msgId = `${PHONE_NUMBER}_${signalTs}`;
    if (!seenMsgIds.has(msgId)) {
      seenMsgIds.add(msgId);
      const storedQuote = quoteBody ? { body: quoteBody.slice(0, 100), contact: normPhone(quoteAuthor) === PHONE_NUMBER ? 'Ich' : (quoteAuthor || '') } : undefined;
      const msg = { id: msgId, from: PHONE_NUMBER, body: message, timestamp: signalTs, fromMe: true, ack: 0, signalTimestamp: signalTs, quotedMsg: storedQuote };
      if (!messagesByChatId.has(to)) messagesByChatId.set(to, []);
      messagesByChatId.get(to).push(msg);
      if (!chatMap.has(to)) {
        chatMap.set(to, { id: to, name: to, phone: to, lastMsg: message, lastTime: signalTs, lastFromMe: true });
      } else {
        const chat = chatMap.get(to);
        chat.lastMsg = message; chat.lastTime = signalTs; chat.lastFromMe = true;
      }
      scheduleSave();
    }
    res.json({ success: true });
  } catch (e) { res.status(500).json({ error: String(e.message || e) }); }
});

app.post('/api/forward', async (req, res) => {
  const { msgId, to } = req.body;
  if (!msgId || !to) return res.status(400).json({ error: 'msgId and to required' });
  let origMsg = null;
  for (const msgs of messagesByChatId.values()) { origMsg = msgs.find(m => m.id === msgId); if (origMsg) break; }
  if (!origMsg) return res.status(404).json({ error: 'Message not found' });
  try {
    let payload;
    if ((origMsg.type === 'photo' || origMsg.type === 'voice' || origMsg.type === 'video') && origMsg.mediaFile) {
      const fp = MEDIA_DIR + origMsg.mediaFile;
      if (fs.existsSync(fp)) {
        const ext = origMsg.mediaFile.split('.').pop();
        const mimeMap = { jpg: 'image/jpeg', png: 'image/png', gif: 'image/gif', webp: 'image/webp', ogg: 'audio/ogg', mp3: 'audio/mpeg' };
        payload = { message: origMsg.body || '', number: PHONE_NUMBER, recipients: [to], base64_attachments: [`data:${mimeMap[ext] || 'image/jpeg'};base64,${fs.readFileSync(fp).toString('base64')}`] };
      }
    }
    if (!payload) payload = { message: origMsg.body || '', number: PHONE_NUMBER, recipients: [to] };
    const r = await fetch(`${SIGNAL_API}/v2/send`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), timeout: 30000 });
    if (!r.ok) return res.status(500).json({ error: await r.json() });
    const result = await r.json();
    const signalTs = Number(result.timestamp) > 0 ? Number(result.timestamp) : Date.now();
    const newMsgId = `${PHONE_NUMBER}_${signalTs}`;
    if (!seenMsgIds.has(newMsgId)) {
      seenMsgIds.add(newMsgId);
      const preview = origMsg.body || (origMsg.type === 'video' ? '📹 Video' : origMsg.type === 'photo' ? '📷 Foto' : origMsg.type === 'voice' ? '🎵 Sprachnachricht' : '');
      const newMsg = { id: newMsgId, from: PHONE_NUMBER, body: origMsg.body || '', timestamp: signalTs, fromMe: true, ack: 0, signalTimestamp: signalTs, type: origMsg.type || 'text', mediaFile: origMsg.mediaFile || null };
      if (!messagesByChatId.has(to)) messagesByChatId.set(to, []);
      messagesByChatId.get(to).push(newMsg);
      if (!chatMap.has(to)) {
        chatMap.set(to, { id: to, name: to, phone: to, lastMsg: preview, lastTime: signalTs, lastFromMe: true });
      } else {
        const chat = chatMap.get(to); chat.lastMsg = preview; chat.lastTime = signalTs; chat.lastFromMe = true;
      }
      scheduleSave();
    }
    res.json({ success: true });
  } catch (e) { res.status(500).json({ error: String(e.message || e) }); }
});

app.post('/api/send-media', upload.single('file'), async (req, res) => {
  const { to, caption } = req.body;
  if (!to || !req.file) return res.status(400).json({ error: 'Missing to/file' });
  try {
    const { mimetype, buffer, originalname } = req.file;
    const dataUri = `data:${mimetype};filename=${encodeURIComponent(originalname)};base64,${buffer.toString('base64')}`;
    const r = await fetch(`${SIGNAL_API}/v2/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: caption || '', number: PHONE_NUMBER, recipients: [to], base64_attachments: [dataUri] }),
      timeout: 30000,
    });
    const result = await r.json();
    if (!r.ok) return res.status(500).json({ error: result });

    const safeName = originalname.replace(/[^a-zA-Z0-9._-]/g, '_');
    const isImg = mimetype.startsWith('image/');
    const signalTs = Number(result.timestamp) > 0 ? Number(result.timestamp) : Date.now();
    const msgId = `${PHONE_NUMBER}_${signalTs}`;
    if (!seenMsgIds.has(msgId)) {
      seenMsgIds.add(msgId);
      let mediaFile = null;
      if (isImg && DOWNLOAD_MEDIA) {
        enforceMediaLimit();
        const fname = `${signalTs}_${safeName}`;
        const fpath = path.resolve(MEDIA_DIR, fname);
        if (!fpath.startsWith(path.resolve(MEDIA_DIR) + path.sep)) throw new Error('Invalid media path');
        fs.writeFileSync(fpath, buffer);
        mediaFile = fname;
      }
      const msg = isImg
        ? { id: msgId, from: PHONE_NUMBER, body: caption || '', type: 'photo', timestamp: signalTs, signalTimestamp: signalTs, fromMe: true, ack: 0, attIds: [], mediaFile }
        : { id: msgId, from: PHONE_NUMBER, body: caption || '', type: 'document', filename: safeName, timestamp: signalTs, signalTimestamp: signalTs, fromMe: true, ack: 0, attIds: [], mediaFile: null };
      if (!messagesByChatId.has(to)) messagesByChatId.set(to, []);
      messagesByChatId.get(to).push(msg);
      if (chatMap.has(to)) {
        chatMap.get(to).lastMsg = caption || (isImg ? '📷 Foto' : safeName);
        chatMap.get(to).lastTime = signalTs;
        chatMap.get(to).lastFromMe = true;
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

app.delete('/api/messages/:chatId/:msgId', deleteRateLimit, async (req, res) => {
  const { chatId, msgId } = req.params;
  dbg(`Deleting message ${msgId}`);
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
        dbg(`delete-for-everyone not supported: ${t.trim()}`);
      }
    } catch (e) {
      dbg(`delete-for-everyone: ${e.message}`);
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

const _SVG = {
  moon:      '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
  sun:       '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>',
  disk:      '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;flex-shrink:0"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>',
  download:  '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
  imageOn:   '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>',
  imageOff:  '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>',
  trash:     '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>',
  chevUp:    '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg>',
  chevDown:  '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>',
  chevLeft:  '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>',
  search:    '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
  x:         '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  smile:     '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>',
  paperclip: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>',
  globe:     '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
  doc:       '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
  fwd:       '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 10 20 15 15 20"/><path d="M4 4v7a4 4 0 0 0 4 4h12"/></svg>',
  reply:     '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/></svg>',
};

function getHtml() {
  return `<!DOCTYPE html>
<html lang="de" class="${DARK_MODE ? 'dark' : 'light'}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>Signal</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; height: var(--app-height, 100dvh); display: flex; flex-direction: column; background: #f0f2f5; color: #111; }

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

#topbar { display: none; align-items: center; background: #2c6bed; color: #fff; padding: 0 16px; height: 56px; gap: 8px; flex-shrink: 0; }
#topbar h1 { font-size: 18px; flex: 1; }
#topbar .phone { font-size: 13px; color: rgba(255,255,255,0.75); }
#storage-info { font-size: 12px; opacity: 0.6; white-space: nowrap; }
.scroll-btn { background: none; border: 1px solid rgba(255,255,255,0.4); color: #fff; padding: 4px 8px; border-radius: 6px; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; opacity: 0.6; }
.scroll-btn:hover { opacity: 1; }
#photo-toggle-btn { background: none; border: 1px solid rgba(255,255,255,0.4); color: rgba(255,255,255,0.7); padding: 4px 8px; border-radius: 6px; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }
#photo-toggle-btn.active { border-color: #fff; color: #fff; background: rgba(255,255,255,0.15); }
#logout-btn, #topbar-back { background: none; border: none; color: rgba(255,255,255,0.6); cursor: pointer; padding: 6px; line-height: 1; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
#logout-btn:hover { color: #f15c5c; }
#topbar-back { display: none; }
#topbar-back:hover { color: rgba(255,255,255,0.9); }
.msg-img { max-width: 250px; max-height: 250px; border-radius: 8px; cursor: zoom-in; display: block; object-fit: cover; margin-top: 4px; }
.photo-placeholder { color: #3a76f8; }
.bubble-doc { display: flex; align-items: center; gap: 10px; padding: 4px 0; }
.bubble-doc .doc-icon { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
.bubble-doc .doc-name { font-size: 13px; word-break: break-all; font-weight: 500; }

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
.chat-meta { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; flex-shrink: 0; }
.unread-dot { width: 10px; height: 10px; background: #3a76f8; border-radius: 50%; }
html.dark .unread-dot { background: #3cdb7c; }

#chat-panel { flex: 1; display: flex; flex-direction: column; background: #e5ddd5; }
#chat-header { background: #1b1b21; color: #fff; padding: 12px 16px; display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
#back-btn { display: none; background: none; border: none; color: #fff; cursor: pointer; padding: 0 8px 0 0; align-items: center; justify-content: center; }
#ch-name { font-weight: 600; font-size: 16px; }
#ch-phone { font-size: 12px; color: #aaa; }
#ch-stats { font-size: 11px; color: rgba(255,255,255,0.55); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#fetch-media-btn, #export-btn, #msg-search-btn { background: none; border: 1px solid rgba(255,255,255,0.25); color: rgba(255,255,255,0.65); padding: 5px 8px; border-radius: 6px; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; font-size: 12px; white-space: nowrap; transition: color 0.15s, border-color 0.15s; }
#fetch-media-btn { margin-left: auto; }
#export-btn { ${DOWNLOAD_MEDIA ? '' : 'margin-left: auto;'} }
#fetch-media-btn:hover, #export-btn:hover { border-color: rgba(255,255,255,0.8); color: #fff; }
#fetch-media-btn:disabled { opacity: 0.4; cursor: default; }
#msg-search-btn:hover { border-color: rgba(255,255,255,0.8); color: #fff; }
#msg-search-btn.active { color: #3a76f8; border-color: #3a76f8; }
#messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 4px; }
#no-chat { flex: 1; display: flex; align-items: center; justify-content: center; color: #999; font-size: 15px; }
.bubble { max-width: 65%; padding: 8px 12px; border-radius: 8px; font-size: 14px; line-height: 1.4; word-break: break-word; }
.bubble.in { background: #fff; border-bottom-left-radius: 2px; }
.bubble.out { background: #d1e3ff; border-bottom-right-radius: 2px; }
.bubble-row { display: flex; align-items: center; gap: 6px; }
.bubble-row.out { justify-content: flex-end; }
.bubble-row.in { justify-content: flex-start; }
.bubble-row.out .del-btn { order: -1; }
.del-btn { display: none; background: none; border: none; cursor: pointer; display: none; align-items: center; justify-content: center; padding: 4px 6px; border-radius: 6px; flex-shrink: 0; }
.bubble-row:hover .del-btn { display: inline-flex; }
html.dark .del-btn { color: rgba(233,237,239,0.6); }
html.light .del-btn { color: rgba(0,0,0,0.4); }
.del-btn:hover { color: #e74c3c !important; }
.fwd-btn, .reply-btn { display: none; background: none; border: none; cursor: pointer; align-items: center; justify-content: center; padding: 4px 6px; border-radius: 6px; flex-shrink: 0; }
.bubble-row:hover .fwd-btn, .bubble-row:hover .reply-btn { display: inline-flex; }
html.dark .fwd-btn, html.dark .reply-btn { color: rgba(134,150,160,0.85); }
html.light .fwd-btn, html.light .reply-btn { color: rgba(0,0,0,0.4); }
.fwd-btn:hover { color: #3a76f8 !important; }
.reply-btn:hover { color: #3a76f8 !important; }
.quoted-block { border-left: 3px solid #3a76f8; background: rgba(58,118,248,0.08); border-radius: 4px; padding: 4px 8px; margin-bottom: 5px; overflow: hidden; }
.quoted-sender { font-size: 11px; font-weight: 600; color: #3a76f8; margin-bottom: 1px; }
.quoted-text { font-size: 12px; color: #999; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
html.dark .quoted-text { color: rgba(134,150,160,0.85); }
#reply-bar { display: none; background: #e8eef4; border-left: 3px solid #3a76f8; padding: 6px 16px; align-items: center; gap: 10px; flex-shrink: 0; }
html.dark #reply-bar { background: #1a2533; }
#reply-bar.active { display: flex; }
.reply-bar-content { flex: 1; overflow: hidden; }
#reply-bar-sender { font-size: 11px; font-weight: 600; color: #3a76f8; }
#reply-bar-text { font-size: 12px; color: #999; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#reply-close { background: none; border: none; color: #999; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; padding: 4px; flex-shrink: 0; }
#reply-close:hover { color: #e74c3c; }
#fwd-modal { display: none; position: fixed; inset: 0; z-index: 400; background: rgba(0,0,0,0.6); align-items: center; justify-content: center; }
#fwd-modal.open { display: flex; }
.fwd-modal-box { background: #202c33; border-radius: 12px; padding: 20px; max-width: 400px; width: 92%; max-height: 70vh; display: flex; flex-direction: column; box-shadow: 0 8px 32px rgba(0,0,0,0.5); }
html.light .fwd-modal-box { background: #fff; }
.fwd-modal-box h3 { font-size: 15px; font-weight: 600; margin-bottom: 12px; color: #e9edef; }
html.light .fwd-modal-box h3 { color: #111; }
#fwd-search { width: 100%; background: #2a3942; border: none; border-radius: 8px; padding: 8px 12px; color: #e9edef; font-size: 14px; outline: none; margin-bottom: 10px; }
html.light #fwd-search { background: #f0f2f5; color: #111; }
#fwd-search::placeholder { color: #8696a0; }
#fwd-chat-list { flex: 1; overflow-y: auto; }
.fwd-chat-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; cursor: pointer; border-radius: 8px; }
.fwd-chat-item:hover { background: #2a3942; }
html.light .fwd-chat-item:hover { background: #f0f2f5; }
.fwd-chat-item-name { font-size: 14px; color: #e9edef; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
html.light .fwd-chat-item-name { color: #111; }
.fwd-modal-cancel { margin-top: 12px; background: #2a3942; color: #e9edef; border: none; border-radius: 8px; padding: 8px 18px; font-size: 14px; cursor: pointer; width: 100%; }
html.light .fwd-modal-cancel { background: #e0e0e0; color: #111; }
.fwd-modal-cancel:hover { background: #3d5259; }
.bubble-time { font-size: 11px; color: #999; text-align: right; margin-top: 2px; }
.msg-ack { font-size: 11px; margin-left: 2px; vertical-align: middle; }
.ack-1, .ack-2 { color: rgba(0,0,0,0.4); }
.ack-3 { color: #3a76f8; }
html.dark .ack-1, html.dark .ack-2 { color: rgba(134,150,160,0.85); }
html.dark .ack-3 { color: #53bdeb; }
.day-sep { text-align: center; margin: 8px 0; }
.day-sep span { background: rgba(255,255,255,0.8); padding: 4px 12px; border-radius: 12px; font-size: 12px; color: #666; }

#input-bar { background: #f0f2f5; padding: 8px 16px; display: flex; gap: 8px; align-items: flex-end; flex-shrink: 0; position: relative; }
#emoji-picker { display: none; position: absolute; bottom: 100%; left: 0; right: 0; background: #fff; border-top: 1px solid #e0e0e0; padding: 8px 12px; max-height: 200px; overflow-y: auto; z-index: 20; box-shadow: 0 -2px 8px rgba(0,0,0,0.08); }
#emoji-picker.open { display: block; }
.emoji-grid { display: flex; flex-wrap: wrap; gap: 2px; }
.emoji-btn { background: none; border: none; font-size: 22px; cursor: pointer; padding: 3px 5px; border-radius: 6px; line-height: 1; }
.emoji-btn:hover { background: #f0f2f5; }
#emoji-toggle { background: none; border: none; cursor: pointer; padding: 6px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
#emoji-toggle:hover { background: rgba(0,0,0,0.08); }
#input-bar #attach-btn { background: none; border: none; cursor: pointer; padding: 6px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; color: #888; }
#input-bar #attach-btn:hover { background: rgba(0,0,0,0.08); }
#attach-bar { display: none; align-items: center; gap: 10px; padding: 6px 16px; font-size: 13px; background: #e8eef4; border-top: 1px solid #d0d8e0; color: #333; }
#attach-bar.visible { display: flex; }
#attach-bar .attach-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#attach-bar .attach-clear { background: none; border: none; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; color: #e74c3c; padding: 2px 6px; border-radius: 4px; flex-shrink: 0; }
#file-input { display: none; }
html.dark #input-bar #attach-btn { color: #8696a0; }
html.dark #attach-bar { background: #1a2533; border-color: #2a3942; color: #c1c9d4; }
#msg-input { flex: 1; padding: 10px 14px; border-radius: 20px; border: none; background: #fff; font-size: 14px; outline: none; resize: none; max-height: 120px; overflow-y: auto; font-family: inherit; }
#send-btn { width: 40px; height: 40px; border-radius: 50%; border: none; background: #3a76f8; color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
#send-btn:hover { background: #2960d6; }

/* ── Nachrichtensuche ── */
#msg-search-bar { display: none; align-items: center; gap: 8px; padding: 6px 12px; flex-shrink: 0; background: #161b22; border-bottom: 1px solid rgba(255,255,255,0.08); }
#msg-search-bar.open { display: flex; }
#msg-search-input { flex: 1; border: none; border-radius: 16px; padding: 6px 12px; font-size: 13px; outline: none; font-family: inherit; background: #2a3942; color: #e9edef; }
#msg-search-input::placeholder { color: #8696a0; }
#msg-search-count { font-size: 12px; color: rgba(255,255,255,0.6); white-space: nowrap; min-width: 40px; text-align: right; }
.msg-search-nav-btn { background: none; border: none; color: rgba(255,255,255,0.6); cursor: pointer; padding: 4px; border-radius: 4px; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
.msg-search-nav-btn:hover { color: #fff; background: rgba(255,255,255,0.1); }
#msg-search-close { background: none; border: none; color: rgba(255,255,255,0.5); cursor: pointer; padding: 4px; border-radius: 4px; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
#msg-search-close:hover { color: #e74c3c; }
.msg-highlight { background: rgba(255,235,59,0.35); border-radius: 3px; }
.msg-highlight-active { background: rgba(255,165,0,0.6); border-radius: 3px; outline: 1px solid rgba(255,165,0,0.9); }

@media (max-width: 768px) {
  #sidebar { width: 100%; max-width: 100%; border-right: none; }
  #chat-panel { display: none; }
  #back-btn { display: none !important; }
  body.chat-open #sidebar { display: none; }
  body.chat-open #chat-panel { display: flex; }
  #lang-btn { display: none !important; }
  #topbar { gap: 6px; }
  #topbar .phone { display: none; }
  #ch-stats { white-space: normal; font-size: 10px; overflow: visible; text-overflow: unset; }
  body.chat-open #topbar h1 { display: none; }
  body.chat-open #topbar-back { display: inline-flex; margin-right: auto; }
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
html.dark .bubble.out { background: #1d3c8a; color: #e9edef; }
html.dark .bubble-time { color: rgba(134,150,160,0.85); }
html.dark .day-sep span { background: rgba(17,27,33,0.9); color: #8696a0; }
html.dark #no-chat { color: #8696a0; }
html.dark #input-bar { background: #202c33; }
html.dark #msg-input { background: #2a3942; color: #e9edef; }
html.dark #emoji-picker { background: #202c33; border-color: #2a3942; }
html.dark .emoji-btn:hover { background: #2a3942; }
html.dark #emoji-toggle { color: #8696a0; }

#chat-filter { display: flex; border-bottom: 1px solid #e0e0e0; background: #fff; }
.filter-tab { flex: 1; padding: 8px 4px; font-size: 12px; text-align: center; cursor: pointer; border: none; background: none; color: #666; border-bottom: 2px solid transparent; transition: all 0.15s; }
.filter-tab.active { color: #3a76f8; border-bottom-color: #3a76f8; font-weight: 600; }
.filter-tab:hover { background: #f5f5f5; }
html.dark #chat-filter { background: #111b21; border-color: #2a3942; }
html.dark .filter-tab { color: #8696a0; }
html.dark .filter-tab.active { color: #3a76f8; border-bottom-color: #3a76f8; }
html.dark .filter-tab:hover { background: #202c33; }
.avatar.type-group { font-size: 20px; }
#logout-modal { display:none; position:fixed; inset:0; z-index:500; background:rgba(0,0,0,0.6); align-items:center; justify-content:center; }
#logout-modal.open { display:flex; }
.logout-modal-box { background:#1b1b21; border-radius:12px; padding:24px; max-width:360px; width:90%; box-shadow:0 8px 32px rgba(0,0,0,0.5); }
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

<div id="spinner-overlay">
  <div class="spinner"></div>
  <div id="spinner-text" data-i18n="spinnerStart">Starte Signal…</div>
</div>

<div id="qr-overlay">
  <h2 data-i18n="qrTitle">Signal verknüpfen</h2>
  <p data-i18n="qrInstr">Signal öffnen → Einstellungen → Verknüpfte Geräte → Gerät hinzufügen → QR-Code scannen</p>
  <div id="qr-img" data-i18n="qrLoading">Lade QR-Code…</div>
  <button id="qr-refresh-btn" onclick="refreshQR()" data-i18n="qrRefreshBtn">QR-Code neu laden</button>
  <p id="qr-uri"></p>
</div>

<div id="topbar">
  <button id="topbar-back" onclick="closeChat()" title="Zurück"><svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><polyline points="15 18 9 12 15 6"/></svg></button>
  <h1 ondblclick="sigConsoleToggle()" style="cursor:default;user-select:none;" title="Doppelklick: Console">Signal</h1>
  <button id="theme-btn" onclick="toggleTheme()" title="Dark / Light Mode" style="background:none;border:none;cursor:pointer;padding:4px 2px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;opacity:0.75;color:inherit;"></button>
  <span class="phone" id="my-phone"></span>
  <span id="storage-info"></span>
  ${DOWNLOAD_MEDIA ? `<button id="photo-toggle-btn" class="active" onclick="togglePhotos()" data-i18n-title="photosOn" title="Medien AN">${_SVG.imageOn}</button>` : ''}
  ${DOWNLOAD_MEDIA ? `<button class="scroll-btn" onclick="cleanupMedia()" data-i18n-title="cleanupTitle" title="Verwaiste Mediendateien löschen">${_SVG.trash}</button>` : ''}
  <button class="scroll-btn" onclick="scrollMsgs(\'top\')" data-i18n-title="btnScrollUp" title="Nach oben">${_SVG.chevUp}</button>
  <button class="scroll-btn" onclick="scrollMsgs(\'bottom\')" data-i18n-title="btnScrollDown" title="Nach unten">${_SVG.chevDown}</button>
  <button id="lang-btn" class="scroll-btn" onclick="switchLang()" title="Sprache / Language" style="gap:4px;padding:0 8px;">${_SVG.globe} DE</button>
  <button id="logout-btn" onclick="confirmLogout()" data-i18n-title="btnLogout" title="Abmelden"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg></button>
</div>

<div id="main">
  <div id="sidebar">
    <div id="search-wrap">
      <input id="search-input" type="text" placeholder="Suchen…" data-i18n-pl="searchPlaceholder" oninput="filterChats(this.value)">
    </div>
    <div id="chat-filter">
      <button class="filter-tab active" onclick="setFilter('all')" data-filter="all" data-i18n="filterAll">Alle</button>
      <button class="filter-tab" onclick="setFilter('private')" data-filter="private" data-i18n="filterPrivate">Privat</button>
      <button class="filter-tab" onclick="setFilter('group')" data-filter="group" data-i18n="filterGroups">Gruppen</button>
    </div>
    <div id="chat-list"></div>
  </div>
  <div id="chat-panel">
    <div id="chat-header">
      <button id="back-btn" onclick="closeChat()">${_SVG.chevLeft}</button>
      <div class="avatar" id="ch-avatar" style="width:36px;height:36px;font-size:14px;background:#3a76f8">?</div>
      <div style="flex:1;overflow:hidden">
        <div id="ch-name" data-i18n="noChatSelected">Kein Chat ausgewählt</div>
        <div id="ch-phone"></div>
        <div id="ch-stats"></div>
      </div>
      ${DOWNLOAD_MEDIA ? `<button id="fetch-media-btn" onclick="fetchMedia()" data-i18n-title="fetchMediaTitle" title="Fehlende Fotos herunterladen">${_SVG.download}</button>` : ''}
      <button id="msg-search-btn" onclick="toggleMsgSearch()" data-i18n-title="msgSearchTitle" title="In Nachrichten suchen">${_SVG.search}</button>
      <button id="export-btn" onclick="exportChat()" data-i18n-title="ttExport" title="Chat exportieren">${_SVG.disk}</button>
    </div>
    <div id="msg-search-bar">
      <input id="msg-search-input" type="text" placeholder="Nachrichten durchsuchen…" oninput="onMsgSearchInput()" onkeydown="if(event.key==='Enter'){stepMsgSearch(event.shiftKey?-1:1);}if(event.key==='Escape'){closeMsgSearch();}">
      <span id="msg-search-count"></span>
      <button class="msg-search-nav-btn" onclick="stepMsgSearch(-1)" title="Vorheriger Treffer">${_SVG.chevUp}</button>
      <button class="msg-search-nav-btn" onclick="stepMsgSearch(1)" title="Nächster Treffer">${_SVG.chevDown}</button>
      <button id="msg-search-close" onclick="closeMsgSearch()">${_SVG.x}</button>
    </div>
    <div id="messages"><div id="no-chat" data-i18n="noChatSelected">Wähle einen Chat aus der Liste</div></div>
    <div id="reply-bar">
      <div class="reply-bar-content">
        <div id="reply-bar-sender"></div>
        <div id="reply-bar-text"></div>
      </div>
      <button id="reply-close" onclick="clearReply()">${_SVG.x}</button>
    </div>
    <div id="attach-bar">
      ${_SVG.paperclip}
      <span class="attach-name" id="attach-name"></span>
      <button class="attach-clear" onclick="clearAttach()" title="Entfernen">${_SVG.x}</button>
    </div>
    <div id="input-bar">
      <div id="emoji-picker"><div class="emoji-grid" id="emoji-grid"></div></div>
      <input type="file" id="file-input" onchange="onFileSelected(this)">
      <button id="emoji-toggle" onclick="toggleEmojiPicker(event)" data-i18n-title="emojiTitle" title="Emoji">${_SVG.smile}</button>
      <button id="attach-btn" onclick="document.getElementById('file-input').click()" data-i18n-title="attachTitle" title="Datei anhängen">${_SVG.paperclip}</button>
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
    spinnerStart: 'Starte Signal…', spinnerConnect: 'Verbinde…', spinnerLogout: 'Abmelden…',
    spinnerError: (e) => 'Fehler: ' + e,
    qrTitle: 'Signal verknüpfen',
    qrInstr: 'Signal öffnen → Einstellungen → Verknüpfte Geräte → Gerät hinzufügen → QR-Code scannen',
    qrLoading: 'Lade QR-Code…', qrLoadingLong: 'Lade QR-Code… (kann bis zu 60s dauern)',
    qrError: (e) => 'Fehler: ' + e, qrRefreshBtn: 'QR-Code neu laden',
    photosOn: 'Medien AN', photosOff: 'Medien AUS',
    cleanupTitle: 'Verwaiste Mediendateien löschen',
    btnScrollUp: 'Nach oben', btnScrollDown: 'Nach unten', btnLogout: 'Abmelden',
    logoutConfirmMsg: 'Möchtest du dich wirklich abmelden?', btnYes: 'Ja', btnNo: 'Nein',
    searchPlaceholder: 'Suchen…', noChatSelected: 'Wähle einen Chat aus der Liste',
    noMessages: 'Noch keine Nachrichten',
    btnFetchMedia: '📥', fetchMediaTitle: 'Fehlende Fotos herunterladen',
    fetchMediaLoading: '⏳ Lade…', fetchMediaDone: '✓ Alle geladen',
    fetchMediaCount: (n) => '⏳ ' + n + ' Fotos…',
    msgPlaceholder: 'Nachricht…', btnDelete: 'Löschen', ttReply: 'Antworten', ttForward: 'Weiterleiten', emojiTitle: 'Emoji', attachTitle: 'Datei anhängen', ttExport: 'Chat als HTML exportieren',
    errSend: (e) => 'Fehler: ' + e,
    statsMsg: 'Nachrichten', statsSince: 'seit',
    cleanupConfirm: 'Verwaiste Mediendateien löschen (nicht mehr referenzierte Fotos)?',
    cleanupSuccess: (c, mb) => c + ' Datei(en) gelöscht, ' + mb + ' MB freigegeben.',
    cleanupError: (e) => 'Fehler beim Cleanup: ' + e,
    filterAll: 'Alle', filterPrivate: 'Privat', filterGroups: 'Gruppen',
    offlineTitle: 'Verbindung unterbrochen', offlineSub: 'Stelle Verbindung wieder her…', offlineReload: 'Neu laden',
    msgSearchTitle: 'In Nachrichten suchen',
  },
  en: {
    spinnerStart: 'Starting Signal…', spinnerConnect: 'Connecting…', spinnerLogout: 'Logging out…',
    spinnerError: (e) => 'Error: ' + e,
    qrTitle: 'Link Signal',
    qrInstr: 'Open Signal → Settings → Linked Devices → Link a Device → Scan QR code',
    qrLoading: 'Loading QR code…', qrLoadingLong: 'Loading QR code… (may take up to 60s)',
    qrError: (e) => 'Error: ' + e, qrRefreshBtn: 'Reload QR code',
    photosOn: 'Media ON', photosOff: 'Media OFF',
    cleanupTitle: 'Delete orphaned media files',
    btnScrollUp: 'Scroll up', btnScrollDown: 'Scroll down', btnLogout: 'Log out',
    logoutConfirmMsg: 'Do you really want to log out?', btnYes: 'Yes', btnNo: 'No',
    searchPlaceholder: 'Search…', noChatSelected: 'Select a chat from the list',
    noMessages: 'No messages yet',
    btnFetchMedia: '📥', fetchMediaTitle: 'Download missing photos',
    fetchMediaLoading: '⏳ Loading…', fetchMediaDone: '✓ All loaded',
    fetchMediaCount: (n) => '⏳ ' + n + ' photos…',
    msgPlaceholder: 'Message…', btnDelete: 'Delete', ttReply: 'Reply', ttForward: 'Forward', emojiTitle: 'Emoji', attachTitle: 'Attach file', ttExport: 'Export chat as HTML',
    errSend: (e) => 'Error: ' + e,
    statsMsg: 'messages', statsSince: 'since',
    cleanupConfirm: 'Delete orphaned media files (photos no longer referenced)?',
    cleanupSuccess: (c, mb) => c + ' file(s) deleted, ' + mb + ' MB freed.',
    cleanupError: (e) => 'Cleanup error: ' + e,
    filterAll: 'All', filterPrivate: 'Private', filterGroups: 'Groups',
    offlineTitle: 'Connection lost', offlineSub: 'Reconnecting…', offlineReload: 'Reload',
    msgSearchTitle: 'Search in messages',
  },
};
const _browserLang = (navigator.language || '').toLowerCase().startsWith('de') ? 'de' : 'en';
let lang = localStorage.getItem('signal_lang') || _browserLang;
// ── Nachrichtensuche ──────────────────────────────────────────────────────────
let _msgSearchMatches = [], _msgSearchIdx = -1;
function toggleMsgSearch() {
  const bar = document.getElementById('msg-search-bar');
  if (!bar) return;
  if (bar.classList.contains('open')) { closeMsgSearch(); return; }
  bar.classList.add('open');
  document.getElementById('msg-search-btn').classList.add('active');
  const inp = document.getElementById('msg-search-input');
  if (inp) { inp.value = ''; inp.focus(); }
  _msgSearchMatches = []; _msgSearchIdx = -1;
  updateMsgSearchCount();
}
function closeMsgSearch() {
  const bar = document.getElementById('msg-search-bar');
  if (bar) bar.classList.remove('open');
  const btn = document.getElementById('msg-search-btn');
  if (btn) btn.classList.remove('active');
  const inp = document.getElementById('msg-search-input');
  if (inp) inp.value = '';
  clearMsgHighlights();
  _msgSearchMatches = []; _msgSearchIdx = -1;
  updateMsgSearchCount();
}
function clearMsgHighlights() {
  document.querySelectorAll('#messages .msg-highlight, #messages .msg-highlight-active').forEach(function(el) {
    const parent = el.parentNode;
    if (parent) { parent.replaceChild(document.createTextNode(el.textContent), el); parent.normalize(); }
  });
}
function updateMsgSearchCount() {
  const el = document.getElementById('msg-search-count');
  if (!el) return;
  el.textContent = _msgSearchMatches.length === 0 ? '' : (_msgSearchIdx + 1) + ' / ' + _msgSearchMatches.length;
}
function onMsgSearchInput() {
  clearMsgHighlights();
  _msgSearchMatches = []; _msgSearchIdx = -1;
  const inp = document.getElementById('msg-search-input');
  if (!inp) return;
  const q = inp.value.trim();
  if (!q) { updateMsgSearchCount(); return; }
  const qLow = q.toLowerCase();
  document.querySelectorAll('#messages .bubble').forEach(function(bubble) { highlightInNode(bubble, qLow, q); });
  _msgSearchMatches = Array.from(document.querySelectorAll('#messages .msg-highlight'));
  if (_msgSearchMatches.length > 0) { _msgSearchIdx = 0; activateMsgSearchMatch(0); }
  updateMsgSearchCount();
}
function highlightInNode(node, qLow, q) {
  if (node.nodeType === Node.TEXT_NODE) {
    const text = node.textContent;
    const idx = text.toLowerCase().indexOf(qLow);
    if (idx === -1) return;
    const before = document.createTextNode(text.slice(0, idx));
    const mark = document.createElement('mark');
    mark.className = 'msg-highlight';
    mark.textContent = text.slice(idx, idx + q.length);
    const after = document.createTextNode(text.slice(idx + q.length));
    const parent = node.parentNode;
    parent.insertBefore(before, node); parent.insertBefore(mark, node); parent.insertBefore(after, node); parent.removeChild(node);
    highlightInNode(after, qLow, q);
    return;
  }
  if (node.nodeType === Node.ELEMENT_NODE) {
    if (node.classList && (node.classList.contains('bubble-time') || node.classList.contains('quoted-block'))) return;
    Array.from(node.childNodes).forEach(function(child) { highlightInNode(child, qLow, q); });
  }
}
function activateMsgSearchMatch(idx) {
  if (_msgSearchMatches.length === 0) return;
  _msgSearchMatches.forEach(function(el) { el.className = 'msg-highlight'; });
  const el = _msgSearchMatches[idx];
  if (!el) return;
  el.className = 'msg-highlight-active';
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}
function stepMsgSearch(dir) {
  if (_msgSearchMatches.length === 0) return;
  _msgSearchIdx = (_msgSearchIdx + dir + _msgSearchMatches.length) % _msgSearchMatches.length;
  activateMsgSearchMatch(_msgSearchIdx);
  updateMsgSearchCount();
}

function t(key) { const v = LANG[lang][key]; return (typeof v === 'function' || v === undefined) ? (LANG.de[key] || key) : v; }
function tf(key, ...args) { const v = LANG[lang][key]; return typeof v === 'function' ? v(...args) : (LANG.de[key] ? LANG.de[key](...args) : key); }
function locale() { return lang === 'de' ? 'de-DE' : 'en-GB'; }
function applyLang() {
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll('[data-i18n-pl]').forEach(el => { el.placeholder = t(el.dataset.i18nPl); });
  document.querySelectorAll('[data-i18n-title]').forEach(el => { el.title = t(el.dataset.i18nTitle); });
  const lb = document.getElementById('lang-btn');
  if (lb) lb.innerHTML = '${_SVG.globe} ' + (lang === 'de' ? 'DE' : 'EN');
  const fmb = document.getElementById('fetch-media-btn');
  if (fmb && !fmb.disabled) fmb.innerHTML = '${_SVG.download}';
  const ptb = document.getElementById('photo-toggle-btn');
  if (ptb) ptb.title = document.getElementById('photo-toggle-btn').classList.contains('active') ? t('photosOn') : t('photosOff');
}
function switchLang() {
  lang = lang === 'de' ? 'en' : 'de';
  localStorage.setItem('signal_lang', lang);
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
  localStorage.setItem('signal_theme', nowDark ? 'light' : 'dark');
  applyTheme();
}
(function() {
  var saved = localStorage.getItem('signal_theme');
  if (saved) { document.documentElement.classList.remove('dark', 'light'); document.documentElement.classList.add(saved); }
  applyTheme();
})();

const BASE = location.pathname.replace(/\\/$/, '');
let currentStatus = '';
let selectedChatId = null;
let allChats = [];
let currentFilter = 'all';
let _lastMsgFingerprint = {};
let lastSeenTime = JSON.parse(localStorage.getItem('signal_last_seen') || '{}');
let showPhotos = ${DOWNLOAD_MEDIA} && localStorage.getItem('signal_show_photos') !== 'false';

function api(path) { return BASE + path; }

function showSpinner(msg) {
  document.getElementById('spinner-overlay').style.display = 'flex';
  document.getElementById('spinner-text').textContent = msg || t('spinnerConnect');
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
        el.textContent = tf('qrError', d.error);
      } else {
        el.textContent = t('qrLoadingLong');
      }
      if (uriEl) uriEl.textContent = d.uri ? 'URI: ' + d.uri.substring(0, 40) + '…' : '';
    }).catch(() => {});
  if (!qrInterval) qrInterval = setInterval(loadQR, 5000);
}

function refreshQR() {
  const el = document.getElementById('qr-img');
  el.textContent = t('qrLoading');
  document.getElementById('qr-uri').textContent = '';
  // Tell server to fetch a fresh QR code
  fetch(api('/api/qr/refresh'), { method: 'POST' }).catch(() => {});
  setTimeout(loadQR, 1000);
}

let _offlineFails = 0;
function showOfflineBanner() { document.getElementById('offline-banner').style.display = 'flex'; }
function hideOfflineBanner() { document.getElementById('offline-banner').style.display = 'none'; }

async function refresh() {
  try {
    const d = await fetch(api('/api/status')).then(r => r.json());
    _offlineFails = 0;
    if (navigator.onLine !== false) hideOfflineBanner();
    if (d.status === currentStatus) return;
    currentStatus = d.status;

    if (d.status === 'starting') {
      showSpinner(t('spinnerStart'));
    } else if (d.status === 'not-linked') {
      if (qrInterval) { clearInterval(qrInterval); qrInterval = null; }
      showQR();
    } else if (d.status === 'linked') {
      if (qrInterval) { clearInterval(qrInterval); qrInterval = null; }
      showMain(d.phone);
      loadChats();
    } else if (d.status === 'error') {
      showSpinner(tf('spinnerError', d.error));
    }
  } catch (e) {
    _offlineFails++;
    if (_offlineFails >= 3) showOfflineBanner();
  }
}

setInterval(refresh, 3000);
if (!navigator.onLine) showOfflineBanner();
refresh();
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') refresh();
});
window.addEventListener('online', () => { _offlineFails = 0; refresh(); });
window.addEventListener('offline', () => showOfflineBanner());

// Chat list
const COLORS = ['#e53935','#8e24aa','#1e88e5','#00897b','#43a047','#fb8c00','#d81b60','#6d4c41'];
function avatarColor(s) {
  let h = 0; for (const c of String(s)) h = (h * 31 + c.charCodeAt(0)) & 0xffff;
  return COLORS[h % COLORS.length];
}
function avatarInitial(s) { return (String(s || '?')).charAt(0).toUpperCase(); }

function formatTime(ts) {
  if (!ts) return '';
  const n = Number(ts);
  const d = new Date(n > 1e12 ? n : n * 1000);
  if (!Number.isFinite(d.getTime())) return '';
  const now = new Date();
  if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' });
  return d.toLocaleDateString(locale(), { day: '2-digit', month: '2-digit' });
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
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

function ackMark(ack) {
  if (ack >= 2) return '<span class="msg-ack ack-3">✓✓</span>';
  if (ack === 1) return '<span class="msg-ack ack-2">✓✓</span>';
  if (ack === 0) return '<span class="msg-ack ack-1">✓</span>';
  return '';
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

function setFilter(f) {
  currentFilter = f;
  document.querySelectorAll('.filter-tab').forEach(btn => btn.classList.toggle('active', btn.dataset.filter === f));
  renderChats(allChats);
}

function chatAvatar(c) {
  if (c.isGroup) return \`<div class="avatar type-group" style="background:#3a76f0">👥</div>\`;
  return \`<div class="avatar" style="background:\${avatarColor(c.name || c.id)}">\${avatarInitial(c.name || c.id)}</div>\`;
}

function renderChats(chats) {
  const q = document.getElementById('search-input').value.toLowerCase();
  let filtered = q ? chats.filter(c => (c.name||'').toLowerCase().includes(q) || (c.phone||'').includes(q)) : chats;
  if (currentFilter === 'group') filtered = filtered.filter(c => c.isGroup);
  if (currentFilter === 'private') filtered = filtered.filter(c => !c.isGroup);
  const el = document.getElementById('chat-list');
  el.innerHTML = filtered.map(c => {
    if (c.id === selectedChatId) lastSeenTime[c.id] = Math.max(lastSeenTime[c.id] || 0, c.lastTime || 0);
    const hasUnread = c.id !== selectedChatId && !c.lastFromMe && (c.lastTime || 0) > (lastSeenTime[c.id] || 0);
    return \`
    <div class="chat-item\${c.id === selectedChatId ? ' active' : ''}" data-chatid="\${escHtml(c.id)}" onclick="openChatById(this.dataset.chatid)">
      \${chatAvatar(c)}
      <div class="chat-info">
        <div class="chat-name">\${escHtml(c.name || c.id)}</div>
        <div class="chat-preview">\${escHtml(c.lastMsg || '')}</div>
      </div>
      <div class="chat-meta">
        <div class="chat-time">\${formatTime(c.lastTime)}</div>
        \${hasUnread ? '<div class="unread-dot"></div>' : ''}
      </div>
    </div>\`;
  }).join('');
}

function exportChat() {
  if (!selectedChatId) return;
  window.location.href = api('/api/export/' + encodeURIComponent(selectedChatId) + '?lang=' + lang);
}

function filterChats() {
  renderChats(allChats);
}

function openChatById(chatId) {
  const chat = allChats.find(c => c.id === chatId);
  if (chat) openChat(chat);
}

function openChat(chat) {
  closeMsgSearch();
  selectedChatId = chat.id;
  lastSeenTime[chat.id] = chat.lastTime || Date.now();
  localStorage.setItem('signal_last_seen', JSON.stringify(lastSeenTime));
  document.body.classList.add('chat-open');
  clearAttach();
  document.getElementById('ch-name').textContent = chat.name || chat.id;
  document.getElementById('ch-stats').textContent = '';
  const ph = chat.phone || '';
  document.getElementById('ch-phone').textContent = /^\\+?\\d{7,15}$/.test(ph) ? ph : '';
  const av = document.getElementById('ch-avatar');
  av.onclick = null;
  if (chat.isGroup) {
    av.textContent = '👥';
    av.style.background = '#3a76f0';
    av.style.fontSize = '18px';
  } else {
    av.textContent = avatarInitial(chat.name || chat.id);
    av.style.background = avatarColor(chat.name || chat.id);
    av.style.fontSize = '14px';
  }
  renderChats(allChats);
  _lastMsgFingerprint[chat.id] = '';
  loadMessages(chat.id);
}

function closeChat() {
  closeMsgSearch();
  document.body.classList.remove('chat-open');
  selectedChatId = null;
  clearAttach();
}

function msgFingerprint(msgs) {
  if (!msgs || !msgs.length) return '';
  const last = msgs[msgs.length - 1];
  const videoKey = msgs.filter(m => m.type === 'video').map(m => m.id + ':' + (m.mediaFile || '0')).join('|');
  return msgs.length + ':' + last.id + ':' + (last.mediaFile || '') + ':' + videoKey;
}

async function loadMessages(chatId) {
  if (!chatId) return;
  try {
    const msgs = await fetch(api('/api/messages/' + encodeURIComponent(chatId))).then(r => r.json());
    const fp = msgFingerprint(msgs);
    if (_lastMsgFingerprint[chatId] === fp) return;
    _lastMsgFingerprint[chatId] = fp;
    renderMessages(msgs);
    updateChatStats(chatId);
  } catch (e) {}
}

async function updateChatStats(chatId) {
  if (chatId !== selectedChatId) return;
  try {
    const s = await fetch(api('/api/stats?chat=' + encodeURIComponent(chatId))).then(r => r.json());
    const sinceStr = s.first ? new Date(s.first).toLocaleDateString(locale()) : '';
    const photoStr = s.photos ? '  📷 ' + s.photos : '';
    document.getElementById('ch-stats').textContent =
      s.total + ' ' + t('statsMsg') + '  ↑ ' + s.sent + '  ↓ ' + s.received + photoStr + (sinceStr ? '  ' + t('statsSince') + ' ' + sinceStr : '');
  } catch(e) {}
}

function renderMessages(msgs) {
  const el = document.getElementById('messages');
  if (!msgs.length) { el.innerHTML = '<div id="no-chat">' + t('noMessages') + '</div>'; return; }
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  let lastDate = '';
  el.innerHTML = msgs.map(m => {
    const tsNum = Number(m.timestamp);
    const tsMs = tsNum > 1e12 ? tsNum : tsNum * 1000;
    const d = new Date(Number.isFinite(tsMs) && tsMs > 0 ? tsMs : Date.now());
    const dateStr = d.toLocaleDateString(locale(), { day: '2-digit', month: '2-digit', year: 'numeric' });
    let sep = '';
    if (dateStr !== lastDate) { sep = \`<div class="day-sep"><span>\${dateStr}</span></div>\`; lastDate = dateStr; }
    const time = d.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' });
    const ack = m.fromMe ? ackMark(m.ack ?? -1) : '';
    let content;
    if (m.type === 'voice' && m.mediaFile) {
      content = \`<audio controls style="min-width:220px;max-width:280px;width:100%" src="\${api('/api/media/'+encodeURIComponent(m.mediaFile))}"></audio>\`;
      if (m.body) content += \`<div>\${formatText(m.body)}</div>\`;
    } else if (m.type === 'voice') {
      content = '<span class="photo-placeholder">🎵 Sprachnachricht</span>';
    } else if (m.type === 'video') {
      if (m.mediaFile) {
        content = \`<video controls style="max-width:280px;max-height:360px;display:block;border-radius:8px" src="\${api('/api/media/'+encodeURIComponent(m.mediaFile))}"></video>\`;
      } else {
        const sz = m.videoSize || 0;
        const mb = sz ? ' · ' + (sz/1024/1024).toFixed(1) + ' MB' : '';
        content = \`<span class="photo-placeholder" data-msgid="\${escHtml(m.id)}" onclick="fetchVideo(this)" style="cursor:pointer;opacity:0.85;user-select:none;text-decoration:underline">⬇ Video herunterladen\${mb}</span>\`;
      }
      if (m.body) content += \`<div>\${formatText(m.body)}</div>\`;
    } else if (m.mediaFile) {
      content = showPhotos
        ? \`<img class="msg-img" src="\${api('/api/media/'+encodeURIComponent(m.mediaFile))}" onclick="openImg(this.src)" alt="Foto">\`
        : '<span class="photo-placeholder">📷 Foto</span>';
      if (m.body) content += \`<div>\${formatText(m.body)}</div>\`;
    } else if (m.type === 'photo' && (m.attIds && m.attIds.length > 0)) {
      content = '<span class="photo-placeholder">📷 Foto</span>';
      if (m.body) content += \`<div>\${formatText(m.body)}</div>\`;
    } else if (m.type === 'document' && m.filename) {
      content = \`<div class="bubble-doc"><span class="doc-icon">${_SVG.doc}</span><span class="doc-name">\${escHtml(m.filename)}</span></div>\`;
      if (m.body) content += \`<div style="margin-top:4px;font-size:13px">\${formatText(m.body)}</div>\`;
    } else {
      content = formatText(m.body || '');
    }
    const quotedHtml = m.quotedMsg ? \`<div class="quoted-block"><div class="quoted-sender">\${escHtml(m.quotedMsg.contact||'')}</div><div class="quoted-text">\${escHtml(m.quotedMsg.body||'')}</div></div>\` : '';
    const chatForReply = allChats.find(c => c.id === selectedChatId);
    const replyContact = m.fromMe ? 'Ich' : (chatForReply?.name || selectedChatId || '');
    const replyPreview = escHtml((m.body || (m.type==='voice'?'🎵 Sprachnachricht':m.type==='video'?'📹 Video':m.type==='photo'?'📷 Foto':'')).slice(0,60));
    return sep + \`<div class="bubble-row \${m.fromMe ? 'out' : 'in'}" data-msgid="\${escHtml(m.id)}" data-chatid="\${escHtml(selectedChatId)}"><div class="bubble \${m.fromMe ? 'out' : 'in'}">\${quotedHtml}\${content}<div class="bubble-time">\${time}\${ack}</div></div><button class="del-btn" title="\${t('btnDelete')}">${_SVG.x}</button><button class="fwd-btn" data-msgid="\${escHtml(m.id)}" title="\${t('ttForward')}">${_SVG.fwd}</button><button class="reply-btn" data-msgid="\${escHtml(m.id)}" data-contact="\${escHtml(replyContact)}" data-preview="\${replyPreview}" data-from="\${escHtml(m.from||'')}" data-ts="\${m.timestamp}" title="\${t('ttReply')}">${_SVG.reply}</button></div>\`;
  }).join('');
  if (atBottom) el.scrollTop = el.scrollHeight;
}

let _attachFile = null;
let _replyMsgId = null, _replyFrom = null, _replyTs = null, _replyBody = null;

function setReply(msgId, contact, preview, from, ts) {
  _replyMsgId = msgId; _replyFrom = from; _replyTs = ts; _replyBody = preview;
  document.getElementById('reply-bar-sender').textContent = contact;
  document.getElementById('reply-bar-text').textContent = preview;
  document.getElementById('reply-bar').classList.add('active');
  document.getElementById('msg-input').focus();
}
function clearReply() {
  _replyMsgId = null; _replyFrom = null; _replyTs = null; _replyBody = null;
  document.getElementById('reply-bar').classList.remove('active');
}

async function fetchVideo(el) {
  const msgId = el.dataset.msgid;
  if (!msgId) return;
  el.textContent = '⏳';
  el.style.cursor = 'default';
  el.onclick = null;
  try {
    const r = await fetch(api('/api/fetch-video'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ msgId })
    }).then(r => r.json());
    if (r.mediaFile) {
      _lastMsgFingerprint[selectedChatId] = '';
      await loadMessages(selectedChatId);
    } else {
      el.textContent = '❌ ' + (r.error || 'Fehler');
    }
  } catch(e) { el.textContent = '❌ Fehler'; }
}

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
  renderFwdList(q ? allChats.filter(c => (c.name||'').toLowerCase().includes(q)) : allChats);
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
    await fetch(api('/api/forward'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ msgId, to: chatId }) });
    if (chatId === selectedChatId) await loadMessages(selectedChatId);
    await loadChats();
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
      fetch(api('/api/poll'), { method: 'POST' });
      await loadMessages(selectedChatId);
      await loadChats();
    } catch (e) { alert(tf('errSend', e.message)); }
    return;
  }
  if (!text) return;
  const replyId = _replyMsgId, replyFrom = _replyFrom, replyTs = _replyTs, replyBody = _replyBody;
  clearReply();
  inp.value = '';
  inp.style.height = '';
  try {
    const endpoint = replyId ? api('/api/reply') : api('/api/send');
    const payload = replyId
      ? { to: selectedChatId, message: text, quoteTimestamp: Number(replyTs), quoteAuthor: replyFrom, quoteBody: replyBody }
      : { to: selectedChatId, message: text };
    await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    lastSeenTime[selectedChatId] = Date.now();
    localStorage.setItem('signal_last_seen', JSON.stringify(lastSeenTime));
    fetch(api('/api/poll'), { method: 'POST' });
    await loadMessages(selectedChatId);
    await loadChats();
  } catch (e) { alert(tf('errSend', e.message)); }
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
  showSpinner(t('spinnerLogout'));
  await fetch(api('/api/logout'), { method: 'POST' }).catch(() => {});
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
      el.title = locale() === 'de'
        ? \`Gesamt /config: \${d.mb} MB\nMedienordner: \${d.mediaMb} MB von \${autoAt} MB (\${d.mediaPct}%)\nAuto-Delete startet bei \${autoAt} MB → löscht auf \${autoTo} MB\`
        : \`Total /config: \${d.mb} MB\nMedia folder: \${d.mediaMb} MB of \${autoAt} MB (\${d.mediaPct}%)\nAuto-delete starts at \${autoAt} MB → cleans to \${autoTo} MB\`;
    }
  } catch(e) {}
}
loadStorage();
setInterval(loadStorage, 60000);

async function cleanupMedia() {
  if (!confirm(t('cleanupConfirm'))) return;
  try {
    const d = await fetch(api('/api/cleanup-media'), { method: 'POST' }).then(r => r.json());
    alert(tf('cleanupSuccess', d.deleted, d.freedMb));
    loadStorage();
  } catch(e) { alert(tf('cleanupError', e.message)); }
}

async function fetchMedia() {
  const btn = document.getElementById('fetch-media-btn');
  if (!btn || !selectedChatId) return;
  btn.disabled = true;
  btn.textContent = t('fetchMediaLoading');
  try {
    const d = await fetch(api('/api/fetch-media/' + encodeURIComponent(selectedChatId)), { method: 'POST' }).then(r => r.json());
    if (!d.total) {
      btn.textContent = t('fetchMediaDone');
      setTimeout(() => { btn.disabled = false; btn.innerHTML = '${_SVG.download}'; }, 2500);
      return;
    }
    btn.textContent = tf('fetchMediaCount', d.total);
    let polls = 0;
    const iv = setInterval(async () => {
      await loadMessages(selectedChatId);
      polls++;
      if (polls >= 20) { clearInterval(iv); btn.disabled = false; btn.innerHTML = '${_SVG.download}'; }
    }, 2000);
  } catch(e) { btn.disabled = false; btn.innerHTML = '${_SVG.download}'; }
}

function togglePhotos() {
  showPhotos = !showPhotos;
  localStorage.setItem('signal_show_photos', showPhotos ? 'true' : 'false');
  const btn = document.getElementById('photo-toggle-btn');
  if (btn) { btn.innerHTML = showPhotos ? '${_SVG.imageOn}' : '${_SVG.imageOff}'; btn.title = showPhotos ? t('photosOn') : t('photosOff'); btn.classList.toggle('active', showPhotos); }
  if (selectedChatId) loadMessages(selectedChatId);
}

function openImg(src) {
  const ov = document.createElement('div');
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:999;display:flex;align-items:center;justify-content:center;cursor:zoom-out;';
  const img = document.createElement('img');
  img.src = src;
  img.style.cssText = 'max-width:90%;max-height:90%;border-radius:8px;object-fit:contain;';
  ov.appendChild(img);
  ov.onclick = () => document.body.removeChild(ov);
  document.body.appendChild(ov);
}

async function deleteMsg(chatId, msgId) {
  try {
    await fetch(api('/api/messages/'+encodeURIComponent(chatId)+'/'+encodeURIComponent(msgId)), {method:'DELETE'});
    _lastMsgFingerprint[chatId] = '';
    await loadMessages(chatId);
  } catch(e) {}
}
document.getElementById('messages').addEventListener('click', e => {
  const del = e.target.closest('.del-btn');
  if (del) { const row = del.closest('.bubble-row'); if (row) deleteMsg(row.dataset.chatid, row.dataset.msgid); return; }
  const fwd = e.target.closest('.fwd-btn');
  if (fwd) { openFwdModal(fwd.dataset.msgid); return; }
  const rpl = e.target.closest('.reply-btn');
  if (rpl) { setReply(rpl.dataset.msgid, rpl.dataset.contact, rpl.dataset.preview, rpl.dataset.from, rpl.dataset.ts); return; }
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

applyLang();
</script>
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
<div id="offline-banner">
  <div class="ob-icon">📡</div>
  <div class="ob-title" data-i18n="offlineTitle">Verbindung unterbrochen</div>
  <div class="ob-sub" data-i18n="offlineSub">Stelle Verbindung wieder her…</div>
  <button class="ob-reload" onclick="window.location.reload()" data-i18n="offlineReload">Neu laden</button>
</div>
  <style>
    #sig-console{display:none;position:fixed;bottom:80px;right:20px;width:560px;height:340px;background:#0d1117;border:1px solid #30363d;border-radius:8px;z-index:9999;flex-direction:column;font-family:monospace;font-size:12px;box-shadow:0 8px 32px rgba(0,0,0,0.6);resize:both;overflow:hidden;min-width:320px;min-height:180px;}
    #sig-console.open{display:flex;}
    #sig-console-header{display:flex;align-items:center;justify-content:space-between;padding:5px 10px;background:#161b22;border-bottom:1px solid #30363d;flex-shrink:0;cursor:move;user-select:none;border-radius:7px 7px 0 0;}
    #sig-console-title{color:#8b949e;font-size:11px;font-weight:600;letter-spacing:.05em;}
    #sig-console-close{background:none;border:none;color:#8b949e;cursor:pointer;font-size:14px;padding:2px 6px;line-height:1;}
    #sig-console-close:hover{color:#f85149;}
    #sig-console-body{flex:1;overflow-y:auto;padding:6px 10px;line-height:1.6;}
    #sig-console-body::-webkit-scrollbar{width:5px;}#sig-console-body::-webkit-scrollbar-thumb{background:#30363d;border-radius:3px;}
    .sgc-info{color:#3fb950;}.sgc-warn{color:#d29922;}.sgc-error{color:#f85149;}.sgc-debug{color:#6e7681;}
    @media(max-width:767px){#sig-console{display:none!important;}}
  </style>
  <div id="sig-console">
    <div id="sig-console-header">
      <span id="sig-console-title">⬛ CONSOLE — Signal · signal-cli</span>
      <button id="sig-console-close" onclick="sigConsoleToggle()">✕</button>
    </div>
    <div id="sig-console-body"></div>
  </div>
  <script>
    (function(){
      var _open=false,_lastTs=0,_timer=null;
      var panel=document.getElementById('sig-console');
      var header=document.getElementById('sig-console-header');
      var body=document.getElementById('sig-console-body');
      var _dx=0,_dy=0,_drag=false;
      header.addEventListener('mousedown',function(e){
        if(e.target.id==='sig-console-close')return;
        _drag=true;_dx=e.clientX-panel.offsetLeft;_dy=e.clientY-panel.offsetTop;e.preventDefault();
      });
      document.addEventListener('mousemove',function(e){
        if(!_drag)return;
        panel.style.left=Math.max(0,Math.min(e.clientX-_dx,window.innerWidth-panel.offsetWidth))+'px';
        panel.style.top=Math.max(0,Math.min(e.clientY-_dy,window.innerHeight-panel.offsetHeight))+'px';
        panel.style.right='auto';panel.style.bottom='auto';
      });
      document.addEventListener('mouseup',function(){_drag=false;});
      function sigConsoleToggle(){
        if(window.innerWidth<768)return;
        _open=!_open;panel.classList.toggle('open',_open);
        if(_open){_poll();_timer=setInterval(_poll,2000);}
        else{clearInterval(_timer);_timer=null;}
      }
      window.sigConsoleToggle=sigConsoleToggle;
      function _cls(l){return l==='WARN'?'sgc-warn':l==='ERROR'?'sgc-error':l==='DEBUG'?'sgc-debug':'sgc-info';}
      async function _poll(){
        try{
          var entries=await fetch(api('/api/logs')+'?since='+_lastTs).then(function(r){return r.json();});
          if(!entries.length)return;
          var atBottom=body.scrollHeight-body.scrollTop-body.clientHeight<40;
          entries.forEach(function(e){
            _lastTs=Math.max(_lastTs,e.ts);
            var line=document.createElement('div');line.className=_cls(e.level);line.textContent=e.msg;body.appendChild(line);
          });
          if(atBottom)body.scrollTop=body.scrollHeight;
          if(body.children.length>600)for(var i=0;i<100;i++)body.removeChild(body.firstChild);
        }catch(e){}
      }
    })();
  </script>
</body>
</html>`;
}

process.on('unhandledRejection', (reason) => {
  console.error('[ERROR] Unhandled rejection:', reason?.message || reason);
});

async function init() {
  console.log('[INFO] Signal UI starting...');
  try { fs.mkdirSync(MEDIA_DIR, { recursive: true }); } catch (e) {}
  loadFromDisk();
  try {
    let best = null;
    for (const [chatId, msgs] of messagesByChatId.entries()) {
      for (const m of msgs) {
        if (!m.fromMe && (!best || m.timestamp > best.timestamp)) {
          const chat = chatMap.get(chatId);
          best = {
            timestamp: m.timestamp,
            iso: new Date(m.timestamp).toISOString(),
            chatId,
            chatName: chat?.name || chatId,
            contact: chat?.name || chatId,
            preview: m.body || (m.type === 'photo' ? '📷 Foto' : '[Medien]'),
          };
        }
      }
    }
    if (best) lastReceivedMsg = best;
  } catch (e) { console.error('[ERROR] lastReceivedMsg init:', e.message); }
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
