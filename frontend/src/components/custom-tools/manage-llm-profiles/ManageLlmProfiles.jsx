import { DeleteOutlined, EditOutlined } from "@ant-design/icons";
import { Button, Radio, Table, Tooltip, Typography } from "antd";
import { useEffect, useState } from "react";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { AddLlmProfile } from "../add-llm-profile/AddLlmProfile";
import "./ManageLlmProfiles.css";
import usePostHogEvents from "../../../hooks/usePostHogEvents";

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
    title: "",
    dataIndex: "delete",
    key: "delete",
    width: 30,
  },
  {
    title: "",
    dataIndex: "edit",
    key: "edit",
    width: 30,
  },
  {
    title: "Select Default",
    dataIndex: "select",
    key: "select",
    align: "center",
  },
];
function ManageLlmProfiles() {
  const [rows, setRows] = useState([]);
  const [isAddLlm, setIsAddLlm] = useState(false);
  const [editLlmProfileId, setEditLlmProfileId] = useState(null);
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const {
    details,
    defaultLlmProfile,
    updateCustomTool,
    llmProfiles,
    isPublicSource,
  } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const { setPostHogCustomEvent } = usePostHogEvents();
  const MAX_PROFILE_COUNT = 4;
  const isMaxProfile = llmProfiles.length >= MAX_PROFILE_COUNT;

  const handleDefaultLlm = (profileId) => {
    try {
      setPostHogCustomEvent("ps_profile_changed_per_prompt", {
        info: "Selected default LLM profile",
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }

    const body = {
      default_profile: profileId,
    };

    const requestOptions = {
      method: "PATCH",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-studio-profile/${details?.tool_id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        const updatedState = {
          defaultLlmProfile: data?.default_profile,
        };
        updateCustomTool(updatedState);
        setAlertDetails({
          type: "success",
          content: "Default LLM Profile updated successfully",
        });
      })
      .catch((err) => {
        handleException(err, "Failed to set default LLM Profile");
      });
  };

  useEffect(() => {
    const modifiedRows = llmProfiles.map((item) => {
      return {
        key: item?.profile_id,
        name: item?.profile_name || "",
        llm: item?.llm || "",
        embedding_model: item?.embedding_model || "",
        vector_db: item?.vector_store || "",
        text_extractor: item?.x2text || "",
        delete: (
          <ConfirmModal
            handleConfirm={() => handleDelete(item?.profile_id)}
            content="The LLM profile will be permanently deleted."
          >
            <Button
              size="small"
              className="display-flex-align-center"
              disabled={isPublicSource}
            >
              <DeleteOutlined classID="manage-llm-pro-icon" />
            </Button>
          </ConfirmModal>
        ),
        edit: (
          <Button
            size="small"
            className="display-flex-align-center"
            disabled={isPublicSource}
            onClick={() => handleEdit(item?.profile_id)}
          >
            <EditOutlined classID="manage-llm-pro-icon" />
          </Button>
        ),
        select: (
          <Radio
            checked={defaultLlmProfile === item?.profile_id}
            onClick={() => handleDefaultLlm(item?.profile_id)}
            disabled={isPublicSource}
          />
        ),
      };
    });
    setRows(modifiedRows);
  }, [llmProfiles, defaultLlmProfile]);

  const handleAddNewLlmProfileBtnClick = () => {
    setIsAddLlm(true);

    try {
      setPostHogCustomEvent("intent_ps_new_llm_profile", {
        info: "Clicked on 'Add New LLM Profile' button",
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
  };

  const handleEdit = (id) => {
    setEditLlmProfileId(id);
    setIsAddLlm(true);
  };

  const handleDelete = (id) => {
    const requestOptions = {
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/profile-manager/${id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    axiosPrivate(requestOptions)
      .then(() => {
        const modifiedLlmProfiles = [...llmProfiles].filter(
          (item) => item?.profile_id !== id
        );
        const body = {
          llmProfiles: modifiedLlmProfiles,
        };

        // Reset the default LLM profile if it got deleted.
        if (id === defaultLlmProfile) {
          body["defaultLlmProfile"] = "";
        }

        updateCustomTool(body);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to delete"));
      });
  };

  if (isAddLlm) {
    return (
      <AddLlmProfile
        editLlmProfileId={editLlmProfileId}
        setEditLlmProfileId={setEditLlmProfileId}
        setIsAddLlm={setIsAddLlm}
        handleDefaultLlm={handleDefaultLlm}
      />
    );
  }

  return (
    <div className="settings-body-pad-top">
      <SpaceWrapper>
        <div>
          <Typography.Text className="add-cus-tool-header">
            LLM Profiles Manager
          </Typography.Text>
        </div>
        <div>
          <Table
            columns={columns}
            dataSource={rows}
            size="small"
            bordered
            max-width="100%"
            pagination={{ pageSize: 10 }}
          />
        </div>
      </SpaceWrapper>
      <div className="display-flex-right">
        <Tooltip
          title={
            isMaxProfile
              ? `Max profile count(${MAX_PROFILE_COUNT})`
              : "Add New LLM Profile"
          }
        >
          <CustomButton
            type="primary"
            onClick={handleAddNewLlmProfileBtnClick}
            disabled={isMaxProfile || isPublicSource}
          >
            Add New LLM Profile
          </CustomButton>
        </Tooltip>
      </div>
    </div>
  );
}

export { ManageLlmProfiles };
