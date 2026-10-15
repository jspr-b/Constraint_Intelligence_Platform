import { createHash } from "node:crypto";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
const { authorizeUrl, exchange, newFlow } = await import("./oidc");

const ENV = {
  issuer: "https://kc.example.test/realms/plant",
  clientId: "cip-web",
  clientSecret: "s3cret",
};
const REDIRECT = "https://app.example.test/auth/oidc/callback";

function idToken(claims: object): string {
  const part = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${part({ alg: "RS256" })}.${part(claims)}.signature`;
}

afterEach(() => vi.unstubAllGlobals());

describe("oidc", () => {
  it("builds an authorization URL with PKCE S256, state and nonce", () => {
    const flow = newFlow();
    const url = new URL(
      authorizeUrl(`${ENV.issuer}/protocol/openid-connect/auth`, ENV, REDIRECT, flow),
    );
    const challenge = createHash("sha256").update(flow.verifier).digest("base64url");
    expect(url.searchParams.get("code_challenge")).toBe(challenge);
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("state")).toBe(flow.state);
    expect(url.searchParams.get("nonce")).toBe(flow.nonce);
    expect(url.searchParams.get("redirect_uri")).toBe(REDIRECT);
    expect(url.searchParams.get("scope")).toBe("openid email profile");
  });

  it("exchanges the code with the verifier and returns the ID token", async () => {
    const flow = newFlow();
    const token = idToken({ nonce: flow.nonce });
    const fetchMock = vi.fn(async () => Response.json({ id_token: token }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      exchange("https://kc.example.test/token", ENV, REDIRECT, "c0de", flow),
    ).resolves.toBe(token);
    const body = new URLSearchParams(
      String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body),
    );
    expect(body.get("code_verifier")).toBe(flow.verifier);
    expect(body.get("client_secret")).toBe("s3cret");
    expect(body.get("grant_type")).toBe("authorization_code");
  });

  it("rejects a token with the wrong nonce", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ id_token: idToken({ nonce: "other" }) })),
    );
    await expect(
      exchange("https://kc.example.test/token", ENV, REDIRECT, "c0de", newFlow()),
    ).rejects.toThrow("nonce");
  });

  it("fails when the provider refuses the code", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("", { status: 400 })),
    );
    await expect(
      exchange("https://kc.example.test/token", ENV, REDIRECT, "bad", newFlow()),
    ).rejects.toThrow("400");
  });
});
