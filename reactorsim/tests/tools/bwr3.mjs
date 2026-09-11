import { createEngine } from '../../static/js/sim/engine.js';
import * as bwr from '../../static/js/plants/bwr.js';
const DT = 0.05;
const run = (e, sec) => { for (let i=0;i<sec/DT;i++) e.step(DT); };

// MSIV im Detail
{
  const e = createEngine(bwr, { n: 1.0 }); const s = e.state;
  run(e, 300);
  console.log('MSIV-Schliessung, erste Sekunden:');
  console.log('   t     n%    void    rho_void  rho    p_dome');
  s.msiv = 0;
  for (let k = 0; k <= 24; k++) {
    if (k) run(e, 0.25);
    const d = e.derive();
    if (k % 2 === 0) console.log(
      (k*0.25).toFixed(2).padStart(5), (s.n*100).toFixed(1).padStart(7),
      s.alphaBar.toFixed(4).padStart(8), (d.breakdown.void*1e5).toFixed(0).padStart(8),
      d.rho_pcm.toFixed(0).padStart(7), s.p_dome.toFixed(2).padStart(8),
      s.scram.active ? 'SCRAM' : '');
  }
}

// Instabilitaet: Durchsatz runter, Staebe vorsichtig ziehen bis die Leistung wieder hoch ist
{
  const e = createEngine(bwr, { n: 1.0 }); const s = e.state;
  run(e, 300);
  s.recircDmd = 0.45;
  run(e, 200);
  console.log('\nnach Durchsatzabsenkung auf 45 %: n =', (s.n*100).toFixed(1), '%');
  let steps = 0;
  while (s.n < 0.88 && steps < 600 && !s.scram.active && s.rodDmd[0] > 0.001) {
    s.rodDmd[0] = Math.max(0, s.rodDmd[0] - 0.002);
    run(e, 8);
    steps++;
  }
  const d = e.derive();
  console.log('  n', (s.n*100).toFixed(1), '%  Durchsatz', (d.recirc*100).toFixed(0),
    '%  S', (s.n/Math.max(d.recirc,0.05)).toFixed(2), ' DR', d.decayRatio.toFixed(2));
  let amp = 0;
  for (let i=0;i<300/DT;i++) { e.step(DT); amp = Math.max(amp, Math.abs(s.osc)); }
  console.log('  groesste Amplitude', amp.toFixed(3),
    ' Abschaltung:', s.scram.active ? s.scram.cause : 'keine',
    ' DR', e.derive().decayRatio.toFixed(2));
}
