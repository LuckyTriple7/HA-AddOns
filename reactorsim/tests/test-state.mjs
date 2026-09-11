// Zustandsvektor: Startwerte, Grenzwächter, bitgenauer Hash.

import test from 'node:test';
import assert from 'node:assert/strict';

import { createState, sanitize, hash, numbers } from '../static/js/sim/state.js';
import { makeKinetics } from '../static/js/sim/kinetics.js';

const spec = {
  id: 'probe',
  P0_e: 1400,
  rodBanks: [{ worth: 1200, initial: 0.2 }, { worth: 3800, initial: 0 }],
  coolant: { W0: 20000, p0: 158 },
  feedback: { boron_ref_ppm: 1000 },
};

const kin = makeKinetics(0.0065, 2e-5);

test('Startzustand sitzt im Gleichgewicht', () => {
  const s = createState(spec, { kin, n: 1 });
  assert.equal(s.rod[0], 0.2);
  assert.equal(s.C_B, 1000);
  assert.ok(Math.abs(s.X - 1) < 1e-12, 'Xenon nicht im Gleichgewicht');
  let sum = 0;
  for (let j = 0; j < s.D.length; j++) sum += s.D[j];
  assert.ok(Math.abs(sum - 0.07) < 1e-12, 'Nachzerfallswärme nicht im Gleichgewicht');
});

test('sanitize klemmt Ausreißer und meldet Unmögliches', () => {
  const s = createState(spec, { kin });
  s.rod[0] = 1.7;
  s.p_prim = -5;
  assert.equal(sanitize(s), true);
  assert.equal(s.rod[0], 1);
  assert.ok(s.p_prim > 0);

  const bad = createState(spec, { kin });
  bad.T_f = NaN;
  assert.equal(sanitize(bad), false);
  assert.ok(bad.fault.includes('T_f'));

  const worse = createState(spec, { kin });
  worse.c[2] = Infinity;
  assert.equal(sanitize(worse), false);
});

test('Hash ist stabil und reagiert auf jede Zahl', () => {
  const a = createState(spec, { kin });
  const b = createState(spec, { kin });
  assert.equal(hash(a), hash(b));
  assert.equal(numbers(a).length, numbers(b).length);

  b.n += 1e-15;
  assert.notEqual(hash(a), hash(b), 'Hash bemerkt kleinste Änderung nicht');
});

test('Zustand enthält keine abgeleiteten Größen', () => {
  const s = createState(spec, { kin });
  for (const key of ['t_avg', 'p_th', 'dnbr', 'period', 'subcool']) {
    assert.ok(!(key in s), `${key} darf nicht im Zustand stehen`);
  }
});
