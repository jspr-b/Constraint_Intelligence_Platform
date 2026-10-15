/**
 * Same-origin proxy to the platform API, so the session cookie stays first-party.
 *
 * Dev only (CIP_ENV=dev, no session cookie): when CIP_DEV_TENANT_ID is set, the proxy adds the
 * API's dev headers, with the role from the role switch (cookie cip_view_as). Never outside dev.
 */
import type { NextRequest } from "next/server";

const API = process.env.CIP_API_URL ?? "http://localhost:58000";
const FORWARD = ["content-type", "accept", "cookie", "accept-language"];

async function proxy(request: NextRequest, path: string[]): Promise<Response> {
  const target = new URL(`${API}/${path.map(encodeURIComponent).join("/")}`);
  target.search = request.nextUrl.search;
  const headers = new Headers();
  for (const name of FORWARD) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const devTenant = process.env.CIP_DEV_TENANT_ID;
  if (process.env.CIP_ENV === "dev" && devTenant && !request.cookies.has("cip_session")) {
    headers.set("x-tenant-id", devTenant);
    const role = request.cookies.get("cip_view_as")?.value;
    if (role) headers.set("x-role", role);
  }
  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? null : await request.arrayBuffer(),
      redirect: "manual",
      cache: "no-store",
    });
    const out = new Headers();
    for (const [name, value] of upstream.headers) {
      if (["content-type", "set-cookie", "cache-control"].includes(name)) out.append(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers: out });
  } catch {
    return Response.json({ detail: "API unreachable" }, { status: 502 });
  }
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, { params }: Context) {
  return proxy(request, (await params).path);
}
export async function POST(request: NextRequest, { params }: Context) {
  return proxy(request, (await params).path);
}
export async function PUT(request: NextRequest, { params }: Context) {
  return proxy(request, (await params).path);
}
export async function DELETE(request: NextRequest, { params }: Context) {
  return proxy(request, (await params).path);
}
