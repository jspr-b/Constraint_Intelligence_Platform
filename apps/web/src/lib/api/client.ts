import createClient from "openapi-fetch";
import type { paths } from "./schema";

/** Typed client for the platform API, generated from apps/api/openapi.json. Same-origin proxy. */
export const api = createClient<paths>({ baseUrl: "/api", credentials: "same-origin" });
