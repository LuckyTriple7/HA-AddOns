import { createEngine } from '../../static/js/sim/engine.js';
import * as rbmk from '../../static/js/plants/rbmk.js';
const DT = 0.05;
const e = createEngine(rbmk, { n: 1.0 });
const s = e.state;
console.log('  h     ao     Xtop   Xbot    n%    rho');
for (let h = 0; h <= 40; h += 2) {
  while (s.t_sim < h * 3600) e.step(DT);
  const d = e.derive();
  console.log(String(h).padStart(4), s.ao.toFixed(3).padStart(7), s.zTop.X.toFixed(3).padStart(7),
    s.zBot.X.toFixed(3).padStart(7), (s.n*100).toFixed(1).padStart(6), d.rho_pcm.toFixed(0).padStart(6),
    s.scram.active ? 'SCRAM' : '');
  if (s.scram.active) break;
}
