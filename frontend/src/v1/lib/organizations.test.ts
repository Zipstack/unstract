import { describe, expect, test } from "vitest";
import {
  describeOrganization,
  initial,
  initials,
  landingPath,
  organizationInitials,
  roleLabel,
} from "./organizations";

describe("roleLabel", () => {
  test.each([
    ["admin", "Admin"],
    ["unstract_admin", "Admin"],
    ["user", "Member"],
    ["unstract_user", "Member"],
    ["unstract_supervisor", "Supervisor"],
    ["unstract_reviewer", "Reviewer"],
  ])("%s reads %s", (role, label) => {
    expect(roleLabel(role)).toBe(label);
  });

  test("an unknown role is not guessed", () => {
    expect(roleLabel("auditor")).toBeUndefined();
    expect(roleLabel(undefined)).toBeUndefined();
  });
});

describe("describeOrganization", () => {
  test("role, member count and region, as frame NEW10 shows", () => {
    expect(
      describeOrganization({ role: "admin", member_count: 40, region: "US" }),
    ).toBe("Admin · 40 members · US");
  });

  test("one member is singular", () => {
    expect(describeOrganization({ role: "admin", member_count: 1 })).toBe(
      "Admin · 1 member",
    );
  });

  test("absent fields are left out, never guessed (OSS sends no region)", () => {
    expect(describeOrganization({ role: "user" })).toBe("Member");
    expect(describeOrganization({ member_count: 3 })).toBe("3 members");
    expect(describeOrganization({})).toBe("");
  });
});

describe("initials", () => {
  test.each([
    ["Zipstack", "Z"],
    ["Tanushree Daga", "TD"],
    ["Tanushree’s organisation", "TO"],
    ["  ", "?"],
  ])("%s gives %s", (name, expected) => {
    expect(initials(name)).toBe(expected);
  });
});

describe("initial", () => {
  test.each([
    ["Tanushree Daga", "T"],
    ["athul@zipstack.com", "A"],
    ["  ", "?"],
  ])("%s gives %s", (name, expected) => {
    expect(initial(name)).toBe(expected);
  });
});

describe("organizationInitials", () => {
  test.each([
    ["Zipstack", "ZI"],
    ["Tanushree’s organisation", "TO"],
    ["Acme Data Labs", "AD"],
    ["X", "X"],
    ["  ", "?"],
  ])("%s gives %s", (name, expected) => {
    expect(organizationInitials(name)).toBe(expected);
  });
});

describe("landingPath", () => {
  test("keeps the section in the new organisation", () => {
    expect(landingPath("/zipstack/workflows", "zipstack", "tanushree")).toBe(
      "/tanushree/workflows",
    );
  });

  test("drops anything under the section: that record may not exist there", () => {
    expect(
      landingPath("/zipstack/tools/123/settings", "zipstack", "tanushree"),
    ).toBe("/tanushree/tools");
  });

  test("falls back to the dashboard when the path has no section", () => {
    expect(landingPath("/zipstack", "zipstack", "tanushree")).toBe(
      "/tanushree/dashboard",
    );
    expect(landingPath("/zipstack/", "zipstack", "tanushree")).toBe(
      "/tanushree/dashboard",
    );
  });

  test("falls back to the dashboard outside the current organisation's paths", () => {
    expect(landingPath("/landing", "zipstack", "tanushree")).toBe(
      "/tanushree/dashboard",
    );
  });
});
