/** Unit suffixes of standard field names, and how they are shown. */
const UNIT_SUFFIX: [string, string][] = [
  ["_eur_cents", "€"],
  ["_min_per_unit", "min/unit"],
  ["_min", "min"],
  ["_h", "h"],
  ["_pct", "%"],
  ["_units", "units"],
  ["_at", ""],
];

/** "truly_variable_cost_eur_cents" → ["truly variable cost", "€"]. Display only. */
export function inputName(key: string): [string, string] {
  const [suffix, unit] = UNIT_SUFFIX.find(([s]) => key.endsWith(s)) ?? ["", ""];
  return [key.slice(0, key.length - suffix.length).replaceAll("_", " "), unit];
}

/** A missing value's name in plain words: its message when there is one, else the name without
 * underscores or unit suffix (never a raw field name such as `ideal_min`). */
export function missingName(
  t: { has: (key: string) => boolean; (key: string): string },
  what: string,
): string {
  return t.has(`inputNames.${what}`) ? t(`inputNames.${what}`) : inputName(what)[0];
}
