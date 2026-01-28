import { useAlertStore } from "../store/alert-store";

function useCopyToClipboard() {
  const { setAlertDetails } = useAlertStore();

  const copyToClipboard = (text, label = "Text") => {
    if (!navigator.clipboard) {
      setAlertDetails({
        type: "error",
        content: "Clipboard not available in this browser",
      });
      return;
    }
    navigator.clipboard.writeText(text).then(
      () => {
        setAlertDetails({
          type: "success",
          content: `${label} copied to clipboard`,
        });
      },
      (err) => {
        setAlertDetails({
          type: "error",
          content: `Failed to copy: ${err.message || "Unknown error"}`,
        });
      }
    );
  };

  return copyToClipboard;
}

export { useCopyToClipboard };
