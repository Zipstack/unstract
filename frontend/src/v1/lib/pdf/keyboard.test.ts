import { expect, it } from "vitest";
import { viewerKeyAction } from "./keyboard";

it("maps paging and zoom keys", () => {
  expect(viewerKeyAction({ key: "PageUp" })).toBe("previous-page");
  expect(viewerKeyAction({ key: "PageDown" })).toBe("next-page");
  expect(viewerKeyAction({ key: "Home" })).toBe("first-page");
  expect(viewerKeyAction({ key: "End" })).toBe("last-page");
  expect(viewerKeyAction({ key: "+" })).toBe("zoom-in");
  expect(viewerKeyAction({ key: "=" })).toBe("zoom-in");
  expect(viewerKeyAction({ key: "-" })).toBe("zoom-out");
});

it("leaves other keys and modified keys to the browser", () => {
  expect(viewerKeyAction({ key: "ArrowDown" })).toBeNull();
  expect(viewerKeyAction({ key: "+", ctrlKey: true })).toBeNull();
  expect(viewerKeyAction({ key: "-", metaKey: true })).toBeNull();
  expect(viewerKeyAction({ key: "Home", altKey: true })).toBeNull();
});
