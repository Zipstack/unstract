import { DeleteOutlined, EditOutlined } from "@ant-design/icons";
import { Button, Radio, Space, Table, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { handleException } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import "./ManageLlmProfiles.css";

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
function ManageLlmProfiles({
  setOpen,
  setOpenLlm,
  setEditLlmProfileId,
  setModalTitle,
}) {
  const [rows, setRows] = useState([]);
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { details, defaultLlmProfile, updateCustomTool, llmProfiles } =
    useCustomToolStore();
  const { setAlertDetails } = useAlertStore();

  const handleDefaultLlm = (profileId) => {
    const body = {
      default_profile: profileId,
    };

    const requestOptions = {
      method: "PATCH",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/profiles/${details?.tool_id}/`,
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
    const modifiedRows = llmProfiles.map((item, index) => {
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
            <Button size="small" className="display-flex-align-center">
              <DeleteOutlined classID="manage-llm-pro-icon" />
            </Button>
          </ConfirmModal>
        ),
        edit: (
          <Button
            size="small"
            className="display-flex-align-center"
            onClick={() => handleEdit(item?.profile_id)}
          >
            <EditOutlined classID="manage-llm-pro-icon" />
          </Button>
        ),
        select: (
          <Radio
            checked={defaultLlmProfile === item?.profile_id}
            onClick={() => handleDefaultLlm(item?.profile_id)}
          />
        ),
      };
    });
    setRows(modifiedRows);
  }, [llmProfiles, defaultLlmProfile]);

  const handleAddNewLlm = () => {
    setOpen(false);
    setOpenLlm(true);
  };

  const handleEdit = (id) => {
    setEditLlmProfileId(id);
    setModalTitle("Manage LLM profile");
    handleAddNewLlm();
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

  return (
    <div>
      <div className="pre-post-amble-body">
        <SpaceWrapper>
          <div>
            <Typography.Text className="add-cus-tool-header">
              LLM Profiles Manager
            </Typography.Text>
          </div>
          <div className="add-cus-tool-gap" />
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
      </div>
      <div className="pre-post-amble-footer display-flex-right">
        <Space>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <CustomButton type="primary" onClick={handleAddNewLlm}>
            Add New LLM Profile
          </CustomButton>
        </Space>
      </div>
    </div>
  );
}

ManageLlmProfiles.propTypes = {
  setOpen: PropTypes.func.isRequired,
  setOpenLlm: PropTypes.func.isRequired,
  setEditLlmProfileId: PropTypes.func.isRequired,
  setModalTitle: PropTypes.func.isRequired,
};

export { ManageLlmProfiles };
