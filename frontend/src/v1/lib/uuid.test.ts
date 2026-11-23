import { expect, it, vi } from "vitest";
import { newUuid } from "./uuid";

const V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

it("uses randomUUID where the browser has it", () => {
  expect(newUuid()).toMatch(V4);
});

it("builds a v4 UUID from random bytes outside a secure context", () => {
  vi.stubGlobal("crypto", {
    getRandomValues: (bytes: Uint8Array) => bytes.fill(0xff),
  });
  expect(newUuid()).toBe("ffffffff-ffff-4fff-bfff-ffffffffffff");
});
