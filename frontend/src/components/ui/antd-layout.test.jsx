import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Col, Flex, Row, Space } from "@/components/ui/antd-layout";

describe("antd-compatible layout shims (P1-05)", () => {
  // The reason these are shims rather than a gap-* swap: 20 hand-written CSS
  // rules in this repo select antd's internal wrapper elements.

  it("wraps each Space child in .ant-space-item, as existing CSS expects", () => {
    const { container } = render(
      <Space>
        <span>a</span>
        <span>b</span>
        <span>c</span>
      </Space>,
    );
    expect(container.querySelectorAll(".ant-space-item")).toHaveLength(3);
    expect(container.querySelector(".ant-space")).toBeTruthy();
  });

  it("skips falsy children so conditional renders do not leave empty gaps", () => {
    const show = false;
    const { container } = render(
      <Space>
        <span>a</span>
        {show && <span>hidden</span>}
        {null}
        <span>b</span>
      </Space>,
    );
    expect(container.querySelectorAll(".ant-space-item")).toHaveLength(2);
  });

  it("wraps mapped children individually", () => {
    const { container } = render(
      <Space>
        {["x", "y", "z"].map((k) => (
          <span key={k}>{k}</span>
        ))}
      </Space>,
    );
    expect(container.querySelectorAll(".ant-space-item")).toHaveLength(3);
  });

  it("stacks vertically for direction=vertical", () => {
    const { container } = render(
      <Space direction="vertical">
        <span>a</span>
      </Space>,
    );
    const el = container.querySelector(".ant-space");
    expect(el.className).toContain("flex-col");
    expect(el.className).toContain("ant-space-vertical");
  });

  it("maps antd size tokens to a px gap", () => {
    const { container } = render(
      <Space size="large">
        <span>a</span>
      </Space>,
    );
    expect(container.querySelector(".ant-space").style.gap).toBe("24px");
  });

  it("accepts a numeric size", () => {
    const { container } = render(
      <Space size={5}>
        <span>a</span>
      </Space>,
    );
    expect(container.querySelector(".ant-space").style.gap).toBe("5px");
  });

  it("keeps the .ant-row / .ant-col hooks", () => {
    const { container } = render(
      <Row>
        <Col span={12}>half</Col>
      </Row>,
    );
    expect(container.querySelector(".ant-row")).toBeTruthy();
    expect(container.querySelector(".ant-col")).toBeTruthy();
  });

  it("converts Col span to a percentage of antd's 24-column grid", () => {
    const { container } = render(
      <Row>
        <Col span={12}>half</Col>
      </Row>,
    );
    expect(container.querySelector(".ant-col").style.width).toBe("50%");
  });

  it("applies gutter as negative row margin plus column padding", () => {
    const { container } = render(
      <Row gutter={16}>
        <Col span={24}>full</Col>
      </Row>,
    );
    expect(container.querySelector(".ant-row").style.marginLeft).toBe("-8px");
    expect(container.querySelector(".ant-col").style.paddingLeft).toBe("8px");
  });

  it("renders Flex with direction and gap", () => {
    const { container } = render(
      <Flex vertical gap={8}>
        <span>a</span>
      </Flex>,
    );
    const el = container.firstChild;
    expect(el.className).toContain("flex-col");
    expect(el.style.gap).toBe("8px");
  });

  it("passes className and props through on every component", () => {
    render(
      <Space className="cell-content" data-testid="s">
        <span>a</span>
      </Space>,
    );
    expect(screen.getByTestId("s").className).toContain("cell-content");
  });
});
