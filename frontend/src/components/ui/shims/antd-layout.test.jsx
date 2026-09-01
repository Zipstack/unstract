import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Col, Flex, Row, Space } from "@/components/ui/shims/antd-layout";

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

  it("wraps fragment children individually, as antd's toArray does", () => {
    // The playground header shape: everything behind one conditional
    // fragment. React's Children.toArray counts that as a single child, so
    // without flattening the whole header lands in one .ant-space-item and
    // loses its gaps.
    const show = true;
    const { container } = render(
      <Space>
        {show && (
          <>
            <span>a</span>
            <span>b</span>
            <span>c</span>
          </>
        )}
      </Space>,
    );
    expect(container.querySelectorAll(".ant-space-item")).toHaveLength(3);
  });

  it("flattens nested fragments and drops their falsy children", () => {
    const { container } = render(
      <Space>
        <span>a</span>
        <>
          <span>b</span>
          {false && <span>hidden</span>}
          <>
            <span>c</span>
          </>
        </>
      </Space>,
    );
    expect(container.querySelectorAll(".ant-space-item")).toHaveLength(3);
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

  /*
   * antd's responsive Col props were not destructured, so `<Col xs={24}>` fell
   * into `...props`, hit the DOM as an unknown attribute, and the column got
   * NO width — the Dashboard's "Usage by Deployment" card shrank to fit its
   * empty state instead of spanning the row.
   */
  it("sizes a Col from its responsive breakpoint props", () => {
    const { container } = render(
      <Row>
        <Col xs={24}>full</Col>
      </Row>,
    );
    expect(container.querySelector(".ant-col").style.width).toBe("100%");
  });

  it("does not leak breakpoint props onto the DOM", () => {
    const { container } = render(
      <Row>
        <Col xs={24} md={12}>
          x
        </Col>
      </Row>,
    );
    const col = container.querySelector(".ant-col");
    expect(col).not.toHaveAttribute("xs");
    expect(col).not.toHaveAttribute("md");
  });

  it("prefers the largest specified breakpoint over span", () => {
    const { container } = render(
      <Row>
        <Col span={6} xs={24} md={12}>
          x
        </Col>
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
