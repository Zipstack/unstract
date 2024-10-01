import { BarChartOutlined } from "@ant-design/icons";
import { Button, Space, Tooltip } from "antd";
import { useNavigate } from "react-router-dom";

import { useCustomToolStore } from "../../../store/custom-tool-store";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { useTokenUsageStore } from "../../../store/token-usage-store";
import { RunAllPrompts } from "../prompt-card/RunAllPrompts";

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
  // The component will remain null of it is not available
}

function ToolsMainActionBtns() {
  const {
    isMultiPassExtractLoading,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    isSimplePromptStudio,
    defaultLlmProfile,
    selectedDoc,
  } = useCustomToolStore();
  const navigate = useNavigate();
  const { setPostHogCustomEvent } = usePostHogEvents();
  const { tokenUsage } = useTokenUsageStore();
  const tokenUsageId = `single_pass__${defaultLlmProfile}__${selectedDoc?.document_id}`;

  const handleOutputAnalyzerBtnClick = () => {
    navigate("outputAnalyzer");

    try {
      setPostHogCustomEvent("ps_output_analyser_seen", {
        info: "Clicked on 'Output Analyzer' button",
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
  };

  if (isSimplePromptStudio && AddPromptBtn) {
    return <AddPromptBtn />;
  }

  return (
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
    </Space>
  );
}

export { ToolsMainActionBtns };
