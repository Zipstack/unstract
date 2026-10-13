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
    render(<DisplayPromptResult {...baseProps} output={largeArray} />);

    // Top indicator shows count
    expect(screen.getByText(/Showing 50 of 200 items/)).toBeInTheDocument();

    // "show more" links should appear (top + bottom)
    expect(screen.getAllByText(/show more \(150 remaining\)/).length).toBe(2);

    // Item 50 text should NOT be in the document
    expect(screen.queryByText(/item-50/)).not.toBeInTheDocument();
  });

  it("reveals next batch on 'show more' click", () => {
    storeOverride = { ...defaultStore, details: { enable_highlight: true } };

    const largeArray = Array.from({ length: 120 }, (_, i) => `item-${i}`);
    render(<DisplayPromptResult {...baseProps} output={largeArray} />);

    // Initially 50 visible
    expect(screen.getByText(/Showing 50 of 120/)).toBeInTheDocument();
    expect(screen.getAllByText(/show more \(70 remaining\)/).length).toBe(2);

    // Click the first "show more" (top indicator)
    fireEvent.click(screen.getAllByText(/show more/)[0]);

    // Now 100 items visible
    expect(screen.getByText(/Showing 100 of 120/)).toBeInTheDocument();
    expect(screen.getAllByText(/show more \(20 remaining\)/).length).toBe(2);

    // Click again to show the rest
    fireEvent.click(screen.getAllByText(/show more/)[0]);

    // All 120 items visible, no "show more" link or indicator
    expect(screen.queryByText(/show more/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Showing/)).not.toBeInTheDocument();
  });
});
