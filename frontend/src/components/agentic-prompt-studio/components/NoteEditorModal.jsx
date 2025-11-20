import PropTypes from "prop-types";
import { useState, useEffect } from "react";
import { Modal, Button, message } from "antd";

import MonacoEditor from "./MonacoEditor";
import { useMockApi } from "../hooks/useMockApi";

const NoteEditorModal = ({
  visible,
  onClose,
  projectId,
  documentId,
  fieldPath,
  initialNoteText,
  onSuccess,
}) => {
  const [noteText, setNoteText] = useState(initialNoteText || "");
  const [saving, setSaving] = useState(false);
  const { createNote, updateNote } = useMockApi();

  // Update local state when initialNoteText changes
  useEffect(() => {
    setNoteText(initialNoteText || "");
  }, [initialNoteText, visible]);

  const handleSave = async () => {
    if (!noteText.trim()) {
      message.error("Note text cannot be empty");
      return;
    }

    setSaving(true);
    try {
      // TODO: Replace with actual API call
      // Determine if creating new note or updating existing
      if (initialNoteText) {
        await updateNote("note_id", {
          field_path: fieldPath,
          note_text: noteText,
        });
      } else {
        await createNote(projectId, documentId, {
          field_path: fieldPath,
          note_text: noteText,
        });
      }

      message.success("Note saved successfully");
      if (onSuccess) {
        onSuccess();
      }
      handleCancel();
    } catch (error) {
      message.error("Failed to save note");
      console.error("Save note error:", error);
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setNoteText(initialNoteText || "");
    onClose();
  };

  return (
    <Modal
      title={
        <div>
          <div style={{ fontSize: "18px", fontWeight: 600 }}>
            Extraction Note
          </div>
          <div style={{ fontSize: "13px", color: "#666", marginTop: "4px" }}>
            Field:{" "}
            <code
              style={{
                background: "#f5f5f5",
                padding: "2px 6px",
                borderRadius: "3px",
              }}
            >
              {fieldPath}
            </code>
          </div>
        </div>
      }
      open={visible}
      onCancel={handleCancel}
      footer={[
        <Button key="cancel" onClick={handleCancel} disabled={saving}>
          Cancel
        </Button>,
        <Button key="save" type="primary" onClick={handleSave} loading={saving}>
          Save Note
        </Button>,
      ]}
      width={900}
      style={{ top: 40 }}
      destroyOnClose
      maskClosable={!saving}
    >
      <div style={{ height: "500px", marginTop: "16px" }}>
        <MonacoEditor
          value={noteText}
          onChange={(value) => setNoteText(value || "")}
          language="markdown"
          readOnly={saving}
          height="500px"
        />
      </div>
    </Modal>
  );
};

NoteEditorModal.propTypes = {
  visible: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  projectId: PropTypes.string.isRequired,
  documentId: PropTypes.string.isRequired,
  fieldPath: PropTypes.string.isRequired,
  initialNoteText: PropTypes.string,
  onSuccess: PropTypes.func,
};

export default NoteEditorModal;
