import { create } from "zustand";

const defaultState = {
  projectId: "",
  projectName: "",
  logId: "",
  prompt: "",
  isLoading: false,
  loadingType: "",
  source: {},
  destination: {},
  details: {},
  allowChangeEndpoint: true,
};

const STORE_VARIABLES = { ...defaultState };

const useWorkflowStore = create((setState, getState) => ({
  ...STORE_VARIABLES,
  setDefaultWorkflowState: () => {
    setState({ ...defaultState });
  },
  setWorkflow: (entireState) => {
    setState(entireState);
  },
  updateWorkflow: (entireState) => {
    const existingState = { ...getState() };
    setState({ existingState, ...entireState });
  },
  getMetadata: (toolInstanceId) => {
    try {
      const existingState = { ...getState() };
      const toolInstances = existingState?.details?.tool_instances || [];
      const toolInstance = toolInstances.find(
        (tool) => tool?.id === toolInstanceId,
      );
      return toolInstance?.metadata;
    } catch {
      return {};
    }
  },
  updateMetadata: (toolId, metadata) => {
    try {
      const existingState = { ...getState() };
      const toolInstances = existingState?.details?.tool_instances || [];
      const index = toolInstances.findIndex((tool) => tool?.id === toolId);
      toolInstances[index]["metadata"] = metadata;
      existingState["details"]["tool_instances"] = toolInstances;
      setState({ ...existingState });
    } catch {
      return;
    }
  },
  addNewTool: (toolInstance) => {
    try {
      const existingState = { ...getState() };
      const toolInstances = [...(existingState?.details?.tool_instances || [])];
      toolInstances.push(toolInstance);
      existingState.details["tool_instances"] = [...toolInstances];
      setState(() => {
        return { ...getState(), ...{ existingState } };
      });
    } catch (err) {
      return;
    }
  },
  deleteToolInstance: (toolId) => {
    try {
      const existingState = { ...getState() };
      const toolInstances = [...(existingState?.details?.tool_instances || [])];
      const filteredToolInstances = toolInstances.filter(
        (tool) => tool?.id !== toolId,
      );
      existingState.details["tool_instances"] = [...filteredToolInstances];
      setState({ ...getState(), existingState });
    } catch {
      return;
    }
  },
}));

export { useWorkflowStore };
