import { createEngine } from '../../static/js/sim/engine.js';
import * as pwr from '../../static/js/plants/pwr.js';
import { hg, hf, tsat, rhog } from '../../static/js/sim/steam.js';

const e = createEngine(pwr, { n: 1.0 });
const s = e.state, sp = e.spec, ctx = e.ctx;
for (let t = 0; t < 1200; t += 0.05) e.step(0.05);

const hfw = 4.2 * (sp.sg.T_fw - 273.15);
const W = s.W_core, cp = sp.coolant.cp;
const UA2 = 2 * sp.sg.UA;
const Wcp = W * cp;
const Tm = s.T_sgm, Tsat_sg = tsat(s.p_sg);
const qPrim = (UA2 * (s.T_co - Tm)) / (1 + UA2 / (2 * Wcp));
const qSec = UA2 * (Tm - Tsat_sg);
console.log('n                ', (s.n*100).toFixed(2), '%');
console.log('P_th             ', s.P_th.toFixed(1), 'MW');
console.log('Kern abgefuehrt  ', (Wcp * (s.T_co - s.T_ci) / 1000).toFixed(1), 'MW   (T_co', (s.T_co-273.15).toFixed(2), 'T_ci', (s.T_ci-273.15).toFixed(2), ')');
console.log('qPrim (SG)       ', (qPrim/1000).toFixed(1), 'MW');
console.log('qSec  (SG)       ', (qSec/1000).toFixed(1), 'MW   T_sgm', (Tm-273.15).toFixed(2), 'Tsat', (Tsat_sg-273.15).toFixed(2));
console.log('W_steam          ', s.W_steam.toFixed(1), 'kg/s  Ventil', ctx.govValve.pos.toFixed(3), 'Bypass', ctx.bypassValve.pos.toFixed(4));
const W_t = ctx.govValve.flow(sp.turbine.Cv, rhog(s.p_sg), s.p_sg - s.p_cond);
const W_bp = ctx.bypassValve.flow(sp.turbine.bypassCv, rhog(s.p_sg), s.p_sg - s.p_cond);
console.log('  davon Turbine  ', W_t.toFixed(1), ' Umleitung', W_bp.toFixed(1));
console.log('Dampfenergie raus', (s.W_steam * (hg(s.p_sg) - hfw) / 1000).toFixed(1), 'MW');
console.log('P_e              ', s.P_e.toFixed(1), 'MWe   Wirkungsgrad', (100*s.P_e/s.P_th).toFixed(2), '%');
console.log('M_sg             ', s.M_sg.toFixed(0), 'kg   L_sg', s.L_sg.toFixed(3), 'W_fw', s.W_fw.toFixed(1));
console.log('p_sg             ', s.p_sg.toFixed(3), 'bar   p_cond', s.p_cond.toFixed(4));
