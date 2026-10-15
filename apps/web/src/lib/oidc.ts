import "server-only";
import { createHash, randomBytes } from "node:crypto";

/**
 * OIDC authorization-code flow with PKCE against Keycloak (docs/auth.md). The web server only
 * moves the ID token to the API, which checks signature, issuer, audience and expiry.
 */
export const FLOW_COOKIE = "cip_oidc_flow";

export interface OidcEnv {
  issuer: string;
  clientId: string;
  clientSecret: string | undefined;
}

export function oidcEnv(): OidcEnv | null {
  const issuer = process.env.CIP_OIDC_ISSUER;
  const clientId = process.env.CIP_OIDC_CLIENT_ID;
  if (!issuer || !clientId) return null;
  return {
    issuer: issuer.replace(/\/$/, ""),
    clientId,
    clientSecret: process.env.CIP_OIDC_CLIENT_SECRET,
  };
}

export interface Discovery {
  authorization_endpoint: string;
  token_endpoint: string;
}

export async function discover(issuer: string): Promise<Discovery> {
  const response = await fetch(`${issuer}/.well-known/openid-configuration`, { cache: "no-store" });
  if (!response.ok) throw new Error(`discovery failed: ${response.status}`);
  return (await response.json()) as Discovery;
}

const b64url = (bytes: Buffer) => bytes.toString("base64url");

export interface Flow {
  state: string;
  nonce: string;
  verifier: string;
}

export function newFlow(): Flow {
  return {
    state: b64url(randomBytes(16)),
    nonce: b64url(randomBytes(16)),
    verifier: b64url(randomBytes(32)),
  };
}

export function authorizeUrl(
  endpoint: string,
  env: OidcEnv,
  redirectUri: string,
  flow: Flow,
): string {
  const url = new URL(endpoint);
  url.search = new URLSearchParams({
    response_type: "code",
    client_id: env.clientId,
    redirect_uri: redirectUri,
    scope: "openid email profile",
    state: flow.state,
    nonce: flow.nonce,
    code_challenge: b64url(createHash("sha256").update(flow.verifier).digest()),
    code_challenge_method: "S256",
  }).toString();
  return url.toString();
}

/** Exchange the code for tokens and return the ID token after checking the nonce. */
export async function exchange(
  endpoint: string,
  env: OidcEnv,
  redirectUri: string,
  code: string,
  flow: Flow,
): Promise<string> {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: redirectUri,
    client_id: env.clientId,
    code_verifier: flow.verifier,
  });
  if (env.clientSecret) body.set("client_secret", env.clientSecret);
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`token exchange failed: ${response.status}`);
  const { id_token: idToken } = (await response.json()) as { id_token?: string };
  if (!idToken) throw new Error("no id_token");
  const payload = JSON.parse(Buffer.from(idToken.split(".")[1] ?? "", "base64url").toString()) as {
    nonce?: string;
  };
  if (payload.nonce !== flow.nonce) throw new Error("nonce mismatch");
  return idToken;
}
