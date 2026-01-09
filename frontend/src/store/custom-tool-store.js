import { create } from "zustand";

import { promptType } from "../helpers/GetStaticData";

const defaultState = {
  dropdownItems: {},
  selectedDoc: null,
  listOfDocs: [],
  refreshRawView: false,
  defaultLlmProfile: "",
  llmProfiles: [],
  details: {},
  disableLlmOrDocChange: [],
  indexDocs: [],
  rawIndexStatus: [],
  summarizeIndexStatus: [],
  singlePassExtractMode: false,
  isMultiPassExtractLoading: false,
  isSinglePassExtractLoading: false,
  isSimplePromptStudio: false,
  shareId: null,
  isPublicSource: false,
  isChallengeEnabled: false,
  adapters: [],
  selectedHighlight: null,
  hasUnsavedChanges: false,
  lastExportedAt: null,
  deploymentUsageInfo: null,
};

const defaultPromptInstance = {
  prompt_key: "Enter key",
  prompt: "Enter prompt",
  output_type: "Text",
  output_processing: "Default",
  prompt_type: promptType.prompt,
};

const defaultNoteInstance = {
  prompt_key: "Enter key",
  prompt: "Enter notes",
  output_type: "Text",
  output_processing: "Default",
  prompt_type: promptType.notes,
};

const STORE_VARIABLES = { ...defaultState };

const useCustomToolStore = create((setState, getState) => ({
  ...STORE_VARIABLES,
  setDefaultCustomTool: () => {
    setState({ ...defaultState });
  },
  setCustomTool: (entireState) => {
    // Reset unsaved changes when loading a new tool
    setState({
      ...entireState,
      hasUnsavedChanges: false,
      deploymentUsageInfo: entireState?.deploymentUsageInfo ?? null,
      lastExportedAt: entireState?.lastExportedAt ?? null,
    });
  },
  updateCustomTool: (entireState) => {
    setState((state) => ({ state, ...entireState }));
  },
  addNewInstance: (type) => {
    const newState = { ...getState() };
    const promptsAndNotes = newState?.details?.prompts;

    if (type === promptType.prompt) {
      const newPrompt = { ...defaultPromptInstance };
      newPrompt["prompt_id"] = `unsaved_${promptsAndNotes.length + 1}`;
      promptsAndNotes.push(newPrompt);
    } else {
      const newNote = { ...defaultNoteInstance };
      newNote["prompt_id"] = `unsaved_${promptsAndNotes.length + 1}`;
      promptsAndNotes.push(newNote);
    }
    newState["details"]["prompts"] = [...promptsAndNotes];
    // Mark as having unsaved changes when a new prompt/note is added
    newState["hasUnsavedChanges"] = true;
    setState({ ...newState });
  },
  deleteInstance: (promptId) => {
    const newState = { ...getState() };
    const promptsAndNotes = newState?.details?.prompts;
    const filteredData = promptsAndNotes.filter(
      (item) => item?.prompt_id !== promptId
    );
    newState["details"]["prompts"] = filteredData;
    // Mark as having unsaved changes when a prompt/note is deleted
    newState["hasUnsavedChanges"] = true;
    setState({ ...newState });
  },
  getDropdownItems: (propertyName) => {
    const existingState = { ...getState() };
    const dropdownItems = existingState?.dropdownItems || {};
    return dropdownItems[propertyName];
  },
  pushIndexDoc: (docId) => {
    const existingState = { ...getState() };
    const docs = [...(existingState?.indexDocs || [])];
    docs.push(docId);

    existingState.indexDocs = docs;
    setState(existingState);
  },
  deleteIndexDoc: (docId) => {
    const existingState = { ...getState() };
    const docs = [...(existingState?.indexDocs || [])].filter(
      (item) => item !== docId
    );
    existingState.indexDocs = docs;
    setState(existingState);
  },
  setHasUnsavedChanges: (hasChanges) => {
    setState({ hasUnsavedChanges: hasChanges });
  },
  setLastExportedAt: (timestamp) => {
    setState({ lastExportedAt: timestamp });
  },
  setDeploymentUsageInfo: (info) => {
    setState({ deploymentUsageInfo: info });
  },
  markChangesAsExported: () => {
    setState({
      hasUnsavedChanges: false,
      lastExportedAt: new Date().toISOString(),
    });
  },
}));

export { useCustomToolStore };
