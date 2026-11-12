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
 * the fallback. A failed sign-in names the step that failed and why, for
 * every mode it tried.
 */

import type {
  APIRequestContext,
  APIResponse,
  BrowserContext,
  Page,
} from "@playwright/test";
import {
  type AuthMode,
  BACKEND_URL,
  configuredAuthMode,
  FRONTEND_URL,
  ORG_ID,
  RIG_MANAGED,
} from "./env.ts";
import { settle } from "./settle.ts";
import { test as base } from "./tags.ts";

/**
 * A seeded user's role. `admin` is the stack's seeded user; any other role
 * needs UNSTRACT_E2E_<ROLE>_USER and UNSTRACT_E2E_<ROLE>_PASSWORD (see
 * `roleEnvKey`). A test asking for a role with no credentials skips with
 * that reason, and fails under the rig, which seeds only the admin.
 */
export type Role = "admin" | (string & {});

interface Credentials {
  username: string;
  password: string;
}

/** The `<ROLE>` in UNSTRACT_E2E_<ROLE>_USER / _PASSWORD. */
export function roleEnvKey(role: Role): string {
  return role.toUpperCase().replace(/[^A-Z0-9]/g, "_");
}

function credentialsFor(role: Role): Credentials | null {
  const key = roleEnvKey(role);
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
  /**
   * The role the test asked for. Not verified against the signed-in user:
   * credentials set for a role sign in as whoever they belong to, so a role
   * spec must check what it relies on.
   */
  role: Role;
  mode: AuthMode;
  /** For API calls: `/api/v1/unstract/<orgId>/...`. */
  orgId: string;
  /** For browser routes: the app's URLs carry the org's name, not its id. */
  orgName: string;
  /** The signed-in user's id, as the v0 session holds it (per-user v1 preferences). */
  userId: string;
  /** Shares cookies with the browser context, so API and UI are one user. */
  api: APIRequestContext;
  /** Headers a mutating API call needs (Django CSRF). */
  csrfHeaders(): Promise<Record<string, string>>;
}

export interface App {
  orgId: string;
  /** The `:orgName` route param for this session's organisation. */
  orgName: string;
  /** Opens an org-scoped route (`workflows` -> `/<orgName>/workflows`). */
  goto(route: string): ReturnType<Page["goto"]>;
}

export interface Organization {
  id: string;
  name: string;
}

/**
 * The organisation as the frontend sees it once it is set. Routes carry
 * `organization.name` from the set response (useSessionValid), which need not
 * equal the id (cloud: `org_…` id, slug name); the listed name is the fallback.
 */
export function routedOrganization(
  listed: Organization,
  setBody: unknown,
): Organization {
  const name = (setBody as { organization?: { name?: unknown } } | null)
    ?.organization?.name;
  return {
    id: listed.id,
    name: typeof name === "string" && name ? name : listed.name,
  };
}

/**
 * The signed-in user's id from the set response's `user`, which is what the
 * v0 session stores (useSessionValid) and hands the version switch.
 */
export function sessionUserId(setBody: unknown): string | null {
  const id = (setBody as { user?: { id?: unknown } } | null)?.user?.id;
  return typeof id === "string" || typeof id === "number" ? String(id) : null;
}

interface SignedIn {
  org: Organization;
  userId: string;
}

/**
 * A sign-in step's outcome. A failure keeps the step and why, so a failed
 * login says where it stopped, as tests/e2e/conftest.py does.
 */
type Failure = { ok: false; step: string; detail: string };
type Attempt<T> = { ok: true; value: T } | Failure;

function failed(step: string, detail: string): Failure {
  return { ok: false, step, detail };
}

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Resolves to the response, or to an Error when the request itself failed. */
function settledResponse(
  request: Promise<APIResponse>,
): Promise<APIResponse | Error> {
  return request.catch((err: unknown) => new Error(errorText(err)));
}

/** Status and the start of the body, for a failure message. No request data. */
async function describeResponse(res: APIResponse): Promise<string> {
  const body = await res.text().catch(() => "");
  return `${res.status()} ${body.slice(0, 200)}`.trim();
}

