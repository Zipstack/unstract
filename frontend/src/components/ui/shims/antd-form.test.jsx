import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Form } from "@/components/ui/shims/antd-form";
import { Input } from "@/components/ui/input";

function Harness({ onReady, onFinish }) {
  const [form] = Form.useForm();
  onReady?.(form);
  return (
    <Form form={form} layout="vertical" onFinish={onFinish}>
      <Form.Item
        label="Name"
        name="name"
        rules={[{ required: true, message: "Group name is required" }]}
      >
        <Input />
      </Form.Item>
      <Form.Item label="Description" name="description">
        <Input />
      </Form.Item>
      <button type="submit">Save</button>
    </Form>
  );
}

describe("antd-compatible Form shim (P3)", () => {
  it("renders labels and inputs", () => {
    render(<Harness />);
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Description")).toBeInTheDocument();
  });

  it("setFieldsValue populates inputs, as edit-mode modals rely on", async () => {
    let form;
    render(<Harness onReady={(f) => (form = f)} />);
    form.setFieldsValue({ name: "Engineering", description: "team" });
    await waitFor(() =>
      expect(screen.getByDisplayValue("Engineering")).toBeInTheDocument(),
    );
  });

  it("getFieldsValue reads current values back", async () => {
    let form;
    render(<Harness onReady={(f) => (form = f)} />);
    form.setFieldsValue({ name: "Ops" });
    await waitFor(() => expect(form.getFieldsValue().name).toBe("Ops"));
  });

  // The critical behaviour: antd REJECTS on invalid, and call-sites do
  // `await form.validateFields().catch(() => null)` to bail out. If this
  // resolved instead, invalid forms would submit.

  it("validateFields rejects when a required field is empty", async () => {
    let form;
    render(<Harness onReady={(f) => (form = f)} />);
    const values = await form.validateFields().catch(() => null);
    expect(values).toBeNull();
  });

  it("validateFields resolves with values once valid", async () => {
    let form;
    render(<Harness onReady={(f) => (form = f)} />);
    form.setFieldsValue({ name: "Filled" });
    await waitFor(async () => {
      const values = await form.validateFields().catch(() => null);
      expect(values?.name).toBe("Filled");
    });
  });

  it("shows the rule's message inline when validation fails", async () => {
    let form;
    render(<Harness onReady={(f) => (form = f)} />);
    await form.validateFields().catch(() => null);
    await waitFor(() =>
      expect(screen.getByText("Group name is required")).toBeInTheDocument(),
    );
  });

  it("resetFields clears the inputs", async () => {
    let form;
    render(<Harness onReady={(f) => (form = f)} />);
    form.setFieldsValue({ name: "Temp" });
    await waitFor(() => screen.getByDisplayValue("Temp"));
    form.resetFields();
    await waitFor(() =>
      expect(screen.queryByDisplayValue("Temp")).not.toBeInTheDocument(),
    );
  });

  it("accepts typed input and submits via onFinish", async () => {
    const onFinish = vi.fn();
    render(<Harness onFinish={onFinish} />);
    userEvent.type(screen.getAllByRole("textbox")[0], "Typed");
    userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onFinish).toHaveBeenCalled());
    expect(onFinish.mock.calls[0][0].name).toBe("Typed");
  });

  it("blocks onFinish while a required field is empty", async () => {
    const onFinish = vi.fn();
    render(<Harness onFinish={onFinish} />);
    userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(screen.getByText("Group name is required")).toBeInTheDocument(),
    );
    expect(onFinish).not.toHaveBeenCalled();
  });

  it("renders a name-less Form.Item as plain layout", () => {
    render(
      <Form>
        <Form.Item label="Static">
          <span>content</span>
        </Form.Item>
      </Form>,
    );
    expect(screen.getByText("content")).toBeInTheDocument();
    expect(screen.getByText("Static")).toBeInTheDocument();
  });
});

/**
 * antd's NamePath allows arrays. react-hook-form's Controller calls
 * `.split(".")` on the name, so an array crashed with
 * "TypeError: s.split is not a function" — taking down the whole route, not
 * just the field. InviteEditUser uses `name={["email"]}`; the cloud
 * StripeProductForm uses nested `name={["tier1", "up_to"]}`.
 */
