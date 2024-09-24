import { SettingOutlined } from "@ant-design/icons";
import { Button, Tooltip, Typography } from "antd";
import PropTypes from "prop-types";
import { useState } from "react";

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

  const handleExport = (selectedUsers, toolDetail, isSharedWithEveryone) => {
    const body = {
      is_shared_with_org: isSharedWithEveryone,
      user_id: isSharedWithEveryone ? [] : selectedUsers,
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
        setAlertDetails(handleException(err, "Failed to export"));
      })
      .finally(() => {
        setIsExportLoading(false);
        setOpenExportToolModal(false);
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
        <div>
          <Tooltip title="Export as tool">
            <CustomButton
              type="primary"
              onClick={() => handleShare(true)}
              loading={isExportLoading}
              disabled={isPublicSource}
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
  setOpenCloneModal: PropTypes.func.isRequired,
  setOpenShareModal: PropTypes.func.isRequired,
};

export { Header };
