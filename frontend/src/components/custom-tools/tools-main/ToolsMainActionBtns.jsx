import { BarChartOutlined } from "@ant-design/icons";
import { Button, Space, Tooltip } from "antd";
import { useNavigate } from "react-router-dom";

import { useCustomToolStore } from "../../../store/custom-tool-store";
import usePostHogEvents from "../../../hooks/usePostHogEvents";

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

function ToolsMainActionBtns() {
  const {
    disableLlmOrDocChange,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    isSimplePromptStudio,
  } = useCustomToolStore();
  const navigate = useNavigate();
  const { setPostHogCustomEvent } = usePostHogEvents();

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
      <Tooltip title="Output Analyzer">
        <Button
          icon={<BarChartOutlined />}
          onClick={handleOutputAnalyzerBtnClick}
          disabled={
            disableLlmOrDocChange?.length > 0 || isSinglePassExtractLoading
          }
        />
      </Tooltip>
    </Space>
  );
}

export { ToolsMainActionBtns };
