import { displayURL } from "../helpers/GetStaticData";
import { useAlertStore } from "../store/alert-store";
import { useExceptionHandler } from "./useExceptionHandler";

const usePipelineHelper = () => {
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const getApiKeys = (apiService, id, setApiKeys, setOpenManageKeysModal) => {
    apiService
      .getApiKeys(id)
      .then((res) => {
        setApiKeys(res?.data);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setOpenManageKeysModal(true);
      });
  };

  const downloadPostmanCollection = (apiService, id) => {
    apiService
      .downloadPostmanCollection(id)
      .then((res) => {
        const { data, headers } = res;
        const href = URL.createObjectURL(data);
        // Get filename from header or use a default
        const filename =
          headers["content-disposition"]
            ?.split("filename=")[1]
            ?.trim()
            .replaceAll('"', "") || "postman_collection.json";
        // create "a" HTML element with href to file & click
        const link = document.createElement("a");
        link.href = href;
        link.setAttribute("download", filename);
        document.body.appendChild(link);
        link.click();

        // clean up "a" element & remove ObjectURL
        document.body.removeChild(link);
        URL.revokeObjectURL(href);
        setAlertDetails({
          type: "success",
          content: "Collection downloaded successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  const copyUrl = (text) => {
    const completeUrl = displayURL(text);
    navigator.clipboard
      .writeText(completeUrl)
      .then(() => {
        setAlertDetails({
          type: "success",
          content: "Endpoint copied to clipboard",
        });
      })
      .catch((error) => {
        setAlertDetails({
          type: "error",
          content: "Copy failed",
        });
      });
  };

  return {
    getApiKeys,
    downloadPostmanCollection,
    copyUrl,
  };
};

export default usePipelineHelper;
