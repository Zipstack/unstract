import { create } from "zustand";

const STORE_VARIABLES = {
  alertDetails: {
    type: "",
    content: "",
    title: "",
    duration: undefined,
  },
};
const useAlertStore = create((setState) => ({
  ...STORE_VARIABLES,
  setAlertDetails: (details) => {
    setState(() => {
      const title = details.title;
      const notificationTitle =
        title || (details.type === "error" ? "Failed" : "Success");
      const duration =
        details.duration || details.type === "error" ? 0 : undefined;
      return {
        alertDetails: {
          ...details,
          title: notificationTitle,
          duration: duration,
        },
      };
    });
  },
}));

export { useAlertStore };
