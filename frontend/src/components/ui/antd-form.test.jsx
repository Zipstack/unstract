import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Form } from "@/components/ui/antd-form";
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
