/**
 * Self-test: the env var a role's skip message names is the one
 * `credentialsFor()` reads, so following the hint takes effect.
 */

import { roleEnvKey } from "../../fixtures/auth.ts";
import { DIST, expect, test } from "../../fixtures/index.ts";

test.describe("harness: role credential env vars", { tag: DIST.all }, () => {
  test("non-alphanumerics in the role become underscores", () => {
    expect(`UNSTRACT_E2E_${roleEnvKey("org-admin")}_USER`).toBe(
      "UNSTRACT_E2E_ORG_ADMIN_USER",
    );
    expect(roleEnvKey("viewer")).toBe("VIEWER");
  });
});
