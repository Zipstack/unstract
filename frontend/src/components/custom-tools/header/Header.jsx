import {
  ArrowLeftOutlined,
  EditOutlined,
  SettingOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { Button, Tooltip, Typography } from "antd";
import PropTypes from "prop-types";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./Header.css";

import { ExportToolIcon } from "../../../assets";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { SharePermission } from "../../widgets/share-permission/SharePermission";

let SinglePassToggleSwitch;
try {
  SinglePassToggleSwitch =
    require("../../../plugins/single-pass-toggle-switch/SinglePassToggleSwitch").SinglePassToggleSwitch;
} catch {
  // The variable will remain undefined if the component is not available.
}
function Header({ setOpenSettings, handleUpdateTool, setOpenManageExport }) {
  const [isExportLoading, setIsExportLoading] = useState(false);
  const { details } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const navigate = useNavigate();
  const handleException = useExceptionHandler();
  const [userList, setUserList] = useState([]);
  const [openSharePermissionModal, setOpenSharePermissionModal] =
    useState(false);

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
        setOpenSharePermissionModal(false);
      });
  };

  const handleShare = (isEdit) => {
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
            setOpenSharePermissionModal(true);
            setToolDetails({ ...res?.data, created_by: details?.created_by });
          })
          .catch((err) => {
            if (err?.response?.status === 404) {
              setToolDetails(details);
              setOpenSharePermissionModal(true);
              setAlertDetails(handleException(err, "Tool not exported yet"));
            } else {
              setAlertDetails(handleException(err));
            }
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
          <Tooltip title="Manage Exported Tools">
            <Button
              icon={<UnorderedListOutlined />}
              onClick={() => setOpenManageExport(true)}
            />
          </Tooltip>
        </div>
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
          <Tooltip title="Export as tool">
            <CustomButton
              type="primary"
              onClick={() => handleShare(true)}
              loading={isExportLoading}
            >
              <ExportToolIcon />
            </CustomButton>
          </Tooltip>
        </div>
        <SharePermission
          allUsers={userList}
          open={openSharePermissionModal}
          setOpen={setOpenSharePermissionModal}
          onApply={handleExport}
          loading={isExportLoading}
          adapter={toolDetails}
          permissionEdit={true}
          isSharableToOrg={true}
        />
      </div>
    </div>
  );
}

Header.propTypes = {
  setOpenSettings: PropTypes.func.isRequired,
  handleUpdateTool: PropTypes.func.isRequired,
  setOpenManageExport: PropTypes.func.isRequired,
};

export { Header };
