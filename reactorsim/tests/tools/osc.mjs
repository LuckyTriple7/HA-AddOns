import { createEngine } from '../../static/js/sim/engine.js';
import * as pwr from '../../static/js/plants/pwr.js';
const DT = 0.05;
const e = createEngine(pwr, { n: 1.0 });
const s = e.state;
for (let i = 0; i < 300/DT; i++) e.step(DT);
const target = 0.6 * e.spec.P0_e, start = s.P_demand;
const n = Math.round(1800 / DT);
for (let i = 0; i < n; i++) { s.P_demand = start + (target-start)*(i/n); e.step(DT); }
for (let i = 0; i < 1800/DT; i++) e.step(DT);
console.log('   t     p_sg    P_e     gov   govPos  W_st   n%');
for (let k = 0; k < 60; k++) {
  for (let i = 0; i < 1/DT; i++) e.step(DT);
  console.log(String(k+1).padStart(4), s.p_sg.toFixed(3).padStart(8), s.P_e.toFixed(1).padStart(7),
    s.gov.toFixed(3).padStart(7), e.ctx.govValve.pos.toFixed(3).padStart(7),
    s.W_steam.toFixed(0).padStart(6), (s.n*100).toFixed(2).padStart(7));
}
