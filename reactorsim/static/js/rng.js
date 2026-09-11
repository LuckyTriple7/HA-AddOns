// Gesäter Zufall (xorshift128+).
//
// Math.random ist in sim/ verboten: ohne reproduzierbare Folge gibt es keine
// Wiedergabe eines Laufs, keine Regressionstests gegen einen festen Startwert
// und keine spätere serverseitige Nachrechnung eines Spielstands.

export class Rng {
  constructor(seed = 1) {
    // Zwei 32-Bit-Hälften aus einem einzigen Startwert auffächern (splitmix32),
    // sonst korrelieren benachbarte Startwerte sichtbar.
    let x = (seed >>> 0) || 1;
    const mix = () => {
      x = (x + 0x9e3779b9) >>> 0;
      let z = x;
      z = Math.imul(z ^ (z >>> 16), 0x21f0aaad) >>> 0;
      z = Math.imul(z ^ (z >>> 15), 0x735a2d97) >>> 0;
      return (z ^ (z >>> 15)) >>> 0;
    };
    this.s0 = mix();
    this.s1 = mix();
    this.s2 = mix();
    this.s3 = mix();
  }

  /** Gleichverteilt in [0, 1). */
  next() {
    // xoshiro128+: schnell, ausreichend gut für Störungszeitpunkte und Rauschen.
    const r = (this.s0 + this.s3) >>> 0;
    const t = (this.s1 << 9) >>> 0;
    this.s2 ^= this.s0;
    this.s3 ^= this.s1;
    this.s1 ^= this.s2;
    this.s0 ^= this.s3;
    this.s2 ^= t;
    this.s3 = ((this.s3 << 11) | (this.s3 >>> 21)) >>> 0;
    return r / 4294967296;
  }

  /** Gleichverteilt in [lo, hi). */
  range(lo, hi) { return lo + (hi - lo) * this.next(); }

  /** Ganzzahl in [lo, hi]. */
  int(lo, hi) { return Math.floor(this.range(lo, hi + 1)); }

  /** Standardnormalverteilt (Box-Muller), für Messrauschen. */
  normal() {
    let u = this.next();
    if (u < 1e-12) u = 1e-12;
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * this.next());
  }
}
