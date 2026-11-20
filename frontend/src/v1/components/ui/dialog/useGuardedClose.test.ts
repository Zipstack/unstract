import { act, renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { type CloseGuard, useGuardedClose } from "./useGuardedClose";

function setup(guard: Omit<CloseGuard, "onOpenChange">) {
  const onOpenChange = vi.fn();
  const { result } = renderHook(() =>
    useGuardedClose({ ...guard, onOpenChange }),
  );
  return { request: result.current, onOpenChange };
}

it("opens and closes straight away with no guard", () => {
  const { request, onOpenChange } = setup({});
  request(true);
  request(false);
  expect(onOpenChange.mock.calls).toEqual([[true], [false]]);
});

it("ignores a close while busy", () => {
  const { request, onOpenChange } = setup({ busy: true });
  request(false);
  expect(onOpenChange).not.toHaveBeenCalled();
});

it("stays open when the guard says no and closes when it says yes", async () => {
  const beforeClose = vi
    .fn()
    .mockResolvedValueOnce(false)
    .mockReturnValue(true);
  const { request, onOpenChange } = setup({ beforeClose });
  await act(async () => request(false));
  expect(onOpenChange).not.toHaveBeenCalled();
  await act(async () => request(false));
  expect(onOpenChange).toHaveBeenCalledWith(false);
  expect(beforeClose).toHaveBeenCalledTimes(2);
});

it("asks once while the guard is still answering", async () => {
  let answer: (ok: boolean) => void = () => undefined;
  const beforeClose = vi.fn(
    () =>
      new Promise<boolean>((resolve) => {
        answer = resolve;
      }),
  );
  const { request, onOpenChange } = setup({ beforeClose });
  request(false);
  request(false);
  await act(async () => answer(true));
  expect(beforeClose).toHaveBeenCalledTimes(1);
  expect(onOpenChange).toHaveBeenCalledTimes(1);
});

it("stays open, logs and asks again after the guard throws", async () => {
  const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
  const beforeClose = vi
    .fn()
    .mockRejectedValueOnce(new Error("save failed"))
    .mockReturnValue(true);
  const { request, onOpenChange } = setup({ beforeClose });
  await act(async () => request(false));
  expect(onOpenChange).not.toHaveBeenCalled();
  expect(error).toHaveBeenCalledOnce();
  await act(async () => request(false));
  expect(onOpenChange).toHaveBeenCalledWith(false);
});
