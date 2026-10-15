import { NextResponse, type NextRequest } from "next/server";
import { FLOW_COOKIE, discover, exchange, oidcEnv, type Flow } from "@/lib/oidc";
import { signInTenant } from "@/lib/tenant";

const API = process.env.CIP_API_URL ?? "http://localhost:58000";

export async function GET(request: NextRequest) {
  const fail = NextResponse.redirect(new URL("/login?error=sso", request.url));
  fail.cookies.delete({ name: FLOW_COOKIE, path: "/auth/oidc" });
  const env = oidcEnv();
  const tenant = signInTenant();
  const raw = request.cookies.get(FLOW_COOKIE)?.value;
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  if (!env || !tenant || !raw || !code) return fail;
  try {
    const flow = JSON.parse(raw) as Flow;
    if (state !== flow.state) return fail;
    const { token_endpoint: endpoint } = await discover(env.issuer);
    const redirectUri = new URL("/auth/oidc/callback", request.url).toString();
    const idToken = await exchange(endpoint, env, redirectUri, code, flow);
    const signIn = await fetch(`${API}/auth/oidc-login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ tenant_id: tenant, id_token: idToken }),
      cache: "no-store",
    });
    if (!signIn.ok) return fail;
    const done = NextResponse.redirect(new URL("/", request.url));
    for (const cookie of signIn.headers.getSetCookie()) done.headers.append("set-cookie", cookie);
    done.cookies.delete({ name: FLOW_COOKIE, path: "/auth/oidc" });
    return done;
  } catch {
    return fail;
  }
}
