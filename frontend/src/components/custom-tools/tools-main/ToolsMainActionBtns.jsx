import { BarChartOutlined, UnorderedListOutlined } from "@ant-design/icons";
import { Button, Space, Tooltip } from "antd";
import { useNavigate, useParams } from "react-router-dom";
import { useEffect, useRef, useState, useCallback, useMemo } from "react";

import { useCustomToolStore } from "../../../store/custom-tool-store";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { useTokenUsageStore } from "../../../store/token-usage-store";
import { RunAllPrompts } from "../prompt-card/RunAllPrompts";
import { PromptsReorderModal } from "../prompts-reorder/PromptsReorderModal";
import { useSessionStore } from "../../../store/session-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

// Import single pass related components
let RunSinglePassBtn;
try {
  RunSinglePassBtn =
    require("../../../plugins/run-single-pass-btn/RunSinglePassBtn").RunSinglePassBtn;
} catch {
  // The variable will remain undefined if the component is not available
}

// Import simple prompt studio related components
let AddPromptBtn;
try {
  AddPromptBtn =
    require("../../../plugins/simple-prompt-studio/AddPromptBtn").AddPromptBtn;
} catch {
  // The variable will remain undefined if the component is not available
}

let ChallengeModal;
try {
  ChallengeModal =
    require("../../../plugins/challenge-modal/ChallengeModal").ChallengeModal;
} catch {
  // The component will remain undefined if it is not available
}

function ToolsMainActionBtns() {
  const [openReorderModal, setOpenReorderModal] = useState(false);
  const [isNewOrderLoading, setIsNewOrderLoading] = useState(false);
  const isReordered = useRef(false);
  const { id } = useParams();
  const {
    isMultiPassExtractLoading,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    isSimplePromptStudio,
    defaultLlmProfile,
    selectedDoc,
    updateCustomTool,
  } = useCustomToolStore();

  const navigate = useNavigate();
  const { setPostHogCustomEvent } = usePostHogEvents();
  const { tokenUsage } = useTokenUsageStore();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const tokenUsageId = useMemo(
    () => `single_pass__${defaultLlmProfile}__${selectedDoc?.document_id}`,
    [defaultLlmProfile, selectedDoc?.document_id]
  );

  const handleOutputAnalyzerBtnClick = useCallback(() => {
    navigate("outputAnalyzer");

    try {
      setPostHogCustomEvent("ps_output_analyser_seen", {
        info: "Clicked on 'Output Analyzer' button",
      });
    } catch (err) {
      // If an error occurs while setting custom PostHog event, ignore it and continue
    }
  }, [navigate, setPostHogCustomEvent]);

  const updateReorderedStatus = useCallback((status) => {
    isReordered.current = status;
  }, []);

  const getPromptDetails = useCallback(() => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/${id}`,
    };

    setIsNewOrderLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data || {};
        updateCustomTool({ details: data });
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to fetch prompt details"));
      })
      .finally(() => {
        setIsNewOrderLoading(false);
      });
  }, []);

  // Fetch prompt details after reorder modal closes
  useEffect(() => {
    if (!openReorderModal && isReordered.current === true) {
      getPromptDetails();
      updateReorderedStatus(false);
    }
  }, [openReorderModal]);

  if (isSimplePromptStudio && AddPromptBtn) {
    return <AddPromptBtn />;
  }

  return (
    <>
      <Space>
        {singlePassExtractMode && RunSinglePassBtn && <RunSinglePassBtn />}
        {singlePassExtractMode && ChallengeModal && (
          <ChallengeModal
            challengeData={tokenUsage?.[`${tokenUsageId}__challenge_data`]}
            context={tokenUsage?.[`${tokenUsageId}__context`]}
            tokenUsage={tokenUsage?.[tokenUsageId]}
          />
        )}
        {!singlePassExtractMode && <RunAllPrompts />}
        <Tooltip title="Output Analyzer">
          <Button
            icon={<BarChartOutlined />}
            onClick={handleOutputAnalyzerBtnClick}
            disabled={isMultiPassExtractLoading || isSinglePassExtractLoading}
          />
        </Tooltip>
        <Tooltip title="Reorder the list of prompts">
          <Button
            icon={<UnorderedListOutlined />}
            onClick={() => setOpenReorderModal(true)}
            loading={isNewOrderLoading}
          />
        </Tooltip>
      </Space>
      <PromptsReorderModal
        open={openReorderModal}
        setOpen={setOpenReorderModal}
        updateReorderedStatus={updateReorderedStatus}
      />
    </>
  );
}

export { ToolsMainActionBtns };
