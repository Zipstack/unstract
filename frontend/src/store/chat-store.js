import { create } from "zustand";

const defaultChatState = {
  chatHistory: [],
  chatTranscript: [],
  currentContext: {},
};

const CHAT_VARIABLES = { ...defaultChatState };
const useChatStore = create((setState, getState) => ({
  ...CHAT_VARIABLES,
  setDefaultChatDetails: () => {
    setState({ ...defaultChatState });
  },
  setChatDetails: (details) => {
    setState(details);
  },
  setChatHistory: (history) => {
    setState(() => {
      return { chatHistory: history };
    });
  },
  setChatTranscript: (transcripts) => {
    setState(() => {
      return { chatTranscript: transcripts };
    });
  },
  updateChatHistory: (record) => {
    const existingState = { ...getState() };
    existingState.chatHistory = [record, ...existingState.chatHistory];
    setState({ ...existingState });
  },
  updateChatTranscript: (record) => {
    const existingState = { ...getState() };
    existingState.chatTranscript = [record, ...existingState.chatTranscript];
    setState({ ...existingState });
  },
  setCurrentContext: (context) => {
    setState(() => {
      return { currentContext: context };
    });
  },
}));

export { useChatStore };
