/**
 * Module-level store for the app-wide confirm dialog.
 *
 * antd's `Modal.confirm()` renders into a container it owns, so it survives the
 * caller unmounting. The shim's `Modal.useModal()` keeps that state in a hook
 * instead, which breaks whenever the trigger lives inside something that closes
 * on click — a Radix DropdownMenu unmounts its content, taking the hook and its
 * contextHolder with it. That is why Delete in a prompt card's kebab menu did
 * nothing at all: the dialog was requested, then destroyed in the same tick.
 *
 * Keeping the state outside React lets <ConfirmHost> (mounted once, near the
 * app root) render the dialog no matter which subtree asked for it.
 */

let current = null;
const listeners = new Set();

function emit() {
  for (const listener of listeners) {
    listener(current);
  }
}

/** Subscribe to dialog state. Returns an unsubscribe function. */
export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getConfirmState() {
  return current;
}

/**
 * Open the dialog. Resolves true on confirm, false on cancel/escape/outside
 * click, so a caller can `await` it instead of splitting across callbacks.
 */
export function openConfirm(options = {}) {
  return new Promise((resolve) => {
    // A second request supersedes the first; settle the old promise so nothing
    // is left pending forever.
    current?.resolve?.(false);
    current = {
      title: options.title ?? "Are you sure?",
      content: options.content ?? options.description ?? "",
      okText: options.okText ?? "Confirm",
      cancelText: options.cancelText ?? "Cancel",
      danger: options.danger ?? options.okType === "danger",
      onOk: options.onOk,
      onCancel: options.onCancel,
      resolve,
    };
    emit();
  });
}

/**
 * Drop any open dialog without settling it. For test teardown — the store
 * outlives a single render, so a dialog left open leaks `pointer-events: none`
 * on <body> into the next test.
 */
export function resetConfirm() {
  current = null;
  emit();
}

/** Settle the open dialog and clear it. */
export function settleConfirm(result) {
  const open = current;
  current = null;
  emit();
  if (!open) {
    return;
  }
  if (result) {
    open.onOk?.();
  } else {
    open.onCancel?.();
  }
  open.resolve?.(result);
}
