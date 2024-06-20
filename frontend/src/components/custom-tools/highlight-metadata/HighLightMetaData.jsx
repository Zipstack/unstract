import { Checkbox, Form, Space, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { CustomButton } from "../../../components/widgets/custom-button/CustomButton";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

function HighLightMetaData({ handleUpdateTool }) {
  const [enableHighlighting, setEnableHighlighting] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const { details, updateCustomTool } = useCustomToolStore();

  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  useEffect(() => {
    setEnableHighlighting(details?.enable_challenge || false);
  }, []);

  const handleSubmit = () => {
    const body = {
      enable_highlight: enableHighlighting,
    };
    setIsLoading(true);
    handleUpdateTool(body)
      .then((res) => {
        const data = res?.data;
        const updatedDetails = { ...details };

        updatedDetails["enable_highlight"] = data?.enable_challenge;
        updateCustomTool({ details: updatedDetails });

        setAlertDetails({
          type: "success",
          content: "Saved highlight settings successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to update"));
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  return (
    <SpaceWrapper>
      <div className="settings-body-pad-top">
        <Typography.Text strong className="pre-post-amble-title">
          Enable highlighting ( Will only work with LLM whisperer as text
          extractor)
        </Typography.Text>
      </div>
      <Form layout="vertical" onFinish={handleSubmit}>
        <Form.Item>
          <Space>
            <Checkbox
              checked={enableHighlighting}
              onChange={(e) => setEnableHighlighting(e.target.checked)}
            />
            <Typography.Text>Enable Highlighting</Typography.Text>
          </Space>
        </Form.Item>
        <Form.Item className="display-flex-right">
          <CustomButton type="primary" htmlType="submit" loading={isLoading}>
            Save
          </CustomButton>
        </Form.Item>
      </Form>
    </SpaceWrapper>
  );
}

HighLightMetaData.propTypes = {
  handleUpdateTool: PropTypes.func.isRequired,
};

export { HighLightMetaData };
