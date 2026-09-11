import { createEngine } from '../../static/js/sim/engine.js';
import * as rbmk from '../../static/js/plants/rbmk.js';
const DT = 0.05;
const run = (e, sec) => { for (let i=0;i<sec/DT;i++) e.step(DT); };

function report(e, tag) {
  const s = e.state, d = e.derive();
  console.log(tag, ' n', (s.n*100).toFixed(2)+'%', ' rod', s.rod[0].toFixed(3),
    ' ORM', d.orm.toFixed(1), ' a_void', d.voidCoeff.toFixed(0), ' ao', s.ao.toFixed(3),
    ' void', s.alphaBar.toFixed(3), ' Xtop', s.zTop.X.toFixed(2), ' Xbot', s.zBot.X.toFixed(2),
    ' X', s.X.toFixed(2), s.scram.active ? ' SCRAM '+s.scram.cause : '');
}

// Die historische Vorgeschichte nachfahren: Volllast, Absenkung, langes Halten
// bei kleiner Leistung, waehrend Xenon aufbaut.
const e = createEngine(rbmk, { n: 1.0 });
const s = e.state;
run(e, 600);
report(e, 'Volllast   ');

// In 40 Minuten auf 7 %.
const n0 = s.n;
for (let i = 0, N = Math.round(2400/DT); i < N; i++) {
  e.ctx.powerCtl.setpoint = n0 + (0.07 - n0) * (i/N);
  e.step(DT);
}
e.ctx.powerCtl.setpoint = 0.07;
report(e, 'nach Rampe ');

for (const h of [0.25, 0.5, 1, 1.5, 2, 3]) {
  const target = 600 + 2400 + h*3600;
  while (s.t_sim < target && !s.scram.active) e.step(DT);
  report(e, `+${h} h      `);
  if (s.scram.active) break;
}
