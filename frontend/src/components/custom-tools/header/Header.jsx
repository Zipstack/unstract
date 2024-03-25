import {
  ArrowLeftOutlined,
  EditOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Button, Tooltip, Typography } from "antd";
import PropTypes from "prop-types";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./Header.css";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { ExportToolIcon } from "../../../assets";

let SinglePassToggleSwitch;
try {
  SinglePassToggleSwitch =
    require("../../../plugins/single-pass-toggle-switch/SinglePassToggleSwitch").SinglePassToggleSwitch;
} catch {
  // The variable will remain undefined if the component is not available.
}
function Header({ setOpenSettings, handleUpdateTool }) {
  const [isExportLoading, setIsExportLoading] = useState(false);
  const { details, disableLlmOrDocChange, isSinglePassExtractLoading } =
    useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const navigate = useNavigate();
  const handleException = useExceptionHandler();

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
        {SinglePassToggleSwitch && (
          <SinglePassToggleSwitch handleUpdateTool={handleUpdateTool} />
        )}
        <div>
          <Tooltip title="Settings">
            <Button
              icon={<SettingOutlined />}
              onClick={() => setOpenSettings(true)}
              disabled={
                disableLlmOrDocChange?.length > 0 || isSinglePassExtractLoading
              }
            />
          </Tooltip>
        </div>
        <div className="custom-tools-header-v-divider" />
        <div>
          <Tooltip title="Export as tool">
            <CustomButton
              type="primary"
              onClick={handleExport}
              loading={isExportLoading}
            >
              <ExportToolIcon />
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
