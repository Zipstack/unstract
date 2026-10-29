import { fireEvent, render, screen } from "@testing-library/react";
import { PRODUCT_MARKS, PROVIDER_MARKS, REGION_FLAGS } from "@v1/assets/marks";
import { PROVIDERS } from "@v1/test/providers.fixture";
import { describe, expect, it } from "vitest";
import { ProductMark, ProviderLogo, RegionFlag } from "./BrandMark";

describe("ProviderLogo", () => {
  it.each(
    PROVIDERS.map((p) => [`${p.kind} ${p.key} (${p.name})`, p] as const),
  )("renders a logo for %s", (_, p) => {
    render(
      <ProviderLogo
        provider={`${p.key}|0f6e2c1a`}
        name={p.name}
        icon={p.icon}
        category={p.category}
      />,
    );
    const logo = screen.getByRole("img", { name: p.name });
    const expected = p.hasMark ? PROVIDER_MARKS[p.key].src : p.icon;
    expect(logo.getAttribute("src")).toBe(expected);
  });

  it("covers every provider the design draws a mark for", () => {
    const missing = PROVIDERS.filter(
      (p) => p.hasMark && !(p.key in PROVIDER_MARKS),
    ).map((p) => p.key);
    expect(missing).toEqual([]);
  });

  it("falls back to the category glyph when the icon is the unavailable marker", () => {
    render(
      <ProviderLogo
        provider="somenewllm|1"
        name="Some New LLM"
        icon="⚠️"
        category="llm"
      />,
    );
    const logo = screen.getByRole("img", { name: "Some New LLM" });
    expect(logo.tagName).toBe("SPAN");
    expect(logo.dataset.fallback).toBe("true");
    expect(logo.querySelector("svg")).not.toBeNull();
  });

  it("falls back to the name's initial without a category", () => {
    render(<ProviderLogo provider="acme" name="acme storage" />);
    expect(screen.getByRole("img", { name: "acme storage" }).textContent).toBe(
      "A",
    );
  });

  it("moves to the API icon, then the fallback, as images fail to load", () => {
    render(
      <ProviderLogo
        provider="openai|1"
        name="OpenAI"
        icon="/icons/adapter-icons/OpenAI.png"
        category="llm"
      />,
    );
    const mark = screen.getByRole("img", { name: "OpenAI" });
    expect(mark.getAttribute("src")).toBe(PROVIDER_MARKS.openai.src);

    fireEvent.error(mark);
    const png = screen.getByRole("img", { name: "OpenAI" });
    expect(png.getAttribute("src")).toBe("/icons/adapter-icons/OpenAI.png");

    fireEvent.error(png);
    expect(screen.getByRole("img", { name: "OpenAI" }).dataset.fallback).toBe(
      "true",
    );
  });

  it("inverts one-ink marks on the dark theme only", () => {
    const { rerender } = render(
      <ProviderLogo provider="openai" name="OpenAI" />,
    );
    expect(screen.getByRole("img").className).toContain("ui:dark:invert");
    rerender(<ProviderLogo provider="gdrive" name="Google Drive" />);
    expect(screen.getByRole("img").className).not.toContain("invert");
  });

  it("hides a decorative logo from assistive technology", () => {
    const { container } = render(
      <ProviderLogo provider="gdrive" name="Google Drive" decorative />,
    );
    expect(screen.queryByRole("img")).toBeNull();
    expect(container.querySelector("img")?.getAttribute("alt")).toBe("");
  });
});

describe("ProductMark and RegionFlag", () => {
  it("render the design's SVGs with an optional label", () => {
    render(
      <>
        <ProductMark product="llmwhisperer" label="LLMWhisperer" />
        <RegionFlag region="eu" label="Europe" />
        <RegionFlag region="us" />
      </>,
    );
    expect(
      screen.getByRole("img", { name: "LLMWhisperer" }).getAttribute("src"),
    ).toBe(PRODUCT_MARKS.llmwhisperer.src);
    expect(
      screen.getByRole("img", { name: "Europe" }).getAttribute("src"),
    ).toBe(REGION_FLAGS.eu.src);
    expect(screen.getAllByRole("img")).toHaveLength(2);
  });
});
