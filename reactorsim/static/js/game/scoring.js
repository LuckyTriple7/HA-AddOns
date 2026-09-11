// Wertung.
//
// Diese Formel steht zweimal: hier und in scoring.py. Das ist Absicht und kein
// Versehen -- der Server darf dem Browser den Punktestand nicht glauben, also
// muss er ihn aus denselben Kennzahlen selbst ausrechnen. Wer hier etwas
// ändert, ändert dort dasselbe; ein Test vergleicht beide an festen Beispielen.

export const WEIGHTS = {
  energy: 1000,
  deviation: 2,
  alarmSecond: 0.05,
  violation: { 1: 0.2, 2: 1.0, 3: 4.0 },
  scram: 500,
  fuelDamage: 5000,
  difficultyBonus: 250,
};

/**
 * @param {object} sum Zusammenfassung aus RunState.summary()
 * @returns {{score:number, parts:object}}
 */
export function score(sum) {
  const demanded = Math.max(sum.energy_mwh_demanded || 0, 1e-9);
  const ratio = Math.min((sum.energy_mwh_delivered || 0) / demanded, 1);

  const parts = {
    energy: WEIGHTS.energy * ratio,
    deviation: -WEIGHTS.deviation * (sum.deviation_mwh || 0),
    alarms: -WEIGHTS.alarmSecond * (sum.alarm_seconds_unacked || 0),
    violations: 0,
    scram: -WEIGHTS.scram * (sum.scram_count || 0),
    fuel: sum.fuel_damage ? -WEIGHTS.fuelDamage : 0,
    bonus: sum.completed ? WEIGHTS.difficultyBonus * (sum.difficulty || 1) : 0,
  };
  const vs = sum.violation_seconds || {};
  for (const sev of [1, 2, 3]) {
    parts.violations -= WEIGHTS.violation[sev] * (Number(vs[sev]) || 0);
  }

  let total = 0;
  for (const v of Object.values(parts)) total += v;
  return { score: Math.round(total), parts };
}
