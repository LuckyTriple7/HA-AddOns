import { createEngine } from '../../static/js/sim/engine.js';
import * as rbmk from '../../static/js/plants/rbmk.js';
const DT = 0.05;
const run = (e, sec) => { for (let i=0;i<sec/DT;i++) e.step(DT); };

function setup(holdH) {
  const e = createEngine(rbmk, { n: 1.0 });
  const s = e.state;
  run(e, 600);
  const n0 = s.n;
  for (let i = 0, N = Math.round(2400/DT); i < N; i++) {
    e.ctx.powerCtl.setpoint = n0 + (0.07 - n0) * (i/N);
    e.step(DT);
  }
  e.ctx.powerCtl.setpoint = 0.07;
  run(e, holdH*3600);
  return e;
}

function az5(e, tag) {
  const s = e.state, d0 = e.derive();
  console.log(`\n${tag}: ORM ${d0.orm.toFixed(1)}  a_void ${d0.voidCoeff.toFixed(0)} pcm/%  ` +
    `n ${(s.n*100).toFixed(2)}%  ao ${s.ao.toFixed(3)}`);
  e.scram('az5');
  console.log('   t     n%      rho   tip   void  rods   T_f   Enthalpie  rod');
  for (let k = 0; k <= 60; k++) {
    if (k) run(e, 0.5);
    const d = e.derive(), b = d.breakdown;
    if (k % 4 === 0 || s.destroyed) console.log(
      (k*0.5).toFixed(1).padStart(5),
      (s.n*100).toFixed(2).padStart(9),
      d.rho_pcm.toFixed(0).padStart(6),
      (b.tip*1e5).toFixed(0).padStart(5),
      (b.void*1e5).toFixed(0).padStart(6),
      (b.rods*1e5).toFixed(0).padStart(6),
      (s.T_f-273.15).toFixed(0).padStart(6),
      s.enthalpy.toFixed(0).padStart(9),
      s.rod[0].toFixed(3).padStart(6),
      s.destroyed ? 'KERN ZERSTOERT' : '');
    if (s.destroyed) break;
  }
}

az5(setup(4), 'Fall a: nach 4 h bei 7 % Leistung');
{
  const e = createEngine(rbmk, { n: 1.0 });
  run(e, 900);
  az5(e, 'Fall b: aus dem Nennbetrieb');
}
