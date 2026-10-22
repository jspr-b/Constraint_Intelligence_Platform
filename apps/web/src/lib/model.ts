/** Plain labels for standard-model fields (`resources.resource_code` → "Machines · machine code"). */
type T = (key: string) => string;
type Has = (key: string) => boolean;

export function fieldLabel(field: string, t: T, has: Has): string {
  const [table = "", name = ""] = field.split(".");
  const tableLabel = has(`tables.${table}`) ? t(`tables.${table}`) : table;
  const nameLabel = has(`fields.${name}`) ? t(`fields.${name}`) : name.replaceAll("_", " ");
  return `${tableLabel} · ${nameLabel}`;
}

export function conversionLabel(conversion: string, t: T, has: Has): string {
  const kind = conversion.split(":")[0] ?? conversion;
  return has(`conversions.${kind}`) ? t(`conversions.${kind}`) : conversion;
}
