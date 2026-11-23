import { act, renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { type CloseGuard, useGuardedClose } from "./useGuardedClose";

type Props = Omit<CloseGuard, "onOpenChange"> & Readonly<{ open?: boolean }>;

function setup(guard: Props) {
  const onOpenChange = vi.fn();
  const { result, rerender, unmount } = renderHook(
    ({ open = true, ...props }: Props) =>
      useGuardedClose({ ...props, open, onOpenChange }),
    { initialProps: guard },
  );
  const request = (open: boolean) => result.current(open);
  return { request, rerender, unmount, onOpenChange };
}

// A guard that waits for the test to answer each ask.
function pendingGuard() {
  const answers: Array<(ok: boolean) => void> = [];
  const beforeClose = vi.fn(
    () =>
      new Promise<boolean>((resolve) => {
        answers.push(resolve);
      }),
  );
  return { beforeClose, answers };
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
  const { beforeClose, answers } = pendingGuard();
  const { request, onOpenChange } = setup({ beforeClose });
  request(false);
  request(false);
  await act(async () => answers[0]?.(true));
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

it("ignores a yes that comes after the dialog turned busy", async () => {
  const { beforeClose, answers } = pendingGuard();
  const { request, rerender, onOpenChange } = setup({ beforeClose });
  request(false);
  rerender({ beforeClose, busy: true });
  await act(async () => answers[0]?.(true));
  expect(onOpenChange).not.toHaveBeenCalled();
  rerender({ beforeClose });
  request(false);
  expect(beforeClose).toHaveBeenCalledTimes(2);
});

it("ignores the answer to an ask from an earlier open", async () => {
  const { beforeClose, answers } = pendingGuard();
  const { request, rerender, onOpenChange } = setup({ beforeClose });
  request(false);
  rerender({ beforeClose, open: false });
  rerender({ beforeClose, open: true });
  request(false);
  expect(beforeClose).toHaveBeenCalledTimes(2);
  await act(async () => answers[0]?.(true));
  expect(onOpenChange).not.toHaveBeenCalled();
  await act(async () => answers[1]?.(true));
  expect(onOpenChange.mock.calls).toEqual([[false]]);
});

it("does not let an earlier open's no end the current ask", async () => {
  const { beforeClose, answers } = pendingGuard();
  const { request, rerender } = setup({ beforeClose });
  request(false);
  rerender({ beforeClose, open: false });
  rerender({ beforeClose, open: true });
  request(false);
  await act(async () => answers[0]?.(false));
  request(false);
  expect(beforeClose).toHaveBeenCalledTimes(2);
});

it("does not close again when a close from outside lands with the yes", async () => {
  const { beforeClose, answers } = pendingGuard();
  const { request, rerender, onOpenChange } = setup({ beforeClose });
  request(false);
  await act(async () => {
    answers[0]?.(true);
    await new Promise((done) => setTimeout(done, 0));
    rerender({ beforeClose, open: false });
  });
  expect(onOpenChange).not.toHaveBeenCalled();
});

it("ignores a yes that comes after the dialog unmounted", async () => {
  const { beforeClose, answers } = pendingGuard();
  const { request, unmount, onOpenChange } = setup({ beforeClose });
  request(false);
  unmount();
  await act(async () => answers[0]?.(true));
  expect(onOpenChange).not.toHaveBeenCalled();
});
