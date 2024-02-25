import {
  ArrowLeftOutlined,
  CodeOutlined,
  DiffOutlined,
  EditOutlined,
  ExportOutlined,
  FilePdfOutlined,
  FileTextOutlined,
  MessageOutlined,
} from "@ant-design/icons";
import { Button, Tooltip, Typography } from "antd";
import PropTypes from "prop-types";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./Header.css";

import { handleException } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { PreAndPostAmbleModal } from "../pre-and-post-amble-modal/PreAndPostAmbleModal";

function Header({
  setOpenCusSynonymsModal,
  setOpenManageDocsModal,
  setOpenManageLlmModal,
  handleUpdateTool,
}) {
  const [openPreOrPostAmbleModal, setOpenPreOrPostAmbleModal] = useState(false);
  const [preOrPostAmble, setPreOrPostAmble] = useState("");
  const [isExportLoading, setIsExportLoading] = useState(false);
  const { details } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const navigate = useNavigate();

  const handleOpenPreOrPostAmbleModal = (type) => {
    setOpenPreOrPostAmbleModal(true);
    setPreOrPostAmble(type);
  };
  const handleClosePreOrPostAmbleModal = () => {
    setOpenPreOrPostAmbleModal(false);
    setPreOrPostAmble("");
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
        <div>
          <Tooltip title="Manage Grammar">
            <Button onClick={() => setOpenCusSynonymsModal(true)}>
              <MessageOutlined />
            </Button>
          </Tooltip>
        </div>
        <div>
          <Tooltip title="Manage Documents">
            <Button onClick={() => setOpenManageDocsModal(true)}>
              <FilePdfOutlined />
            </Button>
          </Tooltip>
        </div>
        <div>
          <Tooltip title="Manage LLM Profiles">
            <Button onClick={() => setOpenManageLlmModal(true)}>
              <CodeOutlined />
            </Button>
          </Tooltip>
        </div>
        <div className="custom-tools-header-v-divider" />
        <div>
          <Tooltip title="Preamble">
            <Button onClick={() => handleOpenPreOrPostAmbleModal("PREAMBLE")}>
              <DiffOutlined />
            </Button>
          </Tooltip>
        </div>
        <div>
          <Tooltip title="Postamble">
            <Button onClick={() => handleOpenPreOrPostAmbleModal("POSTAMBLE")}>
              <FileTextOutlined />
            </Button>
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
      <PreAndPostAmbleModal
        isOpen={openPreOrPostAmbleModal}
        closeModal={handleClosePreOrPostAmbleModal}
        type={preOrPostAmble}
        handleUpdateTool={handleUpdateTool}
      />
    </div>
  );
}

Header.propTypes = {
  setOpenCusSynonymsModal: PropTypes.func.isRequired,
  setOpenManageDocsModal: PropTypes.func.isRequired,
  setOpenManageLlmModal: PropTypes.func.isRequired,
  handleUpdateTool: PropTypes.func.isRequired,
};

export { Header };
