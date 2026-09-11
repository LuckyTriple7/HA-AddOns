import { createEngine } from '../../static/js/sim/engine.js';
import * as rbmk from '../../static/js/plants/rbmk.js';
const DT = 0.05;
const run = (e, sec) => { for (let i=0;i<sec/DT;i++) e.step(DT); };

const e = createEngine(rbmk, { n: 1.0 });
const s = e.state;
let d = e.derive();
console.log('Nennbetrieb:');
console.log('  rod', s.rod[0].toFixed(3), ' ORM', d.orm.toFixed(1), ' void', s.alphaBar.toFixed(3),
  ' x_e', s.x_e.toFixed(3), ' a_void', d.voidCoeff.toFixed(1), 'pcm/%',
  ' ao', s.ao.toFixed(3), ' T_gr', (s.T_gr-273.15).toFixed(0), 'C');
console.log('  P_th', s.P_th.toFixed(0), ' P_e', s.P_e.toFixed(0), ' rho', d.rho_pcm.toFixed(1),
  ' dTsub', s.dTsub.toFixed(1));
console.log('   t     n%    P_e   p_drum  L    void  ORM  a_v   ao    rho');
const log = () => { d = e.derive(); console.log(
  String(Math.round(s.t_sim)).padStart(5), (s.n*100).toFixed(1).padStart(6), s.P_e.toFixed(0).padStart(6),
  s.p_drum.toFixed(2).padStart(7), s.L_drum.toFixed(2).padStart(5), s.alphaBar.toFixed(3).padStart(6),
  d.orm.toFixed(0).padStart(4), d.voidCoeff.toFixed(0).padStart(4), s.ao.toFixed(2).padStart(6),
  d.rho_pcm.toFixed(0).padStart(6), s.scram.active ? 'SCRAM '+s.scram.cause : ''); };
log();
for (const m of [30, 120, 600, 1800, 3600]) { while (s.t_sim < m) e.step(DT); log(); }
