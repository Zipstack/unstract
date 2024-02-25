import { DeleteOutlined, EditOutlined } from "@ant-design/icons";
import { Button, Card, Col, Row, Space, Tooltip } from "antd";
import PropTypes from "prop-types";

import "./NotesCard.css";
import { EditableText } from "../editable-text/EditableText";
import { useState } from "react";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";

function NotesCard({ details, handleChange, handleDelete }) {
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [isEditingNote, setIsEditingNote] = useState(false);

  const enableEdit = (event) => {
    event.stopPropagation();
    setIsEditingTitle(true);
    setIsEditingNote(true);
  };

  return (
    <Card className="tool-ide-notes-card">
      <Space direction="vertical" className="width-100">
        <Row>
          <Col span={18}>
            <EditableText
              isEditing={isEditingTitle}
              setIsEditing={setIsEditingTitle}
              promptId={details?.prompt_id}
              defaultText={details?.prompt_key}
              handleChange={handleChange}
            />
          </Col>
          <Col span={6} className="display-flex-right">
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
              handleConfirm={() => handleDelete(details?.prompt_id)}
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
        <EditableText
          isEditing={isEditingNote}
          setIsEditing={setIsEditingNote}
          promptId={details?.prompt_id}
          defaultText={details?.prompt}
          handleChange={handleChange}
          isTextarea={true}
        />
      </Space>
    </Card>
  );
}

NotesCard.propTypes = {
  details: PropTypes.object.isRequired,
  handleChange: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
};

export { NotesCard };
