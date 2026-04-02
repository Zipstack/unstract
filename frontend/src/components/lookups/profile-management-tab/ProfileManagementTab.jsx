import { DeleteOutlined, EditOutlined, CopyOutlined } from "@ant-design/icons";
import { Button, Radio, Table, Tooltip, Typography } from "antd";
import { useEffect, useState } from "react";
import PropTypes from "prop-types";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { ProfileFormModal } from "./ProfileFormModal";
import "./ProfileManagementTab.css";

const columns = [
  {
    title: "Name",
    dataIndex: "name",
    key: "name",
  },
  {
    title: "LLM",
    dataIndex: "llm",
    key: "llm",
  },
  {
    title: "Embedding Model",
    dataIndex: "embedding_model",
    key: "embedding_model",
  },
  {
    title: "Vector Database",
    dataIndex: "vector_db",
    key: "vector_db",
  },
  {
    title: "Text Extractor",
    dataIndex: "text_extractor",
    key: "text_extractor",
  },
  {
    title: "Actions",
    dataIndex: "actions",
    key: "actions",
    width: 120,
  },
  {
    title: "Select Default",
    dataIndex: "select",
    key: "select",
    align: "center",
  },
];

function ProfileManagementTab({ projectId }) {
  const [rows, setRows] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [defaultProfile, setDefaultProfile] = useState(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editProfileId, setEditProfileId] = useState(null);
  const [loading, setLoading] = useState(false);

  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const MAX_PROFILE_COUNT = 10;
  const isMaxProfile = profiles.length >= MAX_PROFILE_COUNT;

  // Fetch profiles for the lookup project
  const fetchProfiles = () => {
    setLoading(true);
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-profiles/?lookup_project=${projectId}`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const profilesData = res?.data?.results || [];
        setProfiles(profilesData);

        // Find default profile
        const defaultProf = profilesData.find((p) => p.is_default);
        if (defaultProf) {
          setDefaultProfile(defaultProf.profile_id);
        }
      })
      .catch((err) => {
        handleException(err, "Failed to fetch profiles");
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    if (projectId) {
      fetchProfiles();
    }
  }, [projectId]);

  const handleSetDefault = (profileId) => {
    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-profiles/${profileId}/set-default/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
    };

    axiosPrivate(requestOptions)
      .then(() => {
        setDefaultProfile(profileId);
        setAlertDetails({
          type: "success",
          content: "Default profile updated successfully",
        });
        fetchProfiles(); // Refresh to get updated state
      })
      .catch((err) => {
        handleException(err, "Failed to set default profile");
      });
  };

  const handleEdit = (profileId) => {
    setEditProfileId(profileId);
    setIsModalOpen(true);
  };

  const copyProfileId = (profileId) => {
    navigator.clipboard.writeText(profileId);
    setAlertDetails({
      type: "success",
      content: "Profile ID copied to clipboard",
    });
  };

  const handleDelete = (profileId) => {
    const requestOptions = {
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-profiles/${profileId}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    axiosPrivate(requestOptions)
      .then(() => {
        setAlertDetails({
          type: "success",
          content: "Profile deleted successfully",
        });
        fetchProfiles(); // Refresh list
      })
      .catch((err) => {
        handleException(err, "Failed to delete profile");
      });
  };

  const handleModalClose = (shouldRefresh) => {
    setIsModalOpen(false);
    setEditProfileId(null);
    if (shouldRefresh) {
      fetchProfiles();
    }
  };

  useEffect(() => {
    const modifiedRows = profiles.map((item) => {
      return {
        key: item?.profile_id,
        name: item?.profile_name || "",
        llm: item?.llm || "N/A",
        embedding_model: item?.embedding_model || "N/A",
        vector_db: item?.vector_store || "N/A",
        text_extractor: item?.x2text || "N/A",
        actions: (
          <div className="action-buttons-container">
            <Tooltip title="Copy Profile ID">
              <Button
                size="small"
                className="display-flex-align-center"
                onClick={() => copyProfileId(item?.profile_id)}
              >
                <CopyOutlined className="profile-icon" />
              </Button>
            </Tooltip>
            <Button
              size="small"
              className="display-flex-align-center"
              onClick={() => handleEdit(item?.profile_id)}
            >
              <EditOutlined className="profile-icon" />
            </Button>
            <ConfirmModal
              handleConfirm={() => handleDelete(item?.profile_id)}
              content="The profile will be permanently deleted."
            >
              <Tooltip
                title={
                  defaultProfile === item?.profile_id &&
                  "Default profile cannot be deleted"
                }
              >
                <Button
                  size="small"
                  className="display-flex-align-center"
                  disabled={defaultProfile === item?.profile_id}
                >
                  <DeleteOutlined className="profile-icon" />
                </Button>
              </Tooltip>
            </ConfirmModal>
          </div>
        ),
        select: (
          <Radio
            checked={defaultProfile === item?.profile_id}
            onClick={() => handleSetDefault(item?.profile_id)}
          />
        ),
      };
    });
    setRows(modifiedRows);
  }, [profiles, defaultProfile]);

  return (
    <div className="profile-management-container">
      <SpaceWrapper>
        <div className="profile-tab-header">
          <div>
            <Typography.Text className="profile-header">
              Profile Settings
            </Typography.Text>
            <Typography.Paragraph
              type="secondary"
              className="profile-description"
            >
              Manage adapter configurations for text extraction, embeddings,
              vector storage, and LLM processing.
            </Typography.Paragraph>
          </div>
          <Tooltip
            title={
              isMaxProfile
                ? `Max profile count (${MAX_PROFILE_COUNT})`
                : "Add New Profile"
            }
          >
            <CustomButton
              type="primary"
              onClick={() => setIsModalOpen(true)}
              disabled={isMaxProfile}
            >
              Add New Profile
            </CustomButton>
          </Tooltip>
        </div>
        <div>
          <Table
            columns={columns}
            dataSource={rows}
            size="small"
            bordered
            loading={loading}
            pagination={{ pageSize: 10 }}
          />
        </div>
      </SpaceWrapper>

      {isModalOpen && (
        <ProfileFormModal
          projectId={projectId}
          profileId={editProfileId}
          onClose={handleModalClose}
        />
      )}
    </div>
  );
}

ProfileManagementTab.propTypes = {
  projectId: PropTypes.string.isRequired,
};

export { ProfileManagementTab };
