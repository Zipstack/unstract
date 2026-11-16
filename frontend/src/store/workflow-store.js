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
    setState({ ...entireState });
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
    const { details } = getState();
    const toolInstances = details?.tool_instances || [];
    if (!toolInstances.some((tool) => tool?.id === toolId)) {
      return;
    }
    setState({
      details: {
        ...details,
        tool_instances: toolInstances.map((tool) =>
          tool?.id === toolId ? { ...tool, metadata } : tool,
        ),
      },
    });
  },
  addNewTool: (toolInstance) => {
    const { details } = getState();
    if (!details) {
      return;
    }
    setState({
      details: {
        ...details,
        tool_instances: [...(details.tool_instances || []), toolInstance],
      },
    });
  },
  deleteToolInstance: (toolId) => {
    const { details } = getState();
    if (!details) {
      return;
    }
    setState({
      details: {
        ...details,
        tool_instances: (details.tool_instances || []).filter(
          (tool) => tool?.id !== toolId,
        ),
      },
    });
  },
}));

export { useWorkflowStore };
