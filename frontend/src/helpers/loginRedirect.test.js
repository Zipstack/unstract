import { describe, expect, it } from "vitest";

import { getPostLoginPath } from "./loginRedirect.js";

describe("getPostLoginPath", () => {
  it("keeps the path and query of the page the visitor asked for", () => {
    expect(
      getPostLoginPath({
        pathname: "/acme/workflows",
        search: "?tab=runs",
        hash: "#top",
      }),
    ).toBe("/acme/workflows?tab=runs");
  });

  it.each([
    ["no location", undefined],
    ["the root path", { pathname: "/" }],
    ["a protocol-relative path", { pathname: "//evil.example/x" }],
    ["a backslash path", { pathname: "/\\evil.example/x" }],
    ["an absolute URL", { pathname: "https://evil.example/x" }],
    ["a scheme", { pathname: "javascript:alert(1)" }],
    ["a relative path", { pathname: "acme/workflows" }],
    ["a tab that collapses to //", { pathname: "/\t/evil.example" }],
  ])("returns null for %s", (_label, from) => {
    expect(getPostLoginPath(from)).toBeNull();
  });

  it("drops a search that is not a query string", () => {
    expect(
      getPostLoginPath({ pathname: "/acme/workflows", search: "//evil" }),
    ).toBe("/acme/workflows");
  });
});
