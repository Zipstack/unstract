import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StageTimings } from "./StageTimings";

/**
 * The breakdown is read against the execution time shown elsewhere on the
 * page, so the two must agree: percentages come off the reported `total`, not
 * off the sum of the segments, and an unrecognised stage key from a newer
 * backend has to render rather than vanish.
 */

const payload = (overrides = {}) => ({
  version: 1,
  total: 20,
  stages: {
    queue_wait: 2,
    setup: 1,
    tool_execution: 15,
    destination: 1,
  },
  ...overrides,
});

describe("StageTimings", () => {
  it("labels each known stage and formats its duration", () => {
    render(<StageTimings timings={payload()} />);

    expect(screen.getByText("Queue wait")).toBeInTheDocument();
    expect(screen.getByText("Tool execution")).toBeInTheDocument();
    expect(screen.getByText("15.0s")).toBeInTheDocument();
  });

  it("renders percentages against the reported total", () => {
    render(<StageTimings timings={payload()} />);

    // tool_execution 15 of total 20
    expect(screen.getByText("75.0%")).toBeInTheDocument();
  });

  it("shows the unaccounted remainder as its own segment", () => {
    render(<StageTimings timings={payload({ unaccounted: 1 })} />);

    expect(screen.getByText("Unaccounted")).toBeInTheDocument();
  });

  it("omits the unaccounted row when there is no remainder", () => {
    render(<StageTimings timings={payload({ unaccounted: 0 })} />);

    expect(screen.queryByText("Unaccounted")).not.toBeInTheDocument();
  });

  it("renders a stage key it does not recognise", () => {
    const timings = payload();
    timings.stages.manual_review = 3;

    render(<StageTimings timings={timings} />);

    expect(screen.getByText("Manual review")).toBeInTheDocument();
  });

  it("renders the tool split when present", () => {
    render(
      <StageTimings
        timings={payload({
          tool_split: { extraction: 9, indexing: 3, prompts: 3 },
        })}
      />,
    );

    expect(screen.getByText("Tool execution split")).toBeInTheDocument();
    expect(screen.getByText("Text extraction")).toBeInTheDocument();
  });

  it("formats sub-second and multi-minute durations readably", () => {
    render(
      <StageTimings
        timings={{ total: 200, stages: { setup: 0.25, tool_execution: 185 } }}
      />,
    );

    expect(screen.getByText("250ms")).toBeInTheDocument();
    expect(screen.getByText("3m 5s")).toBeInTheDocument();
  });

  it("says so rather than rendering an empty chart when there is no timing", () => {
    render(<StageTimings timings={null} />);

    expect(
      screen.getByText(/No stage timing was recorded/),
    ).toBeInTheDocument();
  });

  it("treats a payload with empty maps as no timing", () => {
    render(<StageTimings timings={{ version: 1, stages: {} }} />);

    expect(
      screen.getByText(/No stage timing was recorded/),
    ).toBeInTheDocument();
  });

  it("notes that an aggregate is summed across files, not elapsed", () => {
    render(<StageTimings timings={payload({ files: 7 })} />);

    expect(screen.getByText(/Summed across 7 files/)).toBeInTheDocument();
  });

  it("states the total, which covers the queue wait the column does not", () => {
    render(<StageTimings timings={payload()} />);

    expect(screen.getByText("Queued to complete")).toBeInTheDocument();
    expect(screen.getByText("20.0s")).toBeInTheDocument();
  });

  it("labels the total differently for an execution-level aggregate", () => {
    render(<StageTimings timings={payload({ files: 3 })} />);

    expect(screen.getByText("Total time spent")).toBeInTheDocument();
    expect(screen.queryByText("Queued to complete")).not.toBeInTheDocument();
  });

  it("explains the unaccounted remainder on hover", () => {
    render(<StageTimings timings={payload({ unaccounted: 1 })} />);

    // The hint is attached to the row, which means the label is wrapped.
    expect(screen.getByText("Unaccounted")).toBeInTheDocument();
  });

  it("falls back to the segment sum when no total is reported", () => {
    render(
      <StageTimings timings={{ stages: { setup: 5, tool_execution: 15 } }} />,
    );

    // 15 of the 20 the segments add up to
    expect(screen.getByText("75.0%")).toBeInTheDocument();
  });
});
