/*
 * Stopping a running prompt (UN-1031).
 *
 * The rules pinned here are the ones a user notices when they go wrong: a Stop
 * on one prompt must not stop the others, queued-but-unsent runs must vanish
 * without a request, and a stopped run must clear its spinner rather than hang
 * until the 16-minute timeout.
 */
import { act, renderHook } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const requests = [];
let nextResponse = { data: { status: "accepted" } };

vi.mock("./useAxiosPrivate", () => ({
  useAxiosPrivate: () => (options) => {
    requests.push(options);
    return Promise.resolve(nextResponse);
  },
}));

import { generateApiRunStatusId } from "../helpers/GetStaticData";
import { useAlertStore } from "../store/alert-store";
import { useCustomToolStore } from "../store/custom-tool-store";
import { usePromptRunQueueStore } from "../store/prompt-run-queue-store";
import { usePromptRunStatusStore } from "../store/prompt-run-status-store";
import { useSessionStore } from "../store/session-store";
import usePromptRun from "./usePromptRun";

const TOOL_ID = "tool-1";
const PROMPT_A = "prompt-a";
const PROMPT_B = "prompt-b";
const DOC = "doc-1";
const PROFILE = "profile-1";

const cancelRequests = () =>
  requests.filter((req) => req.url?.endsWith("/cancel/"));

// usePromptRun reaches useExceptionHandler, which calls useNavigate.
const wrapper = ({ children }) => <MemoryRouter>{children}</MemoryRouter>;
const renderUsePromptRun = () => renderHook(() => usePromptRun(), { wrapper });

