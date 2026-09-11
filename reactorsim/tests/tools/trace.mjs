import { createEngine } from '../../static/js/sim/engine.js';
import * as pwr from '../../static/js/plants/pwr.js';

const e = createEngine(pwr, { n: 1.0 });
const s = e.state;
const dt = 0.05;
const marks = new Set([0, 1, 2, 5, 10, 20, 40, 60, 120, 300, 600, 1800, 3600]);
console.log('  t     n%     P_th   rho    T_avg   T_f    p_sg   L_sg  W_st  W_fw  pzr_p  pzr_L  rod0   P_e');
let t = 0;
function line() {
  const d = e.derive();
  console.log(
    String(Math.round(t)).padStart(5),
    (s.n * 100).toFixed(1).padStart(6),
    s.P_th.toFixed(0).padStart(6),
    d.rho_pcm.toFixed(0).padStart(6),
    (d.T_avg - 273.15).toFixed(1).padStart(7),
    (s.T_f - 273.15).toFixed(0).padStart(6),
    s.p_sg.toFixed(1).padStart(6),
    s.L_sg.toFixed(2).padStart(5),
    s.W_steam.toFixed(0).padStart(5),
    s.W_fw.toFixed(0).padStart(5),
    s.pzr_p.toFixed(1).padStart(6),
    s.pzr_L.toFixed(2).padStart(6),
    s.rod[0].toFixed(3).padStart(6),
    s.P_e.toFixed(0).padStart(5),
    s.scram.active ? 'SCRAM ' + s.scram.cause : '');
}
line();
for (t = dt; t <= 3600; t += dt) {
  e.step(dt);
  if (marks.has(Math.round(t * 100) / 100)) line();
}
