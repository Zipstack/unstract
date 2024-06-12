import {
  ArrowLeftOutlined,
  EditOutlined,
  SettingOutlined,
  ShareAltOutlined,
  CopyOutlined,
} from "@ant-design/icons";
import { Button, Tooltip, Typography } from "antd";
import PropTypes from "prop-types";
import { useState, useEffect } from "react";
import { useNavigate, useLocation,useParams } from "react-router-dom";
import "./Header.css";
import { PromptShareModal } from "../prompt-public-share-modal/PromptShareModal";
import { PromptShareLink } from "../prompt-public-link-modal/PromptShareLink";
import { ExportToolIcon } from "../../../assets";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { ExportTool } from "../export-tool/ExportTool";
import usePostHogEvents from "../../../hooks/usePostHogEvents";

let SinglePassToggleSwitch;
try {
  SinglePassToggleSwitch =
    require("../../../plugins/single-pass-toggle-switch/SinglePassToggleSwitch").SinglePassToggleSwitch;
} catch {
  // The variable will remain undefined if the component is not available.
}
function Header({ setOpenSettings, handleUpdateTool, setOpenShareModal }) {
  const [isExportLoading, setIsExportLoading] = useState(false);
  const { details } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const navigate = useNavigate();
  const handleException = useExceptionHandler();
  const [userList, setUserList] = useState([]);
  const [openExportToolModal, setOpenExportToolModal] = useState(false);
  const { setPostHogCustomEvent } = usePostHogEvents();
  const location = useLocation()
  const [toolDetails, setToolDetails] = useState(null);
  const { id } = useParams();

  const handleExport = (selectedUsers, toolDetail, isSharedWithEveryone) => {
    // const body = {
    //   is_shared_with_org: isSharedWithEveryone,
    //   user_id: isSharedWithEveryone ? [] : selectedUsers,
    // };
    const requestOptions = {
      method: "POST",
      // url: `/api/v1/unstract/${sessionDetails?.orgId}/public-share-manager/prompt-metadata/?id=d0134a50-e7b6-4918-b660-d8bb3fff465d`,
      url: `/api/v1/unstract/${sessionDetails?.orgId}/share-manager/?id=21468f4d-ca25-4050-8c51-917d85964816`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: {
        share_type: "PROMPT_STUDIO",
      },
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
        setOpenExportToolModal(false);
      });
  };

  const handleClone = (isClone) => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/clone/${id}`,
    };

    axiosPrivate(requestOptions)
      .then((response) => {
        const cloned_tool = response?.data?.tool_id || undefined;
        navigate(`/${sessionDetails?.orgName}/tools/${cloned_tool}`);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to clone project"));
      });
  };
  const handleShare = (isEdit) => {
    try {
      setPostHogCustomEvent("ps_exported_tool", {
        info: `Clicked on the 'Export' button`,
        tool_name: details?.tool_name,
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }

    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/share-manager/`,
      data: {
        id: "21468f4d-ca25-4050-8c51-917d85964816",
        share_type: "PROMPT_STUDIO",
      },
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    setIsExportLoading(true);
    getAllUsers().then((users) => {
      if (users.length < 2) {
        handleExport([details?.created_by], details, false);
      } else {
        axiosPrivate(requestOptions)
          .then((res) => {
            setOpenExportToolModal(true);
            setToolDetails({ ...res?.data, created_by: details?.created_by });
          })
          .catch((err) => {
            setAlertDetails(handleException(err));
          })
          .finally(() => {
            setIsExportLoading(false);
          });
      }
    });
  };

  const getAllUsers = async () => {
    setIsExportLoading(true);
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/users/`,
    };

    const userList = axiosPrivate(requestOptions)
      .then((response) => {
        const users = response?.data?.members || [];
        setUserList(
          users.map((user) => ({
            id: user?.id,
            email: user?.email,
          }))
        );
        return users;
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to load"));
      })
      .finally(() => {
        setIsExportLoading(false);
      });

    return userList;
  };

  return (
    <div className="custom-tools-header-layout">
      <div>
        <Button
          size="small"
          type="text"
          disabled={window.location.pathname.startsWith(`/share`)}
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
          <SinglePassToggleSwitch handleUpdateTool={handleUpdateTool}
          disabled={window.location.pathname.startsWith(`/share`)}
          />
        )}
        <div>
          <Tooltip title="Settings">
            <Button
              icon={<SettingOutlined />}
              onClick={() => setOpenSettings(true)}
            />
          </Tooltip>
        </div>
        <div>
          <Tooltip title="Clone">
            <Button icon={<CopyOutlined />} onClick={() => handleClone(true)} />
          </Tooltip>
        </div>
        <div>
            <Tooltip title="Public Share">
              <Button
                icon={<ShareAltOutlined />}
                disabled={window.location.pathname.startsWith(`/share`)}
                onClick={() => setOpenShareModal(true)}
              />
            </Tooltip>
        </div>
        <div className="custom-tools-header-v-divider" />
        <div>
          <Tooltip title="Export as tool">
            <CustomButton
              type="primary"
              disabled={window.location.pathname.startsWith(`/share`)}
              onClick={() => handleShare(true)}
              loading={isExportLoading}
            >
              <ExportToolIcon />
            </CustomButton>
          </Tooltip>
        </div>
        <ExportTool
          allUsers={userList}
          open={openExportToolModal}
          setOpen={setOpenExportToolModal}
          onApply={handleExport}
          loading={isExportLoading}
          toolDetails={toolDetails}
        />
      </div>
    </div>
  );
}

Header.propTypes = {
  setOpenSettings: PropTypes.func.isRequired,
  handleUpdateTool: PropTypes.func.isRequired,
};

export { Header };
