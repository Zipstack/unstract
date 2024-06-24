import { BarChartOutlined } from "@ant-design/icons";
import { Button, Space, Tooltip } from "antd";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useNavigate } from "react-router-dom";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { AddPromptBtn } from "../../../plugins/simple-prompt-studio/AddPromptBtn";

let RunSinglePassBtn;
try {
  RunSinglePassBtn =
    require("../../../plugins/run-single-pass-btn/RunSinglePassBtn").RunSinglePassBtn;
} catch {
  // The variable is remain undefined if the component is not available
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

  if (isSimplePromptStudio) {
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
