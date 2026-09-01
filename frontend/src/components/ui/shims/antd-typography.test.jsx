import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  Paragraph,
  Text,
  Title,
  Typography,
} from "@/components/ui/shims/antd-typography";

describe("Typography shim (P1-03)", () => {
  it("renders Text as a span with the content", () => {
    render(<Text>hello</Text>);
    expect(screen.getByText("hello").tagName).toBe("SPAN");
  });

  it("maps antd `type` onto Midnight Bloom token classes", () => {
    render(
      <>
        <Text type="secondary">sec</Text>
        <Text type="danger">dang</Text>
        <Text type="success">succ</Text>
        <Text type="warning">warn</Text>
      </>,
    );
    expect(screen.getByText("sec").className).toContain(
      "text-muted-foreground",
    );
    expect(screen.getByText("dang").className).toContain("text-destructive");
    expect(screen.getByText("succ").className).toContain("text-success");
    expect(screen.getByText("warn").className).toContain("text-warning");
  });

  it("supports strong / italic / delete / code", () => {
    render(
      <>
        <Text strong>s</Text>
        <Text italic>i</Text>
        <Text delete>d</Text>
        <Text code>c</Text>
      </>,
    );
    expect(screen.getByText("s").className).toContain("font-semibold");
    expect(screen.getByText("i").className).toContain("italic");
    expect(screen.getByText("d").className).toContain("line-through");
    expect(screen.getByText("c").className).toContain("font-mono");
  });

  /*
   * antd's inline code carries a border as well as a fill. Without it the
   * snippets in Custom Data ("{{custom_data.key}}") sat at #f5f5f5 on a
   * #fafafa surface — a five-value difference, effectively invisible.
   */
  it("gives inline code a border so it stands out from body text", () => {
    render(<Text code>{"{{custom_data.key}}"}</Text>);
    const el = screen.getByText("{{custom_data.key}}");
    expect(el.className).toContain("border");
    expect(el.className).toContain("bg-muted");
  });

  it("renders Title at the requested heading level", () => {
    render(
      <>
        <Title level={1}>h1</Title>
        <Title level={3}>h3</Title>
        <Title level={5}>h5</Title>
      </>,
    );
    expect(screen.getByText("h1").tagName).toBe("H1");
    expect(screen.getByText("h3").tagName).toBe("H3");
    expect(screen.getByText("h5").tagName).toBe("H5");
  });

  it("renders Paragraph as a <p>", () => {
    render(<Paragraph>para</Paragraph>);
    expect(screen.getByText("para").tagName).toBe("P");
  });

  it("exposes the antd-style Typography.X namespace", () => {
    render(<Typography.Text>ns</Typography.Text>);
    expect(screen.getByText("ns").tagName).toBe("SPAN");
  });

  // The behaviour that made a plain `truncate` swap unsafe:

  it("truncates on a single line for ellipsis={true}", () => {
    render(<Text ellipsis>long</Text>);
    expect(screen.getByText("long").className).toContain("truncate");
  });

  it("clamps to N lines for ellipsis={{ rows: n }} using a static class", () => {
    render(<Text ellipsis={{ rows: 2, expandable: false }}>two</Text>);
    // Must be the literal class Tailwind can see at build time.
    expect(screen.getByText("two").className).toContain("line-clamp-2");
  });

  it("keeps the text reachable when a tooltip is requested", () => {
    render(<Text ellipsis={{ tooltip: true }}>tipped</Text>);
    // Radix renders the trigger; the content mounts on interaction. The point
    // of the assertion is that requesting a tooltip does not drop the text.
    expect(screen.getByText("tipped")).toBeInTheDocument();
    expect(screen.getByText("tipped").className).toContain("truncate");
  });

  it("accepts custom tooltip content without losing the visible text", () => {
    render(<Text ellipsis={{ tooltip: "full value" }}>short</Text>);
    expect(screen.getByText("short")).toBeInTheDocument();
  });

  it("passes through className and arbitrary props", () => {
    render(
      <Text className="custom-cls" data-testid="probe" title="t">
        x
      </Text>,
    );
    const el = screen.getByTestId("probe");
    expect(el.className).toContain("custom-cls");
    expect(el.getAttribute("title")).toBe("t");
  });
});
