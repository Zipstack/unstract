import "prismjs/components/prism-json";
import "prismjs/plugins/line-numbers/prism-line-numbers.css";
import "prismjs/plugins/line-numbers/prism-line-numbers.js";
import "prismjs/themes/prism.css";
import { useEffect, useState, useCallback, useRef } from "react";
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

  // Lookup enrichment state
  const [isEnriching, setIsEnriching] = useState(false);
  const [enrichmentResult, setEnrichmentResult] = useState(null);
  const [hasLinkedLookups, setHasLinkedLookups] = useState(false);
  const enrichmentCheckedRef = useRef(false);

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

  // Check if there are linked Look-Ups for this project
  useEffect(() => {
    if (isSimplePromptStudio || isPublicSource) return;

    // Use id from URL params as fallback (same as tool_id)
    const toolId = details?.tool_id || id;
    if (!toolId || !sessionDetails?.orgId) return;

    // Skip if already checked for this tool
    if (enrichmentCheckedRef.current === toolId) return;

    const checkLinkedLookups = async () => {
      try {
        const url = `/api/v1/unstract/${sessionDetails?.orgId}/lookup-links/?prompt_studio_project_id=${toolId}`;
        const res = await axiosPrivate.get(url);
        const links = res?.data?.results || res?.data || [];
        setHasLinkedLookups(links.length > 0);
        enrichmentCheckedRef.current = toolId;
      } catch (err) {
        // Silently fail - lookups may not be available
        console.debug("Could not check for linked Look-Ups:", err);
        setHasLinkedLookups(false);
      }
    };

    checkLinkedLookups();
  }, [details?.tool_id, id, sessionDetails?.orgId]);

  // Reset enrichment when document changes
  useEffect(() => {
    setEnrichmentResult(null);
  }, [docId]);

  // Handler for enriching output with Look-Ups
  const handleEnrichWithLookups = useCallback(async () => {
    if (isEnriching || Object.keys(filteredCombinedOutput).length === 0) return;

    setIsEnriching(true);
    try {
      const toolId = details?.tool_id || id;
      const url = `/api/v1/unstract/${sessionDetails?.orgId}/lookup-debug/enrich_ps_output/`;

      // Get fresh CSRF token from cookie
      const csrfToken =
        sessionDetails?.csrfToken ||
        document.cookie
          .split("; ")
          .find((row) => row.startsWith("csrftoken="))
          ?.split("=")[1];

      const res = await axiosPrivate.post(
        url,
        {
          prompt_studio_project_id: toolId,
          extracted_data: filteredCombinedOutput,
        },
        {
          headers: {
            "X-CSRFToken": csrfToken,
            "Content-Type": "application/json",
          },
        }
      );

      setEnrichmentResult(res.data);
      setAlertDetails({
        type: "success",
        content: `Successfully enriched with ${
          res.data._lookup_metadata?.lookups_executed || 0
        } Look-Up(s)`,
      });
    } catch (err) {
      setAlertDetails(handleException(err, "Failed to enrich with Look-Ups"));
    } finally {
      setIsEnriching(false);
    }
  }, [
    filteredCombinedOutput,
    details?.tool_id,
    id,
    sessionDetails?.orgId,
    isEnriching,
  ]);

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
          const output = Object.entries(data).reduce((acc, [key, value]) => {
            acc[key] = displayPromptResult(value, false);
            return acc;
          }, {});
          setCombinedOutput(output);
        } else {
          const output = prompts.reduce((acc, item) => {
            if (item?.prompt_type !== promptType.notes) {
              const profileManager = selectedProfile || item?.profile_manager;
              const outputDetails = data.find(
                (outputValue) =>
                  outputValue?.prompt_id === item?.prompt_id &&
                  outputValue?.profile_manager === profileManager
              );

              acc[item?.prompt_key] =
                outputDetails?.output?.length > 0
                  ? displayPromptResult(outputDetails?.output, false)
                  : "";
            }
            return acc;
          }, {});
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
      onEnrichWithLookups={handleEnrichWithLookups}
      isEnriching={isEnriching}
      enrichmentResult={enrichmentResult}
      hasLinkedLookups={hasLinkedLookups}
    />
  );
}

CombinedOutput.propTypes = {
  docId: PropTypes.string.isRequired,
  setFilledFields: PropTypes.func,
  selectedPrompts: PropTypes.object.isRequired,
};

export { CombinedOutput };
