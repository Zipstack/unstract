/**
 * Login and organisation selection for the v1 E2E suite.
 *
 * Written fresh for v1 rather than imported from tests/e2e/ui (v1 and v0 stay
 * separate in tests too), but the handshake is the same one
 * tests/e2e/conftest.py::authed_session performs, so a change to that flow
 * breaks every suite together instead of silently skipping this one.
 *
 *   oss    Django mock-login: form POST to /api/v1/login (302 + session), then
 *          GET /organization (csrftoken) and POST /organization/<id>/set.
 *   auth0  Cloud: the IdP owns the credential exchange, so start the login the
 *          way the Login button does, drive the hosted form in the browser
 *          and let the app complete its own callback.
 *
 * UNSTRACT_AUTH_MODE pins the mode; otherwise OSS is tried first and auth0 is
 * the fallback.
 */

import {
  type APIRequestContext,
  type BrowserContext,
  test as base,
  type Page,
} from "@playwright/test";
import {
  type AuthMode,
  BACKEND_URL,
  configuredAuthMode,
  FRONTEND_URL,
  ORG_ID,
  RIG_MANAGED,
} from "./env.ts";

/**
 * A seeded user's role. `admin` is the stack's seeded user; any other role
 * needs UNSTRACT_E2E_<ROLE>_USER and UNSTRACT_E2E_<ROLE>_PASSWORD, and a test
 * asking for a role with no credentials skips with that reason.
 */
export type Role = "admin" | (string & {});

interface Credentials {
  username: string;
  password: string;
}

function credentialsFor(role: Role): Credentials | null {
  const key = role.toUpperCase().replace(/[^A-Z0-9]/g, "_");
  const username = process.env[`UNSTRACT_E2E_${key}_USER`];
  const password = process.env[`UNSTRACT_E2E_${key}_PASSWORD`];
  if (username && password) {
    return { username, password };
  }
  if (role !== "admin") {
    return null;
  }
  // Same fallbacks as the `ui` suite, so one env file drives both.
  return {
    username:
      process.env.UNSTRACT_ADMIN_USER ??
      process.env.UNSTRACT_AUTH0_USER ??
      "unstract",
    password:
      process.env.UNSTRACT_ADMIN_PASSWORD ??
      process.env.UNSTRACT_AUTH0_PASSWORD ??
      "unstract",
  };
}

export interface Session {
  role: Role;
  mode: AuthMode;
  orgId: string;
  /** Shares cookies with the browser context, so API and UI are one user. */
  api: APIRequestContext;
  /** Headers a mutating API call needs (Django CSRF). */
  csrfHeaders(): Promise<Record<string, string>>;
}

export interface App {
  orgId: string;
  /** Opens an org-scoped route (`workflows` -> `/<orgId>/workflows`). */
  goto(route: string): ReturnType<Page["goto"]>;
}

interface Organization {
  id: string;
}

async function listOrgIds(context: BrowserContext): Promise<string[] | null> {
  const res = await context.request
    .get(`${BACKEND_URL}/api/v1/organization`, { failOnStatusCode: false })
    .catch(() => null);
  if (!res?.ok()) {
    return null;
  }
  const body = (await res.json()) as { organizations?: Organization[] };
  return (body.organizations ?? []).map((o) => o.id);
}

async function csrfHeaders(
  context: BrowserContext,
): Promise<Record<string, string>> {
  const token = (await context.cookies()).find(
    (c) => c.name === "csrftoken",
  )?.value;
  return token ? { "X-CSRFToken": token } : {};
}

/** Picks UNSTRACT_E2E_ORG_ID when the user belongs to it, else the first. */
async function selectOrg(context: BrowserContext): Promise<string | null> {
  const orgIds = await listOrgIds(context);
  if (!orgIds?.length) {
    return null;
  }
  if (ORG_ID && !orgIds.includes(ORG_ID)) {
    throw new Error(
      `UNSTRACT_E2E_ORG_ID=${ORG_ID} is not one of this user's organisations: ${orgIds.join(", ")}`,
    );
  }
  const orgId = ORG_ID ?? orgIds[0] ?? null;
  if (!orgId) {
    return null;
  }
  const res = await context.request.post(
    `${BACKEND_URL}/api/v1/organization/${orgId}/set`,
    { headers: await csrfHeaders(context), failOnStatusCode: false },
  );
  return res.ok() ? orgId : null;
}

async function loginOss(
  context: BrowserContext,
  creds: Credentials,
): Promise<string | null> {
  const login = await context.request
    .post(`${BACKEND_URL}/api/v1/login`, {
      form: { username: creds.username, password: creds.password },
      maxRedirects: 0,
      failOnStatusCode: false,
    })
    .catch(() => null);
  // 200 is the login form re-rendering: bad credentials, or not an OSS stack.
  if (login?.status() !== 302) {
    return null;
  }
  return await selectOrg(context);
}

