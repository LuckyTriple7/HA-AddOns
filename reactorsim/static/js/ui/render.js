// Renderlauf mit Taktbremse je Widget-Klasse.
//
// Ein Handy muss nicht 60-mal je Sekunde eine Zahl neu setzen, die sich in
// Zehntelsekunden kaum ändert. Zeiger laufen jedes Bild (nur transform),
// alles Andere langsamer. Regel für jedes Widget: Knoten einmal bauen, danach
// nur transform, textContent, classList und Custom Properties anfassen --
// niemals innerHTML im laufenden Betrieb.

const PORTRAIT = typeof matchMedia === 'function'
  ? matchMedia('(max-width: 1023.98px)')
  : { matches: false };

export const GROUPS = {
  gauge: 0,        // 0 = jedes Bild
  mimic: 20,
  trend: 10,
  text: 4,
};

export class Render {
  constructor() {
    this.widgets = [];
    this.enabled = true;
  }

  /** @param {'gauge'|'mimic'|'trend'|'text'} group */
  add(group, fn) {
    const w = { group, fn, next: 0 };
    this.widgets.push(w);
    return () => {
      const i = this.widgets.indexOf(w);
      if (i >= 0) this.widgets.splice(i, 1);
    };
  }

  clear() { this.widgets.length = 0; }

  _hz(group) {
    // Im Hochformat ist der Bildschirm klein und das Gerät meist schwächer --
    // die Trendschreiber dürfen dort die Hälfte laufen.
    if (group === 'trend' && PORTRAIT.matches) return 5;
    return GROUPS[group] ?? 4;
  }

  tick(state, now) {
    if (!this.enabled) return;
    for (const w of this.widgets) {
      const hz = this._hz(w.group);
      if (hz > 0) {
        if (now < w.next) continue;
        w.next = now + 1000 / hz;
      }
      w.fn(state, now);
    }
  }
}
