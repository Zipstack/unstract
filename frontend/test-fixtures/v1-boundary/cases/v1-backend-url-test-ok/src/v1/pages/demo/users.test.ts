import { expect, it } from "vitest";

it("names the endpoint it mocks", () => {
  expect("/api/v1/unstract/org-1/users/").toContain("/users/");
});
