'use strict';

// CHROMIUM_PATH=/path/to/chromium node --test privacy-ui-diag.test.js
const { test } = require('node:test');
const assert = require('node:assert/strict');
const puppeteer = require('puppeteer');
const { compareRegistries, snapshotRegistry, inspectPrivacyUi, runPrivacyUiDiagnostic } = require('./privacy-ui-diag');

test('Registry-Vergleich erfasst Platzhalter, ungefilterte Neuzugaenge und fehlende Registry', () => {
  const before = { via: 'test', names: ['WAWebPrivacyLazy', 'old'], factories: [] };
  const after = { via: 'test', names: ['WAWebPrivacyLazy', 'UnrelatedName'], factories: ['WAWebPrivacyLazy', 'UnrelatedName'] };
  const diff = compareRegistries(before, after);
  assert.deepEqual(diff.added, ['UnrelatedName']);
  assert.deepEqual(diff.removed, ['old']);
  assert.deepEqual(diff.privacyAdded, ['WAWebPrivacyLazy']);
  assert.equal(diff.factoriesAddedCount, 2);
  assert.equal(compareRegistries({ error: 'missing', names: [], factories: [] }, after).comparable, false);
  const large = compareRegistries({ names: [], factories: [] }, {
    names: Array.from({ length: 310 }, (_, i) => `module${i}`), factories: [],
  });
  assert.equal(large.addedCount, 310);
  assert.equal(large.added.length, 300);
  assert.equal(large.truncated, true);
});

test('Browser: sichere Navigation und Lazy-Loading-Beobachtung', async t => {
  const browser = await puppeteer.launch({ headless: true,
    ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
  t.after(() => browser.close());
  const page = await browser.newPage();

  await t.test('DE und EN: exakte Navigation; verborgene Treffer, Schalter und Mehrdeutigkeit', async () => {
    for (const label of ['Datenschutz', 'Privacy']) {
      await page.setContent(`<button style="display:none">${label}</button>
        <button role="switch">${label}</button>
        <button id="target"><span>${label}</span><span>Details</span></button>`);
      await page.evaluate(() => {
        window.clicked = [];
        document.querySelectorAll('button').forEach(el => el.onclick = () => window.clicked.push(el.id));
      });
      assert.equal((await page.evaluate(inspectPrivacyUi, 'privacy')).clicked, true);
      assert.deepEqual(await page.evaluate(() => window.clicked), ['target']);
    }
    await page.setContent('<button>Settings</button><button>Einstellungen</button>');
    assert.equal((await page.evaluate(inspectPrivacyUi, 'settings')).error, 'navigation_ambiguous');
    await page.setContent('<button>Confidentialité</button><button>Privacy policy</button>');
    assert.equal((await page.evaluate(inspectPrivacyUi, 'privacy')).error, 'navigation_not_found');
    await page.setContent('<h1>Privacy</h1><span>Profile photo</span>');
    assert.equal((await page.evaluate(inspectPrivacyUi)).privacyVisible, false);
  });

  await t.test('Einstellungen laden Module und materialisieren eine bestehende Factory', async () => {
    await page.setContent('<button aria-label="Settings" id="settings">Open</button>');
    await page.evaluate(() => {
      window.calls = [];
      window.registry = { WAWebPrivacyLazy: {} };
      window.require = name => {
        window.calls.push(name);
        if (name !== '__debug') throw new Error('unerwartete Modul-Probe');
        return { modulesMap: window.registry };
      };
      document.getElementById('settings').onclick = () => {
        document.body.innerHTML = '<h1>Settings</h1><button id="privacy">Privacy</button>';
        document.getElementById('privacy').onclick = () => {
          document.body.innerHTML = '<h1>Privacy</h1><span>Profile photo</span><span>About</span><button role="switch">Read receipts</button>';
          document.querySelector('button').onclick = () => { window.optionChanged = true; };
          setTimeout(() => {
            window.registry.WAWebPrivacyLazy.factory = () => {};
            window.registry.RenamedAction = { factory: () => {} };
          }, 100);
        };
      };
    });
    const result = await runPrivacyUiDiagnostic(page);
    assert.equal(result.ui.privacyVisible, true);
    assert.equal(result.ui.alreadyOpen, false);
    assert.equal(result.ui.error, null);
    assert.deepEqual(result.registry.added, ['RenamedAction']);
    assert.deepEqual(result.registry.privacyAdded, ['WAWebPrivacyLazy']);
    assert.deepEqual(await page.evaluate(() => window.calls), ['__debug', '__debug']);
    assert.equal(await page.evaluate(() => Boolean(window.optionChanged)), false);
    assert.equal((await page.evaluate(inspectPrivacyUi, 'settings')).privacyVisible, true);
  });

  await t.test('Registry-Fallback und fehlende Registry', async () => {
    await page.evaluate(() => {
      delete window.require;
      window.__debug = { modules: { Fallback: { factory: () => {} } } };
    });
    const snapshot = await snapshotRegistry(page);
    assert.equal(snapshot.via, 'window.__debug');
    assert.deepEqual(snapshot.factories, ['Fallback']);
    await page.evaluate(() => { delete window.__debug; });
    assert.equal((await snapshotRegistry(page)).error, 'kein Registry-Modul gefunden');
  });
});
