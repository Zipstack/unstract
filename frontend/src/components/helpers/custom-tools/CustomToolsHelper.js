import { useEffect, useState } from "react";
import { Outlet, useNavigate, useParams } from "react-router-dom";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import { useTokenUsageStore } from "../../../store/token-usage-store";

let shareManagerToolSource;
try {
  shareManagerToolSource =
    require("../../../plugins/prompt-studio-public-share/helpers/PublicShareAPIs").shareManagerToolSource;
} catch (err) {
  // Do nothing, Not-found Page will be triggered.
}
function CustomToolsHelper() {
  const [isLoading, setIsLoading] = useState(true);
  const { id } = useParams();
  const { sessionDetails } = useSessionStore();
  const { updateCustomTool, setDefaultCustomTool } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const navigate = useNavigate();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const { resetTokenUsage } = useTokenUsageStore();

  useEffect(() => {
    const updatedCusTool = {
      listOfDocs: [],
      details: {},
      defaultLlmProfile: "",
      llmProfiles: [],
      selectedDoc: null,
      adapters: [],
    };

    const reqOpsPromptStudio = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/${id}`,
    };

    let selectedDocId = null;
    setIsLoading(true);
    handleApiRequest(reqOpsPromptStudio)
      .then((res) => {
        const data = res?.data;
        updatedCusTool["defaultLlmProfile"] = data?.default_profile;
        updatedCusTool["details"] = data;
        updatedCusTool["singlePassExtractMode"] =
          data?.single_pass_extraction_mode;
        selectedDocId = data?.output;
        updatedCusTool["isSimplePromptStudio"] = false;

        const reqOpsDocs = {
          method: "GET",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-document?tool_id=${data?.tool_id}`,
        };
        return handleApiRequest(reqOpsDocs);
      })
      .then((res) => {
        const data = res?.data || [];
        updatedCusTool["listOfDocs"] = data;

        const doc = data.find((item) => item?.document_id === selectedDocId);
        updatedCusTool["selectedDoc"] = doc || null;

        const reqOpsDropdownItems = {
          method: "GET",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/select_choices`,
        };
        return handleApiRequest(reqOpsDropdownItems);
      })
      .then((res) => {
        const data = res?.data;
        updatedCusTool["dropdownItems"] = data;

        const reqOpsLlmProfiles = {
          method: "GET",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-studio-profile/${id}`,
        };

        return handleApiRequest(reqOpsLlmProfiles);
      })
      .then((res) => {
        const data = res?.data;
        updatedCusTool["llmProfiles"] = data;
        if (shareManagerToolSource) {
          const reqOpsShare = {
            method: "GET",
            url: shareManagerToolSource(id, sessionDetails?.orgId),
          };
          return handleApiRequest(reqOpsShare);
        }
      })
      .then((res) => {
        const data = res?.data;
        updatedCusTool["shareId"] = data?.share_id;
        const reqOpsLlmProfiles = {
          method: "GET",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/`,
        };

        return handleApiRequest(reqOpsLlmProfiles);
      })
      .then((res) => {
        const data = res?.data;
        updatedCusTool["adapters"] = data;
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to load the custom tool"));
        navigate(`/${sessionDetails?.orgName}/tools`);
      })
      .finally(() => {
        updateCustomTool(updatedCusTool);
        setIsLoading(false);
      });
  }, [id]);

  useEffect(() => {
    return () => {
      setDefaultCustomTool();
      resetTokenUsage();
    };
  }, []);

  const handleApiRequest = async (requestOptions) => {
    return axiosPrivate(requestOptions)
      .then((res) => res)
      .catch((err) => {
        throw err;
      });
  };

  if (isLoading) {
    return <SpinnerLoader />;
  }
  return <Outlet />;
}

export { CustomToolsHelper };
