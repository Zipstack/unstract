import { create } from "zustand";

const STORE_VARIABLES = {
  sessionDetails: {},
  isLogoutLoading: false,
};
const useSessionStore = create((setState, getState) => ({
  ...STORE_VARIABLES,
  setSessionDetails: (details) => {
    setState(() => {
      return { sessionDetails: details };
    });
  },
  updateSessionDetails: (details) => {
    setState(() => {
      return { sessionDetails: { ...getState().sessionDetails, ...details } };
    });
  },
  setLogoutLoading: (loading) => {
    setState(() => ({ isLogoutLoading: loading }));
  },
}));

export { useSessionStore };
