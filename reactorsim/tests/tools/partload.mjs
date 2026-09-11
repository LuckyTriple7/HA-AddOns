import { createEngine } from '../../static/js/sim/engine.js';
import * as pwr from '../../static/js/plants/pwr.js';
const DT = 0.05;
const e = createEngine(pwr, { n: 1.0 });
const s = e.state;
for (let i = 0; i < 300/DT; i++) e.step(DT);
const target = 0.6 * e.spec.P0_e, start = s.P_demand;
const n = Math.round(1800 / DT);
for (let i = 0; i < n; i++) { s.P_demand = start + (target-start)*(i/n); e.step(DT); }
console.log('    t   Soll   P_e   gov  govPI  n%   p_sg  T_avg  rod0   X');
const log = (t) => console.log(String(t).padStart(5),
  s.P_demand.toFixed(0).padStart(6), s.P_e.toFixed(0).padStart(6),
  s.gov.toFixed(3).padStart(6), e.ctx.govCtl.pi.i.toFixed(3).padStart(6),
  (s.n*100).toFixed(1).padStart(5), s.p_sg.toFixed(1).padStart(6),
  (0.5*(s.T_ci+s.T_co)-273.15).toFixed(1).padStart(6),
  s.rod[0].toFixed(3).padStart(6), s.X.toFixed(3).padStart(6));
log(1800);
for (const m of [300, 600, 1200, 1800]) { for (let i=0;i<m/DT;i++) e.step(DT); log(1800+m); }

import { hg, hf, tsat, rhog } from '../../static/js/sim/steam.js';
const sp = e.spec, ctx = e.ctx;
const hfw = 4.2 * (sp.sg.T_fw - 273.15);
const W_t = ctx.govValve.flow(sp.turbine.Cv, rhog(s.p_sg), s.p_sg - s.p_cond);
const W_bp = ctx.bypassValve.flow(sp.turbine.bypassCv, rhog(s.p_sg), s.p_sg - s.p_cond);
console.log('\nW_steam', s.W_steam.toFixed(1), ' Turbine', W_t.toFixed(1), ' Umleitung', W_bp.toFixed(1),
            ' govPos', ctx.govValve.pos.toFixed(3), ' bpPos', ctx.bypassValve.pos.toFixed(4), ' s.bypass', s.bypass.toFixed(3));
console.log('P_th', s.P_th.toFixed(0), ' qSec_aequiv', (s.W_steam*(hg(s.p_sg)-hfw)/1000).toFixed(0),
            ' wSpec', ((hg(s.p_sg)-hf(s.p_cond))*sp.turbine.workFactor).toFixed(1),
            ' P_e(rechnerisch)', (W_t*(hg(s.p_sg)-hf(s.p_cond))*sp.turbine.workFactor/1000).toFixed(1));

const Wcp = s.W_core * sp.coolant.cp;
const UA2 = 2 * sp.sg.UA;
const qPrim = (UA2 * (s.T_co - s.T_sgm)) / (1 + UA2 / (2 * Wcp));
console.log('Kern abgefuehrt', (Wcp*(s.T_co-s.T_ci)/1000).toFixed(1),
            ' T_co', (s.T_co-273.15).toFixed(2), ' T_ci', (s.T_ci-273.15).toFixed(2),
            ' dT', (s.T_co-s.T_ci).toFixed(2));
console.log('qPrim', (qPrim/1000).toFixed(1), ' T_sgm', (s.T_sgm-273.15).toFixed(2),
            ' Tsat', (tsat(s.p_sg)-273.15).toFixed(2), ' qSec', (UA2*(s.T_sgm-tsat(s.p_sg))/1000).toFixed(1));
console.log('W_fw', s.W_fw.toFixed(1), ' M_sg', s.M_sg.toFixed(0), ' L_sg', s.L_sg.toFixed(3));
