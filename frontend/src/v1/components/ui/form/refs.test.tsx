import { render, screen } from "@testing-library/react";
import { createRef, type JSX, type Ref } from "react";
import { expect, it, vi } from "vitest";
import { PromptTextarea } from "./PromptTextarea";
import { SearchField } from "./SearchField";
import { SecretField } from "./SecretField";

// These three keep their own ref to the node, so the caller's ref goes through composeRefs.
const COMPOSED: [string, (ref: Ref<never>) => JSX.Element][] = [
  ["PromptTextarea", (ref) => <PromptTextarea aria-label="C" ref={ref} />],
  ["SearchField", (ref) => <SearchField aria-label="C" ref={ref} />],
  [
    "SecretField",
    (ref) => (
      <SecretField aria-label="C" ref={ref} onCopyResult={() => undefined} />
    ),
  ],
];

it.each(COMPOSED)("forwards an object ref to the %s control", (_, make) => {
  const ref = createRef<HTMLElement>();
  const { unmount } = render(make(ref as Ref<never>));
  expect(ref.current).toBe(screen.getByLabelText("C"));
  unmount();
  expect(ref.current).toBeNull();
});

it.each(COMPOSED)("forwards a callback ref to the %s control", (_, make) => {
  const ref = vi.fn();
  const { unmount } = render(make(ref));
  expect(ref).toHaveBeenCalledWith(screen.getByLabelText("C"));
  unmount();
  expect(ref).toHaveBeenLastCalledWith(null);
});
