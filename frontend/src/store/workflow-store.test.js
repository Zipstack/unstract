import { beforeEach, describe, expect, it } from "vitest";

import { useWorkflowStore } from "./workflow-store";

const toolA = { id: "a", metadata: { x: 1 } };
const toolB = { id: "b", metadata: { y: 2 } };

describe("workflow-store tool instance actions", () => {
  beforeEach(() => {
    useWorkflowStore.getState().setDefaultWorkflowState();
    useWorkflowStore.setState({
      details: { id: "wf", tool_instances: [toolA] },
    });
  });

  it("addNewTool replaces details instead of mutating it", () => {
    const before = useWorkflowStore.getState().details;

    useWorkflowStore.getState().addNewTool(toolB);

    const state = useWorkflowStore.getState();
    expect(state.details).not.toBe(before);
    expect(before.tool_instances).toEqual([toolA]);
    expect(state.details).toEqual({ id: "wf", tool_instances: [toolA, toolB] });
    expect(state).not.toHaveProperty("existingState");
  });

  it("deleteToolInstance replaces details instead of mutating it", () => {
    const before = useWorkflowStore.getState().details;

    useWorkflowStore.getState().deleteToolInstance("a");

    const state = useWorkflowStore.getState();
    expect(state.details).not.toBe(before);
    expect(before.tool_instances).toEqual([toolA]);
    expect(state.details.tool_instances).toEqual([]);
    expect(state).not.toHaveProperty("existingState");
  });

  it("updateMetadata replaces the instance instead of mutating it", () => {
    const before = useWorkflowStore.getState().details;

    useWorkflowStore.getState().updateMetadata("a", { x: 9 });

    const state = useWorkflowStore.getState();
    expect(state.details).not.toBe(before);
    expect(toolA.metadata).toEqual({ x: 1 });
    expect(state.getMetadata("a")).toEqual({ x: 9 });
  });

  it("updateMetadata ignores an unknown tool id", () => {
    const before = useWorkflowStore.getState().details;

    useWorkflowStore.getState().updateMetadata("missing", { x: 9 });

    expect(useWorkflowStore.getState().details).toBe(before);
  });

  it("updateWorkflow does not add an existingState key", () => {
    useWorkflowStore.getState().updateWorkflow({ isLoading: true });

    const state = useWorkflowStore.getState();
    expect(state.isLoading).toBe(true);
    expect(state).not.toHaveProperty("existingState");
  });
});
