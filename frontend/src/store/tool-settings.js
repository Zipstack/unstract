import { create } from "zustand";

const STORE_VARIABLES = {
  toolSettings: {
    id: "",
    tool_id: "",
  },
};

const useToolSettingsStore = create((setState, getState) => ({
  ...STORE_VARIABLES,
  setToolSettings: (details) => {
    const toolSettings = { toolSettings: { ...details } };
    setState(() => {
      return { ...toolSettings };
    });
  },
  updateToolSettings: (details) => {
    setState(() => {
      return { toolSettings: { ...getState().toolSettings, ...details } };
    });
  },
  cleanUpToolSettings: () => {
    setState(STORE_VARIABLES);
  },
}));

export { useToolSettingsStore };
