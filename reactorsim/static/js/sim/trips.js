// Grenzwerte, Meldungen, Auslösungen -- tabellengetrieben.
//
// Jeder Eintrag ist ein Datensatz, keine if-Kaskade im Rechenpfad:
//
//   { id, key, severity, test(s, d), delay_s, hold_s, action }
//
// `test` liefert true, solange die Bedingung ansteht. `delay_s` ist die Zeit,
// die sie anstehen muss, bevor die Meldung kommt (verhindert Flattern bei
// Messrauschen), `hold_s` die Zeit, die sie weg sein muss, bevor die Meldung
// geht. Zwei getrennte Zeiten statt einer Hysterese auf dem Messwert: das
// funktioniert für jede Größe gleich, auch für zusammengesetzte Bedingungen.
//
// `action: 'scram'` löst NICHTS von selbst aus -- das System meldet nur, es
// greift nicht ein. Die Schnellabschaltung bleibt allein Sache des Bedieners
// am SCRAM/RESA/AZ-5-Knopf. Das Feld markiert lediglich, welche Meldungen
// schutzwürdig sind: engine.resetScram() lässt sich erst zurücksetzen, wenn
// keine davon mehr ansteht.
//
// Die Kachelzustände folgen der Ringback-Folge nach ISA-18.2:
//
//   normal → new (schnelles Blinken, Hupe) → ack (Dauerlicht)
//          → clear (langsames Blinken, wenn die Ursache weg, aber nicht
//                   quittiert wurde) → normal
//
// Dass Quittieren eine eigene Handlung ist, ist Absicht: unquittierte
// Alarmsekunden gehen in die Wertung ein.

export const SEVERITY = { INFO: 1, WARN: 2, TRIP: 3 };

export class TripSystem {
  constructor(defs) {
    this.defs = defs;
    this.states = new Map();
    for (const d of defs) {
      this.states.set(d.id, {
        def: d,
        active: false,     // Bedingung steht an
        latched: false,    // Meldung ist gekommen
        tile: 'normal',    // normal | new | ack | clear
        tOn: 0,            // wie lange steht die Bedingung an
        tOff: 0,           // wie lange ist sie weg
        since: 0,
        unackS: 0,         // Summe unquittierter Sekunden (für die Wertung)
      });
    }
    this.events = [];
    this.horn = false;
  }

  /** Ein Takt. Gibt die Kennung der schlimmsten anstehenden Meldung zurück. */
  step(s, d, dt) {
    let worst = 0;
    let worstId = null;
    let horn = false;

    for (const st of this.states.values()) {
      const def = st.def;
      let cond = false;
      try {
        cond = !!def.test(s, d);
      } catch {
        // Eine kaputte Bedingung darf nicht die ganze Simulation anhalten.
        cond = false;
      }

      if (cond) { st.tOn += dt; st.tOff = 0; } else { st.tOff += dt; st.tOn = 0; }

      const delay = def.delay_s || 0;
      const hold = def.hold_s !== undefined ? def.hold_s : 2;

      if (!st.latched && cond && st.tOn >= delay) {
        st.latched = true;
        st.active = true;
        st.tile = 'new';
        st.since = s.t_sim;
        this.events.push({ t: s.t_sim, id: def.id, key: def.key, severity: def.severity, kind: 'on' });
      } else if (st.latched && !cond && st.tOff >= hold) {
        st.latched = false;
        st.active = false;
        // Gegangen, aber noch nicht quittiert: die Kachel blinkt langsam weiter,
        // damit ein kurzer Ausschlag nicht unbemerkt verschwindet.
        st.tile = st.tile === 'ack' ? 'normal' : 'clear';
        this.events.push({ t: s.t_sim, id: def.id, key: def.key, severity: def.severity, kind: 'off' });
      }

      if (st.tile === 'new') { st.unackS += dt; horn = true; }
      if (st.tile === 'clear') st.unackS += dt;

      if (st.latched && def.severity > worst) { worst = def.severity; worstId = def.id; }
    }

    this.horn = horn;
    return { severity: worst, id: worstId };
  }

  /** Quittieren: Hupe aus, gekommene Meldungen auf Dauerlicht, gegangene weg. */
  ack() {
    for (const st of this.states.values()) {
      if (st.tile === 'new') st.tile = 'ack';
      else if (st.tile === 'clear') st.tile = 'normal';
    }
    this.horn = false;
  }

  /** Rückstellen: nur was nicht mehr ansteht. Eine anstehende Meldung lässt
   *  sich nicht wegdrücken -- das ist der Sinn einer Meldetafel. */
  reset() {
    for (const st of this.states.values()) {
      if (!st.latched) st.tile = 'normal';
    }
  }

  /** Anstehende und kürzlich gegangene Meldungen für die Anzeige. */
  tiles() {
    const out = [];
    for (const st of this.states.values()) {
      out.push({ id: st.def.id, key: st.def.key, severity: st.def.severity, tile: st.tile });
    }
    return out;
  }

  /** Summe unquittierter Alarmsekunden -- geht in die Wertung ein. */
  unacknowledgedSeconds() {
    let sum = 0;
    for (const st of this.states.values()) sum += st.unackS;
    return sum;
  }

  /** Protokolleinträge abholen und Puffer leeren. */
  drainEvents() {
    const e = this.events;
    this.events = [];
    return e;
  }
}