async function listOrgs(
  context: BrowserContext,
): Promise<Attempt<Organization[]>> {
  const step = "GET /api/v1/organization";
  const res = await settledResponse(
    context.request.get(`${BACKEND_URL}/api/v1/organization`, {
      failOnStatusCode: false,
    }),
  );
  if (res instanceof Error) {
    return failed(step, res.message);
  }
  if (!res.ok()) {
    return failed(step, await describeResponse(res));
  }
  const body = (await res.json()) as { organizations?: Organization[] };
  const orgs = body.organizations ?? [];
  return orgs.length
    ? { ok: true, value: orgs }
    : failed(step, "the user has no organisations");
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
async function selectOrg(context: BrowserContext): Promise<Attempt<SignedIn>> {
  const listed = await listOrgs(context);
  if (!listed.ok) {
    return listed;
  }
  const orgs = listed.value;
  const org = ORG_ID ? orgs.find((o) => o.id === ORG_ID) : orgs[0];
  if (!org) {
    throw new Error(
      `UNSTRACT_E2E_ORG_ID=${ORG_ID} is not one of this user's organisations: ${orgs.map((o) => o.id).join(", ")}`,
    );
  }
  const step = `POST /api/v1/organization/${org.id}/set`;
  const res = await settledResponse(
    context.request.post(`${BACKEND_URL}/api/v1/organization/${org.id}/set`, {
      headers: await csrfHeaders(context),
      failOnStatusCode: false,
    }),
  );
  if (res instanceof Error) {
    return failed(step, res.message);
  }
  if (!res.ok()) {
    return failed(step, await describeResponse(res));
  }
  const body: unknown = await res.json().catch(() => null);
  const userId = sessionUserId(body);
  if (!userId) {
    throw new Error(`${step} returned no user.id: ${JSON.stringify(body)}`);
  }
  return { ok: true, value: { org: routedOrganization(org, body), userId } };
}

async function loginOss(
  context: BrowserContext,
  creds: Credentials,
): Promise<Attempt<SignedIn>> {
  const step = "POST /api/v1/login";
  const login = await settledResponse(
    context.request.post(`${BACKEND_URL}/api/v1/login`, {
      form: { username: creds.username, password: creds.password },
      maxRedirects: 0,
      failOnStatusCode: false,
    }),
  );
  if (login instanceof Error) {
    return failed(step, login.message);
  }
  // 200 is the login form re-rendering: bad credentials, or not an OSS stack.
  if (login.status() !== 302) {
    return failed(step, `expected 302, got ${login.status()}`);
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

/** The error `action` threw, or null when it completed. */
function caught(action: Promise<unknown>): Promise<string | null> {
  return action.then(
    () => null,
    (err: unknown) => errorText(err),
  );
}

async function loginAuth0(
  page: Page,
  context: BrowserContext,
  creds: Credentials,
): Promise<Attempt<SignedIn>> {
  // `/` only renders the app's own login page. Its Login button navigates to
  // <app origin>/api/v1/login, and the backend builds the callback URL from
  // the Referer, so go there the same way.
  const appOrigin = new URL(FRONTEND_URL).origin;
  const openError = await caught(
    page.goto("/api/v1/login", {
      referer: `${appOrigin}/`,
      waitUntil: "domcontentloaded",
    }),
  );
  if (openError) {
    return failed("open /api/v1/login", openError);
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
    const steps: [string, () => Promise<unknown>][] = [
      ["fill the IdP username", () => user.fill(creds.username, { timeout })],
      [
        // Identifier-first tenants ask for the password on a second screen.
        "continue to the IdP password screen",
        async () => {
          if (!(await password.isVisible())) {
            await submit.click({ timeout });
          }
        },
      ],
      [
        "fill the IdP password",
        () => password.fill(creds.password, { timeout }),
      ],
      ["submit the IdP form", () => submit.click({ timeout })],
      [
        // Wrong credentials, MFA or consent all leave the browser on the IdP.
        "return to the app from the IdP",
        () => page.waitForURL((url) => url.origin === appOrigin, { timeout }),
      ],
    ];
    for (const [step, run] of steps) {
      const error = await caught(run()); // NOSONAR: sign-in steps run in order
      if (error) {
        return failed(step, `${error} (at ${page.url()})`);
      }
    }
  }
  // The callback bounces through the app; the landing URL differs by tenant.
  await settle(page);
  return await selectOrg(context);
}

function describeFailure(mode: AuthMode, failure: Failure): string {
  return `${mode}: ${failure.step} failed: ${failure.detail}`;
}

/**
 * Signs in by the configured mode. In auto mode OSS is tried first and auth0
 * after; when both fail, both failures are reported, since an OSS stack also
 * "fails" auth0 and the auth0 failure alone would point the wrong way.
 */
async function authenticate(
  page: Page,
  context: BrowserContext,
  creds: Credentials,
): Promise<{ signedIn: SignedIn | null; mode: AuthMode; failures: string[] }> {
  const mode = configuredAuthMode();
  const failures: string[] = [];
  if (mode !== "auth0") {
    const oss = await loginOss(context, creds);
    if (oss.ok) {
      return { signedIn: oss.value, mode: "oss", failures };
    }
    failures.push(describeFailure("oss", oss));
    if (mode === "oss") {
      return { signedIn: null, mode: "oss", failures };
    }
  }
  const auth0 = await loginAuth0(page, context, creds);
  if (auth0.ok) {
    return { signedIn: auth0.value, mode: "auth0", failures: [] };
  }
  failures.push(describeFailure("auth0", auth0));
  return { signedIn: null, mode: "auth0", failures };
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
      if (!creds) {
        const reason = `no credentials for role "${role}": set UNSTRACT_E2E_${roleEnvKey(role)}_USER and _PASSWORD`;
        // The rig provisions only the admin user, so a role spec under it
        // would skip on every run and still read green; a typo'd role too.
        if (RIG_MANAGED) {
          throw new Error(reason);
        }
        test.skip(true, reason);
        return;
      }
      const { signedIn, mode, failures } = await authenticate(
        page,
        context,
        creds,
      );
      if (!signedIn) {
        const reason =
          `could not sign in as "${role}" against ${BACKEND_URL} (UNSTRACT_AUTH_MODE=${configuredAuthMode()}):\n  ${failures.join("\n  ")}\n` +
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
        orgId: signedIn.org.id,
        orgName: signedIn.org.name,
        userId: signedIn.userId,
        api: context.request,
        csrfHeaders: () => csrfHeaders(context),
      });
    },
    { timeout: SESSION_TIMEOUT_MS },
  ],

  app: async ({ page, session }, use) => {
    await use({
      orgId: session.orgId,
      orgName: session.orgName,
      async goto(route) {
        const path = route.replace(/^\//, "");
        const response = await page.goto(`/${session.orgName}/${path}`, {
          waitUntil: "domcontentloaded",
        });
        // The SPA renders after hydration; wait for it, not a fixed sleep.
        await settle(page);
        return response;
      },
    });
  },
});
