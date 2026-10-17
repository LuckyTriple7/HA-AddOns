// Mein Status / Meine Story — identisch in telegram/ und signal/ (Vorbild: WhatsApp-Add-on).
// Was der jeweilige Messenger kann, steht in window.MS_CFG (setzt server.js).
// Text-Storys gibt es bei Telegram und Signal nicht: der Text wird hier im
// Browser auf ein Bild gemalt und als Bild-Story gepostet.
(function () {
  'use strict';
  const CFG = window.MS_CFG || {};
  const PROFILE = CFG.profile || { fields: [], aboutMax: 140 };

  const L = {
    de: {
      open: 'Mein Status', title: 'Meine Story',
      tabText: 'Text', tabMedia: 'Bild / Video', tabTpl: 'Vorlagen', tabProfile: 'Profil', tabPriv: 'Datenschutz',
      textPh: 'Was möchtest du teilen?', background: 'Hintergrund', font: 'Schrift',
      textNote: 'Wird als Bild gepostet – {0} kennt keine reinen Text-Storys.',
      pickFile: 'Bild oder Video wählen', clearMedia: 'Auswahl entfernen', caption: 'Text zum Bild (optional)', captionPh: 'Bildunterschrift…',
      noCaption: '{0} übernimmt bei Storys keinen Text zum Bild.',
      videoTooLong: 'Das Video ist {0} s lang – {1} erlaubt höchstens {2} s.',
      videoNoPreview: 'Video gewählt (keine Vorschau).',
      visibility: 'Sichtbar für', visContacts: 'Meine Kontakte', visAll: 'Alle', visClose: 'Enge Freunde',
      send: 'Story posten', sending: 'Poste …', needText: 'Bitte Text eingeben.', needFile: 'Bitte ein Bild oder Video wählen.',
      sentText: 'Text-Story gepostet.', sentMedia: 'Story gepostet.', error: 'Fehler: {0}',
      tplSaved: 'Gespeicherte Vorlagen', tplEmpty: 'Noch keine Vorlagen.', tplSaveLbl: 'Aktuellen Entwurf als Vorlage speichern',
      tplNamePh: 'Name der Vorlage…', tplSave: 'Vorlage speichern', tplUpdate: 'Vorlage aktualisieren',
      tplHint: 'Die Vorlage übernimmt Text, Farbe, Schrift und – falls gewählt – das Bild aus dem Editor.',
      tplText: 'Text', tplImage: 'Bild', tplVideo: 'Video', tplNameMissing: 'Bitte einen Namen für die Vorlage eingeben.',
      tplSavedOk: 'Vorlage gespeichert.', tplDeleted: 'Vorlage gelöscht.', tplDeleteConfirm: 'Vorlage „{0}“ löschen?',
      tplLoaded: 'Vorlage „{0}“ geladen.', tplFileNote: 'Bild aus Vorlage „{0}“',
      profileLbl: 'Profil', save: 'Speichern', profileSaved: 'Profil gespeichert.',
      firstName: 'Vorname', lastName: 'Nachname', givenName: 'Vorname', familyName: 'Nachname',
      about: 'Info', aboutEmoji: 'Info-Emoji',
      liveTitle: 'Meine laufenden Storys', liveLoading: 'Lade …', liveEmpty: 'Gerade keine laufende Story.',
      liveDelete: 'Story löschen', liveDeleteConfirm: 'Diese Story löschen?', liveDeleted: 'Story gelöscht.',
      liveEdit: 'Text ändern', liveEditPrompt: 'Neuer Text zur Story:', liveEdited: 'Text geändert.',
      liveViews: '{0} Aufrufe', liveUntil: 'bis {0}',
      liveLocalNote: 'Gezeigt werden nur Storys, die über dieses Add-on gepostet wurden. Löschen geht nur in der Signal-App.',
      privTitle: 'Wer darf was sehen', privAll: 'Alle', privContacts: 'Meine Kontakte', privNobody: 'Niemand',
      privExceptions: '+ {0} Ausnahme(n)', privSaved: 'Gespeichert.',
      priv_phone: 'Telefonnummer', priv_lastSeen: 'Zuletzt online', priv_photo: 'Profilbild', priv_about: 'Bio',
      priv_forwards: 'Weitergeleitete Nachrichten', priv_calls: 'Anrufe', priv_invites: 'Gruppen & Kanäle', priv_voice: 'Sprachnachrichten',
      close: 'Schließen', cancel: 'Abbrechen',
    },
    en: {
      open: 'My status', title: 'My story',
      tabText: 'Text', tabMedia: 'Image / video', tabTpl: 'Templates', tabProfile: 'Profile', tabPriv: 'Privacy',
      textPh: 'What would you like to share?', background: 'Background', font: 'Font',
      textNote: 'Posted as an image – {0} has no text-only stories.',
      pickFile: 'Pick an image or video', clearMedia: 'Remove selection', caption: 'Caption (optional)', captionPh: 'Caption…',
      noCaption: '{0} does not take a caption on stories.',
      videoTooLong: 'The video is {0} s long – {1} allows at most {2} s.',
      videoNoPreview: 'Video selected (no preview).',
      visibility: 'Visible to', visContacts: 'My contacts', visAll: 'Everyone', visClose: 'Close friends',
      send: 'Post story', sending: 'Posting …', needText: 'Please enter some text.', needFile: 'Please pick an image or video.',
      sentText: 'Text story posted.', sentMedia: 'Story posted.', error: 'Error: {0}',
      tplSaved: 'Saved templates', tplEmpty: 'No templates yet.', tplSaveLbl: 'Save current draft as template',
      tplNamePh: 'Template name…', tplSave: 'Save template', tplUpdate: 'Update template',
      tplHint: 'The template stores text, colour, font and – if chosen – the image from the editor.',
      tplText: 'Text', tplImage: 'Image', tplVideo: 'Video', tplNameMissing: 'Please enter a template name.',
      tplSavedOk: 'Template saved.', tplDeleted: 'Template deleted.', tplDeleteConfirm: 'Delete template "{0}"?',
      tplLoaded: 'Template "{0}" loaded.', tplFileNote: 'Image from template "{0}"',
      profileLbl: 'Profile', save: 'Save', profileSaved: 'Profile saved.',
      firstName: 'First name', lastName: 'Last name', givenName: 'First name', familyName: 'Last name',
      about: 'About', aboutEmoji: 'About emoji',
      liveTitle: 'My active stories', liveLoading: 'Loading …', liveEmpty: 'No active story right now.',
      liveDelete: 'Delete story', liveDeleteConfirm: 'Delete this story?', liveDeleted: 'Story deleted.',
      liveEdit: 'Edit caption', liveEditPrompt: 'New caption:', liveEdited: 'Caption changed.',
      liveViews: '{0} views', liveUntil: 'until {0}',
      liveLocalNote: 'Only stories posted through this add-on are shown. Deleting only works in the Signal app.',
      privTitle: 'Who can see what', privAll: 'Everyone', privContacts: 'My contacts', privNobody: 'Nobody',
      privExceptions: '+ {0} exception(s)', privSaved: 'Saved.',
      priv_phone: 'Phone number', priv_lastSeen: 'Last seen', priv_photo: 'Profile photo', priv_about: 'Bio',
      priv_forwards: 'Forwarded messages', priv_calls: 'Calls', priv_invites: 'Groups & channels', priv_voice: 'Voice messages',
      close: 'Close', cancel: 'Cancel',
    },
  };
  /* global lang */
  const cur = () => ((typeof lang !== 'undefined' && lang === 'en') ? 'en' : 'de');
  const t = (k) => (L[cur()][k] !== undefined ? L[cur()][k] : (L.de[k] !== undefined ? L.de[k] : k));
  const tf = (k, ...a) => t(k).replace(/\{(\d)\}/g, (_, i) => (a[i] !== undefined ? a[i] : ''));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const NAME = CFG.name || '';

  const COLORS = ['#0a5f55', '#128c7e', '#25d366', '#34b7f1', '#4a6cf7', '#7f5af0', '#b5179e', '#e63946',
                  '#f4772b', '#f2b705', '#6d4c41', '#5c6bc0', '#607d8b', '#263238', '#1b1b1b'];
  const FONTS = [
    (s) => `600 ${s}px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`,
    (s) => `italic 600 ${s}px Georgia, "Times New Roman", serif`,
    (s) => `600 ${s}px ui-monospace, Consolas, "Courier New", monospace`,
    (s) => `${s}px "Segoe Script", "Brush Script MT", "Comic Sans MS", cursive`,
    (s) => `900 ${s}px "Arial Black", system-ui, sans-serif`,
  ];

  const S = { tab: 'text', color: COLORS[0], font: 0, file: null, tplFile: null, videoMeta: null,
              templates: [], editingTpl: null, busy: false, built: false };

  // ── Text auf ein Bild malen ────────────────────────────────────────────────
  function wrapLines(g, text, maxW) {
    const out = [];
    for (const para of String(text).split('\n')) {
      const words = para.split(/\s+/).filter(Boolean);
      if (!words.length) { out.push(''); continue; }
      let line = '';
      for (let w of words) {
        // Ueberlange Woerter zeichenweise umbrechen
        while (g.measureText(w).width > maxW && w.length > 1) {
          let n = w.length - 1;
          while (n > 1 && g.measureText(w.slice(0, n)).width > maxW) n--;
          if (line) { out.push(line); line = ''; }
          out.push(w.slice(0, n));
          w = w.slice(n);
        }
        const test = line ? line + ' ' + w : w;
        if (!line || g.measureText(test).width <= maxW) line = test;
        else { out.push(line); line = w; }
      }
      out.push(line);
    }
    return out;
  }

  function paintText(cv, text, color, font) {
    const w = cv.width, h = cv.height, k = w / 1080;
    const g = cv.getContext('2d');
    g.fillStyle = color; g.fillRect(0, 0, w, h);
    g.fillStyle = '#fff'; g.textAlign = 'center'; g.textBaseline = 'middle';
    let size = 104, lines = [];
    for (; size >= 36; size -= 8) {
      g.font = FONTS[font](Math.round(size * k));
      lines = wrapLines(g, text, w * 0.84);
      if (lines.length * size * 1.3 * k <= h * 0.82) break;
    }
    const lh = size * 1.3 * k;
    let y = h / 2 - (lines.length - 1) * lh / 2;
    for (const ln of lines) { g.fillText(ln, w / 2, y); y += lh; }
  }

  function textToFile(text) {
    const cv = document.createElement('canvas');
    cv.width = 1080; cv.height = 1920;
    paintText(cv, text, S.color, S.font);
    return new Promise((resolve, reject) => cv.toBlob(b => b ? resolve(new File([b], 'status.png', { type: 'image/png' }))
                                                            : reject(new Error('canvas')), 'image/png'));
  }

  // ── Hilfen ─────────────────────────────────────────────────────────────────
  async function apiJson(r) {
    const txt = await r.text();
    let d;
    try { d = JSON.parse(txt); } catch (e) { throw new Error('HTTP ' + r.status); }
    if (!r.ok || d.error) throw new Error(typeof d.error === 'string' ? d.error : 'HTTP ' + r.status);
    return d;
  }
  const postJson = (url, body) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(apiJson);
  const $ = (id) => document.getElementById(id);
  const fmt = (ms) => new Date(ms).toLocaleString(cur() === 'en' ? 'en-GB' : 'de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

  function show(kind, text) {
    const el = $('mys-msg');
    el.className = 'mys-msg show ' + (kind === 'err' ? 'err' : 'ok');
    el.textContent = text;
    if (kind !== 'err') setTimeout(() => { if (el.textContent === text) el.className = 'mys-msg'; }, 4000);
  }

  // ── Aufbau ─────────────────────────────────────────────────────────────────
  const CSS = `
#mys-modal{display:none;position:fixed;inset:0;z-index:600;background:rgba(0,0,0,.55);align-items:center;justify-content:center}
#mys-modal.open{display:flex}
#mys-modal{--bg:#fff;--fg:#1f2328;--mut:#6b7280;--bd:#d0d7de;--in:#f6f8fa;--acc:${CFG.accent || '#2563eb'}}
html.dark #mys-modal{--bg:#17212b;--fg:#e6edf3;--mut:#8b98a5;--bd:#2b3a4a;--in:#0e1621}
.mys-box{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--fg);width:min(560px,96vw);max-height:92vh;border-radius:14px;display:flex;flex-direction:column;overflow:hidden;font-size:14px}
.mys-head{display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid var(--bd)}
.mys-head h3{flex:1;font-size:16px;margin:0}
.mys-x{background:none;border:none;color:var(--mut);font-size:18px;cursor:pointer}
.mys-body{padding:12px 16px;overflow-y:auto;display:flex;flex-direction:column;gap:10px}
.mys-tabs{display:flex;gap:4px;flex-wrap:wrap}
.mys-tabs button{background:none;border:1px solid var(--bd);color:var(--mut);border-radius:16px;padding:5px 11px;cursor:pointer;font-size:13px}
.mys-tabs button.active{background:var(--acc);border-color:var(--acc);color:#fff}
.mys-pane{display:none;flex-direction:column;gap:8px}.mys-pane.active{display:flex}
.mys-label{font-size:12px;font-weight:600;color:var(--mut);text-transform:uppercase;letter-spacing:.04em;margin-top:4px}
.mys-hint{font-size:12px;color:var(--mut);line-height:1.4}
.mys-in,.mys-area,.mys-sel{width:100%;box-sizing:border-box;background:var(--in);color:var(--fg);border:1px solid var(--bd);border-radius:8px;padding:8px 10px;font:inherit}
.mys-area{min-height:72px;resize:vertical}
.mys-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.mys-prev{align-self:center;width:180px;height:320px;border-radius:10px;box-shadow:0 1px 6px rgba(0,0,0,.3)}
.mys-colors,.mys-fonts{display:flex;gap:6px;flex-wrap:wrap}
.mys-sw{width:26px;height:26px;border-radius:50%;border:2px solid transparent;cursor:pointer}
.mys-sw.active{border-color:var(--fg)}
.mys-font{min-width:42px;height:32px;border-radius:8px;border:1px solid var(--bd);background:var(--in);color:var(--fg);cursor:pointer;font-size:16px}
.mys-font.active{border-color:var(--acc);box-shadow:0 0 0 1px var(--acc)}
.mys-media{max-width:100%;max-height:260px;border-radius:8px;align-self:center;display:none}
.mys-media.show{display:block}
.mys-btn{border:none;border-radius:8px;padding:8px 14px;cursor:pointer;font:inherit;font-weight:600}
.mys-btn.primary{background:var(--acc);color:#fff}.mys-btn.primary:disabled{opacity:.5;cursor:default}
.mys-btn.ghost{background:none;border:1px solid var(--bd);color:var(--fg)}
.mys-actions{display:flex;gap:8px;align-items:center;padding:10px 16px;border-top:1px solid var(--bd)}
.mys-actions .mys-sel{width:auto;flex:1;min-width:0}
.mys-msg{display:none;border-radius:8px;padding:7px 10px;font-size:13px}
.mys-msg.show{display:block}.mys-msg.ok{background:rgba(46,160,67,.15)}.mys-msg.err{background:rgba(248,81,73,.15)}
.mys-item{display:flex;gap:10px;align-items:center;border:1px solid var(--bd);border-radius:10px;padding:6px 8px;cursor:pointer}
.mys-thumb{width:44px;height:44px;border-radius:8px;flex-shrink:0;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;overflow:hidden;background:var(--in);object-fit:cover}
.mys-thumb img{width:100%;height:100%;object-fit:cover}
.mys-info{flex:1;min-width:0}
.mys-name{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mys-sub{font-size:12px;color:var(--mut);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mys-ico{background:none;border:none;cursor:pointer;font-size:16px;padding:4px;color:var(--mut)}
.mys-priv{display:flex;gap:8px;align-items:center}.mys-priv span{flex:1}.mys-priv .mys-sel{width:auto}
#mys-open{gap:0}
@media (max-width:768px){.mys-box{width:100vw;max-height:100vh;height:100vh;border-radius:0}body.chat-open #mys-open{display:none}}
`;

  function build() {
    if (S.built) return;
    S.built = true;
    const st = document.createElement('style');
    st.textContent = CSS;
    document.head.appendChild(st);

    const tabs = [['text', 'tabText'], ['media', 'tabMedia'], ['tpl', 'tabTpl'], ['profile', 'tabProfile']];
    if (CFG.privacy) tabs.push(['priv', 'tabPriv']);
    const m = document.createElement('div');
    m.id = 'mys-modal';
    m.innerHTML = `
<div class="mys-box">
  <div class="mys-head"><h3 data-mys="title"></h3><button class="mys-x" data-act="close">✕</button></div>
  <div class="mys-body">
    <div id="mys-msg" class="mys-msg"></div>
    <div class="mys-tabs">${tabs.map(([k, l]) => `<button data-tab="${k}" data-mys="${l}"></button>`).join('')}</div>
    <div class="mys-pane" data-pane="text">
      <canvas id="mys-prev" class="mys-prev" width="270" height="480"></canvas>
      <textarea id="mys-text" class="mys-area" maxlength="700" data-mys-pl="textPh"></textarea>
      <div class="mys-hint" id="mys-text-note"></div>
      <div class="mys-label" data-mys="background"></div><div class="mys-colors" id="mys-colors"></div>
      <div class="mys-label" data-mys="font"></div><div class="mys-fonts" id="mys-fonts"></div>
    </div>
    <div class="mys-pane" data-pane="media">
      <input type="file" id="mys-file" accept="image/*${CFG.video ? ',video/*' : ''}" class="mys-in">
      <img id="mys-img" class="mys-media" alt=""><video id="mys-vid" class="mys-media" muted playsinline controls></video>
      <div class="mys-hint" id="mys-media-note"></div>
      <button class="mys-btn ghost" id="mys-clear" style="display:none" data-mys="clearMedia"></button>
      ${CFG.caption ? `<div class="mys-label" data-mys="caption"></div><textarea id="mys-caption" class="mys-area" maxlength="${CFG.captionMax || 700}" data-mys-pl="captionPh"></textarea>`
                    : `<div class="mys-hint" id="mys-nocap"></div>`}
    </div>
    <div class="mys-pane" data-pane="tpl">
      <div class="mys-label" data-mys="tplSaved"></div><div id="mys-tpl-list" class="mys-pane active"></div>
      <div class="mys-label" data-mys="tplSaveLbl"></div>
      <input type="text" id="mys-tpl-name" class="mys-in" maxlength="80" data-mys-pl="tplNamePh">
      <div class="mys-row"><button class="mys-btn ghost" data-act="tpl-save" data-mys="tplSave"></button>
        <button class="mys-btn ghost" id="mys-tpl-update" style="display:none" data-act="tpl-update" data-mys="tplUpdate"></button></div>
      <div class="mys-hint" data-mys="tplHint"></div>
    </div>
    <div class="mys-pane" data-pane="profile">
      ${PROFILE.fields.map(f => `<div class="mys-label" data-mys="${f}"></div><input type="text" class="mys-in" id="mys-p-${f}" maxlength="${f === 'about' ? PROFILE.aboutMax : f === 'aboutEmoji' ? 8 : 64}">`).join('')}
      <div class="mys-row"><button class="mys-btn ghost" data-act="profile-save" data-mys="save"></button></div>
      <div class="mys-label" data-mys="liveTitle"></div>
      <div id="mys-live" class="mys-pane active"></div>
      ${CFG.liveLocal ? '<div class="mys-hint" data-mys="liveLocalNote"></div>' : ''}
    </div>
    ${CFG.privacy ? '<div class="mys-pane" data-pane="priv"><div class="mys-label" data-mys="privTitle"></div><div id="mys-priv" class="mys-pane active"></div></div>' : ''}
  </div>
  <div class="mys-actions">
    ${CFG.storyPrivacy ? `<select id="mys-vis" class="mys-sel" title=""><option value="contacts" data-mys="visContacts"></option><option value="all" data-mys="visAll"></option><option value="close" data-mys="visClose"></option></select>` : '<span style="flex:1"></span>'}
    <button class="mys-btn ghost" data-act="close" data-mys="cancel"></button>
    <button class="mys-btn primary" id="mys-send" data-mys="send"></button>
  </div>
</div>`;
    document.body.appendChild(m);

    m.addEventListener('click', (e) => {
      if (e.target === m) return close();
      const el = e.target.closest('[data-act],[data-tab]');
      if (!el) return;
      if (el.dataset.tab) return setTab(el.dataset.tab);
      const act = el.dataset.act;
      if (act === 'close') close();
      else if (act === 'tpl-save') saveTemplate(false);
      else if (act === 'tpl-update') saveTemplate(true);
      else if (act === 'profile-save') saveProfile();
    });
    $('mys-send').addEventListener('click', send);
    $('mys-text').addEventListener('input', renderPreview);
    $('mys-file').addEventListener('change', filePicked);
    $('mys-clear').addEventListener('click', clearMedia);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && m.classList.contains('open')) close(); });
    buildPickers();
  }

  function applyLang() {
    document.querySelectorAll('[data-mys]').forEach(el => { el.textContent = t(el.dataset.mys); });
    document.querySelectorAll('[data-mys-pl]').forEach(el => { el.placeholder = t(el.dataset.mysPl); });
    const note = $('mys-text-note'); if (note) note.textContent = tf('textNote', NAME);
    const nocap = $('mys-nocap'); if (nocap) nocap.textContent = tf('noCaption', NAME);
    const btn = $('mys-open'); if (btn) btn.title = t('open');
  }

  function buildPickers() {
    const cw = $('mys-colors');
    cw.innerHTML = '';
    for (const c of COLORS) {
      const b = document.createElement('button');
      b.className = 'mys-sw' + (c === S.color ? ' active' : '');
      b.style.background = c;
      b.onclick = () => { S.color = c; buildPickers(); renderPreview(); };
      cw.appendChild(b);
    }
    const free = document.createElement('input');
    free.type = 'color'; free.value = S.color;
    free.oninput = (e) => { S.color = e.target.value; renderPreview(); };
    cw.appendChild(free);
    const fw = $('mys-fonts');
    fw.innerHTML = '';
    FONTS.forEach((f, i) => {
      const b = document.createElement('button');
      b.className = 'mys-font' + (i === S.font ? ' active' : '');
      b.textContent = 'Aa';
      b.style.font = f(16);
      b.onclick = () => { S.font = i; buildPickers(); renderPreview(); };
      fw.appendChild(b);
    });
  }

  function renderPreview() {
    paintText($('mys-prev'), $('mys-text').value || '…', S.color, S.font);
  }

  function setTab(tab) {
    S.tab = tab;
    document.querySelectorAll('#mys-modal [data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    document.querySelectorAll('#mys-modal [data-pane]').forEach(p => p.classList.toggle('active', p.dataset.pane === tab));
    const sending = tab === 'text' || tab === 'media';
    $('mys-send').style.display = sending ? '' : 'none';
    const vis = $('mys-vis'); if (vis) vis.style.visibility = sending ? '' : 'hidden';
    if (tab === 'text') renderPreview();
    if (tab === 'tpl') renderTemplates();
    if (tab === 'profile') { loadProfile(); loadLive(); }
    if (tab === 'priv') loadPrivacy();
  }

  async function open() {
    build();
    applyLang();
    $('mys-msg').className = 'mys-msg';
    $('mys-modal').classList.add('open');
    resetEditor();
    setTab('text');
    loadTemplates();
  }
  function close() { $('mys-modal').classList.remove('open'); }

  function resetEditor() {
    $('mys-text').value = '';
    const cap = $('mys-caption'); if (cap) cap.value = '';
    S.editingTpl = null;
    $('mys-tpl-name').value = '';
    $('mys-tpl-update').style.display = 'none';
    clearMedia();
    renderPreview();
  }

  // ── Medien ─────────────────────────────────────────────────────────────────
  function clearMedia() {
    S.file = null; S.tplFile = null; S.videoMeta = null;
    $('mys-file').value = '';
    $('mys-img').classList.remove('show'); $('mys-img').removeAttribute('src');
    const v = $('mys-vid'); v.classList.remove('show'); v.removeAttribute('src');
    $('mys-media-note').textContent = '';
    $('mys-clear').style.display = 'none';
  }

  function filePicked() {
    const f = $('mys-file').files[0];
    clearMedia();
    if (!f) return;
    S.file = f;
    $('mys-clear').style.display = '';
    const url = URL.createObjectURL(f);
    if (f.type.startsWith('video/')) {
      const v = $('mys-vid');
      v.onloadedmetadata = () => {
        S.videoMeta = { duration: v.duration, w: v.videoWidth, h: v.videoHeight };
        if (CFG.videoMaxSec && v.duration > CFG.videoMaxSec + 0.5) {
          $('mys-media-note').textContent = tf('videoTooLong', Math.round(v.duration), NAME, CFG.videoMaxSec);
        }
      };
      v.src = url; v.classList.add('show');
    } else {
      $('mys-img').src = url; $('mys-img').classList.add('show');
    }
  }

  // ── Senden ─────────────────────────────────────────────────────────────────
  async function send() {
    if (S.busy) return;
    const btn = $('mys-send');
    const busy = (b) => { S.busy = b; btn.disabled = b; btn.textContent = b ? t('sending') : t('send'); };
    try {
      const fd = new FormData();
      const vis = $('mys-vis'); if (vis) fd.append('privacy', vis.value);
      if (S.tab === 'text') {
        const text = $('mys-text').value.trim();
        if (!text) return show('err', t('needText'));
        busy(true);
        fd.append('file', await textToFile(text));
      } else {
        if (!S.file && !S.tplFile) return show('err', t('needFile'));
        if (S.videoMeta && CFG.videoMaxSec && S.videoMeta.duration > CFG.videoMaxSec + 0.5) {
          return show('err', tf('videoTooLong', Math.round(S.videoMeta.duration), NAME, CFG.videoMaxSec));
        }
        busy(true);
        if (S.file) fd.append('file', S.file); else fd.append('templateFile', S.tplFile);
        const cap = $('mys-caption'); if (cap && cap.value.trim()) fd.append('caption', cap.value.trim());
        if (S.videoMeta) {
          fd.append('duration', String(S.videoMeta.duration));
          fd.append('w', String(S.videoMeta.w)); fd.append('h', String(S.videoMeta.h));
        }
      }
      await fetch('api/my-status/media', { method: 'POST', body: fd }).then(apiJson);
      show('ok', S.tab === 'text' ? t('sentText') : t('sentMedia'));
      resetEditor();
    } catch (e) {
      show('err', tf('error', e.message || String(e)));
    } finally {
      busy(false);
    }
  }

  // ── Vorlagen ───────────────────────────────────────────────────────────────
  async function loadTemplates() {
    try { S.templates = (await fetch('api/status-templates').then(apiJson)).templates || []; }
    catch (e) { S.templates = []; }
    if (S.tab === 'tpl') renderTemplates();
  }

  function renderTemplates() {
    const box = $('mys-tpl-list');
    box.innerHTML = '';
    if (!S.templates.length) { box.innerHTML = '<div class="mys-hint">' + esc(t('tplEmpty')) + '</div>'; return; }
    for (const tpl of S.templates) {
      const row = document.createElement('div');
      row.className = 'mys-item';
      row.onclick = () => applyTemplate(tpl.id);
      const th = document.createElement('div');
      th.className = 'mys-thumb';
      if (tpl.mediaFile && tpl.mediaType !== 'video') {
        const i = document.createElement('img');
        i.src = 'api/status-template-media/' + encodeURIComponent(tpl.mediaFile);
        th.appendChild(i);
      } else {
        th.style.background = tpl.backgroundColor || COLORS[0];
        th.textContent = tpl.mediaFile ? '🎬' : 'Aa';
      }
      const info = document.createElement('div');
      info.className = 'mys-info';
      const kind = tpl.mediaFile ? (tpl.mediaType === 'video' ? t('tplVideo') : t('tplImage')) : t('tplText');
      const prev = (tpl.text || '').replace(/\s+/g, ' ').slice(0, 60);
      info.innerHTML = '<div class="mys-name">' + esc(tpl.name) + '</div><div class="mys-sub">' + esc(kind + (prev ? ' · ' + prev : '')) + '</div>';
      const del = document.createElement('button');
      del.className = 'mys-ico'; del.textContent = '🗑';
      del.onclick = (e) => { e.stopPropagation(); deleteTemplate(tpl.id); };
      row.append(th, info, del);
      box.appendChild(row);
    }
  }

  function applyTemplate(id) {
    const tpl = S.templates.find(x => x.id === id);
    if (!tpl) return;
    S.editingTpl = tpl.id;
    $('mys-tpl-update').style.display = '';
    $('mys-tpl-name').value = tpl.name;
    S.color = tpl.backgroundColor || COLORS[0];
    S.font = Math.min(tpl.fontStyle || 0, FONTS.length - 1);
    buildPickers();
    if (tpl.mediaFile) {
      clearMedia();
      S.tplFile = tpl.mediaFile;
      const cap = $('mys-caption'); if (cap) cap.value = tpl.text || '';
      if (tpl.mediaType === 'video') {
        $('mys-media-note').textContent = t('videoNoPreview');
      } else {
        $('mys-img').src = 'api/status-template-media/' + encodeURIComponent(tpl.mediaFile);
        $('mys-img').classList.add('show');
        $('mys-media-note').textContent = tf('tplFileNote', tpl.name);
      }
      $('mys-clear').style.display = '';
      setTab('media');
    } else {
      $('mys-text').value = tpl.text || '';
      setTab('text');
    }
    show('ok', tf('tplLoaded', tpl.name));
  }

  async function saveTemplate(update) {
    const name = $('mys-tpl-name').value.trim();
    if (!name) return show('err', t('tplNameMissing'));
    const fd = new FormData();
    fd.append('name', name);
    fd.append('backgroundColor', S.color);
    fd.append('fontStyle', String(S.font));
    if (update && S.editingTpl) fd.append('id', S.editingTpl);
    const cap = $('mys-caption');
    if (S.file) {
      fd.append('file', S.file);
      fd.append('text', cap ? cap.value : '');
    } else if (S.tplFile) {
      fd.append('text', cap ? cap.value : '');
    } else {
      fd.append('text', $('mys-text').value);
      fd.append('removeMedia', '1');
    }
    try {
      const d = await fetch('api/status-templates', { method: 'POST', body: fd }).then(apiJson);
      S.editingTpl = d.template.id;
      $('mys-tpl-update').style.display = '';
      await loadTemplates();
      renderTemplates();
      show('ok', t('tplSavedOk'));
    } catch (e) { show('err', tf('error', e.message)); }
  }

  async function deleteTemplate(id) {
    const tpl = S.templates.find(x => x.id === id);
    if (!tpl || !confirm(tf('tplDeleteConfirm', tpl.name))) return;
    try {
      await fetch('api/status-templates/' + encodeURIComponent(id) + '/delete', { method: 'POST' }).then(apiJson);
      if (S.editingTpl === id) { S.editingTpl = null; $('mys-tpl-update').style.display = 'none'; }
      await loadTemplates();
      renderTemplates();
      show('ok', t('tplDeleted'));
    } catch (e) { show('err', tf('error', e.message)); }
  }

  // ── Profil + laufende Storys ───────────────────────────────────────────────
  async function loadProfile() {
    try {
      const d = await fetch('api/me').then(apiJson);
      for (const f of PROFILE.fields) { const el = $('mys-p-' + f); if (el) el.value = d[f] || ''; }
    } catch (e) { show('err', tf('error', e.message)); }
  }

  async function saveProfile() {
    const body = {};
    for (const f of PROFILE.fields) body[f] = $('mys-p-' + f).value;
    try { await postJson('api/me/profile', body); show('ok', t('profileSaved')); }
    catch (e) { show('err', tf('error', e.message)); }
  }

  async function loadLive() {
    const box = $('mys-live');
    box.innerHTML = '<div class="mys-hint">' + esc(t('liveLoading')) + '</div>';
    let list = [];
    try { list = (await fetch('api/my-status').then(apiJson)).stories || []; }
    catch (e) { box.innerHTML = '<div class="mys-hint">' + esc(tf('error', e.message)) + '</div>'; return; }
    box.innerHTML = '';
    if (!list.length) { box.innerHTML = '<div class="mys-hint">' + esc(t('liveEmpty')) + '</div>'; return; }
    for (const s of list) {
      const row = document.createElement('div');
      row.className = 'mys-item';
      row.style.cursor = 'default';
      const th = document.createElement('div');
      th.className = 'mys-thumb';
      th.textContent = s.type === 'video' ? '🎬' : '📷';
      if (s.thumb) {
        const i = document.createElement('img');
        i.onerror = () => i.remove();
        i.onload = () => { th.textContent = ''; th.appendChild(i); };
        i.src = 'api/my-status/thumb/' + encodeURIComponent(s.id);
      }
      const info = document.createElement('div');
      info.className = 'mys-info';
      const sub = [fmt(s.date)];
      if (s.expires) sub.push(tf('liveUntil', fmt(s.expires)));
      if (typeof s.views === 'number') sub.push(tf('liveViews', s.views));
      info.innerHTML = '<div class="mys-name">' + esc(s.caption || (s.type === 'video' ? '🎬' : '📷')) + '</div><div class="mys-sub">' + esc(sub.join(' · ')) + '</div>';
      row.append(th, info);
      if (CFG.liveEdit) {
        const ed = document.createElement('button');
        ed.className = 'mys-ico'; ed.textContent = '✏️'; ed.title = t('liveEdit');
        ed.onclick = () => editLive(s);
        row.appendChild(ed);
      }
      if (CFG.liveDelete) {
        const del = document.createElement('button');
        del.className = 'mys-ico'; del.textContent = '🗑'; del.title = t('liveDelete');
        del.onclick = () => deleteLive(s.id);
        row.appendChild(del);
      }
      box.appendChild(row);
    }
  }

  async function editLive(s) {
    const caption = prompt(t('liveEditPrompt'), s.caption || '');
    if (caption === null) return;
    try { await postJson('api/my-status/edit', { id: s.id, caption }); show('ok', t('liveEdited')); loadLive(); }
    catch (e) { show('err', tf('error', e.message)); }
  }

  async function deleteLive(id) {
    if (!confirm(t('liveDeleteConfirm'))) return;
    try { await postJson('api/my-status/delete', { id }); show('ok', t('liveDeleted')); loadLive(); }
    catch (e) { show('err', tf('error', e.message)); }
  }

  // ── Datenschutz (nur wo der Messenger es von hier aus zulaesst) ─────────────
  async function loadPrivacy() {
    const box = $('mys-priv');
    box.innerHTML = '<div class="mys-hint">' + esc(t('liveLoading')) + '</div>';
    let items = [];
    try { items = (await fetch('api/privacy').then(apiJson)).items || []; }
    catch (e) { box.innerHTML = '<div class="mys-hint">' + esc(tf('error', e.message)) + '</div>'; return; }
    box.innerHTML = '';
    for (const it of items) {
      const row = document.createElement('div');
      row.className = 'mys-priv';
      const lbl = document.createElement('span');
      lbl.textContent = t('priv_' + it.key) + (it.exceptions ? '  ' + tf('privExceptions', it.exceptions) : '');
      const sel = document.createElement('select');
      sel.className = 'mys-sel';
      for (const v of ['all', 'contacts', 'nobody']) {
        const o = document.createElement('option');
        o.value = v; o.textContent = t(v === 'all' ? 'privAll' : v === 'contacts' ? 'privContacts' : 'privNobody');
        sel.appendChild(o);
      }
      sel.value = it.value;
      sel.onchange = async () => {
        sel.disabled = true;
        try { await postJson('api/privacy', { key: it.key, value: sel.value }); show('ok', t('privSaved')); }
        catch (e) { show('err', tf('error', e.message)); sel.value = it.value; }
        finally { sel.disabled = false; }
        it.value = sel.value;
      };
      row.append(lbl, sel);
      box.appendChild(row);
    }
  }

  // ── Knopf in der Kopfzeile ─────────────────────────────────────────────────
  function addButton() {
    const bar = document.getElementById('topbar');
    if (!bar || document.getElementById('mys-open')) return;
    const b = document.createElement('button');
    b.id = 'mys-open';
    b.className = 'scroll-btn';
    b.title = t('open');
    b.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="9" stroke-dasharray="4 3"/><circle cx="12" cy="12" r="4.5" fill="currentColor" stroke="none"/></svg>';
    b.onclick = open;
    const anchor = bar.querySelector('.uname, .phone');
    if (anchor) anchor.after(b); else bar.appendChild(b);
  }

  // Sprachwechsel des Add-ons mitnehmen
  if (typeof window.switchLang === 'function') {
    const orig = window.switchLang;
    window.switchLang = function () { orig.apply(this, arguments); applyLang(); };
  }
  window.msOpenMyStatus = open;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', addButton);
  else addButton();
})();
