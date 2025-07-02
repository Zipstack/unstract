import { SettingOutlined } from "@ant-design/icons";
import { Button, Modal, Tooltip, Typography, Dropdown } from "antd";
import PropTypes from "prop-types";
import { useCallback, useState } from "react";

import { HeaderTitle } from "../header-title/HeaderTitle.jsx";
import { ExportToolIcon } from "../../../assets";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { ExportTool } from "../export-tool/ExportTool";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import "./Header.css";

let SinglePassToggleSwitch;
let CloneButton;
let PromptShareButton;
try {
  SinglePassToggleSwitch =
    require("../../../plugins/single-pass-toggle-switch/SinglePassToggleSwitch").SinglePassToggleSwitch;
} catch {
  // The variable will remain undefined if the component is not available.
}
try {
  PromptShareButton =
    require("../../../plugins/prompt-studio-public-share/public-share-btn/PromptShareButton.jsx").PromptShareButton;
} catch {
  // The variable will remain undefined if the component is not available.
}
try {
  CloneButton =
    require("../../../plugins/prompt-studio-clone/clone-btn/CloneButton.jsx").CloneButton;
} catch {
  // The variable will remain undefined if the component is not available.
}
function Header({
  setOpenSettings,
  handleUpdateTool,
  setOpenShareModal,
  setOpenCloneModal,
}) {
  const [isExportLoading, setIsExportLoading] = useState(false);
  const { details, isPublicSource } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const [userList, setUserList] = useState([]);
  const [openExportToolModal, setOpenExportToolModal] = useState(false);
  const { setPostHogCustomEvent } = usePostHogEvents();

  const [toolDetails, setToolDetails] = useState(null);
  const [confirmModalVisible, setConfirmModalVisible] = useState(false);
  const [lastExportParams, setLastExportParams] = useState(null);

  const handleExport = (
    selectedUsers,
    toolDetail,
    isSharedWithEveryone,
    forcedExport = false
  ) => {
    const body = {
      is_shared_with_org: isSharedWithEveryone,
      user_id: isSharedWithEveryone ? [] : selectedUsers,
      force_export: forcedExport,
    };
    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/export/${details?.tool_id}`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
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
        if (err?.response?.data?.errors[0]?.code === "warning") {
          setLastExportParams({
            selectedUsers,
            toolDetail,
            isSharedWithEveryone,
          });
          setConfirmModalVisible(true); // Show the confirmation modal
          return; // Exit early to prevent any further execution
        }
        setAlertDetails(handleException(err, "Failed to export"));
      })
      .finally(() => {
        setIsExportLoading(false);
        setOpenExportToolModal(false);
      });
  };

  const handleConfirmForceExport = useCallback(() => {
    const { selectedUsers, toolDetail, isSharedWithEveryone } =
      lastExportParams;

    handleExport(selectedUsers, toolDetail, isSharedWithEveryone, true);
    setConfirmModalVisible(false);
  }, [lastExportParams]);

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
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/export/${details?.tool_id}`,
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

  const handleExportProject = () => {
    try {
      setPostHogCustomEvent("intent_tool_export_project", {
        info: "Clicked Export Project in tool IDE",
        tool_id: details?.tool_id,
        tool_name: details?.tool_name,
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }

    setIsExportLoading(true);
    // Create a download link
    const downloadUrl = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/export-project/${details?.tool_id}`;

    // Create a temporary link element and trigger download
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = `${details?.tool_name}_export.json`;

    // Add authorization header by fetching the file
    const requestOptions = {
      method: "GET",
      url: downloadUrl,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      responseType: "blob",
    };

    axiosPrivate(requestOptions)
      .then((response) => {
        // Create blob link to download
        const url = window.URL.createObjectURL(new Blob([response.data]));
        const link = document.createElement("a");
        link.href = url;

        // Get filename from response headers or use default
        const contentDisposition = response.headers["content-disposition"];
        let filename = `${details?.tool_name}_export.json`;
        if (contentDisposition) {
          const filenameMatch =
            contentDisposition.match(/filename="?([^"]+)"?/);
          if (filenameMatch) {
            filename = filenameMatch[1];
          }
        }

        link.setAttribute("download", filename);
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);

        setAlertDetails({
          type: "success",
          content: "Project exported successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to export project"));
      })
      .finally(() => {
        setIsExportLoading(false);
      });
  };

  return (
    <div className="custom-tools-header-layout">
      {isPublicSource ? (
        <div>
          <Typography.Text className="custom-tools-name" strong>
            {details?.tool_name}
          </Typography.Text>
        </div>
      ) : (
        <HeaderTitle />
      )}
      <div className="custom-tools-header-btns">
        {SinglePassToggleSwitch && (
          <SinglePassToggleSwitch handleUpdateTool={handleUpdateTool} />
        )}
        <div>
          <Tooltip title="Settings">
            <Button
              icon={<SettingOutlined />}
              onClick={() => setOpenSettings(true)}
            />
          </Tooltip>
        </div>
        {CloneButton && <CloneButton setOpenCloneModal={setOpenCloneModal} />}
        {PromptShareButton && (
          <PromptShareButton setOpenShareModal={setOpenShareModal} />
        )}
        <div className="custom-tools-header-v-divider" />
        <Dropdown
          menu={{
            items: [
              {
                key: "export-tool",
                label: "Export as Tool",
                onClick: () => handleShare(true),
              },
              {
                key: "export-json",
                label: "Export as JSON",
                onClick: handleExportProject,
              },
            ],
          }}
          trigger={["click"]}
          disabled={isPublicSource}
        >
          <CustomButton
            type="primary"
            loading={isExportLoading}
            disabled={isPublicSource}
            icon={<ExportToolIcon />}
            className="export-text"
          >
            Export
          </CustomButton>
        </Dropdown>
        <ExportTool
          allUsers={userList}
          open={openExportToolModal}
          setOpen={setOpenExportToolModal}
          onApply={handleExport}
          loading={isExportLoading}
          toolDetails={toolDetails}
        />
      </div>
      <Modal
        onOk={handleConfirmForceExport} // Pass the confirm action
        onCancel={() => setConfirmModalVisible(false)} // Close the modal on cancel
        open={confirmModalVisible}
        title="Are you sure"
        okText="Force Export"
        centered
      >
        Unable to export tool. Some prompt(s) were not run. Please run them
        before exporting.{" "}
        <strong>Would you like to force export anyway?</strong>
      </Modal>
    </div>
  );
}

Header.propTypes = {
  setOpenSettings: PropTypes.func.isRequired,
  handleUpdateTool: PropTypes.func.isRequired,
  setOpenCloneModal: PropTypes.func.isRequired,
  setOpenShareModal: PropTypes.func.isRequired,
};

export { Header };
