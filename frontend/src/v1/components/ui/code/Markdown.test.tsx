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
  expect(screen.getByRole("region", { name: "Python code" })).toBeTruthy();
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
  // react-markdown's URL filter replaces the target (React 19 would also
  // block a javascript: URL); either way the payload never survives.
  const link = screen.getByText("click").closest("a");
  expect(link?.getAttribute("href") ?? "").not.toContain("alert");
  expect(
    container.querySelector("img")?.getAttribute("src") ?? "",
  ).not.toContain("alert");
  expect(container.querySelector("img")?.getAttribute("alt")).toBe("p");
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
