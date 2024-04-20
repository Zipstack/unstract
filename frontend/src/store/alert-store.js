import { create } from "zustand";

const STORE_VARIABLES = {
  alertDetails: {
    type: "",
    content: "",
    title: "",
  },
};
const useAlertStore = create((setState) => ({
  ...STORE_VARIABLES,
  setAlertDetails: (details) => {
    setState(() => {
      const title = details.title;
      const notificationTitle =
        title || (details.type === "error" ? "Failed" : "Success");
      return { alertDetails: { ...details, title: notificationTitle } };
    });
  },
}));

export { useAlertStore };
