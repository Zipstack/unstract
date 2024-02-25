import { create } from "zustand";

const STORE_VARIABLES = {
  AlertDetails: {
    type: "",
    content: "",
  },
};
const useAlertStore = create((setState) => ({
  ...STORE_VARIABLES,
  setAlertDetails: (details) => {
    setState(() => {
      return { AlertDetails: { ...details, duration: 5 } };
    });
  },
}));

export { useAlertStore };
