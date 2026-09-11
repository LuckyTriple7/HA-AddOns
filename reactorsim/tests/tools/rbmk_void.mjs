import { createEngine } from '../../static/js/sim/engine.js';
import * as rbmk from '../../static/js/plants/rbmk.js';
import { averageVoid } from '../../static/js/sim/steam.js';
const DT = 0.05;
const e = createEngine(rbmk, { n: 1.0 });
const s = e.state, sp = e.spec;
const show = (tag) => {
  const G = s.W_core / sp.coolant.flowArea_m2;
  const qPerKg = (s.P_th*1000)/Math.max(s.W_core,1);
  const subPerKg = sp.coolant.cp * s.dTsub;
  const fBoil = Math.max(0.05, Math.min(0.98, 1 - subPerKg/Math.max(qPerKg,1e-3)));
  console.log(tag, 'n', (s.n*100).toFixed(2), '% P_th', s.P_th.toFixed(0),
    ' W', s.W_core.toFixed(0), ' x_e', s.x_e.toFixed(4), ' dTsub', s.dTsub.toFixed(2),
    ' fBoil', fBoil.toFixed(3), ' alpha', s.alphaBar.toFixed(3),
    ' direkt', averageVoid(s.x_e, s.p_drum, G, fBoil).toFixed(3),
    ' W_fw', s.W_fw.toFixed(0), ' p_drum', s.p_drum.toFixed(2), ' L', s.L_drum.toFixed(3), ' M', s.M_drum.toFixed(0), ' W_steam', s.W_steam.toFixed(0));
};
for (let i=0;i<600/DT;i++) e.step(DT);
show('Volllast  ');
const n0 = s.n;
for (let i = 0, N = Math.round(2400/DT); i < N; i++) { e.ctx.powerCtl.setpoint = n0 + (0.07-n0)*(i/N); e.step(DT); }
e.ctx.powerCtl.setpoint = 0.07;
show('nach Rampe');
for (let i=0;i<4*3600/DT;i++) e.step(DT);
show('+4 h      ');
