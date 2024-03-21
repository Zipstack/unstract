import {
  ArrowLeftOutlined,
  EditOutlined,
  ExportOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Button, Space, Switch, Tooltip, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./Header.css";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

function Header({ setOpenSettings, handleUpdateTool }) {
  const [isExportLoading, setIsExportLoading] = useState(false);
  const { details, updateCustomTool } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const navigate = useNavigate();
  const handleException = useExceptionHandler();

  useEffect(() => {
    updateCustomTool({
      singlePassExtractMode: details?.single_pass_extraction_mode,
    });
  }, []);

  const handleSinglePassExtractChange = (value) => {
    updateCustomTool({
      singlePassExtractMode: value,
    });

    handleUpdateTool({ single_pass_extraction_mode: value }).catch((err) => {
      setAlertDetails(
        handleException(err, "Failed to switch the single pass extraction mode")
      );
      // Revert the mode if the API fails
      updateCustomTool({
        singlePassExtractMode: !value,
      });
    });
  };

  const handleExport = () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/export/?prompt_registry_id=${details?.tool_id}`,
    };

    setIsExportLoading(true);
    axiosPrivate(requestOptions)
      .then(() => {
        setAlertDetails({
          type: "success",
          content: "Custom tool exported successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to export"));
      })
      .finally(() => {
        setIsExportLoading(false);
      });
  };

  return (
    <div className="custom-tools-header-layout">
      <div>
        <Button
          size="small"
          type="text"
          onClick={() => navigate(`/${sessionDetails?.orgName}/tools`)}
        >
          <ArrowLeftOutlined />
        </Button>
      </div>
      <div className="custom-tools-name">
        <Typography.Text strong>{details?.tool_name}</Typography.Text>
      </div>
      <div>
        <Button size="small" type="text" disabled>
          <EditOutlined />
        </Button>
      </div>
      <div className="custom-tools-header-btns">
        <Space>
          <Typography.Text className="font-size-12">
            Single Pass Extraction
          </Typography.Text>
          <Switch
            size="small"
            onChange={(value) => handleSinglePassExtractChange(value)}
          />
        </Space>
        <div>
          <Tooltip title="Settings">
            <Button
              icon={<SettingOutlined />}
              onClick={() => setOpenSettings(true)}
            />
          </Tooltip>
        </div>
        <div className="custom-tools-header-v-divider" />
        <div>
          <Tooltip title="Export">
            <CustomButton
              type="primary"
              onClick={handleExport}
              loading={isExportLoading}
            >
              <ExportOutlined />
            </CustomButton>
          </Tooltip>
        </div>
      </div>
    </div>
  );
}

Header.propTypes = {
  setOpenSettings: PropTypes.func.isRequired,
  handleUpdateTool: PropTypes.func.isRequired,
};

export { Header };