/** Per IdP wait: the hosted form and the callback are a round trip to it. */
const AUTH0_STEP_TIMEOUT_MS = 20_000;

/**
 * The session fixture's own budget. Its setup counts against the test
 * timeout otherwise, and a slow failed login would surface as a generic
 * timeout instead of the skip or the sign-in error below.
 */
const SESSION_TIMEOUT_MS = 120_000;

/** Resolves true when `action` completes in time, false when it does not. */
function settled(action: Promise<unknown>): Promise<boolean> {
  return action.then(
    () => true,
    () => false,
  );
}

async function loginAuth0(
  page: Page,
  context: BrowserContext,
  creds: Credentials,
): Promise<string | null> {
  // `/` only renders the app's own login page. Its Login button navigates to
  // <app origin>/api/v1/login, and the backend builds the callback URL from
  // the Referer, so go there the same way.
  const appOrigin = new URL(FRONTEND_URL).origin;
  const opened = await settled(
    page.goto("/api/v1/login", {
      referer: `${appOrigin}/`,
      waitUntil: "domcontentloaded",
    }),
  );
  if (!opened) {
    return null;
  }
  // Still on the app means the IdP had a session and skipped its form.
  if (new URL(page.url()).origin !== appOrigin) {
    // Field names are stable across Auth0's Universal Login and classic Lock.
    const user = page
      .locator('input[name="username"], input[name="email"], input#username')
      .first();
    const password = page
      .locator('input[name="password"], input#password')
      .first();
    const submit = page
      .locator('button[type="submit"], button[name="action"]')
      .first();
    const timeout = AUTH0_STEP_TIMEOUT_MS;
    if (!(await settled(user.fill(creds.username, { timeout })))) {
      return null;
    }
    // Identifier-first tenants ask for the password on a second screen.
    if (
      !(await password.isVisible()) &&
      !(await settled(submit.click({ timeout })))
    ) {
      return null;
    }
    const signedIn =
      (await settled(password.fill(creds.password, { timeout }))) &&
      (await settled(submit.click({ timeout }))) &&
      // Wrong credentials, MFA or consent all leave the browser on the IdP.
      (await settled(
        page.waitForURL((url) => url.origin === appOrigin, { timeout }),
      ));
    if (!signedIn) {
      return null;
    }
  }
  // The callback bounces through the app; the landing URL differs by tenant.
  await page.waitForLoadState("networkidle").catch(() => null);
  return await selectOrg(context);
}

async function authenticate(
  page: Page,
  context: BrowserContext,
  creds: Credentials,
): Promise<{ orgId: string | null; mode: AuthMode }> {
  const mode = configuredAuthMode();
  if (mode !== "auth0") {
    const orgId = await loginOss(context, creds);
    if (orgId || mode === "oss") {
      return { orgId, mode: "oss" };
    }
  }
  return { orgId: await loginAuth0(page, context, creds), mode: "auth0" };
}

interface AuthFixtures {
  /** Which seeded user signs in: `test.use({ role: "viewer" })`. */
  role: Role;
  session: Session;
  app: App;
}

export const test = base.extend<AuthFixtures>({
  role: ["admin", { option: true }],

  session: [
    async ({ page, context, role }, use) => {
      const creds = credentialsFor(role);
      test.skip(
        !creds,
        `no credentials for role "${role}": set UNSTRACT_E2E_${role.toUpperCase()}_USER and _PASSWORD`,
      );
      if (!creds) {
        return;
      }
      const { orgId, mode } = await authenticate(page, context, creds);
      if (!orgId) {
        const reason =
          `could not sign in as "${role}" against ${BACKEND_URL} (mode=${mode}). ` +
          "Set UNSTRACT_AUTH_MODE=oss|auth0 plus credentials, or let the rig " +
          "boot a stack (`python -m tests.rig run frontend-v1-e2e`).";
        // Under the rig the stack is known to be up, so a failed login is a bug.
        if (RIG_MANAGED) {
          throw new Error(reason);
        }
        test.skip(true, reason);
        return;
      }
      await use({
        role,
        mode,
        orgId,
        api: context.request,
        csrfHeaders: () => csrfHeaders(context),
      });
    },
    { timeout: SESSION_TIMEOUT_MS },
  ],

  app: async ({ page, session }, use) => {
    await use({
      orgId: session.orgId,
      async goto(route) {
        const path = route.replace(/^\//, "");
        const response = await page.goto(`/${session.orgId}/${path}`, {
          waitUntil: "domcontentloaded",
        });
        // The SPA renders after hydration; wait for it, not a fixed sleep.
        await page.waitForLoadState("networkidle").catch(() => null);
        return response;
      },
    });
  },
});
