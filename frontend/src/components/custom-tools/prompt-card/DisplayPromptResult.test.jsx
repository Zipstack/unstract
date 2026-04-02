import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

// Mock dependencies before importing the component
vi.mock("../../../store/custom-tool-store", () => ({
  useCustomToolStore: () => ({
    singlePassExtractMode: false,
    isSinglePassExtractLoading: false,
    details: {},
    selectedHighlight: null,
  }),
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
  it("shows 'Yet to run' when output is null", () => {
    render(<DisplayPromptResult {...baseProps} output={null} />);
    expect(screen.getByText(/Yet to run/)).toBeInTheDocument();
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
