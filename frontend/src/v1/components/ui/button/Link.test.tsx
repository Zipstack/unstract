import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { expect, it } from "vitest";
import { Link } from "./Link";

it("is a link that stays in the tab by default", () => {
  renderV1(<Link href="/guide">setup guide</Link>);
  const link = screen.getByRole("link", { name: "setup guide" });
  expect(link).toHaveAttribute("href", "/guide");
  expect(link).not.toHaveAttribute("target");
});

it("opens an external link in a new tab and says so", () => {
  const { container } = renderV1(
    <Link href="https://docs.unstract.com" external>
      documentation
    </Link>,
  );
  const link = screen.getByRole("link", {
    name: "documentation (opens in a new tab)",
  });
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
  expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
});

it("keeps the new tab when a caller passes its own target or rel", () => {
  renderV1(
    <Link
      href="https://docs.unstract.com"
      external
      target="_self"
      rel="nofollow"
    >
      documentation
    </Link>,
  );
  const link = screen.getByRole("link", {
    name: "documentation (opens in a new tab)",
  });
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
});

it("puts its classes on the child with asChild", () => {
  renderV1(
    <Link asChild className="extra">
      <a href="/runs">Runs</a>
    </Link>,
  );
  const link = screen.getByRole("link", { name: "Runs" });
  expect(link).toHaveAttribute("data-slot", "link");
  expect(link).toHaveClass("ui:text-primary", "extra");
});

// Type-level guard, never rendered: the marker needs a real `<a>`.
export function _externalNeedsAnAnchor() {
  return (
    // @ts-expect-error external cannot be combined with asChild
    <Link asChild external>
      <a href="/x">x</a>
    </Link>
  );
}
