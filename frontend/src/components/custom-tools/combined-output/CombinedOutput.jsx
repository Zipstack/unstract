import "prismjs/components/prism-json";
import "prismjs/plugins/line-numbers/prism-line-numbers.css";
import "prismjs/plugins/line-numbers/prism-line-numbers.js";
import "prismjs/themes/prism.css";
import { useEffect, useState, useCallback } from "react";
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
  // The component will remain null if it is not available
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
  // The component will remain null if it is not available
}

function CombinedOutput({ docId, setFilledFields, selectedPrompts }) {
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
  const [selectedProfile, setSelectedProfile] = useState(defaultLlmProfile);
  const [filteredCombinedOutput, setFilteredCombinedOutput] = useState({});

  const { id } = useParams();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  useEffect(() => {
    if (isSimplePromptStudio) return;

    const fetchAdapterInfo = async () => {
      let url = `/api/v1/unstract/${sessionDetails?.orgId}/adapter/?adapter_type=LLM`;
      if (isPublicSource) {
        url = publicAdapterApi(id, "LLM");
      }
      try {
        const res = await axiosPrivate.get(url);
        const adapterList = res?.data;
        setAdapterData(getLLMModelNamesForProfiles(llmProfiles, adapterList));
      } catch (err) {
        setAlertDetails(
          handleException(err, "Failed to fetch adapter information")
        );
      }
    };
    fetchAdapterInfo();
  }, []);

  useEffect(() => {
    const key = singlePassExtractMode ? defaultLlmProfile : "0";
    setActiveKey(key);
    setSelectedProfile(singlePassExtractMode ? defaultLlmProfile : null);
  }, [singlePassExtractMode]);

  useEffect(() => {
    if (!docId || isSinglePassExtractLoading) return;

    const fetchCombinedOutput = async () => {
      setIsOutputLoading(true);
      setCombinedOutput({});

      try {
        const res = await handleOutputApiRequest();
        const data = res?.data || [];
        const prompts = details?.prompts || [];

        if (activeKey === "0" && !isSimplePromptStudio) {
          const output = {};
          for (const key in data) {
            if (Object.hasOwn(data, key)) {
              output[key] = displayPromptResult(data[key], false);
            }
          }
          setCombinedOutput(output);
        } else {
          const output = {};
          prompts.forEach((item) => {
            if (item?.prompt_type === promptType.notes) return;

            const profileManager = selectedProfile || item?.profile_manager;
            const outputDetails = data.find(
              (outputValue) =>
                outputValue?.prompt_id === item?.prompt_id &&
                outputValue?.profile_manager === profileManager
            );

            if (outputDetails && outputDetails?.output?.length > 0) {
              output[item?.prompt_key] = displayPromptResult(
                outputDetails.output,
                false
              );
            } else {
              output[item?.prompt_key] = "";
            }
          });
          setCombinedOutput(output);
        }
      } catch (err) {
        setAlertDetails(
          handleException(err, "Failed to generate combined output")
        );
      } finally {
        setIsOutputLoading(false);
      }
    };

    fetchCombinedOutput();
  }, [docId, activeKey]);

  const handleOutputApiRequest = useCallback(async () => {
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
      const orgId = sessionDetails?.orgId;
      const toolId = details?.tool_id;
      const profileManager = selectedProfile || defaultLlmProfile;
      url = `/api/v1/unstract/${orgId}/prompt-studio/prompt-output/?tool_id=${toolId}&document_manager=${docId}&is_single_pass_extract=${singlePassExtractMode}&profile_manager=${profileManager}`;
      if (activeKey === "0") {
        url = `/api/v1/unstract/${orgId}/prompt-studio/prompt-output/prompt-default-profile/?tool_id=${toolId}&document_manager=${docId}`;
      }
    }
    const requestOptions = {
      method: "GET",
      url,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    const res = await axiosPrivate(requestOptions);
    return res;
  }, [
    singlePassExtractMode,
    docId,
    selectedProfile,
    defaultLlmProfile,
    activeKey,
  ]);

  const handleTabChange = useCallback(
    (key) => {
      setActiveKey(key);
      setSelectedProfile(key === "0" ? defaultLlmProfile : key);
    },
    [defaultLlmProfile]
  );

  // Filter combined output based on selectedPrompts
  useEffect(() => {
    const filteredCombinedOutput = Object.fromEntries(
      Object.entries(combinedOutput).filter(
        ([key]) => !selectedPrompts || selectedPrompts[key]
      )
    );

    const filledFields = Object.values(filteredCombinedOutput).filter(
      (value) => value === 0 || (value && value.length > 0)
    ).length;

    if (setFilledFields) {
      setFilledFields(filledFields);
    }
    setFilteredCombinedOutput(filteredCombinedOutput);
  }, [selectedPrompts, combinedOutput]);

  if (isSimplePromptStudio && TableView) {
    return (
      <TableView combinedOutput={combinedOutput} isLoading={isOutputLoading} />
    );
  }

  return (
    <JsonView
      combinedOutput={filteredCombinedOutput}
      handleTabChange={handleTabChange}
      selectedProfile={selectedProfile}
      llmProfiles={llmProfiles}
      activeKey={activeKey}
      adapterData={adapterData}
      isSinglePass={singlePassExtractMode}
      isLoading={isOutputLoading}
    />
  );
}

CombinedOutput.propTypes = {
  docId: PropTypes.string.isRequired,
  setFilledFields: PropTypes.func,
  selectedPrompts: PropTypes.object.isRequired,
};

export { CombinedOutput };
