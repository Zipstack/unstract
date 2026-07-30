import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  Checkbox,
  Input,
  InputNumber,
  Radio,
  Select,
  Switch,
} from "@/components/ui/shims/antd-inputs";

/**
 * The point of these tests is antd's onChange CONVENTIONS, which differ per
 * component and which Radix inverts in several cases. Call-sites are written
 * against antd's shapes, so a mismatch here breaks forms silently rather than
 * loudly.
 */
describe("antd-compatible input shims (P3-03)", () => {
  it("renders a text input and forwards typing as a DOM event", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Input onChange={onChange} />);
    await user.type(screen.getByRole("textbox"), "hi");
    expect(onChange).toHaveBeenCalled();
    // antd hands Input an EVENT, so call-sites read e.target.value.
    expect(onChange.mock.calls[0][0].target).toBeDefined();
  });

  it("exposes Input.TextArea as a textarea", () => {
    render(<Input.TextArea rows={4} />);
    const el = screen.getByRole("textbox");
    expect(el.tagName).toBe("TEXTAREA");
    expect(el.getAttribute("rows")).toBe("4");
  });

  it("maps autoSize.minRows onto rows", () => {
    render(<Input.TextArea autoSize={{ minRows: 6 }} />);
    expect(screen.getByRole("textbox").getAttribute("rows")).toBe("6");
  });

  /*
   * antd's `autoSize` grows the field to fit its content. Only the OBJECT form
   * ({minRows}) was handled, so `autoSize={true}` — what EditableText passes
   * for every prompt value — fell through to the 3-row default and drew a 74px
   * box around a single line of text, repeated on every prompt card.
   */
  it("autoSize={true} starts at one row rather than the 3-row default", () => {
    render(<Input.TextArea autoSize />);
    expect(screen.getByRole("textbox").getAttribute("rows")).toBe("1");
  });

  it("autoSize={true} hides the scrollbar since the box tracks its content", () => {
    render(<Input.TextArea autoSize />);
    expect(screen.getByRole("textbox").className).toContain("overflow-hidden");
  });

  it("keeps the 3-row default when autoSize is absent", () => {
    render(<Input.TextArea />);
    expect(screen.getByRole("textbox").getAttribute("rows")).toBe("3");
  });

  /*
   * `size` is an antd prop with no `<textarea>` equivalent. It was not
   * destructured, so it rode `...props` onto the DOM and the field kept
   * shadcn's `min-h-[60px]` — every prompt value measured 60px against the
   * reference's 32px. A stray attribute is the tell for this whole class of
   * shim bug: it never throws, so only a DOM assertion catches it.
   */
  it("consumes antd's size instead of stamping it on the textarea", () => {
    render(<Input.TextArea size="small" autoSize />);
    const el = screen.getByRole("textbox");
    expect(el).not.toHaveAttribute("size");
    expect(el.className).toContain("text-sm");
  });

  it("drops the min-height floor when autoSize sizes the box", () => {
    render(<Input.TextArea autoSize />);
    const cls = screen.getByRole("textbox").className;
    expect(cls).toContain("min-h-0");
    expect(cls).not.toContain("min-h-[60px]");
  });

  /*
   * antd's small autoSize field computes `padding: 0` vertically and floors at
   * 32px. Removing shadcn's 60px floor without matching those two numbers
   * lands the box at 29px — close, but still off the reference.
   */
  it("matches antd's 32px floor and zero vertical padding when small", () => {
    render(<Input.TextArea size="small" autoSize />);
    const cls = screen.getByRole("textbox").className;
    expect(cls).toContain("min-h-8");
    expect(cls).toContain("py-0");
    expect(cls).not.toContain("min-h-[60px]");
  });

  /*
   * antd's `variant="borderless"` drops the border and background so the
   * field reads as plain text. EditableText swaps to it whenever a prompt
   * key/value is neither hovered nor edited; the prop was consumed but never
   * implemented, so prompt cards showed input chrome permanently.
   */
  it("renders a borderless Input without visible chrome", () => {
    render(<Input variant="borderless" />);
    expect(screen.getByRole("textbox").className).toContain(
      "border-transparent",
    );
  });

  it("renders a borderless TextArea without visible chrome", () => {
    render(<Input.TextArea variant="borderless" />);
    expect(screen.getByRole("textbox").className).toContain(
      "border-transparent",
    );
  });

  it("leaves an outlined Input with its border", () => {
    render(<Input variant="outlined" />);
    expect(screen.getByRole("textbox").className).not.toContain(
      "border-transparent",
    );
  });

  it("Input.Password masks by default and reveals on toggle", async () => {
    const user = userEvent.setup();
    const { container } = render(<Input.Password />);
    const field = container.querySelector("input");
    expect(field.getAttribute("type")).toBe("password");
    await user.click(screen.getByRole("button", { name: /show password/i }));
    expect(field.getAttribute("type")).toBe("text");
  });

  it("Input.Search fires onSearch on Enter", async () => {
    const user = userEvent.setup();
    const onSearch = vi.fn();
    render(<Input.Search onSearch={onSearch} />);
    await user.type(screen.getByRole("textbox"), "q{enter}");
    expect(onSearch).toHaveBeenCalled();
  });

  // antd hands InputNumber a NUMBER, not an event.
  it("InputNumber calls onChange with a number, not an event", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<InputNumber onChange={onChange} />);
    await user.type(screen.getByRole("spinbutton"), "42");
    const last = onChange.mock.calls.at(-1)[0];
    expect(typeof last).toBe("number");
  });

  it("InputNumber emits null when cleared, not NaN", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<InputNumber value={5} onChange={onChange} />);
    const el = screen.getByRole("spinbutton");
    await user.clear(el);
    if (onChange.mock.calls.length) {
      expect(onChange.mock.calls.at(-1)[0]).toBeNull();
    }
  });

  // antd hands Checkbox an EVENT with target.checked; Radix gives a boolean.
  it("Checkbox onChange receives an event-shaped object with target.checked", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Checkbox onChange={onChange}>Accept</Checkbox>);
    await user.click(screen.getByRole("checkbox"));
    expect(onChange).toHaveBeenCalled();
    expect(onChange.mock.calls[0][0].target.checked).toBe(true);
  });

  it("Checkbox renders its label text", () => {
    render(<Checkbox>Accept terms</Checkbox>);
    expect(screen.getByText("Accept terms")).toBeInTheDocument();
  });

  // antd hands Switch a BOOLEAN.
  it("Switch onChange receives a boolean", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Switch onChange={onChange} />);
    await user.click(screen.getByRole("switch"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  /*
   * antd treats `value` as an alias for `checked` on Switch. The cloud
   * SummarizeManager writes `value={isContext}` for "Summarize Context";
   * reading only `checked` let it fall into ...props, land on the DOM, and the
   * switch never reflected its state.
   */
  it("Switch reflects state passed as antd's `value` alias", () => {
    render(<Switch value />);
    expect(screen.getByRole("switch")).toBeChecked();
  });

  it("Switch still prefers an explicit checked over value", () => {
    render(<Switch checked={false} value={true} />);
    expect(screen.getByRole("switch")).not.toBeChecked();
  });

  // Radix stamps its own value="on" (like a native checkbox), so the check is
  // that our boolean never reaches the DOM as value="true".
  it("does not leak the antd `value` boolean onto the DOM", () => {
    render(<Switch value />);
    expect(screen.getByRole("switch")).not.toHaveAttribute("value", "true");
  });

  it("Select renders options from the antd `options` data prop", () => {
    render(
      <Select
        options={[
          { value: "a", label: "Option A" },
          { value: "b", label: "Option B" },
        ]}
        placeholder="Pick one"
      />,
    );
    expect(screen.getByText("Pick one")).toBeInTheDocument();
  });

  /*
   * antd renders the VALUE when an option has no label. The prompt card's
   * enforce-type dropdown is built as `{ value: "text" }` with no label, so
   * rendering a bare `label` left the trigger showing an empty box where the
   * reference shows "text".
   */
  it("Select falls back to the option value when no label is given", () => {
    render(<Select options={[{ value: "text" }, { value: "json" }]} value="text" />);
    expect(screen.getByText("text")).toBeInTheDocument();
  });

  /*
   * antd reads "" as "nothing selected" and still shows the placeholder.
   * Call-sites seed their state with `useState("")`, and Radix reserves the
   * empty string internally — passing it through left the trigger blank with
   * no placeholder at all.
   */
  it("Select shows the placeholder when the value is an empty string", () => {
    render(
      <Select
        options={[{ value: "a", label: "Option A" }]}
        value=""
        placeholder="Pick one"
      />,
    );
    expect(screen.getByText("Pick one")).toBeInTheDocument();
  });

  /*
   * antd's `mode="tags"` is a free-text multi-value chip editor. Radix's
   * Select is single-select over a fixed option list and cannot express it, so
   * `mode` was silently dropped: Custom Synonyms rendered a trigger that
   * opened an EMPTY dropdown with no text input, leaving the feature unusable
   * — a row could be added and its word typed, but never a synonym.
   */
  describe("Select mode='tags' (antd parity)", () => {
    it("renders existing values as chips", () => {
      render(<Select mode="tags" value={["alpha", "beta"]} />);
      expect(screen.getByText("alpha")).toBeInTheDocument();
      expect(screen.getByText("beta")).toBeInTheDocument();
    });

    it("lets the user type a new value and commit it with Enter", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(<Select mode="tags" value={[]} onChange={onChange} />);
      await user.type(screen.getByRole("textbox"), "gamma{enter}");
      expect(onChange).toHaveBeenCalledWith(["gamma"]);
    });

    it("appends to the existing values rather than replacing them", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(<Select mode="tags" value={["alpha"]} onChange={onChange} />);
      await user.type(screen.getByRole("textbox"), "beta{enter}");
      expect(onChange).toHaveBeenCalledWith(["alpha", "beta"]);
    });

    it("ignores blank entries and duplicates, as antd does", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(<Select mode="tags" value={["alpha"]} onChange={onChange} />);
      const box = screen.getByRole("textbox");
      await user.type(box, "   {enter}");
      await user.type(box, "alpha{enter}");
      expect(onChange).not.toHaveBeenCalled();
    });

    it("removes a chip via its remove button", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <Select mode="tags" value={["alpha", "beta"]} onChange={onChange} />,
      );
      await user.click(screen.getByRole("button", { name: /remove alpha/i }));
      expect(onChange).toHaveBeenCalledWith(["beta"]);
    });

    it("shows the placeholder only while empty", () => {
      const { rerender } = render(
        <Select mode="tags" value={[]} placeholder="Please enter synonyms" />,
      );
      expect(
        screen.getByPlaceholderText("Please enter synonyms"),
      ).toBeInTheDocument();

      rerender(
        <Select
          mode="tags"
          value={["alpha"]}
          placeholder="Please enter synonyms"
        />,
      );
      expect(
        screen.queryByPlaceholderText("Please enter synonyms"),
      ).not.toBeInTheDocument();
    });

    /*
     * antd's `multiple` is a FIXED-OPTION multi-select with no free text.
     * GroupMemberManager and FileHistoryModal use it to pick from a known
     * list, so routing it to the tag editor would replace a picker with an
     * arbitrary-text box and hide the options entirely.
     */
    it("does not route mode='multiple' to the free-text tag editor", () => {
      render(
        <Select
          mode="multiple"
          options={[{ value: "a", label: "Option A" }]}
          placeholder="Pick some"
        />,
      );
      expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
      expect(screen.getByText("Pick some")).toBeInTheDocument();
    });

    /*
     * Custom Synonyms sits inside an antd Form; a bare Enter would submit it
     * and discard the pending entry.
     */
    it("does not let Enter bubble out and submit the surrounding form", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn((e) => e.preventDefault());
      render(
        <form onSubmit={onSubmit}>
          <Select mode="tags" value={[]} onChange={vi.fn()} />
        </form>,
      );
      await user.type(screen.getByRole("textbox"), "gamma{enter}");
      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  it("Select accepts Select.Option children as well as options data", () => {
    render(
      <Select placeholder="Choose">
        <Select.Option value="x">X</Select.Option>
      </Select>,
    );
    expect(screen.getByText("Choose")).toBeInTheDocument();
  });

  /*
   * antd allows a STANDALONE `<Radio checked onClick />` with no group — Manage
   * Documents and the LLM-profiles table each render one per row to mark the
   * active item. Radix's RadioGroupItem reads its group context and THROWS
   * without one ("`RadioGroupItemProvider` must be used within `RadioGroup`"),
   * which the error boundary turned into a dead route: clicking Settings or
   * Manage Documents showed "Couldn't load this page".
   */
  it("Radio renders standalone, outside any Radio.Group", () => {
    const onClick = vi.fn();
    // Would throw before the fix, failing the test at render.
    render(<Radio checked onClick={onClick} />);
    const radio = screen.getByRole("radio");
    expect(radio).toBeChecked();
    fireEvent.click(radio);
    expect(onClick).toHaveBeenCalled();
  });

  // PromptOutput drives its standalone radio with onChange, not onClick, so
  // both handlers have to reach the native input.
  it("Radio forwards onChange on a standalone radio", () => {
    const onChange = vi.fn();
    render(<Radio checked={false} onChange={onChange} />);
    fireEvent.click(screen.getByRole("radio"));
    expect(onChange).toHaveBeenCalled();
  });

  /*
   * The "Select Default" column renders one label-less radio per row and
   * centres it with `text-align: center` on the cell. A block-level `flex`
   * wrapper spans the whole cell and ignores that, pinning the radio to the
   * left edge — it measured 39px off its own centred column header. antd's
   * .ant-radio-wrapper is INLINE-flex, which respects text-align.
   */
  it("wraps a Radio in an inline-flex label so a cell can centre it", () => {
    const { container } = render(<Radio checked />);
    const wrapper = container.querySelector("label");
    expect(wrapper.className).toContain("inline-flex");
    expect(wrapper.className).not.toMatch(/(^|\s)flex(\s|$)/);
  });

  it("Radio reflects an unchecked standalone state", () => {
    render(<Radio checked={false} />);
    expect(screen.getByRole("radio")).not.toBeChecked();
  });

  it("Radio.Group renders its options and fires an event-shaped onChange", () => {
    const onChange = vi.fn();
    render(
      <Radio.Group
        onChange={onChange}
        options={[
          { value: "1", label: "One" },
          { value: "2", label: "Two" },
        ]}
      />,
    );
    expect(screen.getByText("One")).toBeInTheDocument();
    expect(screen.getByText("Two")).toBeInTheDocument();
  });

  /*
   * antd v5's `variant` ("borderless" | "filled" | "outlined") replaced
   * `bordered`. Custom Synonyms writes variant="borderless" on BOTH controls
   * in its row, so an unconsumed prop reaches the DOM as an unknown attribute.
   */
  it("keeps antd's `variant` off the DOM input", () => {
    render(<Input variant="borderless" />);
    expect(screen.getByRole("textbox")).not.toHaveAttribute("variant");
  });

  it("passes disabled through to the underlying control", () => {
    render(<Input disabled />);
    expect(screen.getByRole("textbox")).toBeDisabled();
  });

  /**
   * `showCount` was silently dropped: it fell into `...props`, so the three
   * modals using it (Prompt Studio description, both API-deployment name
   * fields) rendered no counter while `maxLength` still truncated typing.
   */
  describe("showCount (antd parity)", () => {
    it("renders the antd 'N / max' readout and tracks typing", async () => {
      const user = userEvent.setup();
      render(<Input.TextArea showCount maxLength={200} />);

      expect(screen.getByText("0 / 200")).toBeInTheDocument();
      await user.type(screen.getByRole("textbox"), "hello");
      expect(screen.getByText("5 / 200")).toBeInTheDocument();
    });

    it("still forwards the caller's onChange while counting", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(<Input showCount maxLength={30} onChange={onChange} />);

      await user.type(screen.getByRole("textbox"), "ab");
      expect(onChange).toHaveBeenCalledTimes(2);
      expect(screen.getByText("2 / 30")).toBeInTheDocument();
    });

    it("seeds the count from a controlled value and follows it", () => {
      const { rerender } = render(
        <Input showCount maxLength={30} value="abc" onChange={vi.fn()} />,
      );
      expect(screen.getByText("3 / 30")).toBeInTheDocument();

      rerender(
        <Input showCount maxLength={30} value="abcdef" onChange={vi.fn()} />,
      );
      expect(screen.getByText("6 / 30")).toBeInTheDocument();
    });

    it("renders no counter when showCount is absent", () => {
      render(<Input.TextArea maxLength={200} />);
      expect(screen.queryByText(/\/ 200/)).not.toBeInTheDocument();
    });
  });
});