beforeEach(() => {
  requests.length = 0;
  nextResponse = { data: { status: "accepted" } };
  useSessionStore.setState({
    sessionDetails: { orgId: "org-1", csrfToken: "csrf" },
  });
  useCustomToolStore.setState({
    details: { tool_id: TOOL_ID, prompts: [] },
    llmProfiles: [],
    listOfDocs: [],
  });
  usePromptRunStatusStore.setState({ promptRunStatus: {}, activeRuns: {} });
  usePromptRunQueueStore.setState({ activeApis: 0, queue: [] });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("stopping prompt runs", () => {
  it("registers a run before the request is sent, so a Stop works during extraction", () => {
    const { result } = renderUsePromptRun();

    act(() => {
      result.current.runPrompt([`${PROMPT_A}__${DOC}__${PROFILE}`]);
    });

    const runs = usePromptRunStatusStore.getState().activeRuns;
    expect(Object.keys(runs)).toHaveLength(1);
    const [runId] = Object.keys(runs);
    // The registered run id is the one sent to the backend, so a later cancel
    // names something the backend can actually find.
    const runPost = requests.find((req) => req.url?.includes("fetch_response"));
    expect(runPost.data.run_id).toBe(runId);
    expect(runs[runId].promptIds).toEqual([PROMPT_A]);
  });

  it("cancels only the named prompt, leaving the rest of a bulk run going", async () => {
    const { result } = renderUsePromptRun();

    act(() => {
      result.current.runPrompt([`${PROMPT_A}__${DOC}__${PROFILE}`]);
    });
    const [runId] = Object.keys(usePromptRunStatusStore.getState().activeRuns);
    // Pretend this run covers two prompts, as a bulk run does.
    act(() => {
      usePromptRunStatusStore.getState().registerRun(runId, {
        promptIds: [PROMPT_A, PROMPT_B],
        docId: DOC,
        profileId: PROFILE,
      });
    });

    act(() => {
      result.current.stopPromptRuns(PROMPT_A);
    });

    const [cancel] = cancelRequests();
    expect(cancel.data.runs).toEqual([
      { run_id: runId, prompt_ids: [PROMPT_A] },
    ]);
  });

  it("cancels whole runs when stopping everything", () => {
    const { result } = renderUsePromptRun();

    act(() => {
      result.current.runPrompt([`${PROMPT_A}__${DOC}__${PROFILE}`]);
    });
    const [runId] = Object.keys(usePromptRunStatusStore.getState().activeRuns);

    act(() => {
      result.current.stopAllRuns();
    });

    const [cancel] = cancelRequests();
    // No prompt_ids: the run's shared extract/index stages stop too.
    expect(cancel.data.runs).toEqual([{ run_id: runId }]);
    expect(cancel.method).toBe("POST");
    expect(cancel.url).toContain(`/prompt-studio/${TOOL_ID}/cancel/`);
  });

  it("drops queued runs locally without asking the backend", () => {
    const { result } = renderUsePromptRun();
    const statusKey = generateApiRunStatusId(DOC, PROFILE);

    act(() => {
      usePromptRunQueueStore.setState({
        activeApis: 0,
        queue: [
          `${PROMPT_A}__${DOC}__${PROFILE}`,
          `${PROMPT_B}__${DOC}__${PROFILE}`,
        ],
      });
      usePromptRunStatusStore.getState().addPromptStatus({
        [PROMPT_A]: { [statusKey]: "RUNNING" },
        [PROMPT_B]: { [statusKey]: "RUNNING" },
      });
    });

    act(() => {
      result.current.stopPromptRuns(PROMPT_A);
    });

    const { queue } = usePromptRunQueueStore.getState();
    expect(queue).toEqual([`${PROMPT_B}__${DOC}__${PROFILE}`]);
    // Nothing was ever sent for the queued run, so there is nothing to cancel.
    expect(cancelRequests()).toHaveLength(0);
    const status = usePromptRunStatusStore.getState().promptRunStatus;
    expect(status[PROMPT_A]).toBeUndefined();
    expect(status[PROMPT_B][statusKey]).toBe("RUNNING");
  });

  it("marks stopped runs as stopping, so the button can say so", () => {
    const { result } = renderUsePromptRun();

    act(() => {
      result.current.runPrompt([`${PROMPT_A}__${DOC}__${PROFILE}`]);
    });
    act(() => {
      result.current.stopAllRuns();
    });

    const runs = usePromptRunStatusStore.getState().activeRuns;
    expect(Object.values(runs).every((run) => run.stopping)).toBe(true);
  });

  it("un-marks and reports a run the backend could not stop", async () => {
    const { result } = renderUsePromptRun();

    act(() => {
      result.current.runPrompt([`${PROMPT_A}__${DOC}__${PROFILE}`]);
    });
    const [runId] = Object.keys(usePromptRunStatusStore.getState().activeRuns);

    // The signal store was unreachable: the run is still going and still
    // billing, so the UI must not keep claiming it is stopping.
    nextResponse = { data: { cancelled: [], failed: [runId] } };
    await act(async () => {
      result.current.stopAllRuns();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(usePromptRunStatusStore.getState().activeRuns[runId].stopping).toBe(
      false,
    );
  });

  // Both raised in code review: a per-prompt Stop was disabling its siblings'
  // buttons, and was too weak to stop a run it was the only prompt of.
  it("stopping one prompt of a bulk run leaves its siblings alone", () => {
    const { result } = renderUsePromptRun();

    act(() => {
      result.current.runPrompt([`${PROMPT_A}__${DOC}__${PROFILE}`]);
    });
    const [runId] = Object.keys(usePromptRunStatusStore.getState().activeRuns);
    act(() => {
      usePromptRunStatusStore.getState().registerRun(runId, {
        promptIds: [PROMPT_A, PROMPT_B],
        docId: DOC,
        profileId: PROFILE,
      });
    });

    act(() => {
      result.current.stopPromptRuns(PROMPT_A);
    });

    const run = usePromptRunStatusStore.getState().activeRuns[runId];
    // B is still running and still billing, so its Stop must stay usable.
    expect(run.stoppingPromptIds).toEqual([PROMPT_A]);
    expect(run.stoppingPromptIds).not.toContain(PROMPT_B);
  });

  it("stops the whole run when no other prompt of it is left running", () => {
    const { result } = renderUsePromptRun();

    act(() => {
      result.current.runPrompt([`${PROMPT_A}__${DOC}__${PROFILE}`]);
    });

    act(() => {
      result.current.stopPromptRuns(PROMPT_A);
    });

    const [cancel] = cancelRequests();
    const [runId] = Object.keys(usePromptRunStatusStore.getState().activeRuns);
    // No prompt_ids: naming one would spare the extraction and indexing this
    // run's prompts share — but there is no sibling left to spare them for.
    expect(cancel.data.runs).toEqual([{ run_id: runId }]);
  });

  it("still spares the shared stages while a sibling is running", () => {
    const { result } = renderUsePromptRun();

    act(() => {
      result.current.runPrompt([`${PROMPT_A}__${DOC}__${PROFILE}`]);
    });
    const [runId] = Object.keys(usePromptRunStatusStore.getState().activeRuns);
    act(() => {
      usePromptRunStatusStore.getState().registerRun(runId, {
        promptIds: [PROMPT_A, PROMPT_B],
        docId: DOC,
        profileId: PROFILE,
      });
    });

    act(() => {
      result.current.stopPromptRuns(PROMPT_A);
    });

    const [cancel] = cancelRequests();
    expect(cancel.data.runs).toEqual([
      { run_id: runId, prompt_ids: [PROMPT_A] },
    ]);
  });

  it("sends nothing when there is nothing running", () => {
    const { result } = renderUsePromptRun();

    act(() => {
      result.current.stopAllRuns();
      result.current.stopPromptRuns(PROMPT_A);
    });

    expect(cancelRequests()).toHaveLength(0);
  });

  // The safety net exists because a socket event can go missing. What it says
  // matters: a run the user stopped themselves must not be reported back to
  // them as a failure of the product.
  const runUntilTheSafetyNetFires = async (result, { stop }) => {
    const statusKey = generateApiRunStatusId(DOC, PROFILE);
    await act(async () => {
      result.current.runPrompt([`${PROMPT_A}__${DOC}__${PROFILE}`]);
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => {
      usePromptRunStatusStore.getState().addPromptStatus({
        [PROMPT_A]: { [statusKey]: "RUNNING" },
      });
    });
    if (stop) {
      await act(async () => {
        result.current.stopAllRuns();
        await Promise.resolve();
        await Promise.resolve();
      });
    }
    act(() => {
      vi.advanceTimersByTime(16 * 60 * 1000);
    });
  };

  it("reports a run the user stopped as stopped, not as a timeout", async () => {
    vi.useFakeTimers();
    try {
      const { result } = renderUsePromptRun();
      await runUntilTheSafetyNetFires(result, { stop: true });

      const { alertDetails } = useAlertStore.getState();
      expect(alertDetails.type).toBe("info");
      expect(alertDetails.content).toContain("stopped");
      // And the run stops being offered as stoppable — nothing more is coming.
      expect(usePromptRunStatusStore.getState().activeRuns).toEqual({});
    } finally {
      vi.useRealTimers();
    }
  });

  it("still reports a genuinely silent run as a timeout", async () => {
    vi.useFakeTimers();
    try {
      const { result } = renderUsePromptRun();
      await runUntilTheSafetyNetFires(result, { stop: false });

      const { alertDetails } = useAlertStore.getState();
      expect(alertDetails.type).toBe("warning");
      expect(alertDetails.content).toContain("timed out");
    } finally {
      vi.useRealTimers();
    }
  });

  it("clears the spinner when the POST itself reports the run was cancelled", async () => {
    nextResponse = { data: { status: "cancelled", run_id: "ignored" } };
    const { result } = renderUsePromptRun();
    const statusKey = generateApiRunStatusId(DOC, PROFILE);

    await act(async () => {
      result.current.runPrompt([`${PROMPT_A}__${DOC}__${PROFILE}`]);
      await Promise.resolve();
      await Promise.resolve();
    });

    // No socket event will ever arrive for this run, so the response has to be
    // the thing that clears it.
    expect(
      usePromptRunStatusStore.getState().promptRunStatus?.[PROMPT_A]?.[
        statusKey
      ],
    ).toBeUndefined();
    expect(usePromptRunStatusStore.getState().activeRuns).toEqual({});
  });
});

describe("prompt run queue store", () => {
  it("keeps activeApis intact when purging the queue", () => {
    usePromptRunQueueStore.setState({ activeApis: 3, queue: ["a__b__c"] });

    act(() => {
      usePromptRunQueueStore.getState().removeQueuedApis(() => true);
    });

    // Requests already in flight cannot be recalled; decrementing here would
    // let the pump exceed its concurrency limit.
    expect(usePromptRunQueueStore.getState().activeApis).toBe(3);
    expect(usePromptRunQueueStore.getState().queue).toEqual([]);
  });

  it("returns the entries it removed", () => {
    usePromptRunQueueStore.setState({
      activeApis: 0,
      queue: ["p1__d__pr", "p2__d__pr"],
    });

    let removed;
    act(() => {
      removed = usePromptRunQueueStore
        .getState()
        .removeQueuedApis((api) => api.startsWith("p1__"));
    });

    expect(removed).toEqual(["p1__d__pr"]);
    expect(usePromptRunQueueStore.getState().queue).toEqual(["p2__d__pr"]);
  });
});
