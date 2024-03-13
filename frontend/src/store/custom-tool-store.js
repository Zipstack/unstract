import { create } from "zustand";

import { promptType } from "../helpers/GetStaticData";

const defaultState = {
  dropdownItems: {},
  selectedDoc: null,
  listOfDocs: [],
  defaultLlmProfile: "",
  llmProfiles: [],
  details: {},
  disableLlmOrDocChange: [],
  indexDocs: [],
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
    setState(entireState);
  },
  updateCustomTool: (entireState) => {
    const existingState = { ...getState() };
    setState({ existingState, ...entireState });
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
    setState({ ...newState });
  },
  deleteInstance: (promptId) => {
    const newState = { ...getState() };
    const promptsAndNotes = newState?.details?.prompts;
    const filteredData = promptsAndNotes.filter(
      (item) => item?.prompt_id !== promptId
    );
    newState["details"]["prompts"] = filteredData;
    setState({ ...newState });
  },
  getDropdownItems: (propertyName) => {
    const existingState = { ...getState() };
    const dropdownItems = existingState?.dropdownItems || {};
    return dropdownItems[propertyName];
  },
}));

export { useCustomToolStore };
