import {
  CheckCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import { Button, Card, Col, Collapse, Row, Space, Tag, Tooltip } from "antd";
import PropTypes from "prop-types";
import "./NotesCard.css";
import { useEffect, useState } from "react";

import { EditableText } from "../editable-text/EditableText";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";
import { promptStudioUpdateStatus } from "../../../helpers/GetStaticData";
import { ExpandCardBtn } from "../prompt-card/ExpandCardBtn";
import { handleUpdateStatus } from "../prompt-card/constants";

function NotesCard({
  promptDetails,
  handleChangePromptCard,
  handleDelete,
  updatePlaceHolder,
  setUpdatedPromptsCopy,
}) {
  const [promptDetailsState, setPromptDetailsState] = useState({});
  const [isPromptDetailsStateUpdated, setIsPromptDetailsStateUpdated] =
    useState(false);
  const [updateStatus, setUpdateStatus] = useState({
    promptId: null,
    status: null,
  });
  const [promptKey, setPromptKey] = useState("");
  const [promptText, setPromptText] = useState("");
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [isEditingNote, setIsEditingNote] = useState(false);
  const [expandCard, setExpandCard] = useState(true);

  useEffect(() => {
    if (
      isPromptDetailsStateUpdated ||
      !Object.keys(promptDetails || {})?.length
    )
      return;
    setPromptDetailsState(promptDetails);
    setIsPromptDetailsStateUpdated(true);
  }, [promptDetails]);

  const enableEdit = (event) => {
    event.stopPropagation();
    setIsEditingTitle(true);
    setIsEditingNote(true);
  };

  const handleChange = async (
    value,
    promptId,
    name,
    isUpdateStatus = false
  ) => {
    const prevPromptDetailsState = { ...promptDetailsState };

    const updatedPromptDetailsState = { ...promptDetailsState };
    updatedPromptDetailsState[name] = value;

    handleUpdateStatus(
      isUpdateStatus,
      promptId,
      promptStudioUpdateStatus.isUpdating,
      setUpdateStatus
    );
    setPromptDetailsState(updatedPromptDetailsState);

    return handleChangePromptCard(name, value, promptId)
      .then((res) => {
        const data = res?.data;
        setUpdatedPromptsCopy((prev) => {
          prev[promptId] = data;
          return prev;
        });
        handleUpdateStatus(
          isUpdateStatus,
          promptId,
          promptStudioUpdateStatus.done,
          setUpdateStatus
        );
      })
      .catch(() => {
        handleUpdateStatus(isUpdateStatus, promptId, null, setUpdateStatus);
        setPromptDetailsState(prevPromptDetailsState);
      })
      .finally(() => {
        if (isUpdateStatus) {
          setTimeout(() => {
            handleUpdateStatus(true, promptId, null, setUpdateStatus);
          }, 3000);
        }
      });
  };

  return (
    <Card className="tool-ide-notes-card">
      <Space
        direction="vertical"
        className="width-100"
        size={expandCard ? 10 : 0}
      >
        <Row>
          <Col span={18}>
            <EditableText
              isEditing={isEditingTitle}
              setIsEditing={setIsEditingTitle}
              text={promptKey}
              setText={setPromptKey}
              promptId={promptDetailsState?.prompt_id}
              defaultText={promptDetailsState?.prompt_key}
              handleChange={handleChange}
              placeHolder={updatePlaceHolder}
            />
          </Col>
          <Col span={6} className="display-flex-right">
            {updateStatus?.promptId === promptDetailsState?.prompt_id && (
              <>
                {updateStatus?.status ===
                  promptStudioUpdateStatus.isUpdating && (
                  <Tag
                    icon={<SyncOutlined spin />}
                    color="processing"
                    className="display-flex-align-center"
                  >
                    Updating
                  </Tag>
                )}
                {updateStatus?.status === promptStudioUpdateStatus.done && (
                  <Tag
                    icon={<CheckCircleOutlined />}
                    color="success"
                    className="display-flex-align-center"
                  >
                    Done
                  </Tag>
                )}
              </>
            )}
            <ExpandCardBtn
              expandCard={expandCard}
              setExpandCard={setExpandCard}
            />
            <Tooltip title="Edit">
              <Button
                size="small"
                type="text"
                className="display-flex-align-center"
                onClick={enableEdit}
              >
                <EditOutlined className="prompt-card-actions-head" />
              </Button>
            </Tooltip>
            <ConfirmModal
              handleConfirm={() => handleDelete(promptDetailsState?.prompt_id)}
              content="The note will be permanently deleted."
            >
              <Tooltip title="Delete">
                <Button size="small" type="text">
                  <DeleteOutlined className="delete-icon" />
                </Button>
              </Tooltip>
            </ConfirmModal>
          </Col>
        </Row>
        <Collapse
          className="prompt-card-collapse"
          ghost
          activeKey={expandCard && "1"}
        >
          <Collapse.Panel key={"1"}>
            <EditableText
              isEditing={isEditingNote}
              setIsEditing={setIsEditingNote}
              text={promptText}
              setText={setPromptText}
              promptId={promptDetailsState?.prompt_id}
              defaultText={promptDetailsState?.prompt}
              handleChange={handleChange}
              isTextarea={true}
              placeHolder={updatePlaceHolder}
            />
          </Collapse.Panel>
        </Collapse>
      </Space>
    </Card>
  );
}

NotesCard.propTypes = {
  promptDetails: PropTypes.object.isRequired,
  handleChangePromptCard: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  updatePlaceHolder: PropTypes.string,
  setUpdatedPromptsCopy: PropTypes.func.isRequired,
};

export { NotesCard };
