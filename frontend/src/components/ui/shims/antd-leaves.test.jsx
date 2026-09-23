import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  Alert,
  Avatar,
  Divider,
  Empty,
  Progress,
  Spin,
  Tag,
} from "@/components/ui/shims/antd-leaves";

describe("antd-compatible leaf shims (P1-06)", () => {
  it("renders Tag content", () => {
    render(<Tag>beta</Tag>);
    expect(screen.getByText("beta")).toBeInTheDocument();
  });

  /*
   * antd's preset tags are TINTED — pale background, saturated text, mid-tone
   * border — not solid fills. Mapping them onto shadcn Badge variants rendered
   * `<Tag color="orange">` as white-on-brown, where the reference draws a pale
   * amber chip. Values below are read off antd's own stylesheet.
   */
  it("renders a preset colour as antd's tinted chip, not a solid fill", () => {
    const { container } = render(<Tag color="orange">Trial</Tag>);
    const { style } = container.firstChild;
    expect(style.backgroundColor).toBe("#fff7e6");
    expect(style.color).toBe("#d46b08");
    expect(style.borderColor).toBe("#ffd591");
  });

  it("tints the status aliases the same way", () => {
    const { container } = render(<Tag color="success">ok</Tag>);
    expect(container.firstChild.style.backgroundColor).toBe("#f6ffed");
    expect(container.firstChild.style.color).toBe("#389e0d");
  });

  it("tints red without the destructive fill", () => {
    const { container } = render(<Tag color="red">bad</Tag>);
    expect(container.firstChild.style.backgroundColor).toBe("#fff1f0");
    expect(container.firstChild.className).not.toContain("destructive");
  });

  // One call-site passes a raw rgb() that antd applied directly — it must not
  // be silently dropped just because it is not a known token.
  it("falls through to inline style for a raw CSS colour", () => {
    const { container } = render(<Tag color="rgb(45, 183, 245)">custom</Tag>);
    expect(container.firstChild.style.backgroundColor).toBe(
      "rgb(45, 183, 245)",
    );
  });

  it("renders a close affordance only when closable", () => {
    const onClose = vi.fn();
    render(
      <Tag closable onClose={onClose}>
        x
      </Tag>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("renders Spin as a status indicator", () => {
    render(<Spin />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders Spin's tip text when supplied", () => {
    render(<Spin tip="Loading data" />);
    expect(screen.getByText("Loading data")).toBeInTheDocument();
  });

  /*
   * The wrapper form used to drop its children outright, which blanked the
   * document list in FetchSpecificModal. Both spinning states are asserted:
   * the content must survive either way, since antd dims it rather than
   * unmounting it.
   */
  it("renders Spin's children in the wrapper form while spinning", () => {
    render(
      <Spin spinning={true}>
        <div>Wrapped content</div>
      </Spin>,
    );
    expect(screen.getByText("Wrapped content")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("drops the indicator but keeps the children once spinning is false", () => {
    render(
      <Spin spinning={false}>
        <div>Wrapped content</div>
      </Spin>,
    );
    expect(screen.getByText("Wrapped content")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("keeps `spinning` off the DOM", () => {
    const { container } = render(
      <Spin spinning={false}>
        <div>Wrapped content</div>
      </Spin>,
    );
    expect(container.querySelector("[spinning]")).toBeNull();
  });

  it("sizes a Tag's icon down to the chip's text", () => {
    const { container } = render(
      <Tag icon={<svg data-testid="tag-icon" />}>Reviewer</Tag>,
    );
    expect(container.firstChild).toHaveClass("[&>svg]:size-3");
  });

  it("renders Alert message and description", () => {
    render(<Alert message="Heads up" description="More detail" />);
    expect(screen.getByText("Heads up")).toBeInTheDocument();
    expect(screen.getByText("More detail")).toBeInTheDocument();
  });

  it("uses the destructive variant for type=error", () => {
    const { container } = render(<Alert type="error" message="Bad" />);
    expect(container.firstChild.className).toContain("destructive");
  });

  /*
   * antd tints info alerts blue (colorInfoBg #e6f4ff / colorInfo #1677ff).
   * `info` had no branch at all, so the "Highlight Feature Availability"
   * notice fell through to the plain default variant and rendered as a
   * neutral grey box with none of the visual language of an info message.
   */
  it("gives an info Alert the blue info theme", () => {
    const { container } = render(
      <Alert type="info" showIcon message="Heads up" />,
    );
    const el =
      container.querySelector('[role="alert"]') ?? container.firstChild;
    expect(el.className).toContain("bg-info-bg");
    expect(el.className).toContain("border-info");
  });

  it("defaults to the info theme when no type is given, as antd does", () => {
    const { container } = render(<Alert message="Heads up" />);
    const el =
      container.querySelector('[role="alert"]') ?? container.firstChild;
    expect(el.className).toContain("bg-info-bg");
  });

  it("Alert dismisses itself when closable, and calls onClose", () => {
    const onClose = vi.fn();
    render(<Alert closable onClose={onClose} message="Dismiss me" />);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
    expect(screen.queryByText("Dismiss me")).not.toBeInTheDocument();
  });

  it("renders a horizontal Divider by default", () => {
    const { container } = render(<Divider />);
    expect(container.firstChild).toBeTruthy();
  });

  it("renders Divider label text when given children", () => {
    render(<Divider>OR</Divider>);
    expect(screen.getByText("OR")).toBeInTheDocument();
  });

  it("Empty shows a default description, and a custom one when given", () => {
    const { rerender } = render(<Empty />);
    expect(screen.getByText("No data")).toBeInTheDocument();
    rerender(<Empty description="Nothing here yet" />);
    expect(screen.getByText("Nothing here yet")).toBeInTheDocument();
  });

  it("Avatar renders a fallback when there is no src", () => {
    render(<Avatar>AB</Avatar>);
    expect(screen.getByText("AB")).toBeInTheDocument();
  });

  it("Avatar accepts a numeric size as explicit dimensions", () => {
    const { container } = render(<Avatar size={48}>Z</Avatar>);
    expect(container.firstChild.style.width).toBe("48px");
  });

  /*
   * antd's `.ant-avatar` is inline, and call-sites depend on it: Share access
   * passes `<><Avatar /><Typography.Text /></>` as one List.Item.Meta title
   * and expects avatar and email on the same line. The shadcn primitive is
   * `flex`, which stacked the email under the avatar.
   */
  it("Avatar lays out inline so it shares a line with adjacent text", () => {
    const { container } = render(<Avatar>Z</Avatar>);
    expect(container.firstChild.className).toContain("inline-flex");
    expect(container.firstChild.className).not.toMatch(/(^|\s)flex(\s|$)/);
  });

  it("Progress shows the rounded percentage", () => {
    render(<Progress percent={42.6} />);
    expect(screen.getByText("43%")).toBeInTheDocument();
  });

  it("Progress hides the readout when showInfo is false", () => {
    render(<Progress percent={50} showInfo={false} />);
    expect(screen.queryByText("50%")).not.toBeInTheDocument();
  });
});
