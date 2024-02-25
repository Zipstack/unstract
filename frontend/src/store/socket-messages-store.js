import { create } from "zustand";

const defaultState = {
  stagedMessages: [],
  message: {},
  pointer: 0,
};

const STORE_VARIABLES = defaultState;

const useSocketMessagesStore = create((setState, getState) => ({
  ...STORE_VARIABLES,
  pushStagedMessage: (msg) => {
    const existingState = { ...getState() };
    const stagedMsgs = [...(existingState?.stagedMessages || [])];
    stagedMsgs.push(msg);
    existingState.stagedMessages = stagedMsgs;
    setState(existingState);
  },
  shiftStagedMessage: () => {
    const existingState = { ...getState() };
    const stagedMsgs = [...(existingState?.stagedMessages || [])];
    stagedMsgs.shift();
    existingState.stagedMessages = stagedMsgs;
    setState(existingState);
  },
  updateMessage: (msg) => {
    const existingState = { ...getState() };
    existingState.message = msg;
    setState(existingState);
  },
  setPointer: (value) => {
    setState({ ...getState(), ...{ pointer: value } });
  },
  setDefault: () => {
    setState(defaultState);
  },
}));

export { useSocketMessagesStore };
