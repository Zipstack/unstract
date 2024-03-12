import {
  ArrowLeftOutlined,
  CodeOutlined,
  DiffOutlined,
  EditOutlined,
  ExportOutlined,
  FileTextOutlined,
  MessageOutlined,
} from "@ant-design/icons";
import { Button, Tooltip, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./Header.css";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { PreAndPostAmbleModal } from "../pre-and-post-amble-modal/PreAndPostAmbleModal";
import { SelectLlmProfileModal } from "../select-llm-profile-modal/SelectLlmProfileModal";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

let SummarizeHeader = null;

try {
  SummarizeHeader =
    require("../../../plugins/summarize-header/SummarizeHeader").SummarizeHeader;
} catch {
  // The component will remain null of it is not available
}

function Header({
  setOpenCusSynonymsModal,
  setOpenManageLlmModal,
  handleUpdateTool,
}) {
  const [openPreOrPostAmbleModal, setOpenPreOrPostAmbleModal] = useState(false);
  const [openSummLlmProfileModal, setOpenSummLlmProfileModal] = useState(false);
  const [preOrPostAmble, setPreOrPostAmble] = useState("");
  const [isExportLoading, setIsExportLoading] = useState(false);
  const [summarizeLlmBtnText, setSummarizeLlmBtnText] = useState(null);
  const [llmItems, setLlmItems] = useState([]);
  const { details, llmProfiles } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const navigate = useNavigate();
  const handleException = useExceptionHandler();

  useEffect(() => {
    getLlmProfilesDropdown();
  }, [llmProfiles]);

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

  const getLlmProfilesDropdown = () => {
    const items = [...llmProfiles].map((item) => {
      return {
        value: item?.profile_id,
        label: item?.profile_name,
      };
    });
    setLlmItems(items);
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
        {SummarizeHeader && (
          <SummarizeHeader
            setOpen={setOpenSummLlmProfileModal}
            btnText={summarizeLlmBtnText}
          />
        )}
        <div>
          <Button
            onClick={() => setOpenCusSynonymsModal(true)}
            icon={<MessageOutlined />}
          >
            Manage Grammar
          </Button>
        </div>
        <div>
          <Button
            onClick={() => setOpenManageLlmModal(true)}
            icon={<CodeOutlined />}
          >
            Manage LLM Profiles
          </Button>
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
      <SelectLlmProfileModal
        open={openSummLlmProfileModal}
        setOpen={setOpenSummLlmProfileModal}
        llmItems={llmItems}
        setBtnText={setSummarizeLlmBtnText}
        handleUpdateTool={handleUpdateTool}
      />
    </div>
  );
}

Header.propTypes = {
  setOpenCusSynonymsModal: PropTypes.func.isRequired,
  setOpenManageLlmModal: PropTypes.func.isRequired,
  handleUpdateTool: PropTypes.func.isRequired,
};

export { Header };
