import "server-only";

/**
 * The tenant this web host signs people into: one tenant per deployment (e.g. per subdomain).
 * In dev the dev tenant is used when CIP_TENANT_ID is not set.
 */
export function signInTenant(): string | undefined {
  const configured = process.env.CIP_TENANT_ID;
  if (configured) return configured;
  return process.env.CIP_ENV === "dev" ? process.env.CIP_DEV_TENANT_ID : undefined;
}