describe("Form.Item accepts antd's array NamePath", () => {
  it("renders a single-element array name without crashing", () => {
    render(
      <Form>
        <Form.Item name={["email"]} label="Email">
          <input />
        </Form.Item>
      </Form>,
    );
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("treats a nested array name as a dotted path", async () => {
    const onFinish = vi.fn();
    render(
      <Form onFinish={onFinish}>
        <Form.Item name={["tier1", "up_to"]} label="Up to">
          <input />
        </Form.Item>
        <button type="submit">Save</button>
      </Form>,
    );

    fireEvent.change(screen.getByLabelText("Up to"), {
      target: { value: "42" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onFinish).toHaveBeenCalled());
    // The nested shape antd would have produced.
    expect(onFinish.mock.calls[0][0]).toMatchObject({ tier1: { up_to: "42" } });
  });
  /**
   * These four antd APIs were all missing, and together they broke every
   * create/edit modal in the app: the Save button appeared to do nothing.
   *
   *   onValuesChange -> never fired, so call-sites mirroring the form into
   *                     component state kept their initial (empty) value and
   *                     submitted an empty body
   *   setFields      -> the handler those call-sites run on each keystroke
   *   validateStatus
   *   + help         -> how the backend's 400 is surfaced per field; the
   *                     call-sites deliberately do NOT validate client-side
   */
  describe("antd Form APIs the create/edit modals depend on", () => {
    it("fires onValuesChange with the changed field and all values", async () => {
      const onValuesChange = vi.fn();
      render(
        <Form layout="vertical" onValuesChange={onValuesChange}>
          <Form.Item label="Name" name="tool_name">
            <Input />
          </Form.Item>
        </Form>,
      );

      fireEvent.change(screen.getByRole("textbox"), {
        target: { value: "abc" },
      });

      await waitFor(() => expect(onValuesChange).toHaveBeenCalled());
      const [changed, all] = onValuesChange.mock.calls.at(-1);
      expect(changed).toMatchObject({ tool_name: "abc" });
      expect(all).toMatchObject({ tool_name: "abc" });
    });

    it("seeds fields from initialValues", () => {
      render(
        <Form layout="vertical" initialValues={{ tool_name: "seeded" }}>
          <Form.Item label="Name" name="tool_name">
            <Input />
          </Form.Item>
        </Form>,
      );
      expect(screen.getByRole("textbox")).toHaveValue("seeded");
    });

    it("ignores later initialValues changes, as antd does", () => {
      // The call-sites pass initialValues={state} AND write that state from
      // onValuesChange. Re-seeding on change would clobber typing.
      const { rerender } = render(
        <Form layout="vertical" initialValues={{ tool_name: "first" }}>
          <Form.Item label="Name" name="tool_name">
            <Input />
          </Form.Item>
        </Form>,
      );
      fireEvent.change(screen.getByRole("textbox"), {
        target: { value: "typed" },
      });
      rerender(
        <Form layout="vertical" initialValues={{ tool_name: "second" }}>
          <Form.Item label="Name" name="tool_name">
            <Input />
          </Form.Item>
        </Form>,
      );
      expect(screen.getByRole("textbox")).toHaveValue("typed");
    });

    it("exposes form.setFields for clearing and setting errors", async () => {
      let api;
      render(
        <Form layout="vertical" onValuesChange={vi.fn()}>
          <Form.Item label="Name" name="tool_name">
            <Input />
          </Form.Item>
        </Form>,
      );
      // The instance form: assert the method exists on a useForm() result.
      function Probe() {
        const [form] = Form.useForm();
        api = form;
        return null;
      }
      render(<Probe />);
      expect(typeof api.setFields).toBe("function");
      // Must not throw for either shape the call-sites use.
      expect(() =>
        api.setFields([{ name: "tool_name", errors: [] }]),
      ).not.toThrow();
      expect(() =>
        api.setFields([{ name: "tool_name", errors: ["Bad name"] }]),
      ).not.toThrow();
    });

    it("renders a backend error through validateStatus + help", () => {
      render(
        <Form layout="vertical">
          <Form.Item
            label="Name"
            name="tool_name"
            validateStatus="error"
            help="Tool name already exists"
          >
            <Input />
          </Form.Item>
        </Form>,
      );
      const msg = screen.getByText("Tool name already exists");
      expect(msg).toBeInTheDocument();
      expect(msg.className).toContain("text-destructive");
      expect(screen.getByRole("textbox").className).toContain(
        "border-destructive",
      );
    });

    it("does not leak validateStatus/help onto the DOM", () => {
      const { container } = render(
        <Form layout="vertical">
          <Form.Item name="x" validateStatus="error" help="msg">
            <Input />
          </Form.Item>
        </Form>,
      );
      const item = container.querySelector(".ant-form-item");
      expect(item.getAttribute("validateStatus")).toBeNull();
      expect(item.getAttribute("help")).toBeNull();
    });
  });
});
