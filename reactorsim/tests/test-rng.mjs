// Gesäter Zufall: reproduzierbar, gleichverteilt, unabhängig von Nachbarsaaten.

import test from 'node:test';
import assert from 'node:assert/strict';

import { Rng } from '../static/js/rng.js';

test('gleicher Startwert liefert gleiche Folge', () => {
  const a = new Rng(4711), b = new Rng(4711);
  for (let i = 0; i < 1000; i++) assert.equal(a.next(), b.next());
});

test('benachbarte Startwerte laufen auseinander', () => {
  const a = new Rng(1), b = new Rng(2);
  let same = 0;
  for (let i = 0; i < 100; i++) if (Math.abs(a.next() - b.next()) < 1e-3) same++;
  assert.ok(same < 5, `${same} von 100 Werten fast gleich`);
});

test('liegt in [0,1) und ist grob gleichverteilt', () => {
  const r = new Rng(99);
  const buckets = new Array(10).fill(0);
  const N = 100000;
  for (let i = 0; i < N; i++) {
    const v = r.next();
    assert.ok(v >= 0 && v < 1, `Wert ${v}`);
    buckets[Math.floor(v * 10)]++;
  }
  for (const b of buckets) assert.ok(Math.abs(b / N - 0.1) < 0.01, `Verteilung schief: ${b / N}`);
});

test('Normalverteilung hat Mittel 0 und Streuung 1', () => {
  const r = new Rng(7);
  let sum = 0, sq = 0;
  const N = 200000;
  for (let i = 0; i < N; i++) { const v = r.normal(); sum += v; sq += v * v; }
  assert.ok(Math.abs(sum / N) < 0.02, `Mittel ${sum / N}`);
  assert.ok(Math.abs(Math.sqrt(sq / N) - 1) < 0.02, `Streuung ${Math.sqrt(sq / N)}`);
});

test('int() trifft beide Ränder und bleibt drin', () => {
  const r = new Rng(3);
  const seen = new Set();
  for (let i = 0; i < 5000; i++) {
    const v = r.int(1, 6);
    assert.ok(v >= 1 && v <= 6 && Number.isInteger(v), `Wert ${v}`);
    seen.add(v);
  }
  assert.equal(seen.size, 6);
});
