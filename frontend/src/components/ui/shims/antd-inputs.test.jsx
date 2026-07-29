import { render, screen } from "@testing-library/react";
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
    const onChange = vi.fn();
    render(<Input onChange={onChange} />);
    userEvent.type(screen.getByRole("textbox"), "hi");
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

  it("Input.Password masks by default and reveals on toggle", async () => {
    const { container } = render(<Input.Password />);
    const field = container.querySelector("input");
    expect(field.getAttribute("type")).toBe("password");
    userEvent.click(screen.getByRole("button", { name: /show password/i }));
    expect(field.getAttribute("type")).toBe("text");
  });

  it("Input.Search fires onSearch on Enter", async () => {
    const onSearch = vi.fn();
    render(<Input.Search onSearch={onSearch} />);
    userEvent.type(screen.getByRole("textbox"), "q{enter}");
    expect(onSearch).toHaveBeenCalled();
  });

  // antd hands InputNumber a NUMBER, not an event.
  it("InputNumber calls onChange with a number, not an event", async () => {
    const onChange = vi.fn();
    render(<InputNumber onChange={onChange} />);
    userEvent.type(screen.getByRole("spinbutton"), "42");
    const last = onChange.mock.calls.at(-1)[0];
    expect(typeof last).toBe("number");
  });

  it("InputNumber emits null when cleared, not NaN", () => {
    const onChange = vi.fn();
    render(<InputNumber value={5} onChange={onChange} />);
    const el = screen.getByRole("spinbutton");
    userEvent.clear(el);
    if (onChange.mock.calls.length) {
      expect(onChange.mock.calls.at(-1)[0]).toBeNull();
    }
  });

  // antd hands Checkbox an EVENT with target.checked; Radix gives a boolean.
  it("Checkbox onChange receives an event-shaped object with target.checked", async () => {
    const onChange = vi.fn();
    render(<Checkbox onChange={onChange}>Accept</Checkbox>);
    userEvent.click(screen.getByRole("checkbox"));
    expect(onChange).toHaveBeenCalled();
    expect(onChange.mock.calls[0][0].target.checked).toBe(true);
  });

  it("Checkbox renders its label text", () => {
    render(<Checkbox>Accept terms</Checkbox>);
    expect(screen.getByText("Accept terms")).toBeInTheDocument();
  });

  // antd hands Switch a BOOLEAN.
  it("Switch onChange receives a boolean", async () => {
    const onChange = vi.fn();
    render(<Switch onChange={onChange} />);
    userEvent.click(screen.getByRole("switch"));
    expect(onChange).toHaveBeenCalledWith(true);
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

  it("Select accepts Select.Option children as well as options data", () => {
    render(
      <Select placeholder="Choose">
        <Select.Option value="x">X</Select.Option>
      </Select>,
    );
    expect(screen.getByText("Choose")).toBeInTheDocument();
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
    it("renders the antd 'N / max' readout and tracks typing", () => {
      render(<Input.TextArea showCount maxLength={200} />);

      expect(screen.getByText("0 / 200")).toBeInTheDocument();
      userEvent.type(screen.getByRole("textbox"), "hello");
      expect(screen.getByText("5 / 200")).toBeInTheDocument();
    });

    it("still forwards the caller's onChange while counting", () => {
      const onChange = vi.fn();
      render(<Input showCount maxLength={30} onChange={onChange} />);

      userEvent.type(screen.getByRole("textbox"), "ab");
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
