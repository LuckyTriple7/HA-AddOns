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
const express = require('express');
const fetch = require('node-fetch');
const QRCode = require('qrcode');
const fs = require('fs');
const multer = require('multer');
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 64 * 1024 * 1024 } });

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3000;
const SIGNAL_API = process.env.SIGNAL_API_URL || 'http://localhost:8080';
const WEBHOOK_INCOMING = process.env.WEBHOOK_INCOMING || '';
let PHONE_NUMBER = process.env.PHONE_NUMBER || '';
const DARK_MODE = process.env.DARK_MODE === 'true';
const DEBUG = process.env.DEBUG_MODE === 'true';
const DOWNLOAD_MEDIA = process.env.DOWNLOAD_MEDIA === 'true';
const HA_NOTIFY = process.env.HA_NOTIFICATIONS === 'true';
const HA_PRIVACY = process.env.HA_NOTIFICATIONS_PRIVACY === 'true';
const HA_TOKEN = process.env.HA_TOKEN || '';
const MEDIA_DIR = '/config/media/';
function dbg(...args) { if (DEBUG) console.log('[DEBUG]', ...args); }
console.log('[INFO] ── Configuration ──────────────────────────────────');
console.log(`[INFO]   phone_number           = ${PHONE_NUMBER ? 'set' : 'not set'}`);
console.log(`[INFO]   signal_api_url         = ${SIGNAL_API}`);
console.log(`[INFO]   dark_mode              = ${DARK_MODE}`);
console.log(`[INFO]   download_media         = ${DOWNLOAD_MEDIA}`);
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
  dbg(`processEnvelope: chatId=${chatId} isOwn=${isOwn} hasDataMessage=${!!dm} hasText=${hasText} hasAttachments=${hasAttachments} body="${(dm?.message||'').slice(0,60)}"`);
  if (!dm || !chatId || (!hasText && !hasAttachments)) { dbg(`processEnvelope: skipping — no dataMessage, chatId, or content`); return; }

  const msgId = `${isOwn ? PHONE_NUMBER : chatId}_${dm.timestamp}`;
  if (seenMsgIds.has(msgId)) { dbg(`processEnvelope: duplicate skipped ${msgId}`); return; }
  seenMsgIds.add(msgId);
  const previewText = dm.message || (hasAttachments ? '📷 Foto' : '');

  const attIds = hasAttachments
    ? dm.attachments.filter(a => a.id).map(a => ({ id: a.id, ct: a.contentType || 'image/jpeg' }))
    : undefined;
  const msgFrom = isOwn ? PHONE_NUMBER : chatId;
  const msg = { id: msgId, from: msgFrom, body: dm.message || '', timestamp: dm.timestamp, fromMe: isOwn, attIds };

  if (DOWNLOAD_MEDIA && hasAttachments) {
    for (const att of dm.attachments) {
      if (att.id) downloadAttachment(att.id, att.contentType || 'image/jpeg', msgId);
    }
  }

  if (!messagesByChatId.has(chatId)) messagesByChatId.set(chatId, []);
  messagesByChatId.get(chatId).push(msg);

  if (!chatMap.has(chatId)) {
    chatMap.set(chatId, { id: chatId, name: senderName, phone: chatId, lastMsg: previewText, lastTime: dm.timestamp });
  } else {
    const chat = chatMap.get(chatId);
    chat.lastMsg = previewText;
    chat.lastTime = dm.timestamp;
    if (senderName && senderName !== chatId) chat.name = senderName;
  }

  scheduleSave();

  dbg(`processEnvelope: stored msgId=${msgId} fromMe=${isOwn} chatId=${chatId}`);

  if (!isOwn) {
    lastReceivedMsg = {
      timestamp: dm.timestamp,
      iso: new Date(dm.timestamp).toISOString(),
      chatId,
      chatName: chatMap.get(chatId)?.name || senderName,
      contact: senderName,
      preview: previewText,
    };
    sendHANotification(senderName, dm.message || previewText);
  }

  if (WEBHOOK_INCOMING && !isOwn) {
    dbg(`Firing incoming webhook: ${WEBHOOK_INCOMING}`);
    fetch(WEBHOOK_INCOMING, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from: chatId, name: senderName, message: dm.message || previewText, timestamp: dm.timestamp }),
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

