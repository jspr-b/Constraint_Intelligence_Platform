# Sign-in and sessions

How people and stations sign in, and how the API knows the tenant and role (ADR-0004, ADR-0005, ADR-0007).

## Two kinds of login

| Login | Who | How | Session belongs to |
|---|---|---|---|
| Personal | Plant director, COO, planner, shift lead, IT | Company identity provider (OIDC), or the dev login in a pilot | The account IT created |
| Station | The screen at a machine | Plant + machine + PIN (4–8 digits) | The machine, never a person |

- An account must exist before anyone can sign in: IT invites by email and role (`POST /users`). The first IT account of a tenant comes from `uv run python -m cip_api.bootstrap --tenant "…" --it-email …`.
- Five wrong PINs in a row lock a station login. IT enables it again (`POST /station-logins/{id}/enable`), which also resets the counter.
- Disabling an account or station login ends its open sessions immediately.

## Sessions

- After sign-in the API sets an httpOnly cookie `cip_session` (SameSite=Lax; Secure outside dev). It lasts `CIP_SESSION_HOURS` (default 12, one long shift).
- The database stores only the SHA-256 of the token, in `sessions`, under row-level security. Before the tenant is known, the API finds a session through one narrow database function, `session_lookup(token_hash)`, that returns a single live session and nothing else.
- Tenant, role, plant and (for stations) machine always come from the session. `POST /auth/logout` deletes it. `GET /auth/me` returns the role, start page and effective access.
- Dev only (`CIP_ENV=dev`, no cookie sent): the `X-Tenant-Id` header, with optional `X-Role` (default `coo`) and `X-Plant`, stands in for a session. Outside dev the header is ignored and the request gets `401 sign-in required`.

## Providers

`CIP_AUTH_PROVIDER` picks how people sign in.

### `dev` (pilot and local)

`POST /auth/dev-login {tenant_id, email}` signs in an existing, not-disabled account. It only exists when `CIP_ENV=dev`; anywhere else it answers 404.

### `oidc` (production, e.g. Microsoft Entra ID)

The web app runs the OIDC authorization-code flow with the provider and posts the resulting ID token to `POST /auth/oidc-login {tenant_id, id_token}`. The API checks the RS256 signature against the provider's keys, the issuer, the audience and the expiry, then matches the token's `email` (or Entra's `preferred_username`) to an account in that tenant.

Settings for Microsoft Entra ID (single-tenant app registration):

```
CIP_AUTH_PROVIDER=oidc
CIP_OIDC_ISSUER=https://login.microsoftonline.com/<directory-id>/v2.0
CIP_OIDC_AUDIENCE=<application-client-id>
CIP_OIDC_JWKS_URL=https://login.microsoftonline.com/<directory-id>/discovery/v2.0/keys
```

In the app registration: platform "Web", redirect URI on the web app's sign-in callback, ID tokens enabled, optional claim `email`. Keycloak and Auth0 work the same way with their issuer, client id and JWKS URL (the auth provider choice is still open).

## Not in this sequence

- Role and plant come from the account in the platform, not from provider groups. Mapping Entra groups to roles is a later option.
- No rate limit per IP on sign-in yet; the PIN lock covers stations. Add one at the reverse proxy before going live.
