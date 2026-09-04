import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

/**
 * Radix announces its own uncontrolled-to-controlled switch by calling
 * `onValueChange("")`.
 *
 * The shim's `toValue` maps antd's "nothing selected" (`""`/null) to
 * `undefined`, because Radix reserves the empty string and would otherwise
 * blank the trigger AND suppress the placeholder. That mapping leaves Radix
 * uncontrolled until a real value arrives — and when one does, Radix emits the
 * `""` above. Forwarding it wrote emptiness back over the value that had just
 * landed, so an antd form seeding a Select through `setFieldsValue` saw the
 * field wiped in the same tick. Prompt Studio's Limit-to Section rendered
 * blank on every edit for exactly this, despite the profile carrying
 * "Default".
 *
 * This lives in its own file because pinning the behaviour means intercepting
 * the callback the shim hands to Radix's Root, and that module mock would
 * otherwise apply to every Select test in the main file.
 *
 * jsdom does NOT reproduce the emission on its own — it warns about the
 * controlled switch but never invokes the callback, so driving this through a
 * rerender asserts nothing. Calling Radix's callback directly is what gives
 * the test teeth.
 */

const captured = { onValueChange: null };

vi.mock("@/components/ui/select", async () => {
  const actual = await vi.importActual("@/components/ui/select");
  return {
    ...actual,
    Select: ({ onValueChange, ...props }) => {
      captured.onValueChange = onValueChange;
      return <actual.Select onValueChange={onValueChange} {...props} />;
    },
  };
});

const { Select } = await import("@/components/ui/shims/antd-inputs");

describe("Select controlled/uncontrolled transition (Radix parity)", () => {
  it("drops the empty string Radix reports, keeping the seeded value", () => {
    const onChange = vi.fn();
    render(
      <Select
        options={[{ value: "Default" }]}
        value="Default"
        onChange={onChange}
      />,
    );

    captured.onValueChange("");

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText("Default")).toBeInTheDocument();
  });

  // The guard must not swallow real selections: Radix rejects a SelectItem
  // whose value is "", so every other value it reports IS a user choice.
  it("still forwards a real selection", () => {
    const onChange = vi.fn();
    render(
      <Select
        options={[{ value: "Default" }, { value: "Other" }]}
        value=""
        onChange={onChange}
      />,
    );

    captured.onValueChange("Other");

    expect(onChange).toHaveBeenCalledWith("Other", expect.anything());
  });
});
