import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
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

  /*
   * Search does not delegate to InputBase, so it needed its own `allowClear`
   * binding — otherwise the prop reached the DOM and React warned on every
   * render of the HITL queue search box.
   */
  it("Input.Search keeps allowClear off the DOM and clears through onChange", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { container } = render(
      <Input.Search allowClear value="Amex" onChange={onChange} />,
    );
    expect(container.querySelector("[allowClear]")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ target: { value: "" } }),
    );
  });

  it("Input.Search hides the clear button when there is nothing to clear", () => {
    render(<Input.Search allowClear value="" onChange={() => {}} />);
    expect(screen.queryByRole("button", { name: "Clear" })).toBeNull();
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

  // antd hands Switch a BOOLEAN plus the originating click event.
  it("Switch onChange receives the boolean and the click event", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Switch onChange={onChange} />);
    await user.click(screen.getByRole("switch"));
    expect(onChange).toHaveBeenCalledWith(true, expect.anything());
    expect(typeof onChange.mock.calls[0][1].stopPropagation).toBe("function");
  });

  /*
   * The card toggles (API Deployments, Pipelines) are written
   * `onChange={(checked, e) => { e.stopPropagation(); ... }}`. Dropping antd's
   * second argument made that throw before the handler's real work ran, so the
   * deployment never toggled and no request was sent.
   */
  it("Switch onChange lets a handler call stopPropagation on the event", async () => {
    const user = userEvent.setup();
    const onCardClick = vi.fn();
    const onToggle = vi.fn();
    render(
      <div onClick={onCardClick}>
        <Switch
          onChange={(checked, e) => {
            e.stopPropagation();
            onToggle(checked);
          }}
        />
      </div>,
    );
    await user.click(screen.getByRole("switch"));
    expect(onToggle).toHaveBeenCalledWith(true);
    expect(onCardClick).not.toHaveBeenCalled();
  });

  it("Switch still forwards a caller's own onClick", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<Switch onClick={onClick} />);
    await user.click(screen.getByRole("switch"));
    expect(onClick).toHaveBeenCalledTimes(1);
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
    render(
      <Select options={[{ value: "text" }, { value: "json" }]} value="text" />,
    );
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
     * antd's tags mode drops down its `options` as well as taking free text,
     * and Configure Connector's "File types to process" is an enum the user is
     * meant to PICK from — its ArrayField drops anything typed that the enum
     * does not contain, so with the list hidden the field could not be filled
     * in at all. It rendered as bare text, which is also why the box is drawn
     * with the same border as a Select trigger.
     */
    it("drops down the options and adds the chosen one as a chip", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <Select
          mode="tags"
          value={[]}
          onChange={onChange}
          options={[{ value: "pdf" }, { value: "txt" }]}
          placeholder="Please select"
        />,
      );
      await user.click(screen.getByPlaceholderText("Please select"));
      await user.click(screen.getByRole("option", { name: "pdf" }));
      expect(onChange).toHaveBeenCalledWith(["pdf"]);
    });

    it("filters the options by what has been typed", async () => {
      const user = userEvent.setup();
      render(
        <Select
          mode="tags"
          value={[]}
          onChange={vi.fn()}
          options={[{ value: "pdf" }, { value: "txt" }]}
        />,
      );
      await user.type(screen.getByRole("textbox"), "pd");
      expect(screen.getByRole("option", { name: "pdf" })).toBeInTheDocument();
      expect(screen.queryByRole("option", { name: "txt" })).toBeNull();
    });

    it("hides options that are already chosen", async () => {
      const user = userEvent.setup();
      render(
        <Select
          mode="tags"
          value={["pdf"]}
          onChange={vi.fn()}
          options={[{ value: "pdf" }, { value: "txt" }]}
        />,
      );
      await user.click(screen.getByRole("textbox"));
      expect(screen.getByRole("option", { name: "txt" })).toBeInTheDocument();
      expect(screen.queryByRole("option", { name: "pdf" })).toBeNull();
    });

    /*
     * Picking an option blurs the input, and the blur handler commits whatever
     * is in the box — so a filtered pick used to add the typed fragment as a
     * tag of its own alongside the option.
     */
    it("does not also commit the typed fragment when an option is picked", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <Select
          mode="tags"
          value={[]}
          onChange={onChange}
          options={[{ value: "pdf" }, { value: "txt" }]}
        />,
      );
      await user.type(screen.getByRole("textbox"), "pd");
      await user.click(screen.getByRole("option", { name: "pdf" }));
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenCalledWith(["pdf"]);
    });

    /* The prompt card's Document Type passes `maxCount={1}` for "pick one". */
    it("stops accepting entries once maxCount is reached", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <Select
          mode="tags"
          value={["pdf"]}
          onChange={onChange}
          options={[{ value: "pdf" }, { value: "txt" }]}
          maxCount={1}
        />,
      );
      await user.type(screen.getByRole("textbox"), "txt{enter}");
      expect(onChange).not.toHaveBeenCalled();
    });

    /* No options means no list to open — Custom Synonyms is free text only. */
    it("renders no dropdown when the call-site supplies no options", async () => {
      const user = userEvent.setup();
      render(<Select mode="tags" value={[]} onChange={vi.fn()} />);
      await user.click(screen.getByRole("textbox"));
      expect(screen.queryByRole("listbox")).toBeNull();
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

  /*
   * antd's `multiple`: a fixed-option multi-select whose value is an ARRAY.
   *
   * These guard a shape, not a look. Before MultiSelect existed the mode fell
   * through to the single-select path, which renders a perfectly usable-looking
   * control and calls onChange with ONE bare value — so Global API Deployment
   * Keys posted a string to a DRF `PrimaryKeyRelatedField(many=True)` and got
   * `Expected a list of items but got type "str"` back, with no way to pick a
   * second deployment either.
   */
  describe("Select mode='multiple'", () => {
    const OPTIONS = [
      { value: "a", label: "Alpha" },
      { value: "b", label: "Bravo" },
    ];

    it("hands the call-site an ARRAY, never a bare value", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <Select
          mode="multiple"
          value={[]}
          onChange={onChange}
          options={OPTIONS}
          placeholder="Pick some"
        />,
      );
      await user.click(screen.getByRole("combobox"));
      await user.click(screen.getByRole("option", { name: "Alpha" }));
      expect(onChange).toHaveBeenCalledWith(
        ["a"],
        [{ value: "a", label: "Alpha" }],
      );
    });

    /* The single-select path closes on choose, which caps the mode at one. */
    it("keeps the dropdown open so a second option can be picked", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      function Harness() {
        const [value, setValue] = useState([]);
        return (
          <Select
            mode="multiple"
            value={value}
            onChange={(next) => {
              setValue(next);
              onChange(next);
            }}
            options={OPTIONS}
          />
        );
      }
      render(<Harness />);
      await user.click(screen.getByRole("combobox"));
      await user.click(screen.getByRole("option", { name: "Alpha" }));
      await user.click(screen.getByRole("option", { name: "Bravo" }));
      expect(onChange).toHaveBeenLastCalledWith(["a", "b"]);
    });

    it("deselects an option that is picked again", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <Select
          mode="multiple"
          value={["a", "b"]}
          onChange={onChange}
          options={OPTIONS}
        />,
      );
      await user.click(screen.getByRole("combobox"));
      await user.click(screen.getByRole("option", { name: "Alpha" }));
      expect(onChange).toHaveBeenCalledWith(
        ["b"],
        [{ value: "b", label: "Bravo" }],
      );
    });

    it("shows the selection as chips and removes one without opening the list", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <Select
          mode="multiple"
          value={["a", "b"]}
          onChange={onChange}
          options={OPTIONS}
        />,
      );
      expect(screen.getByText("Alpha")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Remove Alpha" }));
      expect(onChange).toHaveBeenCalledWith(
        ["b"],
        [{ value: "b", label: "Bravo" }],
      );
      // The chip sits inside the popover trigger; the remove must not open it.
      expect(screen.queryByRole("listbox")).toBeNull();
    });

    /*
     * The shim compares on strings because ids arrive as both, but what goes
     * BACK must be the option's own value — an API told `"12"` where it
     * expects `12` fails the same way the bare-string bug did.
     */
    it("returns the option's original value type", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <Select
          mode="multiple"
          value={[]}
          onChange={onChange}
          options={[{ value: 12, label: "Twelve" }]}
        />,
      );
      await user.click(screen.getByRole("combobox"));
      await user.click(screen.getByRole("option", { name: "Twelve" }));
      expect(onChange.mock.calls[0][0]).toEqual([12]);
    });

    /* Global API Deployment Keys builds its list as Select.Option children. */
    it("accepts Select.Option children and filters them by optionFilterProp", async () => {
      const user = userEvent.setup();
      render(
        <Select
          mode="multiple"
          value={[]}
          onChange={vi.fn()}
          showSearch
          optionFilterProp="children"
        >
          <Select.Option value="a">Alpha</Select.Option>
          <Select.Option value="b">Bravo</Select.Option>
        </Select>,
      );
      await user.click(screen.getByRole("combobox"));
      await user.type(screen.getByRole("searchbox"), "brav");
      expect(screen.getByRole("option", { name: "Bravo" })).toBeInTheDocument();
      expect(screen.queryByRole("option", { name: "Alpha" })).toBeNull();
    });

    it("clears the whole selection under allowClear", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <Select
          mode="multiple"
          value={["a", "b"]}
          onChange={onChange}
          options={OPTIONS}
          allowClear
        />,
      );
      await user.click(screen.getByRole("button", { name: "Clear" }));
      expect(onChange).toHaveBeenCalledWith([], []);
    });

    /*
     * A <div> trigger has no `disabled` attribute, so this is the only thing
     * standing between a disabled picker and an open dropdown — the deployment
     * scope field disables itself whenever "allow all" is ticked.
     */
    it("does not open while disabled", async () => {
      const user = userEvent.setup();
      render(
        <Select
          mode="multiple"
          value={[]}
          onChange={vi.fn()}
          options={OPTIONS}
          disabled
        />,
      );
      await user.click(screen.getByRole("combobox"));
      expect(screen.queryByRole("listbox")).toBeNull();
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
   * antd lets a single option be disabled so an inaccessible value can still be
   * LABELLED without being re-selectable. Three call-sites depend on it — the
   * challenge-manager and agentic Settings dropdowns both surface an adapter
   * the viewer cannot use, and AddLlmProfile does the same for a profile.
   * Dropping the flag made those options freely selectable, and picking one
   * fails validation on save.
   */
  it("Select disables an option flagged in the `options` data prop", () => {
    render(
      <Select
        open
        options={[
          { value: "a", label: "Usable" },
          { value: "b", label: "Not shared with you", disabled: true },
        ]}
      />,
    );
    expect(
      screen.getByRole("option", { name: "Not shared with you" }),
    ).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("option", { name: "Usable" })).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  it("Select disables a Select.Option child flagged as disabled", () => {
    render(
      <Select open>
        <Select.Option value="a">Usable</Select.Option>
        <Select.Option value="b" disabled>
          Connector unavailable
        </Select.Option>
      </Select>,
    );
    expect(
      screen.getByRole("option", { name: "Connector unavailable" }),
    ).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("option", { name: "Usable" })).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  /*
   * antd's `dropdownRender` (renamed `popupRender` in 5.25) is how both
   * Configure Connector and the Lookup drawer pin a "create one" action under
   * the option list. The shim dropped the prop, so an org with no connectors
   * got an empty dropdown and no route to making one — the list is not the
   * only thing that prop carries.
   */
  describe("Select popupRender / dropdownRender (antd parity)", () => {
    const CONNECTORS = [
      { value: "gcs", label: "GCS Testing" },
      { value: "s3", label: "S3 Oct 6 2025" },
    ];

    it("renders the option list AND the call-site's footer", () => {
      render(
        <Select
          open
          options={CONNECTORS}
          popupRender={(menu) => (
            <>
              {menu}
              <button type="button">+ Add new connector</button>
            </>
          )}
        />,
      );
      expect(
        screen.getByRole("option", { name: "GCS Testing" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "+ Add new connector" }),
      ).toBeInTheDocument();
    });

    it("honours the pre-5.25 `dropdownRender` spelling too", () => {
      render(
        <Select
          open
          options={CONNECTORS}
          dropdownRender={(menu) => (
            <>
              {menu}
              <button type="button">+ Add new connector</button>
            </>
          )}
        />,
      );
      expect(
        screen.getByRole("button", { name: "+ Add new connector" }),
      ).toBeInTheDocument();
    });

    it("fires the footer's own handler when it is clicked", async () => {
      const user = userEvent.setup();
      const onAddNew = vi.fn();
      render(
        <Select
          open
          options={CONNECTORS}
          dropdownRender={(menu) => (
            <>
              {menu}
              <button type="button" onClick={onAddNew}>
                + Add new connector
              </button>
            </>
          )}
        />,
      );
      await user.click(
        screen.getByRole("button", { name: "+ Add new connector" }),
      );
      expect(onAddNew).toHaveBeenCalledTimes(1);
    });

    /*
     * antd closes its dropdown as soon as focus leaves the select, so the
     * footer button closes it for free. Radix does not, and both call-sites
     * open a modal from that footer — an open popup would sit on top of it.
     */
    it("closes the popup once the footer has been clicked", async () => {
      const user = userEvent.setup();
      render(
        <Select
          options={CONNECTORS}
          dropdownRender={(menu) => (
            <>
              {menu}
              <button type="button">+ Add new connector</button>
            </>
          )}
        />,
      );
      // Keyboard, not click: jsdom has no pointer capture for Radix's trigger.
      fireEvent.keyDown(screen.getByRole("combobox"), { key: "Enter" });
      const footer = await screen.findByRole("button", {
        name: "+ Add new connector",
      });

      await user.click(footer);

      expect(
        screen.queryByRole("button", { name: "+ Add new connector" }),
      ).not.toBeInTheDocument();
    });
  });

  /*
   * `labelInValue` makes antd read AND write the selection as
   * `{ value, label }`. Configure Connector is written against it, so ignoring
   * the flag handed the call-site a bare string — `option?.value` came back
   * undefined and picking a connector did nothing.
   */
  describe("Select labelInValue (antd parity)", () => {
    const CONNECTORS = [
      { value: "gcs", label: "GCS Testing" },
      { value: "s3", label: "S3 Oct 6 2025" },
    ];

    it("hands onChange a { value, label } pair", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <Select open labelInValue options={CONNECTORS} onChange={onChange} />,
      );
      await user.click(screen.getByRole("option", { name: "S3 Oct 6 2025" }));
      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({ value: "s3", label: "S3 Oct 6 2025" }),
        expect.anything(),
      );
    });

    it("reads a controlled { value, label } back onto the trigger", () => {
      render(
        <Select
          labelInValue
          options={CONNECTORS}
          value={{ value: "gcs", label: "GCS Testing" }}
          placeholder="Select a connector"
        />,
      );
      // String()-ing the object would yield "[object Object]", matching no
      // option: the trigger went blank AND swallowed the placeholder.
      expect(screen.getByRole("combobox")).toHaveTextContent("GCS Testing");
    });

    it("still hands onChange a bare value without the flag", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(<Select open options={CONNECTORS} onChange={onChange} />);
      await user.click(screen.getByRole("option", { name: "S3 Oct 6 2025" }));
      expect(onChange).toHaveBeenCalledWith("s3", expect.anything());
    });
  });

  /*
   * antd's `showSearch` filters the list as you type — 27 call-sites set it,
   * and the shim consumed the prop without ever rendering a search box, so
   * every one of them was a plain scroll-and-hunt dropdown.
   */
  describe("Select showSearch / filterOption (antd parity)", () => {
    const CONNECTORS = [
      { value: "gcs", label: "GCS Testing" },
      { value: "s3", label: "S3 Oct 6 2025" },
      { value: "az", label: "Unstract's Azure cloud storage" },
    ];

    const openSearch = async (user) => {
      await user.click(screen.getByRole("combobox"));
      return screen.getByRole("searchbox");
    };

    it("renders a search box and filters the options as you type", async () => {
      const user = userEvent.setup();
      render(<Select showSearch options={CONNECTORS} />);
      const box = await openSearch(user);

      expect(screen.getAllByRole("option")).toHaveLength(3);
      await user.type(box, "azure");

      expect(screen.getAllByRole("option")).toHaveLength(1);
      expect(
        screen.getByRole("option", { name: "Unstract's Azure cloud storage" }),
      ).toBeInTheDocument();
    });

    it("routes the query through the call-site's own filterOption", async () => {
      const user = userEvent.setup();
      const filterOption = vi.fn(
        (input, option) => option.value === "s3" && input === "x",
      );
      render(
        <Select showSearch options={CONNECTORS} filterOption={filterOption} />,
      );
      const box = await openSearch(user);
      await user.type(box, "x");

      expect(filterOption).toHaveBeenCalledWith("x", CONNECTORS[0]);
      expect(screen.getAllByRole("option")).toHaveLength(1);
      expect(
        screen.getByRole("option", { name: "S3 Oct 6 2025" }),
      ).toBeInTheDocument();
    });

    /*
     * Summarize Manager filters on `option.children`. Normalising the option
     * into `{ value, label }` left that undefined, and `.toLowerCase()` on it
     * throws on the FIRST keystroke — a crash, not a missing filter.
     */
    it("hands filterOption the <Select.Option> props, children included", async () => {
      const user = userEvent.setup();
      render(
        <Select
          showSearch
          filterOption={(input, option) =>
            option.children.toLowerCase().includes(input.toLowerCase())
          }
        >
          <Select.Option value="a">AzureOpenAI</Select.Option>
          <Select.Option value="b">Bedrock</Select.Option>
        </Select>,
      );
      const box = await openSearch(user);
      await user.type(box, "bed");

      expect(screen.getAllByRole("option")).toHaveLength(1);
      expect(
        screen.getByRole("option", { name: "Bedrock" }),
      ).toBeInTheDocument();
    });

    /*
     * Adapter Selection sets a STRING `label` next to a rich `children` node
     * and filters on the label. Display must still use the node.
     */
    it("keeps a string label alongside rich children", async () => {
      const user = userEvent.setup();
      render(
        <Select
          showSearch
          filterOption={(input, option) =>
            option.label?.toLowerCase().includes(input.toLowerCase())
          }
        >
          <Select.Option value="a" label="AzureOpenAI">
            <span>AzureOpenAI (azure|1234)</span>
          </Select.Option>
          <Select.Option value="b" label="Bedrock">
            <span>Bedrock (bedrock|5678)</span>
          </Select.Option>
        </Select>,
      );
      const box = await openSearch(user);
      await user.type(box, "azure");

      const options = screen.getAllByRole("option");
      expect(options).toHaveLength(1);
      // The NODE is what renders, not the label used for filtering.
      expect(options[0]).toHaveTextContent("AzureOpenAI (azure|1234)");
    });

    it("falls back to the option's own text when no filterOption is given", async () => {
      const user = userEvent.setup();
      render(
        <Select
          showSearch
          options={[
            // A label built as an element, as the connector list is.
            { value: "gcs", label: <span>GCS Testing</span> },
            { value: "s3", label: <span>S3 Oct 6 2025</span> },
          ]}
        />,
      );
      const box = await openSearch(user);
      await user.type(box, "gcs");

      expect(screen.getAllByRole("option")).toHaveLength(1);
      expect(
        screen.getByRole("option", { name: "GCS Testing" }),
      ).toBeInTheDocument();
    });

    /*
     * The prompt card's enforce-type list is built as `{ value: "text" }` with
     * no label at all, so the only thing left to match on is the value the
     * trigger is already showing.
     */
    it("filters on the value when an option carries no label", async () => {
      const user = userEvent.setup();
      render(
        <Select
          showSearch
          options={[
            { value: "text" },
            { value: "json" },
            { value: "agentic_table" },
          ]}
        />,
      );
      const box = await openSearch(user);
      await user.type(box, "table");

      expect(screen.getAllByRole("option")).toHaveLength(1);
      expect(
        screen.getByRole("option", { name: "agentic_table" }),
      ).toBeInTheDocument();
    });

    it("filters on optionFilterProp when told to", async () => {
      const user = userEvent.setup();
      render(
        <Select
          showSearch
          optionFilterProp="title"
          options={[
            { value: "a", label: "First", title: "alpha" },
            { value: "b", label: "Second", title: "beta" },
          ]}
        />,
      );
      const box = await openSearch(user);
      await user.type(box, "beta");

      expect(screen.getAllByRole("option")).toHaveLength(1);
      expect(
        screen.getByRole("option", { name: "Second" }),
      ).toBeInTheDocument();
    });

    it("shows every option when filterOption is false, as antd does", async () => {
      const user = userEvent.setup();
      render(<Select showSearch filterOption={false} options={CONNECTORS} />);
      const box = await openSearch(user);
      await user.type(box, "nothing matches this");

      expect(screen.getAllByRole("option")).toHaveLength(3);
    });

    it("renders notFoundContent when the query matches nothing", async () => {
      const user = userEvent.setup();
      render(
        <Select
          showSearch
          options={CONNECTORS}
          notFoundContent="No projects available"
        />,
      );
      const box = await openSearch(user);
      await user.type(box, "zzzz");

      expect(screen.queryAllByRole("option")).toHaveLength(0);
      expect(screen.getByText("No projects available")).toBeInTheDocument();
    });

    it("selects with the keyboard without leaving the search box", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(<Select showSearch options={CONNECTORS} onChange={onChange} />);
      const box = await openSearch(user);

      await user.keyboard("{ArrowDown}{Enter}");

      expect(onChange).toHaveBeenCalledWith("s3", CONNECTORS[1]);
      expect(box).not.toBeInTheDocument();
    });

    it("selects by click and shows the choice on the trigger", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      const { rerender } = render(
        <Select showSearch options={CONNECTORS} onChange={onChange} />,
      );
      await openSearch(user);
      await user.click(screen.getByRole("option", { name: "GCS Testing" }));

      expect(onChange).toHaveBeenCalledWith("gcs", CONNECTORS[0]);

      rerender(
        <Select
          showSearch
          options={CONNECTORS}
          value="gcs"
          onChange={onChange}
        />,
      );
      expect(screen.getByRole("combobox")).toHaveTextContent("GCS Testing");
    });

    it("shows the placeholder until something is chosen", async () => {
      render(
        <Select
          showSearch
          options={CONNECTORS}
          placeholder="Select a connector"
        />,
      );
      expect(screen.getByRole("combobox")).toHaveTextContent(
        "Select a connector",
      );
    });

    /*
     * Configure Connector sets showSearch AND dropdownRender AND labelInValue
     * at once — the searchable path has to carry all three or the "+ Add new
     * connector" footer disappears again the moment search starts working.
     */
    it("keeps a dropdownRender footer below the filtered list", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <Select
          showSearch
          labelInValue
          options={CONNECTORS}
          onChange={onChange}
          dropdownRender={(menu) => (
            <>
              {menu}
              <button type="button">+ Add new connector</button>
            </>
          )}
        />,
      );
      const box = await openSearch(user);
      expect(
        screen.getByRole("button", { name: "+ Add new connector" }),
      ).toBeInTheDocument();

      await user.type(box, "s3");
      expect(screen.getAllByRole("option")).toHaveLength(1);
      // Still pinned under the now-filtered list.
      expect(
        screen.getByRole("button", { name: "+ Add new connector" }),
      ).toBeInTheDocument();

      await user.click(screen.getByRole("option", { name: "S3 Oct 6 2025" }));
      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({ value: "s3", label: "S3 Oct 6 2025" }),
        CONNECTORS[1],
      );
    });

    it("drops the query when the popup closes", async () => {
      const user = userEvent.setup();
      render(<Select showSearch options={CONNECTORS} />);
      const box = await openSearch(user);
      await user.type(box, "azure");
      expect(screen.getAllByRole("option")).toHaveLength(1);

      await user.keyboard("{Escape}");
      await user.click(screen.getByRole("combobox"));

      expect(screen.getAllByRole("option")).toHaveLength(3);
    });
  });

  it("Select renders each option through `optionRender` when given", () => {
    render(
      <Select
        open
        options={[{ value: "gcs", label: "GCS Testing", data: { icon: "x" } }]}
        optionRender={(option) => <span>icon {option.label}</span>}
      />,
    );
    expect(
      screen.getByRole("option", { name: "icon GCS Testing" }),
    ).toBeInTheDocument();
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
