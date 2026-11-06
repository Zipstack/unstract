import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { expect, it } from "vitest";
import { Markdown } from "./Markdown";

it("renders GitHub Markdown with v1 type roles", () => {
  const { container } = renderV1(
    <Markdown>
      {
        "# Title\n\nSome **bold** and `code`.\n\n| a | b |\n| - | - |\n| 1 | 2 |\n\n- [x] done\n- [ ] todo\n\n1. one\n\n> quote\n\n---\n\n~~gone~~"
      }
    </Markdown>,
  );
  expect(
    screen.getByRole("heading", { level: 1, name: "Title" }).className,
  ).toContain("ui:text-section-title");
  expect(screen.getByRole("heading", { level: 1 }).hasAttribute("level")).toBe(
    false,
  );
  expect(
    container.querySelector("code[data-slot=inline-code]")?.textContent,
  ).toBe("code");
  expect(screen.getByRole("table")).toBeTruthy();
  expect(screen.getByRole("checkbox", { name: "Done" })).toBeTruthy();
  expect(screen.getByRole("checkbox", { name: "Not done" })).toBeTruthy();
  expect(container.querySelector("ol")).toBeTruthy();
  expect(container.querySelector("blockquote")?.textContent).toContain("quote");
  expect(container.querySelector("del")?.textContent).toBe("gone");
});

it("renders a fenced block as a highlighted CodeBlock in its language", () => {
  const { container } = renderV1(
    <Markdown>
      {"```py\nx = 'a'\n```\n\n```\nplain\n```\n\n```cobol\nX\n```"}
    </Markdown>,
  );
  const blocks = container.querySelectorAll("[data-slot=code-block]");
  expect([...blocks].map((b) => b.getAttribute("data-language"))).toEqual([
    "python",
    "text",
    "text",
  ]);
  expect(blocks[0].querySelector(".ui\\:text-code-string")?.textContent).toBe(
    "'a'",
  );
  expect(container.querySelector("pre pre")).toBeNull();
  expect(screen.getByRole("region", { name: "Python" })).toBeTruthy();
});

it("opens external links safely and leaves relative ones alone", () => {
  renderV1(
    <Markdown>
      {"[ext](https://x.example) [rel](/docs) [mail](mailto:a@b.c)"}
    </Markdown>,
  );
  const ext = screen.getByRole("link", { name: "ext" });
  expect(ext.getAttribute("target")).toBe("_blank");
  expect(ext.getAttribute("rel")).toBe("noopener noreferrer");
  const rel = screen.getByRole("link", { name: "rel" });
  expect(rel.getAttribute("href")).toBe("/docs");
  expect(rel.hasAttribute("target")).toBe(false);
  expect(screen.getByRole("link", { name: "mail" }).getAttribute("href")).toBe(
    "mailto:a@b.c",
  );
});

it("never renders raw HTML or script URLs", () => {
  const { container } = renderV1(
    <Markdown>
      {
        '<script>alert(1)</script>\n\n<img src=x onerror="alert(1)">\n\n[click](javascript:alert(1)) ![p](javascript:alert(1))\n\n<b>bold</b>'
      }
    </Markdown>,
  );
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("b")).toBeNull();
  expect(container.querySelector("[onerror]")).toBeNull();
  // The tags are dropped, not escaped into visible text.
  expect(container.textContent).not.toContain("<b>");
  expect(container.textContent).not.toContain("<script>");
  // react-markdown's URL filter replaces the target (React 19 would also
  // block a javascript: URL); either way the payload never survives.
  const link = screen.getByText("click").closest("a");
  expect(link?.getAttribute("href") ?? "").not.toContain("alert");
  const image = screen.getByRole("link", { name: "Image: p" });
  expect(image.getAttribute("href") ?? "").not.toContain("alert");
});

it("filters image URLs when images load", () => {
  // React does not filter src, so this pins react-markdown's image filter.
  const { container } = renderV1(
    <Markdown loadImages>{"![p](javascript:alert(1))"}</Markdown>,
  );
  const img = container.querySelector("img");
  expect(img?.getAttribute("alt")).toBe("p");
  expect(img?.getAttribute("src") ?? "").not.toContain("alert");
});

it("shows images as links unless loadImages is set", () => {
  const md = "![chart](https://x.example/c.png) ![](https://x.example/d.png)";
  const { container, rerender } = renderV1(<Markdown>{md}</Markdown>);
  expect(container.querySelector("img")).toBeNull();
  const link = screen.getByRole("link", { name: "Image: chart" });
  expect(link.getAttribute("href")).toBe("https://x.example/c.png");
  expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  expect(screen.getByRole("link", { name: "Image" })).toBeTruthy();
  rerender(<Markdown loadImages>{md}</Markdown>);
  const images = container.querySelectorAll("img");
  expect([...images].map((i) => i.getAttribute("alt"))).toEqual(["chart", ""]);
});

it("passes axe in every mode", async () => {
  for (const theme of ["light", "dark", "unstract"] as const) {
    const { container, unmount } = renderV1(
      <Markdown>
        {"## H\n\nText [l](https://x.example)\n\n```json\n{}\n```\n\n- [ ] t"}
      </Markdown>,
      { theme },
    );
    await expect(container).toHaveNoA11yViolations();
    unmount();
  }
});

it("keeps a linked image as text inside its link, never a link in a link", () => {
  const { container } = renderV1(
    <Markdown>
      {"[![build](https://x.example/b.svg)](https://ci.example/run)"}
    </Markdown>,
  );
  expect(container.querySelectorAll("a")).toHaveLength(1);
  expect(container.querySelector("a a")).toBeNull();
  const link = screen.getByRole("link", { name: "Image: build" });
  expect(link.getAttribute("href")).toBe("https://ci.example/run");
});

it("treats fence names that are Object's own keys as plain text", () => {
  const { container } = renderV1(
    <Markdown>{"```constructor\nx\n```\n\n```__proto__\ny\n```"}</Markdown>,
  );
  const blocks = container.querySelectorAll("[data-slot=code-block]");
  expect([...blocks].map((b) => b.getAttribute("data-language"))).toEqual([
    "text",
    "text",
  ]);
});

it("passes none of react-markdown's own props to the DOM", () => {
  // Only non-boolean props would become attributes; React drops boolean ones
  // (`ordered`, `checked`, `isHeader`), so those cannot be observed here.
  const { container } = renderV1(
    <Markdown>{"# H\n\n- a\n  - b\n\n1. one"}</Markdown>,
  );
  for (const attr of ["depth", "level", "node", "index"]) {
    expect(container.querySelector(`[${attr}]`), attr).toBeNull();
  }
});
