'use strict';

const PRIVACY_NAME = /privacy|lastseen|last_seen|readreceipt|read_receipt|profilepic|groupadd|group_add|onlinevisib/i;

// Absichtlich keine Kandidaten require()n: die Baseline soll durch die Sonde
// selbst weder Module initialisieren noch deren nachgeladene Abhaengigkeiten sehen.
async function snapshotRegistry(page) {
  return page.evaluate(() => {
    const pick = obj => {
      if (!obj || typeof obj !== 'object') return null;
      for (const key of ['modulesMap', 'modules', 'moduleMap', 'map']) {
        if (obj[key] && typeof obj[key] === 'object') return obj[key];
      }
      return null;
    };
    let reg = null, via = null;
    try { reg = pick(window.require('__debug')); if (reg) via = "require('__debug')"; } catch (e) {}
    if (!reg) {
      try { reg = pick(window.__debug); if (reg) via = 'window.__debug'; } catch (e) {}
    }
    if (!reg) return { error: 'kein Registry-Modul gefunden', names: [], factories: [] };
    const names = Object.keys(reg).sort();
    const factories = names.filter(name => {
      try {
        const entry = reg[name];
        return typeof entry === 'function' || (entry && ['factory', 'moduleFactory', 'fn', 'func', '_moduleFactory']
          .some(key => typeof entry[key] === 'function'));
      } catch (e) { return false; }
    });
    return { via, names, factories };
  });
}

function compareRegistries(before, after) {
  const summary = s => ({ via: s.via || null, total: s.names.length,
    factories: s.factories.length, privacyNames: s.names.filter(n => PRIVACY_NAME.test(n)),
    ...(s.error ? { error: s.error } : {}) });
  const out = { before: summary(before), after: summary(after) };
  if (before.error || after.error) return { ...out, comparable: false };
  const oldNames = new Set(before.names), newNames = new Set(after.names);
  const oldFactories = new Set(before.factories);
  const added = after.names.filter(n => !oldNames.has(n));
  const removed = before.names.filter(n => !newNames.has(n));
  // Bereits registrierte Platzhalter koennen erst jetzt eine Factory bekommen.
  const factoriesAdded = after.factories.filter(n => !oldFactories.has(n));
  const changed = [...new Set([...added, ...factoriesAdded])].sort();
  return { ...out, comparable: true, addedCount: added.length, removedCount: removed.length,
    factoriesAddedCount: factoriesAdded.length, added: added.slice(0, 300),
    removed: removed.slice(0, 300), factoriesAdded: factoriesAdded.slice(0, 300),
    truncated: added.length > 300 || removed.length > 300 || factoriesAdded.length > 300,
    privacyAdded: changed.filter(n => PRIVACY_NAME.test(n)) };
}

// Laeuft im Browser. Nur exakte DE/EN-Navigationslabels, niemals Optionswerte,
// Checkboxen oder Schalter anklicken. Bei Mehrdeutigkeit abbrechen.
function inspectPrivacyUi(action) {
  const labels = { settings: ['Settings', 'Einstellungen'], privacy: ['Privacy', 'Datenschutz'] };
  const normalize = s => String(s || '').replace(/\s+/g, ' ').trim();
  const visible = el => {
    const style = getComputedStyle(el);
    return el.getClientRects().length > 0 && style.visibility !== 'hidden' && style.display !== 'none'
      && !el.closest('[aria-hidden="true"], [inert]');
  };
  const elements = [...document.querySelectorAll('h1,h2,h3,span,div,[role="heading"]')].filter(visible);
  const categoryLabels = [
    ['Last seen and online', 'Zuletzt online/Online', 'Zuletzt online und Online', 'Zuletzt online und online'],
    ['Profile photo', 'Profilbild'], ['About', 'Info'], ['Read receipts', 'Lesebestätigungen'],
  ];
  const categories = categoryLabels.filter(group => elements.some(el => group.includes(normalize(el.textContent))));
  const heading = elements.some(el => labels.privacy.includes(normalize(el.textContent))
    && (el.matches('h1,h2,h3,[role="heading"]') || el.closest('header')));
  const privacyVisible = heading && categories.length >= 2;
  if (!action || privacyVisible) return { privacyVisible, categoryMatches: categories.length,
    language: document.documentElement.lang || null };

  const targets = [...document.querySelectorAll('button,[role="button"],[role="menuitem"],a')].filter(el => {
    if (!visible(el) || el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
    if (el.matches('[role="switch"],[role="checkbox"],[role="radio"],input')
      || el.hasAttribute('aria-checked') || el.hasAttribute('aria-pressed')) return false;
    return [el.getAttribute('aria-label'), el.getAttribute('title'), el.textContent,
      ...[...el.querySelectorAll('span')].map(span => span.textContent)]
      .some(value => labels[action].includes(normalize(value)));
  });
  // Verschachtelte Semantik desselben Controls zaehlt nur einmal.
  const unique = targets.filter(el => !targets.some(other => other !== el && el.contains(other)));
  if (unique.length !== 1) return { privacyVisible, action, clicked: false,
    error: unique.length ? 'navigation_ambiguous' : 'navigation_not_found', matches: unique.length };
  unique[0].click();
  return { privacyVisible, action, clicked: true };
}

async function runPrivacyUiDiagnostic(page) {
  const before = await snapshotRegistry(page);
  const steps = [];
  let ui = await page.evaluate(inspectPrivacyUi);
  const alreadyOpen = ui.privacyVisible;
  let navigationError = null;
  try {
    if (!alreadyOpen) {
      const settings = await page.evaluate(inspectPrivacyUi, 'settings');
      steps.push(settings);
      // Auch eine bereits offene Einstellungsansicht kann direkt Datenschutz anbieten.
      if (!settings.clicked && settings.error === 'navigation_ambiguous') navigationError = settings.error;
      if (!navigationError) {
        const deadline = Date.now() + 8000;
        do {
          const privacy = await page.evaluate(inspectPrivacyUi, 'privacy');
          if (privacy.privacyVisible || privacy.clicked || privacy.error === 'navigation_ambiguous') {
            steps.push(privacy);
            if (privacy.error) navigationError = privacy.error;
            break;
          }
          if (Date.now() >= deadline) { steps.push(privacy); navigationError = privacy.error; break; }
          await new Promise(resolve => setTimeout(resolve, 250));
        } while (true);
      }
    }
    // Festes Beobachtungsfenster auch bei fehlgeschlagener Navigation: ein Klick
    // kann Module laden, ohne dass unsere Ansichtserkennung bereits passt.
    await new Promise(resolve => setTimeout(resolve, 5000));
    ui = await page.evaluate(inspectPrivacyUi);
    if (!ui.privacyVisible && !navigationError) navigationError = 'privacy_view_not_confirmed';
  } catch (e) {
    navigationError = e.message;
  }
  const after = await snapshotRegistry(page);
  return { ui: { ...ui, alreadyOpen, steps, error: navigationError,
    observationMs: 5000, leftOpen: true }, registry: compareRegistries(before, after),
    hint: 'Neue Module koennen auch durch Hintergrundaktivitaet entstehen. Keine neuen Module beweisen keine Client-Sperre. Bereits geladene Module bleiben bis zum Neuladen registriert.' };
}

module.exports = { runPrivacyUiDiagnostic, snapshotRegistry, compareRegistries, inspectPrivacyUi };
