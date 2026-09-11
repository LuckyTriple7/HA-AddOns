import { createEngine } from '../../static/js/sim/engine.js';
import * as rbmk from '../../static/js/plants/rbmk.js';
const DT = 0.05;
const freeze = process.argv[2] === 'freeze';
const e = createEngine(rbmk, { n: 1.0 });
const s = e.state;
const ao0 = s.ao;
console.log(freeze ? 'axiales Profil eingefroren' : 'axiales Profil frei');
console.log('  h     ao     n%   rho   doppler graphit  void  xenon  rods   T_gr');
for (let h = 0; h <= 30; h += 2) {
  while (s.t_sim < h*3600) { e.step(DT); if (freeze) s.ao = ao0; }
  const d = e.derive(), b = d.breakdown;
  const pcm = (k) => (b[k]*1e5).toFixed(0).padStart(7);
  console.log(String(h).padStart(4), s.ao.toFixed(3).padStart(7), (s.n*100).toFixed(1).padStart(6),
    d.rho_pcm.toFixed(0).padStart(5), pcm('doppler'), pcm('graphite'), pcm('void'), pcm('xenon'),
    pcm('rods'), (s.T_gr-273.15).toFixed(0).padStart(6), s.scram.active ? 'SCRAM '+s.scram.cause : '');
  if (s.scram.active) break;
}
