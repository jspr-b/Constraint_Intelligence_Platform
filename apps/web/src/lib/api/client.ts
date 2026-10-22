import createClient from "openapi-fetch";
import type { paths } from "./schema";

/** What every API error carries: a stable code and a plain English message to show as it is. */
export interface Problem {
  code: string;
  message: string;
}

/** Read the API's error body; anything else becomes a generic problem with the status text. */
export function problemOf(body: unknown, status: number, statusText = ""): Problem {
  const b = (body ?? {}) as { code?: unknown; message?: unknown; detail?: unknown };
  const message =
    typeof b.message === "string" ? b.message : typeof b.detail === "string" ? b.detail : "";
  return {
    code: typeof b.code === "string" ? b.code : `http_${status}`,
    message: message || statusText || `HTTP ${status}`,
  };
}

/** A read that failed on the server (5xx), or a write the server refused (via ensureOk). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
    readonly problem: Problem,
  ) {
    super(problem.message);
    this.name = "ApiError";
  }

  /** One line for IT: status, address, code. */
  get technical(): string {
    return `${this.status} ${this.path} · ${this.problem.code}`;
  }
}

const pathOf = (url: string) => new URL(url, "http://x").pathname.replace(/^\/api/, "");

/** Typed client for the platform API, generated from apps/api/openapi.json. Same-origin proxy. */
export const api = createClient<paths>({ baseUrl: "/api", credentials: "same-origin" });

// A failed read must never look like "no data yet": throw, so the page says it failed.
api.use({
  async onResponse({ request, response }) {
    if (request.method !== "GET" || response.status < 500) return undefined;
    const body: unknown = await response
      .clone()
      .json()
      .catch(() => null);
    throw new ApiError(
      response.status,
      pathOf(request.url),
      problemOf(body, response.status, response.statusText),
    );
  },
});

/** A write the server refused; the shell shows "your change was not saved" with this reason. */
export async function ensureOk<T extends { response: Response; error?: unknown }>(
  pending: Promise<T> | T,
): Promise<T> {
  const result = await pending;
  if (result.response.ok) return result;
  throw new ApiError(
    result.response.status,
    pathOf(result.response.url),
    problemOf(result.error, result.response.status, result.response.statusText),
  );
}
