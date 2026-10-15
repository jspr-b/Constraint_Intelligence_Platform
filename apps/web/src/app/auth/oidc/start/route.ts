import { NextResponse, type NextRequest } from "next/server";
import { FLOW_COOKIE, authorizeUrl, discover, newFlow, oidcEnv } from "@/lib/oidc";

export async function GET(request: NextRequest) {
  const env = oidcEnv();
  if (!env) return NextResponse.redirect(new URL("/login?error=sso", request.url));
  try {
    const { authorization_endpoint: endpoint } = await discover(env.issuer);
    const flow = newFlow();
    const redirectUri = new URL("/auth/oidc/callback", request.url).toString();
    const response = NextResponse.redirect(authorizeUrl(endpoint, env, redirectUri, flow));
    response.cookies.set(FLOW_COOKIE, JSON.stringify(flow), {
      httpOnly: true,
      sameSite: "lax",
      secure: request.nextUrl.protocol === "https:",
      path: "/auth/oidc",
      maxAge: 600,
    });
    return response;
  } catch {
    return NextResponse.redirect(new URL("/login?error=sso", request.url));
  }
}
