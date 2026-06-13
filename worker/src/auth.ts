import type { MiddlewareHandler } from "hono";
import { getCookie, setCookie } from "hono/cookie";
import { createRemoteJWKSet, jwtVerify } from "jose";

export type AuthEnv = {
  ACCESS_TEAM_DOMAIN: string;
  ACCESS_AUD: string;
  API_TOKEN?: string;
};

export const TOKEN_COOKIE = "vb_token";

// JWKS fetchers cache keys in instance memory; keyed by team domain (config, not request state).
const jwksByDomain = new Map<string, ReturnType<typeof createRemoteJWKSet>>();

async function verifyAccessJwt(token: string, teamDomain: string, aud: string): Promise<boolean> {
  let jwks = jwksByDomain.get(teamDomain);
  if (!jwks) {
    jwks = createRemoteJWKSet(new URL(`${teamDomain}/cdn-cgi/access/certs`));
    jwksByDomain.set(teamDomain, jwks);
  }
  try {
    await jwtVerify(token, jwks, { issuer: teamDomain, audience: aud });
    return true;
  } catch {
    return false;
  }
}

/** Constant-time string comparison via SHA-256 digests (equal length by construction). */
async function tokenMatches(candidate: string, expected: string): Promise<boolean> {
  const enc = new TextEncoder();
  const [a, b] = await Promise.all([
    crypto.subtle.digest("SHA-256", enc.encode(candidate)),
    crypto.subtle.digest("SHA-256", enc.encode(expected)),
  ]);
  const va = new Uint8Array(a);
  const vb = new Uint8Array(b);
  let diff = 0;
  for (let i = 0; i < va.length; i++) diff |= (va[i] ?? 0) ^ (vb[i] ?? 0);
  return diff === 0;
}

/**
 * Allow a request if any of:
 *  - Authorization: Bearer <API_TOKEN>          (poller, scripts, iOS shortcut)
 *  - vb_token cookie matching API_TOKEN         (browser before Access is set up; see /login)
 *  - valid Cloudflare Access JWT                (browser SSO / Access service tokens)
 */
export function requireAuth<E extends { Bindings: AuthEnv }>(): MiddlewareHandler<E> {
  return async (c, next) => {
    const apiToken = c.env.API_TOKEN;

    const header = c.req.header("authorization");
    if (apiToken && header?.startsWith("Bearer ")) {
      if (await tokenMatches(header.slice("Bearer ".length), apiToken)) return next();
      return c.json({ error: "invalid bearer token" }, 401);
    }

    const cookie = getCookie(c, TOKEN_COOKIE);
    if (apiToken && cookie && (await tokenMatches(cookie, apiToken))) return next();

    const jwt = c.req.header("cf-access-jwt-assertion");
    if (jwt && c.env.ACCESS_TEAM_DOMAIN && c.env.ACCESS_AUD) {
      if (await verifyAccessJwt(jwt, c.env.ACCESS_TEAM_DOMAIN, c.env.ACCESS_AUD)) return next();
      return c.json({ error: "invalid Access JWT" }, 401);
    }

    return c.json({ error: "unauthorized" }, 401);
  };
}

/** One-time browser login before Cloudflare Access exists: GET /login?token=... sets an HttpOnly cookie. */
export function loginHandler<E extends { Bindings: AuthEnv }>(): MiddlewareHandler<E> {
  return async (c) => {
    const token = c.req.query("token");
    const apiToken = c.env.API_TOKEN;
    if (!token || !apiToken || !(await tokenMatches(token, apiToken))) {
      return c.json({ error: "invalid or missing token" }, 401);
    }
    setCookie(c, TOKEN_COOKIE, token, {
      httpOnly: true,
      secure: true,
      sameSite: "Lax",
      path: "/",
      maxAge: 60 * 60 * 24 * 90,
    });
    return c.redirect("/");
  };
}
