import {
  ArrowLeftOutlined,
  EditOutlined,
  SettingOutlined,
  TagOutlined,
} from "@ant-design/icons";
import { Button, Dropdown, Space, Tooltip, Typography } from "antd";
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
import { ExportTool } from "../export-tool/ExportTool";
import usePostHogEvents from "../../../hooks/usePostHogEvents";

let SinglePassToggleSwitch;
try {
  SinglePassToggleSwitch =
    require("../../../plugins/single-pass-toggle-switch/SinglePassToggleSwitch").SinglePassToggleSwitch;
} catch {
  // The variable will remain undefined if the component is not available.
}
function Header({ setOpenSettings, handleUpdateTool }) {
  const [isExportLoading, setIsExportLoading] = useState(false);
  const { details, updateCustomTool } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const navigate = useNavigate();
  const handleException = useExceptionHandler();
  const [userList, setUserList] = useState([]);
  const [openExportToolModal, setOpenExportToolModal] = useState(false);
  const [isNewExport, setIsNewExport] = useState(true);
  const { setPostHogCustomEvent } = usePostHogEvents();

  const [toolDetails, setToolDetails] = useState(null);
  const handleExportNew = (newExport = false) => {
    setIsNewExport(newExport);
    handleShare(true);
  };
  const items = [
    {
      label: "Export as New Tool",
      key: "0",
      onClick: () => handleExportNew(true),
    },
    {
      label: "Manage Exported Tool",
      key: "1",
      onClick: handleExportNew,
    },
  ];
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
      console.log(users);
      console.log(details);
      // if (users.length < 2) {
      //   handleExport([details?.created_by], details, false);
      // } else {
      axiosPrivate(requestOptions)
        .then((res) => {
          console.log(res.data);
          // setIsNewExport();
          setOpenExportToolModal(true);
          setToolDetails({ ...res?.data, created_by: details?.created_by });
        })
        .catch((err) => {
          setAlertDetails(handleException(err));
        })
        .finally(() => {
          setIsExportLoading(false);
        });
      // }
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
      <Space
        style={{
          padding: "8px",
          marginLeft: "7px",
          border: "1px solid #D9D9D9",
          fontSize: "14px",
        }}
      >
        <TagOutlined rotate={270} />
        <Typography.Text
          strong
          ellipsis={{
            tooltip:
              "Initial Versio dawd awdawd awdawdaw dawd aw ndwadawdawdawdawdawdawdawdw",
          }} // Optional tooltip to show full text
          style={{
            maxWidth: 200, // Adjust the minimum width as needed
          }}
        >
          Initial Versio dawd awdawd awdawdaw dawd aw
          ndwadawdawdawdawdawdawdawdw
        </Typography.Text>
        <Typography.Link underline>Manage Tags</Typography.Link>
      </Space>
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
        <div
          onClick={(e) => {
            console.log("HEHEH");
            e.preventDefault();
            e.stopPropagation(); // Stop the event from propagating to the Dropdown
          }}
        >
          {/* <Tooltip title="Export as tool">
            <Dropdown menu={{ menu }} trigger={["click"]}>
              <span>
                <CustomButton type="primary">
                  <ExportToolIcon />
                </CustomButton>
              </span>
            </Dropdown>
          </Tooltip> */}
          <Dropdown
            menu={{
              items,
            }}
            trigger={["click"]}
          >
            <Button type="primary" loading={isExportLoading}>
              <div
                onClick={(event) => {
                  // event.preventDefault();
                  console.log(details);
                  event.stopPropagation(); // stop propagation main button
                }}
              >
                <ExportToolIcon />
              </div>
            </Button>
          </Dropdown>
        </div>
        <ExportTool
          allUsers={userList}
          open={openExportToolModal}
          setOpen={setOpenExportToolModal}
          onApply={handleExport}
          loading={isExportLoading}
          toolDetails={toolDetails}
          isNewExport={isNewExport}
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
