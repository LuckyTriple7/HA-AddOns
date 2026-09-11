import { createEngine } from '../../static/js/sim/engine.js';
import * as bwr from '../../static/js/plants/bwr.js';
const DT = 0.05;
const run = (e, sec) => { for (let i=0;i<sec/DT;i++) e.step(DT); };

// Umwaelzstrom senken
{
  const e = createEngine(bwr, { n: 1.0 }); const s = e.state;
  run(e, 300);
  const n0 = s.n;
  console.log('Umwaelzstrom 100 -> 80 %:');
  s.recircDmd = 0.80;
  for (const m of [10, 30, 60, 180, 600]) {
    run(e, m === 10 ? 10 : 0); if (m > 10) while (s.t_sim < 300 + m) e.step(DT);
    const d = e.derive();
    console.log('  t+', String(m).padStart(4), ' n', (s.n*100).toFixed(1).padStart(6),
      ' void', s.alphaBar.toFixed(3), ' P_e', s.P_e.toFixed(0).padStart(5),
      ' DR', d.decayRatio.toFixed(2), ' p', s.p_dome.toFixed(2));
  }
  console.log('  Leistungsaenderung:', (100*(s.n/n0-1)).toFixed(1), '%');
  s.recircDmd = 1.0;
  run(e, 600);
  console.log('  zurueck auf 100 %:', (s.n*100).toFixed(1), '%  void', s.alphaBar.toFixed(3));
}

// Instabilitaetszone ansteuern
{
  const e = createEngine(bwr, { n: 1.0 }); const s = e.state;
  run(e, 300);
  console.log('\nInstabilitaet: Durchsatz auf 45 %, Staebe ziehen');
  s.recircDmd = 0.45;
  run(e, 120);
  // Staebe etwas ziehen, um die Leistung oben zu halten -> S steigt
  for (let k = 0; k < 40; k++) { s.rodDmd[0] = Math.max(0, s.rodDmd[0] - 0.01); run(e, 15); }
  const d = e.derive();
  console.log('  n', (s.n*100).toFixed(1), '%  Durchsatz', (d.recirc*100).toFixed(0), '%',
    ' DR', d.decayRatio.toFixed(2), ' Amplitude', d.oscAmp.toFixed(3),
    ' Abschaltung:', s.scram.active ? s.scram.cause : 'keine');
}

// Frischdampf-Absperrung
{
  const e = createEngine(bwr, { n: 1.0 }); const s = e.state;
  run(e, 300);
  console.log('\nFrischdampf-Absperrung (MSIV):');
  s.msiv = 0;
  let pMax = 0, nMax = 0;
  for (let i=0;i<200/DT;i++) { e.step(DT); pMax = Math.max(pMax, s.p_dome); nMax = Math.max(nMax, s.n); }
  console.log('  Spitzendruck', pMax.toFixed(1), 'bar   Leistungsspitze', (nMax*100).toFixed(1), '%');
  console.log('  Abschaltung:', s.scram.active ? s.scram.cause : 'keine', ' Brennstoffschaden:', s.destroyed);
}
