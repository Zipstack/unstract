import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useSessionStore } from "../../../store/session-store.js";

let options = {};

function inputService() {
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const path = `/api/v1/unstract/${sessionDetails.orgId.replaceAll('"', "")}`;

  return {
    getFileList: (storageId, filePath = "/") => {
      options = {
        url: `${path}/file`,
        method: "GET",
        params: {
          connector_id: storageId,
          path: filePath,
        },
      };
      return axiosPrivate(options);
    },
  };
}

export { inputService };
