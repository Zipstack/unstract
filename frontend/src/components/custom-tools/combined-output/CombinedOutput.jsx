import "prismjs/components/prism-json";
import "prismjs/plugins/line-numbers/prism-line-numbers.css";
import "prismjs/plugins/line-numbers/prism-line-numbers.js";
import "prismjs/themes/prism.css";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import PropTypes from "prop-types";

import {
  displayPromptResult,
  getLLMModelNamesForProfiles,
  promptType,
} from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import "./CombinedOutput.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { JsonView } from "./JsonView";

let TableView;
let promptOutputApiSps;
try {
  TableView =
    require("../../../plugins/simple-prompt-studio/TableView").TableView;
  promptOutputApiSps =
    require("../../../plugins/simple-prompt-studio/helper").promptOutputApiSps;
} catch {
  // The component will remain null of it is not available
}
let publicOutputsApi;
let publicAdapterApi;
let publicDefaultOutputApi;
try {
  publicOutputsApi =
    require("../../../plugins/prompt-studio-public-share/helpers/PublicShareAPIs").publicOutputsApi;
  publicAdapterApi =
    require("../../../plugins/prompt-studio-public-share/helpers/PublicShareAPIs").publicAdapterApi;
  publicDefaultOutputApi =
    require("../../../plugins/prompt-studio-public-share/helpers/PublicShareAPIs").publicDefaultOutputApi;
} catch {
  // The component will remain null of it is not available
}
function CombinedOutput({ docId, setFilledFields }) {
  const {
    details,
    defaultLlmProfile,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    llmProfiles,
    isSimplePromptStudio,
    isPublicSource,
  } = useCustomToolStore();
  const [combinedOutput, setCombinedOutput] = useState({});
  const [isOutputLoading, setIsOutputLoading] = useState(false);
  const [adapterData, setAdapterData] = useState([]);
  const [activeKey, setActiveKey] = useState(
    singlePassExtractMode ? defaultLlmProfile : "0"
  );
  const { id } = useParams();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const [selectedProfile, setSelectedProfile] = useState(defaultLlmProfile);

  useEffect(() => {
    getAdapterInfo();
  }, []);

  useEffect(() => {
    setActiveKey(singlePassExtractMode ? defaultLlmProfile : "0");
    setSelectedProfile(singlePassExtractMode ? defaultLlmProfile : null);
  }, [singlePassExtractMode]);

  useEffect(() => {
    if (!docId || isSinglePassExtractLoading) {
      return;
    }
    let filledFields = 0;
    setIsOutputLoading(true);
    setCombinedOutput({});
    handleOutputApiRequest()
      .then((res) => {
        const data = res?.data || [];
        const prompts = details?.prompts;
        if (activeKey === "0" && !isSimplePromptStudio) {
          const output = {};
          for (const key in data) {
            if (Object.hasOwn(data, key)) {
              output[key] = displayPromptResult(data[key], false);
            }
          }
          setCombinedOutput(output);
          return;
        }
        const output = {};
        prompts.forEach((item) => {
          if (item?.prompt_type === promptType.notes) {
            return;
          }
          output[item?.prompt_key] = "";

          const profileManager = selectedProfile || item?.profile_manager;
          const outputDetails = data.find(
            (outputValue) =>
              outputValue?.prompt_id === item?.prompt_id &&
              outputValue?.profile_manager === profileManager
          );

          if (!outputDetails) {
            return;
          }

          output[item?.prompt_key] = displayPromptResult(
            outputDetails?.output,
            false
          );

          if (outputDetails?.output?.length > 0) {
            filledFields++;
          }
        });

        setCombinedOutput(output);

        if (setFilledFields) {
          setFilledFields(filledFields);
        }
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to generate combined output")
        );
      })
      .finally(() => {
        setIsOutputLoading(false);
      });
  }, [docId, isSinglePassExtractLoading, activeKey]);

  const handleOutputApiRequest = async () => {
    let url;
    if (isSimplePromptStudio) {
      url = promptOutputApiSps(details?.tool_id, null, docId);
    } else if (isPublicSource) {
      url = publicOutputsApi(
        id,
        null,
        singlePassExtractMode,
        docId,
        selectedProfile || defaultLlmProfile
      );
      if (activeKey === "0") {
        url = publicDefaultOutputApi(id, docId);
      }
    } else {
      url = `/api/v1/unstract/${
        sessionDetails?.orgId
      }/prompt-studio/prompt-output/?tool_id=${
        details?.tool_id
      }&document_manager=${docId}&is_single_pass_extract=${singlePassExtractMode}&profile_manager=${
        selectedProfile || defaultLlmProfile
      }`;
      if (activeKey === "0") {
        url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/prompt-default-profile/?tool_id=${details?.tool_id}&document_manager=${docId}`;
      }
    }
    const requestOptions = {
      method: "GET",
      url,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    return axiosPrivate(requestOptions)
      .then((res) => res)
      .catch((err) => {
        throw err;
      });
  };

  const getAdapterInfo = () => {
    if (isSimplePromptStudio) return;
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/adapter/?adapter_type=LLM`;
    if (isPublicSource) {
      url = publicAdapterApi(id, "LLM");
    }
    axiosPrivate.get(url).then((res) => {
      const adapterList = res?.data;
      setAdapterData(getLLMModelNamesForProfiles(llmProfiles, adapterList));
    });
  };

  if (isOutputLoading) {
    return <SpinnerLoader />;
  }

  const handleTabChange = (key) => {
    if (key === "0") {
      setSelectedProfile(defaultLlmProfile);
    } else {
      setSelectedProfile(key);
    }
    setActiveKey(key);
  };

  if (isSimplePromptStudio && TableView) {
    return <TableView combinedOutput={combinedOutput} />;
  }

  return (
    <JsonView
      combinedOutput={combinedOutput}
      handleTabChange={handleTabChange}
      selectedProfile={selectedProfile}
      llmProfiles={llmProfiles}
      activeKey={activeKey}
      adapterData={adapterData}
      isSinglePass={singlePassExtractMode}
    />
  );
}

CombinedOutput.propTypes = {
  docId: PropTypes.string,
  setFilledFields: PropTypes.func,
};

export { CombinedOutput };
