import { createEngine } from '../../static/js/sim/engine.js';
import * as rbmk from '../../static/js/plants/rbmk.js';
const DT = 0.05;
const run = (e, sec) => { for (let i=0;i<sec/DT;i++) e.step(DT); };

const e = createEngine(rbmk, { n: 1.0 });
const s = e.state;
run(e, 600);
const n0 = s.n;
for (let i = 0, N = Math.round(2400/DT); i < N; i++) { e.ctx.powerCtl.setpoint = n0 + (0.07-n0)*(i/N); e.step(DT); }
e.ctx.powerCtl.setpoint = 0.07;

// warten, bis die Abschaltreserve unter zwoelf Staebe faellt
let t0 = s.t_sim;
while (e.derive().orm > 12 && s.t_sim - t0 < 7200 && !s.scram.active) e.step(DT);
let d = e.derive();
console.log(`Zustand beim Ausloesen (${((s.t_sim-t0)/60).toFixed(0)} min nach der Absenkung):`);
console.log('  n', (s.n*100).toFixed(2)+'%  ORM', d.orm.toFixed(1), ' a_void', d.voidCoeff.toFixed(0),
  ' ao', s.ao.toFixed(3), ' void', s.alphaBar.toFixed(3), ' X', s.X.toFixed(2), ' rod', s.rod[0].toFixed(3));

e.scram('az5');
console.log('   t      n%       rho    tip   void  rods  doppler   T_f   Enth');
for (let k = 0; k <= 80; k++) {
  if (k) run(e, 0.25);
  d = e.derive(); const b = d.breakdown;
  if (k % 2 === 0 || s.destroyed) console.log(
    (k*0.25).toFixed(2).padStart(6),
    (s.n*100).toFixed(2).padStart(10),
    d.rho_pcm.toFixed(0).padStart(6),
    (b.tip*1e5).toFixed(0).padStart(6),
    (b.void*1e5).toFixed(0).padStart(6),
    (b.rods*1e5).toFixed(0).padStart(6),
    (b.doppler*1e5).toFixed(0).padStart(7),
    (s.T_f-273.15).toFixed(0).padStart(6),
    s.enthalpy.toFixed(0).padStart(6),
    s.destroyed ? 'KERN ZERSTOERT' : '');
  if (s.destroyed) break;
}