async function downloadAttachment(attId, contentType, msgId) {
  try {
    const ext = contentType.includes('png') ? 'png' : contentType.includes('gif') ? 'gif' : contentType.includes('webp') ? 'webp' : 'jpg';
    const filename = `${msgId.replace(/[^a-zA-Z0-9_-]/g, '_')}.${ext}`;
    const filepath = MEDIA_DIR + filename;
    if (fs.existsSync(filepath)) { updateMsgMedia(msgId, filename); scheduleSave(); return; }
    dbg(`Downloading attachment ${attId}...`);
    const r = await fetch(`${SIGNAL_API}/v1/attachments/${encodeURIComponent(attId)}`, { timeout: 30000 });
    if (!r.ok) { console.warn(`[WARN] Attachment download failed: HTTP ${r.status}`); return; }
    const buf = await r.buffer();
    fs.writeFileSync(filepath, buf);
    dbg(`Attachment saved: ${filename} (${buf.length} bytes)`);
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
  console.log(`[INFO] HA notification: Signal${HA_PRIVACY ? '' : `: ${senderName}`}`);
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
      preview: last.body || (last.type === 'photo' ? '📷 Foto' : '[Medien]'),
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
    const tsNum = Number(m.timestamp);
    const tsMs = tsNum > 1e12 ? tsNum : tsNum * 1000;
    const d = new Date(tsMs);
    const dateStr = d.toLocaleDateString('de-DE', { weekday:'long', day:'2-digit', month:'long', year:'numeric' });
    const time = d.toLocaleTimeString('de-DE', { hour:'2-digit', minute:'2-digit' });
    let sep = '';
    if (dateStr !== lastDate) { sep = `<div class="day-sep">${escH(dateStr)}</div>`; lastDate = dateStr; }
    let content = '';
    if (m.mediaFile) {
      const fp = MEDIA_DIR + m.mediaFile;
      if (fs.existsSync(fp)) {
        const ext = m.mediaFile.split('.').pop().toLowerCase();
        const mime = ext==='png'?'image/png':ext==='webp'?'image/webp':ext==='gif'?'image/gif':'image/jpeg';
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
  const html = `<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Chat: ${escH(chatName)}</title><style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#e5ddd5;min-height:100vh;padding:16px}h1{text-align:center;font-size:18px;color:#333;padding:12px 0 4px}.export-info{text-align:center;font-size:12px;color:#888;margin-bottom:16px}.day-sep{text-align:center;margin:12px 0;font-size:12px;color:#666;background:rgba(255,255,255,.6);border-radius:8px;display:inline-block;padding:2px 10px;width:100%}.msg{display:flex;margin:3px 0}.msg.in{justify-content:flex-start}.msg.out{justify-content:flex-end}.bubble{max-width:70%;padding:7px 10px;border-radius:8px;font-size:14px;line-height:1.45;word-break:break-word}.msg.in .bubble{background:#fff;border-bottom-left-radius:2px}.msg.out .bubble{background:#d1e3ff;border-bottom-right-radius:2px}.meta{display:flex;justify-content:space-between;gap:8px;margin-bottom:3px;font-size:12px}.sender{font-weight:600;color:#3a76f0}.msg.out .sender{color:#2960d6}.time{color:#999;flex-shrink:0}@media print{body{background:#fff}.msg.out .bubble{background:#ddeeff}}</style></head><body><h1>${escH(chatName)}</h1><p class="export-info">Exportiert am ${exportDate} &bull; ${msgs.length} Nachrichten</p>${msgsHtml}</body></html>`;
  const fname = `signal_${chatName.replace(/[^a-zA-Z0-9_-]/g,'_').slice(0,40)}_${new Date().toISOString().slice(0,10)}.html`;
  res.setHeader('Content-Type','text/html; charset=utf-8');
  res.setHeader('Content-Disposition',`attachment; filename="${fname}"`);
  res.send(html);
});

app.get('/api/media/:filename', (req, res) => {
  const filename = req.params.filename;
  if (!/^[\w.-]+$/.test(filename)) return res.status(400).send('Invalid filename');
  const filepath = MEDIA_DIR + filename;
  if (!fs.existsSync(filepath)) return res.status(404).send('Not found');
  const ext = filename.split('.').pop().toLowerCase();
  const mime = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', gif: 'image/gif', webp: 'image/webp' };
  res.setHeader('Content-Type', mime[ext] || 'application/octet-stream');
  fs.createReadStream(filepath).pipe(res);
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
        const fp = MEDIA_DIR + f;
        try { freed += fs.statSync(fp).size; fs.unlinkSync(fp); count++; } catch(e) {}
      }
    }
    res.json({ deleted: count, freedMb: (freed / (1024 * 1024)).toFixed(1) });
  } catch(e) { res.status(500).json({ error: e.message }); }
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
    dbg(`Sending message to ${to}: "${message.slice(0,60)}${message.length>60?'…':''}"`);
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
      }
      scheduleSave();
    }
    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
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
      if (isImg) {
        const fname = `${signalTs}_${safeName}`;
        fs.writeFileSync(`${MEDIA_DIR}${fname}`, buffer);
        mediaFile = fname;
      }
      const msg = isImg
        ? { id: msgId, from: PHONE_NUMBER, body: caption || '', type: 'photo', timestamp: signalTs, fromMe: true, ack: 0, attIds: [], mediaFile }
        : { id: msgId, from: PHONE_NUMBER, body: caption || '', type: 'document', filename: safeName, timestamp: signalTs, fromMe: true, ack: 0, attIds: [], mediaFile: null };
      if (!messagesByChatId.has(to)) messagesByChatId.set(to, []);
      messagesByChatId.get(to).push(msg);
      if (chatMap.has(to)) {
        chatMap.get(to).lastMsg = caption || (isImg ? '📷 Foto' : safeName);
        chatMap.get(to).lastTime = signalTs;
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
.scroll-btn { background: none; border: 1px solid rgba(255,255,255,0.4); color: #fff; padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 14px; opacity: 0.6; line-height: 1; }
.scroll-btn:hover { opacity: 1; }
#photo-toggle-btn { background: none; border: 1px solid rgba(255,255,255,0.4); color: rgba(255,255,255,0.7); padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 13px; }
#photo-toggle-btn.active { border-color: #fff; color: #fff; background: rgba(255,255,255,0.15); }
#logout-btn, #topbar-back { background: none; border: none; color: rgba(255,255,255,0.6); cursor: pointer; padding: 6px; line-height: 1; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
#logout-btn:hover { color: #f15c5c; }
#topbar-back { display: none; }
#topbar-back:hover { color: rgba(255,255,255,0.9); }
.msg-img { max-width: 250px; max-height: 250px; border-radius: 8px; cursor: zoom-in; display: block; object-fit: cover; margin-top: 4px; }
.photo-placeholder { color: #3a76f8; }
.bubble-doc { display: flex; align-items: center; gap: 10px; padding: 4px 0; }
.bubble-doc .doc-icon { font-size: 28px; flex-shrink: 0; line-height: 1; }
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
#back-btn { display: none; background: none; border: none; color: #fff; font-size: 20px; cursor: pointer; padding: 0 8px 0 0; line-height: 1; }
#ch-name { font-weight: 600; font-size: 16px; }
#ch-phone { font-size: 12px; color: #aaa; }
#ch-stats { font-size: 11px; color: rgba(255,255,255,0.55); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#fetch-media-btn { margin-left: auto; background: none; border: 1px solid rgba(255,255,255,0.3); color: rgba(255,255,255,0.7); padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 12px; flex-shrink: 0; white-space: nowrap; }
#fetch-media-btn:hover { border-color: #fff; color: #fff; }
#fetch-media-btn:disabled { opacity: 0.4; cursor: default; }
#export-btn { ${DOWNLOAD_MEDIA ? '' : 'margin-left: auto;'} background: none; border: 1px solid rgba(255,255,255,0.3); color: rgba(255,255,255,0.7); padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 12px; flex-shrink: 0; white-space: nowrap; }
#export-btn:hover { border-color: #fff; color: #fff; }
#messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 4px; }
#no-chat { flex: 1; display: flex; align-items: center; justify-content: center; color: #999; font-size: 15px; }
.bubble { max-width: 65%; padding: 8px 12px; border-radius: 8px; font-size: 14px; line-height: 1.4; word-break: break-word; }
.bubble.in { background: #fff; border-bottom-left-radius: 2px; }
.bubble.out { background: #d1e3ff; border-bottom-right-radius: 2px; }
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
#emoji-toggle { background: none; border: none; font-size: 20px; cursor: pointer; padding: 6px; border-radius: 50%; flex-shrink: 0; line-height: 1; }
#emoji-toggle:hover { background: rgba(0,0,0,0.08); }
#input-bar #attach-btn { background: none; border: none; font-size: 20px; cursor: pointer; padding: 6px; border-radius: 50%; flex-shrink: 0; line-height: 1; color: #888; }
#input-bar #attach-btn:hover { background: rgba(0,0,0,0.08); }
#attach-bar { display: none; align-items: center; gap: 10px; padding: 6px 16px; font-size: 13px; background: #e8eef4; border-top: 1px solid #d0d8e0; color: #333; }
#attach-bar.visible { display: flex; }
#attach-bar .attach-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#attach-bar .attach-clear { background: none; border: none; cursor: pointer; font-size: 16px; color: #e74c3c; padding: 2px 6px; border-radius: 4px; flex-shrink: 0; }
#file-input { display: none; }
html.dark #input-bar #attach-btn { color: #8696a0; }
html.dark #attach-bar { background: #1a2533; border-color: #2a3942; color: #c1c9d4; }
#msg-input { flex: 1; padding: 10px 14px; border-radius: 20px; border: none; background: #fff; font-size: 14px; outline: none; resize: none; max-height: 120px; overflow-y: auto; font-family: inherit; }
#send-btn { width: 40px; height: 40px; border-radius: 50%; border: none; background: #3a76f8; color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
#send-btn:hover { background: #2960d6; }

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
  <h1>Signal</h1>
  <span class="phone" id="my-phone"></span>
  <span id="storage-info"></span>
  ${DOWNLOAD_MEDIA ? '<button id="photo-toggle-btn" class="active" onclick="togglePhotos()" data-i18n-title="photosOn" title="Fotos AN">📷</button>' : ''}
  ${DOWNLOAD_MEDIA ? '<button class="scroll-btn" onclick="cleanupMedia()" data-i18n-title="cleanupTitle" title="Verwaiste Mediendateien löschen">🗑️</button>' : ''}
  <button class="scroll-btn" onclick="scrollMsgs(\'top\')" data-i18n-title="btnScrollUp" title="Nach oben">↑</button>
  <button class="scroll-btn" onclick="scrollMsgs(\'bottom\')" data-i18n-title="btnScrollDown" title="Nach unten">↓</button>
  <button id="lang-btn" class="scroll-btn" onclick="switchLang()" title="Sprache / Language" style="font-size:14px;padding:0 6px;">🌐 DE</button>
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
      <button id="back-btn" onclick="closeChat()">&#8592;</button>
      <div class="avatar" id="ch-avatar" style="width:36px;height:36px;font-size:14px;background:#3a76f8">?</div>
      <div style="flex:1;overflow:hidden">
        <div id="ch-name" data-i18n="noChatSelected">Kein Chat ausgewählt</div>
        <div id="ch-phone"></div>
        <div id="ch-stats"></div>
      </div>
      ${DOWNLOAD_MEDIA ? '<button id="fetch-media-btn" onclick="fetchMedia()" data-i18n-title="fetchMediaTitle" title="Fehlende Fotos herunterladen">📥</button>' : ''}
      <button id="export-btn" onclick="exportChat()" data-i18n-title="ttExport" title="Chat exportieren">💾</button>
    </div>
    <div id="messages"><div id="no-chat" data-i18n="noChatSelected">Wähle einen Chat aus der Liste</div></div>
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
    spinnerStart: 'Starte Signal…', spinnerConnect: 'Verbinde…', spinnerLogout: 'Abmelden…',
    spinnerError: (e) => 'Fehler: ' + e,
    qrTitle: 'Signal verknüpfen',
    qrInstr: 'Signal öffnen → Einstellungen → Verknüpfte Geräte → Gerät hinzufügen → QR-Code scannen',
    qrLoading: 'Lade QR-Code…', qrLoadingLong: 'Lade QR-Code… (kann bis zu 60s dauern)',
    qrError: (e) => 'Fehler: ' + e, qrRefreshBtn: 'QR-Code neu laden',
    photosOn: 'Fotos AN', photosOff: 'Fotos AUS',
    cleanupTitle: 'Verwaiste Mediendateien löschen',
    btnScrollUp: 'Nach oben', btnScrollDown: 'Nach unten', btnLogout: 'Abmelden',
    logoutConfirmMsg: 'Möchtest du dich wirklich abmelden?', btnYes: 'Ja', btnNo: 'Nein',
    searchPlaceholder: 'Suchen…', noChatSelected: 'Wähle einen Chat aus der Liste',
    noMessages: 'Noch keine Nachrichten',
    btnFetchMedia: '📥', fetchMediaTitle: 'Fehlende Fotos herunterladen',
    fetchMediaLoading: '⏳ Lade…', fetchMediaDone: '✓ Alle geladen',
    fetchMediaCount: (n) => '⏳ ' + n + ' Fotos…',
    msgPlaceholder: 'Nachricht…', btnDelete: 'Löschen', emojiTitle: 'Emoji', attachTitle: 'Datei anhängen', ttExport: 'Chat als HTML exportieren',
    errSend: (e) => 'Fehler: ' + e,
    statsMsg: 'Nachrichten', statsSince: 'seit',
    cleanupConfirm: 'Verwaiste Mediendateien löschen (nicht mehr referenzierte Fotos)?',
    cleanupSuccess: (c, mb) => c + ' Datei(en) gelöscht, ' + mb + ' MB freigegeben.',
    cleanupError: (e) => 'Fehler beim Cleanup: ' + e,
    filterAll: 'Alle', filterPrivate: 'Privat', filterGroups: 'Gruppen',
  },
  en: {
    spinnerStart: 'Starting Signal…', spinnerConnect: 'Connecting…', spinnerLogout: 'Logging out…',
    spinnerError: (e) => 'Error: ' + e,
    qrTitle: 'Link Signal',
    qrInstr: 'Open Signal → Settings → Linked Devices → Link a Device → Scan QR code',
    qrLoading: 'Loading QR code…', qrLoadingLong: 'Loading QR code… (may take up to 60s)',
    qrError: (e) => 'Error: ' + e, qrRefreshBtn: 'Reload QR code',
    photosOn: 'Photos ON', photosOff: 'Photos OFF',
    cleanupTitle: 'Delete orphaned media files',
    btnScrollUp: 'Scroll up', btnScrollDown: 'Scroll down', btnLogout: 'Log out',
    logoutConfirmMsg: 'Do you really want to log out?', btnYes: 'Yes', btnNo: 'No',
    searchPlaceholder: 'Search…', noChatSelected: 'Select a chat from the list',
    noMessages: 'No messages yet',
    btnFetchMedia: '📥', fetchMediaTitle: 'Download missing photos',
    fetchMediaLoading: '⏳ Loading…', fetchMediaDone: '✓ All loaded',
    fetchMediaCount: (n) => '⏳ ' + n + ' photos…',
    msgPlaceholder: 'Message…', btnDelete: 'Delete', emojiTitle: 'Emoji', attachTitle: 'Attach file', ttExport: 'Export chat as HTML',
    errSend: (e) => 'Error: ' + e,
    statsMsg: 'messages', statsSince: 'since',
    cleanupConfirm: 'Delete orphaned media files (photos no longer referenced)?',
    cleanupSuccess: (c, mb) => c + ' file(s) deleted, ' + mb + ' MB freed.',
    cleanupError: (e) => 'Cleanup error: ' + e,
    filterAll: 'All', filterPrivate: 'Private', filterGroups: 'Groups',
  },
};
const _browserLang = (navigator.language || '').toLowerCase().startsWith('de') ? 'de' : 'en';
let lang = localStorage.getItem('signal_lang') || _browserLang;
function t(key) { const v = LANG[lang][key]; return (typeof v === 'function' || v === undefined) ? (LANG.de[key] || key) : v; }
function tf(key, ...args) { const v = LANG[lang][key]; return typeof v === 'function' ? v(...args) : (LANG.de[key] ? LANG.de[key](...args) : key); }
function locale() { return lang === 'de' ? 'de-DE' : 'en-GB'; }
function applyLang() {
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll('[data-i18n-pl]').forEach(el => { el.placeholder = t(el.dataset.i18nPl); });
  document.querySelectorAll('[data-i18n-title]').forEach(el => { el.title = t(el.dataset.i18nTitle); });
  const lb = document.getElementById('lang-btn');
  if (lb) lb.textContent = lang === 'de' ? '🌐 DE' : '🌐 EN';
  const fmb = document.getElementById('fetch-media-btn');
  if (fmb && !fmb.disabled) fmb.textContent = t('btnFetchMedia');
  const ptb = document.getElementById('photo-toggle-btn');
  if (ptb) ptb.title = document.getElementById('photo-toggle-btn').classList.contains('active') ? t('photosOn') : t('photosOff');
}
function switchLang() {
  lang = lang === 'de' ? 'en' : 'de';
  localStorage.setItem('signal_lang', lang);
  applyLang();
}

const BASE = location.pathname.replace(/\\/$/, '');
let currentStatus = '';
let selectedChatId = null;
let allChats = [];
let currentFilter = 'all';
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

async function refresh() {
  try {
    const d = await fetch(api('/api/status')).then(r => r.json());
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
    const hasUnread = c.id !== selectedChatId && (c.lastTime || 0) > (lastSeenTime[c.id] || 0);
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
  window.location.href = api('/api/export/' + encodeURIComponent(selectedChatId));
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
  loadMessages(chat.id);
}

function closeChat() {
  document.body.classList.remove('chat-open');
  selectedChatId = null;
  clearAttach();
}

async function loadMessages(chatId) {
  if (!chatId) return;
  try {
    const msgs = await fetch(api('/api/messages/' + encodeURIComponent(chatId))).then(r => r.json());
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
    if (m.mediaFile) {
      content = (showPhotos || m.fromMe)
        ? \`<img class="msg-img" src="\${api('/api/media/'+encodeURIComponent(m.mediaFile))}" onclick="openImg(this.src)" alt="Foto">\`
        : '<span class="photo-placeholder">📷 Foto</span>';
      if (m.body) content += \`<div>\${formatText(m.body)}</div>\`;
    } else if (m.type === 'photo' || (m.attIds && m.attIds.length > 0)) {
      content = '<span class="photo-placeholder">📷 Foto</span>';
      if (m.body) content += \`<div>\${formatText(m.body)}</div>\`;
    } else if (m.type === 'document' && m.filename) {
      content = \`<div class="bubble-doc"><span class="doc-icon">📄</span><span class="doc-name">\${escHtml(m.filename)}</span></div>\`;
      if (m.body) content += \`<div style="margin-top:4px;font-size:13px">\${formatText(m.body)}</div>\`;
    } else {
      content = formatText(m.body || '');
    }
    return sep + \`<div class="bubble-row \${m.fromMe ? 'out' : 'in'}" data-msgid="\${escHtml(m.id)}" data-chatid="\${escHtml(selectedChatId)}"><div class="bubble \${m.fromMe ? 'out' : 'in'}">\${content}<div class="bubble-time">\${time}\${ack}</div></div><button class="del-btn" title="\${t('btnDelete')}">✕</button></div>\`;
  }).join('');
  if (atBottom) el.scrollTop = el.scrollHeight;
}

let _attachFile = null;

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

function onFileSelected(input) {
  const file = input.files[0];
  if (!file) return;
  _attachFile = file;
  document.getElementById('attach-name').textContent = file.name + ' (' + formatFileSize(file.size) + ')';
  document.getElementById('attach-bar').classList.add('visible');
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
  inp.value = '';
  inp.style.height = '';
  try {
    await fetch(api('/api/send'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to: selectedChatId, message: text }),
    });
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
    if (el) el.textContent = '💾 ' + d.mb + ' MB';
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
      setTimeout(() => { btn.disabled = false; btn.textContent = t('btnFetchMedia'); }, 2500);
      return;
    }
    btn.textContent = tf('fetchMediaCount', d.total);
    let polls = 0;
    const iv = setInterval(async () => {
      await loadMessages(selectedChatId);
      polls++;
      if (polls >= 20) { clearInterval(iv); btn.disabled = false; btn.textContent = t('btnFetchMedia'); }
    }, 2000);
  } catch(e) { btn.disabled = false; btn.textContent = t('btnFetchMedia'); }
}

function togglePhotos() {
  showPhotos = !showPhotos;
  localStorage.setItem('signal_show_photos', showPhotos ? 'true' : 'false');
  const btn = document.getElementById('photo-toggle-btn');
  if (btn) { btn.textContent = showPhotos ? '📷' : '🚫'; btn.title = showPhotos ? t('photosOn') : t('photosOff'); btn.classList.toggle('active', showPhotos); }
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

applyLang();
</script>
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
