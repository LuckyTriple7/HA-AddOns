// Status-/Story-Vorlagen — identisch in telegram/ und signal/ (Vorbild: WhatsApp-Add-on).
// Eine Vorlage haelt Text, Hintergrundfarbe, Schrift und optional ein Bild/Video.
'use strict';
const fs = require('fs');
const path = require('path');

const MAX_TEMPLATES = 100;
const MAX_MEDIA = 16 * 1024 * 1024;

function register(app, { upload, deleteRateLimit, file, dir }) {
  let templates = [];
  try { fs.mkdirSync(dir, { recursive: true }); } catch (e) {}
  try {
    if (fs.existsSync(file)) {
      const data = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (Array.isArray(data)) templates = data;
    }
  } catch (e) { console.error('[ERROR] Status-Vorlagen laden:', e.message); }

  const save = () => {
    try { fs.writeFileSync(file, JSON.stringify(templates)); }
    catch (e) { console.error('[ERROR] Status-Vorlagen speichern:', e.message); }
  };

  // Absoluter Pfad einer Vorlagendatei, oder null wenn der Name aus dem Verzeichnis ausbricht
  const mediaPath = (name) => {
    if (!name || !/^[\w.-]+$/.test(name)) return null;
    const fp = path.resolve(dir, name);
    return fp.startsWith(path.resolve(dir) + path.sep) ? fp : null;
  };

  const mimeOf = (name) => {
    const ext = String(name).split('.').pop().toLowerCase();
    return ext === 'png' ? 'image/png' : ext === 'webp' ? 'image/webp' : ext === 'mp4' ? 'video/mp4' : 'image/jpeg';
  };

  app.get('/api/status-templates', (req, res) => res.json({ templates }));

  app.post('/api/status-templates', upload.single('file'), (req, res) => {
    const name = String(req.body?.name || '').trim().slice(0, 80);
    if (!name) return res.status(400).json({ error: 'name required' });
    const id = req.body?.id ? String(req.body.id) : '';
    const existing = id ? templates.find(t => t.id === id) : null;
    if (id && !existing) return res.status(404).json({ error: 'template not found' });
    if (!existing && templates.length >= MAX_TEMPLATES) return res.status(400).json({ error: 'too many templates' });

    const tpl = existing || { id: 'tpl_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7), createdAt: Date.now() };
    tpl.name = name;
    tpl.text = String(req.body?.text || '').slice(0, 700);
    tpl.backgroundColor = /^#[0-9a-fA-F]{6}$/.test(req.body?.backgroundColor || '') ? req.body.backgroundColor : '#0a5f55';
    tpl.fontStyle = Math.min(Math.max(parseInt(req.body?.fontStyle ?? 0, 10) || 0, 0), 7);
    tpl.updatedAt = Date.now();

    if (req.file) {
      if (!/^(image|video)\//.test(req.file.mimetype || '')) return res.status(400).json({ error: 'only image or video allowed' });
      if (req.file.size > MAX_MEDIA) return res.status(400).json({ error: 'file too large (max 16 MB)' });
      const ext = req.file.mimetype === 'image/png' ? 'png'
        : req.file.mimetype === 'image/webp' ? 'webp'
        : req.file.mimetype.startsWith('video/') ? 'mp4' : 'jpg';
      const fp = mediaPath(`${tpl.id}_${Date.now().toString(36)}.${ext}`);
      if (!fp) return res.status(400).json({ error: 'invalid path' });
      try {
        fs.writeFileSync(fp, req.file.buffer);
        const old = tpl.mediaFile ? mediaPath(tpl.mediaFile) : null;
        if (old && old !== fp) { try { fs.unlinkSync(old); } catch (e) {} }
        tpl.mediaFile = path.basename(fp);
        tpl.mediaType = req.file.mimetype.startsWith('video/') ? 'video' : 'photo';
      } catch (e) {
        console.error('[ERROR] Vorlagenbild speichern:', e.message);
        return res.status(500).json({ error: 'write failed' });
      }
    } else if (req.body?.removeMedia === '1' && tpl.mediaFile) {
      const old = mediaPath(tpl.mediaFile);
      if (old) { try { fs.unlinkSync(old); } catch (e) {} }
      tpl.mediaFile = null;
      tpl.mediaType = null;
    }

    if (!existing) templates.push(tpl);
    save();
    res.json({ success: true, template: tpl });
  });

  app.post('/api/status-templates/:id/delete', deleteRateLimit, (req, res) => {
    const idx = templates.findIndex(t => t.id === req.params.id);
    if (idx === -1) return res.status(404).json({ error: 'template not found' });
    const [tpl] = templates.splice(idx, 1);
    if (tpl.mediaFile) {
      const fp = mediaPath(tpl.mediaFile);
      if (fp) { try { fs.unlinkSync(fp); } catch (e) {} }
    }
    save();
    res.json({ success: true });
  });

  app.get('/api/status-template-media/:filename', (req, res) => {
    const fp = mediaPath(req.params.filename);
    if (!fp || !fs.existsSync(fp)) return res.status(404).end();
    res.setHeader('Content-Type', mimeOf(req.params.filename));
    res.setHeader('Cache-Control', 'public, max-age=3600');
    res.sendFile(fp);
  });

  // Fuer /api/my-status/media: gespeichertes Vorlagenbild statt Upload
  return {
    readMedia(name) {
      const fp = mediaPath(name);
      if (!fp || !fs.existsSync(fp)) return null;
      return { buffer: fs.readFileSync(fp), mimetype: mimeOf(name), originalname: path.basename(fp) };
    },
  };
}

module.exports = { register };
