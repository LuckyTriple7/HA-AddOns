import { createEngine } from '../../static/js/sim/engine.js';
import * as pwr from '../../static/js/plants/pwr.js';

const dt = 0.05;
function boot() {
  const e = createEngine(pwr, { n: 1.0 });
  for (let t = 0; t < 600; t += dt) e.step(dt);   // einschwingen
  return e;
}
function run(e, seconds) { for (let t = 0; t < seconds; t += dt) e.step(dt); }

// ── Schnellabschaltung ────────────────────────────────────────────────────────
{
  const e = boot();
  const s = e.state;
  e.scram('manual');
  const marks = [1, 2, 3, 5, 10, 30, 60, 300, 3600];
  let last = 0;
  console.log('SCRAM aus Volllast:');
  console.log('    t     n%    P_th%   T_f    pzr_p  p_sg  L_sg  W_fw   X');
  for (const m of marks) {
    run(e, m - last); last = m;
    console.log(
      String(m).padStart(5),
      (s.n * 100).toFixed(3).padStart(7),
      (100 * s.P_th / e.spec.P0_th).toFixed(2).padStart(6),
      (s.T_f - 273.15).toFixed(0).padStart(6),
      s.pzr_p.toFixed(1).padStart(7),
      s.p_sg.toFixed(1).padStart(6),
      s.L_sg.toFixed(2).padStart(5),
      s.W_fw.toFixed(0).padStart(5),
      s.X.toFixed(3).padStart(6));
  }
}

// ── Lastfolge 100 -> 60 -> 100 % ──────────────────────────────────────────────
{
  const e = boot();
  const s = e.state;
  console.log('\nLastfolge 100 → 60 → 100 %:');
  console.log('    t    Soll   P_e    n%    T_avg  rod0   C_B    rho');
  const log = (t) => console.log(
    String(Math.round(t)).padStart(5),
    s.P_demand.toFixed(0).padStart(6),
    s.P_e.toFixed(0).padStart(6),
    (s.n * 100).toFixed(1).padStart(6),
    (0.5 * (s.T_ci + s.T_co) - 273.15).toFixed(1).padStart(6),
    s.rod[0].toFixed(3).padStart(6),
    s.C_B.toFixed(0).padStart(6),
    e.derive().rho_pcm.toFixed(0).padStart(6));
  log(0);
  // Rampe 30 Minuten auf 60 %
  const target = 0.6 * e.spec.P0_e;
  const start = s.P_demand;
  for (let t = 0; t < 1800; t += dt) {
    s.P_demand = start + (target - start) * (t / 1800);
    e.step(dt);
  }
  log(1800);
  run(e, 1800); log(3600);
  const back = s.P_demand;
  for (let t = 0; t < 1800; t += dt) {
    s.P_demand = back + (e.spec.P0_e - back) * (t / 1800);
    e.step(dt);
  }
  log(5400);
  run(e, 1800); log(7200);
  console.log('Meldungen:', e.trips.tiles().filter(x => x.tile !== 'normal').map(x => x.id).join(', ') || 'keine');
}

// ── Lastabwurf: Turbinenschnellschluss ohne Reaktorabschaltung ────────────────
{
  const e = boot();
  const s = e.state;
  console.log('\nTurbinenschnellschluss (Reaktorabschaltung zugelassen):');
  s.turbineTripped = true;
  s.breaker = false;
  let pMax = 0, pSgMax = 0;
  for (let t = 0; t < 300; t += dt) {
    e.step(dt);
    pMax = Math.max(pMax, s.pzr_p);
    pSgMax = Math.max(pSgMax, s.p_sg);
  }
  console.log('  Spitzendruck Primaer  ', pMax.toFixed(1), 'bar  (Sicherheitsventil 171)');
  console.log('  Spitzendruck Sekundaer', pSgMax.toFixed(1), 'bar  (Abblasen ab 88)');
  console.log('  Abschaltung:', s.scram.active ? s.scram.cause : 'keine');
  console.log('  T_Huelle max erreicht ', (s.T_cl - 273.15).toFixed(0), 'C');
  console.log('  Brennstoffschaden:', s.destroyed);
}
