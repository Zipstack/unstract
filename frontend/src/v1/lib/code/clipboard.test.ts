import { expect, it, vi } from "vitest";
import { copyText } from "./clipboard";

it("writes to the clipboard and reports it", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  await expect(copyText("hello")).resolves.toBe("copied");
  expect(writeText).toHaveBeenCalledWith("hello");
});

it("reports a refusal instead of throwing", async () => {
  vi.stubGlobal("navigator", {
    clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
  });
  await expect(copyText("x")).resolves.toBe("failed");
});

it("reports a missing Clipboard API as unavailable", async () => {
  vi.stubGlobal("navigator", {});
  await expect(copyText("x")).resolves.toBe("unavailable");
  vi.stubGlobal("navigator", undefined);
  await expect(copyText("x")).resolves.toBe("unavailable");
});
