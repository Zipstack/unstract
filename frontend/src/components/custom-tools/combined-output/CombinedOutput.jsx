import "prismjs";
import "prismjs/components/prism-json";
import "prismjs/plugins/line-numbers/prism-line-numbers.css";
import "prismjs/plugins/line-numbers/prism-line-numbers.js";
import "prismjs/themes/prism.css";
import PropTypes from "prop-types";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

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
  const tvMod = await import("../../../plugins/simple-prompt-studio/TableView");
  TableView = tvMod.TableView;
  const helperMod = await import(
    "../../../plugins/simple-prompt-studio/helper"
  );
  promptOutputApiSps = helperMod.promptOutputApiSps;
} catch {
  // The component will remain null if it is not available
}

let publicOutputsApi;
let publicAdapterApi;
let publicDefaultOutputApi;
try {
  const mod = await import(
    "../../../plugins/prompt-studio-public-share/helpers/PublicShareAPIs"
  );
  publicOutputsApi = mod.publicOutputsApi;
  publicAdapterApi = mod.publicAdapterApi;
  publicDefaultOutputApi = mod.publicDefaultOutputApi;
} catch {
  // The component will remain null if it is not available
}

// OSS falls back to passthrough helpers — no enrichment.
let splitCombinedData = (data) => ({ combined: data, bundle: null });
let buildEnrichedFromBundle = (_output, _bundle, _formatter) => ({});
let getEnrichmentFromItem = (_item) => null;
try {
  const mod = await import("../../../plugins/lookup-enriched-toggle/helpers");
  splitCombinedData = mod.splitCombinedData;
  buildEnrichedFromBundle = mod.buildEnrichedFromBundle;
  getEnrichmentFromItem = mod.getEnrichmentFromItem;
} catch {}

const buildDefaultProfileOutputs = (data) => {
  const { combined: payload, bundle } = splitCombinedData(data);
  const output = Object.entries(payload).reduce((acc, [key, value]) => {
    acc[key] = displayPromptResult(value, false);
    return acc;
  }, {});
  const enriched = buildEnrichedFromBundle(output, bundle, displayPromptResult);
  return {
    output,
    enriched,
    hasEnriched: bundle != null && Object.keys(enriched).length > 0,
  };
};

const buildPerPromptOutput = (item, data, selectedProfile) => {
  const profileManager = selectedProfile || item?.profile_manager;
  const outputDetails = data.find(
    (outputValue) =>
      outputValue?.prompt_id === item?.prompt_id &&
      outputValue?.profile_manager === profileManager,
  );
  const value =
    outputDetails?.output?.length > 0
      ? displayPromptResult(outputDetails?.output, false)
      : "";
  const enrichment = getEnrichmentFromItem(outputDetails);
  const enrichedValue = enrichment?.output
    ? displayPromptResult(enrichment.output, false)
    : value;
  return { value, enrichedValue, hasEnriched: !!enrichment?.output };
};

const buildSelectedProfileOutputs = (data, prompts, selectedProfile) => {
  const output = {};
  const enriched = {};
  let hasEnriched = false;
  for (const item of prompts) {
    if (item?.prompt_type === promptType.notes) continue;
    const {
      value,
      enrichedValue,
      hasEnriched: enrichedHit,
    } = buildPerPromptOutput(item, data, selectedProfile);
    output[item?.prompt_key] = value;
    enriched[item?.prompt_key] = enrichedValue;
    hasEnriched = hasEnriched || enrichedHit;
  }
  return { output, enriched: hasEnriched ? enriched : {}, hasEnriched };
};

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
  const [enrichedOutput, setEnrichedOutput] = useState({});
  const [isOutputLoading, setIsOutputLoading] = useState(false);
  const [adapterData, setAdapterData] = useState([]);
  const [activeKey, setActiveKey] = useState(
    singlePassExtractMode ? defaultLlmProfile : "0",
  );
  const [selectedProfile, setSelectedProfile] = useState(defaultLlmProfile);
  const [filteredCombinedOutput, setFilteredCombinedOutput] = useState({});

  const { id } = useParams();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  useEffect(() => {
    if (isSimplePromptStudio) {
      return;
    }

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
          handleException(err, "Failed to fetch adapter information"),
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
    if (!docId || isSinglePassExtractLoading) {
      return;
    }

    const fetchCombinedOutput = async () => {
      setIsOutputLoading(true);
      setCombinedOutput({});

      try {
        const res = await handleOutputApiRequest();
        const data = res?.data || [];
        const prompts = details?.prompts || [];
        const useDefaultProfile = activeKey === "0" && !isSimplePromptStudio;
        const { output, enriched } = useDefaultProfile
          ? buildDefaultProfileOutputs(data)
          : buildSelectedProfileOutputs(data, prompts, selectedProfile);
        setCombinedOutput(output);
        setEnrichedOutput(enriched);
      } catch (err) {
        setAlertDetails(
          handleException(err, "Failed to generate combined output"),
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
        selectedProfile || defaultLlmProfile,
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
    [defaultLlmProfile],
  );

  // Filter combined output based on selectedPrompts
  useEffect(() => {
    const filteredCombinedOutput = Object.fromEntries(
      Object.entries(combinedOutput).filter(
        ([key]) => !selectedPrompts || selectedPrompts[key],
      ),
    );

    const filledFields = Object.values(filteredCombinedOutput).filter(
      (value) => value === 0 || (value && value.length > 0),
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
      enrichedOutput={enrichedOutput}
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
  selectedPrompts: PropTypes.object,
};

export { CombinedOutput };
