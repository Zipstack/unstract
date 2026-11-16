import { beforeEach, expect, it } from "vitest";
import {
  applyThemeMode,
  getPortalContainer,
  PORTAL_CONTAINER_ID,
} from "./portal";

beforeEach(() => {
  document.body.innerHTML = "";
});

it("creates one container under body with the v1 class and light by default", () => {
  const a = getPortalContainer();
  const b = getPortalContainer();
  expect(a).toBe(b);
  expect(a.id).toBe(PORTAL_CONTAINER_ID);
  expect(a.parentElement).toBe(document.body);
  expect(a.classList.contains("v1")).toBe(true);
  expect(a.dataset.theme).toBe("light");
});

it("copies the mode of an existing v1 root when created", () => {
  document.body.innerHTML = '<div class="v1" data-theme="dark"></div>';
  expect(getPortalContainer().dataset.theme).toBe("dark");
});

it("applyThemeMode updates every v1 element including the container", () => {
  document.body.innerHTML = '<div class="v1" data-theme="light"></div>';
  getPortalContainer();
  applyThemeMode(document, "unstract");
  const themes = [...document.querySelectorAll(".v1")].map(
    (el) => (el as HTMLElement).dataset.theme,
  );
  expect(themes).toEqual(["unstract", "unstract"]);
});
