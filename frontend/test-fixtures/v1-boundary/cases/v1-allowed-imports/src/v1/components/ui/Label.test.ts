import { renderLabel } from "@v1/test/render";
import { expect, it } from "vitest";
import { label } from "./Label";

// Importing vitest here keeps typecheck:v1 honest about test typings.
it("renders", () => {
  expect(renderLabel(label("ok"))).toBe("OK");
});
