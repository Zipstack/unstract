import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

// Mutable store state so individual tests can override it.
const defaultStore = {
  singlePassExtractMode: false,
  isSinglePassExtractLoading: false,
  details: {},
  selectedHighlight: null,
};
let storeOverride = null;

// Mock dependencies before importing the component
vi.mock("../../../store/custom-tool-store", () => ({
  useCustomToolStore: () => storeOverride || defaultStore,
}));

vi.mock("../../../helpers/GetStaticData", () => ({
  displayPromptResult: (output) => output,
  generateApiRunStatusId: () => "key",
  generateUUID: () => "uuid-stub",
  PROMPT_RUN_API_STATUSES: { RUNNING: "RUNNING" },
}));

vi.mock("./PromptCard.css", () => ({}));

vi.mock("../../widgets/spinner-loader/SpinnerLoader", () => ({
  SpinnerLoader: () => React.createElement("div", { "data-testid": "spinner" }),
}));

import { DisplayPromptResult } from "./DisplayPromptResult";

const baseProps = {
  profileId: "profile-1",
  docId: "doc-1",
  promptRunStatus: {},
  handleSelectHighlight: vi.fn(),
  highlightData: null,
  promptDetails: { prompt_id: "p1" },
  confidenceData: null,
  wordConfidenceData: null,
  progressMsg: null,
};

describe("DisplayPromptResult null/undefined guard", () => {
  it("shows 'null' literal when output is null (ran but produced no value)", () => {
    render(<DisplayPromptResult {...baseProps} output={null} />);
    expect(screen.getByText("null")).toBeInTheDocument();
    expect(screen.queryByText(/Yet to run/)).not.toBeInTheDocument();
  });

  it("shows 'Yet to run' when output is undefined", () => {
    render(<DisplayPromptResult {...baseProps} output={undefined} />);
    expect(screen.getByText(/Yet to run/)).toBeInTheDocument();
  });

  it("does NOT show 'Yet to run' for a string output", () => {
    render(<DisplayPromptResult {...baseProps} output="Hello" />);
    expect(screen.queryByText(/Yet to run/)).not.toBeInTheDocument();
  });

  it("does NOT show 'Yet to run' for an empty string output", () => {
    render(<DisplayPromptResult {...baseProps} output="" />);
    expect(screen.queryByText(/Yet to run/)).not.toBeInTheDocument();
  });

  it("does NOT show 'Yet to run' for numeric zero output", () => {
    render(<DisplayPromptResult {...baseProps} output={0} />);
    expect(screen.queryByText(/Yet to run/)).not.toBeInTheDocument();
  });
});

describe("CappedArray rendering", () => {
  afterEach(() => {
    storeOverride = null;
  });

  it("renders only first 50 items for a 200-item array", () => {
    storeOverride = { ...defaultStore, details: { enable_highlight: true } };

    const largeArray = Array.from({ length: 200 }, (_, i) => `item-${i}`);
    const { container } = render(
      <DisplayPromptResult {...baseProps} output={largeArray} />,
    );

    // Count rendered items — each array item is a div inside the padded container
    const paddedDiv = container.querySelector('div[style*="padding-left"]');
    // Items are divs, the "show more" link is an <a>/<span> — count only divs
    const itemDivs = paddedDiv.querySelectorAll(":scope > div");
    expect(itemDivs.length).toBe(50);

    // "show more" link should appear with remaining count
    expect(screen.getByText(/show more \(150 remaining\)/)).toBeInTheDocument();

    // Item 50 text should NOT be in the document
    expect(screen.queryByText(/item-50/)).not.toBeInTheDocument();
  });

  it("reveals next batch on 'show more' click", () => {
    storeOverride = { ...defaultStore, details: { enable_highlight: true } };

    const largeArray = Array.from({ length: 120 }, (_, i) => `item-${i}`);
    const { container } = render(
      <DisplayPromptResult {...baseProps} output={largeArray} />,
    );

    const paddedDiv = container.querySelector('div[style*="padding-left"]');

    // Initially 50 visible
    expect(paddedDiv.querySelectorAll(":scope > div").length).toBe(50);
    expect(screen.getByText(/show more \(70 remaining\)/)).toBeInTheDocument();

    // Click "show more"
    fireEvent.click(screen.getByText(/show more/));

    // Now 100 items visible
    expect(paddedDiv.querySelectorAll(":scope > div").length).toBe(100);
    expect(screen.getByText(/show more \(20 remaining\)/)).toBeInTheDocument();

    // Click again to show the rest
    fireEvent.click(screen.getByText(/show more/));

    // All 120 items visible, no "show more" link
    expect(paddedDiv.querySelectorAll(":scope > div").length).toBe(120);
    expect(screen.queryByText(/show more/)).not.toBeInTheDocument();
  });
});
