import { create } from "zustand";

const STORE_VARIABLES = {
  AlertDetails: {
    type: "",
    content: "",
    title: "",
  },
};
const useAlertStore = create((setState) => ({
  ...STORE_VARIABLES,
  setAlertDetails: (details) => {
    setState(() => {
      let title = details.title;
      if (!title) {
        if (details.type === "error") {
          title = "Failed";
        } else {
          title = "Success";
        }
      }
      return { AlertDetails: { ...details, title } };
    });
  },
}));

export { useAlertStore };
