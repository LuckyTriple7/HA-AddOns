import { createEngine } from '../../static/js/sim/engine.js';
import * as bwr from '../../static/js/plants/bwr.js';
const DT = 0.05;
const e = createEngine(bwr, { n: 1.0 });
const s = e.state;
console.log('Start: rod0', s.rod[0].toFixed(3), ' void', s.alphaBar.toFixed(3),
  ' x_e', s.x_e.toFixed(4), ' dTsub', s.dTsub.toFixed(1), ' W_steam', s.W_steam.toFixed(0),
  ' P_e', s.P_e.toFixed(0), ' rho', (e.derive().rho_pcm).toFixed(1));
console.log('   t     n%    P_th   P_e   p_dome  L    void  x_e  W_rec  rho   DR');
const log = (t) => { const d = e.derive(); console.log(
  String(Math.round(t)).padStart(5), (s.n*100).toFixed(1).padStart(6), s.P_th.toFixed(0).padStart(6),
  s.P_e.toFixed(0).padStart(6), s.p_dome.toFixed(2).padStart(7), s.L_rpv.toFixed(2).padStart(5),
  s.alphaBar.toFixed(3).padStart(6), s.x_e.toFixed(3).padStart(6), (s.W_rec/1000).toFixed(1).padStart(6),
  d.rho_pcm.toFixed(0).padStart(6), d.decayRatio.toFixed(2).padStart(5),
  s.scram.active ? 'SCRAM '+s.scram.cause : ''); };
log(0);
for (const m of [10, 50, 100, 300, 600, 1200, 1800, 3600]) {
  while (s.t_sim < m) e.step(DT);
  log(s.t_sim);
}
