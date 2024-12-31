import {
  CheckCircleOutlined,
  DeleteOutlined,
  LoadingOutlined,
  MoreOutlined,
  PlayCircleFilled,
  PlayCircleOutlined,
  SyncOutlined,
  InfoCircleOutlined,
} from "@ant-design/icons";
import { useEffect, useState } from "react";
import { Button, Checkbox, Col, Dropdown, Row, Tag, Tooltip } from "antd";
import PropTypes from "prop-types";

import {
  PROMPT_RUN_TYPES,
  promptStudioUpdateStatus,
} from "../../../helpers/GetStaticData";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";
import { EditableText } from "../editable-text/EditableText";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { ExpandCardBtn } from "./ExpandCardBtn";

let PromptRunBtnSps;
try {
  PromptRunBtnSps =
    require("../../../plugins/simple-prompt-studio/PromptRunBtnSps").PromptRunBtnSps;
} catch {
  // The component will remain 'undefined' it is not available
}

function Header({
  promptDetails,
  promptKey,
  setPromptKey,
  progressMsg,
  handleRun,
  handleChange,
  handleDelete,
  updateStatus,
  updatePlaceHolder,
  isCoverageLoading,
  isEditingTitle,
  setIsEditingTitle,
  expandCard,
  setExpandCard,
  spsLoading,
  handleSpsLoading,
  enforceType,
}) {
  const {
    selectedDoc,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    indexDocs,
    isPublicSource,
    isSimplePromptStudio,
    details,
  } = useCustomToolStore();
  const [items, setItems] = useState([]);

  const [isDisablePrompt, setIsDisablePrompt] = useState(null);
  const [required, setRequired] = useState(false);

  const handleRunBtnClick = (promptRunType, docId = null) => {
    setExpandCard(true);
    handleRun(promptRunType, promptDetails?.prompt_id, null, docId);
  };

  const handleDisablePrompt = (event) => {
    const check = event?.target?.checked;
    setIsDisablePrompt(check);
    handleChange(check, promptDetails?.prompt_id, "active", true, true).catch(
      () => {
        setIsDisablePrompt(!check);
      }
    );
  };
  const handleRequiredChange = (value) => {
    const newValue = value === required ? null : value; // Allow deselection
    setRequired(newValue);
    handleChange(
      newValue,
      promptDetails?.prompt_id,
      "required",
      true,
      true
    ).catch(() => {
      setRequired(promptDetails?.required || null); // Rollback state in case of error
    });
  };
  useEffect(() => {
    setIsDisablePrompt(promptDetails?.active);
    setRequired(promptDetails?.required);
  }, [promptDetails, details]);

  useEffect(() => {
    const dropdownItems = [
      {
        label: (
          <Checkbox checked={isDisablePrompt} onChange={handleDisablePrompt}>
            {isDisablePrompt ? "Enabled" : "Disabled"}
          </Checkbox>
        ),
        key: "enable",
      },
      {
        label: (
          <div>
            {["json", "table", "record"].indexOf(enforceType) === -1 && (
              <Checkbox
                checked={required === "all"}
                onChange={() => handleRequiredChange("all")}
              >
                Value Required{" "}
                <Tooltip title="Marks this as a required field. Saving this record won't be allowed in Human Quality Review should this field be empty.">
                  <InfoCircleOutlined />
                </Tooltip>
              </Checkbox>
            )}
            {enforceType === "json" && (
              <>
                <Checkbox
                  checked={required === "all"}
                  onChange={() => handleRequiredChange("all")}
                >
                  All JSON Values Required
                </Checkbox>
                <Tooltip title="When set, saving this record won't be allowed in Human Quality Review without all key/values filled in this JSON structure.">
                  <InfoCircleOutlined />
                </Tooltip>
                <Checkbox
                  checked={required === "any"}
                  onChange={() => handleRequiredChange("any")}
                  className="required-checkbox-padding"
                >
                  Atleast 1 JSON Value Required
                </Checkbox>
                <Tooltip title="When set, saving this record won't be allowed in Human Quality Review without at least one value filled in this JSON structure.">
                  <InfoCircleOutlined />
                </Tooltip>
              </>
            )}
          </div>
        ),
        key: "required",
      },
      {
        label: (
          <ConfirmModal
            handleConfirm={() => handleDelete(promptDetails?.prompt_id)}
            content="The prompt will be permanently deleted."
          >
            <DeleteOutlined /> Delete
          </ConfirmModal>
        ),
        key: "delete",
        disabled:
          isCoverageLoading ||
          isSinglePassExtractLoading ||
          indexDocs?.includes(selectedDoc?.document_id) ||
          isPublicSource,
      },
    ];
    if (isSimplePromptStudio) {
      dropdownItems.splice(0, 1);
    }

    setItems(dropdownItems);
  }, [isDisablePrompt, required, enforceType]);

  return (
    <Row>
      <Col span={12}>
        <EditableText
          isEditing={isEditingTitle}
          setIsEditing={setIsEditingTitle}
          text={promptKey}
          setText={setPromptKey}
          promptId={promptDetails?.prompt_id}
          defaultText={promptDetails?.prompt_key}
          handleChange={handleChange}
          placeHolder={updatePlaceHolder}
          isCoverageLoading={isCoverageLoading}
        />
      </Col>
      <Col span={12} className="display-flex-right">
        <div>
          {progressMsg?.message && (
            <Tooltip title={progressMsg?.message || ""}>
              <Tag
                icon={isCoverageLoading && <LoadingOutlined spin />}
                color={progressMsg?.level === "ERROR" ? "error" : "processing"}
                className="display-flex-align-center"
              >
                <div className="tag-max-width ellipsis">
                  {progressMsg?.message}
                </div>
              </Tag>
            </Tooltip>
          )}
        </div>
        {updateStatus?.promptId === promptDetails?.prompt_id && (
          <>
            <div>
              {updateStatus?.status === promptStudioUpdateStatus.isUpdating && (
                <Tag
                  icon={<SyncOutlined spin />}
                  color="processing"
                  className="display-flex-align-center"
                >
                  Updating
                </Tag>
              )}
            </div>
            <div>
              {updateStatus?.status === promptStudioUpdateStatus.done && (
                <Tag
                  icon={<CheckCircleOutlined />}
                  color="success"
                  className="display-flex-align-center"
                >
                  Done
                </Tag>
              )}
            </div>
            <div>
              {updateStatus?.status ===
                promptStudioUpdateStatus.validationError && (
                <Tag
                  icon={<CheckCircleOutlined />}
                  color="error"
                  className="display-flex-align-center"
                >
                  Invalid JSON Key
                </Tag>
              )}
            </div>
          </>
        )}
        {!singlePassExtractMode && !isSimplePromptStudio && (
          <>
            <Tooltip title="Run all LLMs for current document">
              <Button
                size="small"
                type="text"
                className="prompt-card-action-button"
                onClick={() =>
                  handleRunBtnClick(
                    PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ALL_LLMS_ONE_DOC,
                    selectedDoc?.document_id
                  )
                }
                disabled={
                  (updateStatus?.promptId === promptDetails?.prompt_id &&
                    updateStatus?.status ===
                      promptStudioUpdateStatus?.isUpdating) ||
                  isCoverageLoading ||
                  indexDocs?.includes(selectedDoc?.document_id) ||
                  isPublicSource ||
                  spsLoading[selectedDoc?.document_id]
                }
              >
                <PlayCircleOutlined className="prompt-card-actions-head" />
              </Button>
            </Tooltip>
            <Tooltip title="Run all LLMs for all documents">
              <Button
                size="small"
                type="text"
                className="prompt-card-action-button"
                onClick={() =>
                  handleRunBtnClick(
                    PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ALL_LLMS_ALL_DOCS
                  )
                }
                disabled={
                  (updateStatus?.promptId === promptDetails?.prompt_id &&
                    updateStatus?.status ===
                      promptStudioUpdateStatus?.isUpdating) ||
                  isCoverageLoading ||
                  indexDocs?.includes(selectedDoc?.document_id) ||
                  isPublicSource
                }
              >
                <PlayCircleFilled className="prompt-card-actions-head" />
              </Button>
            </Tooltip>
          </>
        )}
        <ExpandCardBtn expandCard={expandCard} setExpandCard={setExpandCard} />
        {isSimplePromptStudio && PromptRunBtnSps && (
          <PromptRunBtnSps
            spsLoading={spsLoading}
            handleSpsLoading={handleSpsLoading}
            handleGetOutput={() => {}}
            promptDetails={promptDetails}
          />
        )}
        <Dropdown menu={{ items }} trigger={["click"]} placement="bottomLeft">
          <Button
            size="small"
            type="text"
            className="prompt-card-action-button"
          >
            <MoreOutlined className="prompt-card-actions-head" />
          </Button>
        </Dropdown>
      </Col>
    </Row>
  );
}

Header.propTypes = {
  promptDetails: PropTypes.object.isRequired,
  promptKey: PropTypes.text,
  setPromptKey: PropTypes.func.isRequired,
  progressMsg: PropTypes.object.isRequired,
  handleRun: PropTypes.func.isRequired,
  handleChange: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  updateStatus: PropTypes.object.isRequired,
  updatePlaceHolder: PropTypes.string,
  isCoverageLoading: PropTypes.bool.isRequired,
  isEditingTitle: PropTypes.bool.isRequired,
  setIsEditingTitle: PropTypes.func.isRequired,
  expandCard: PropTypes.bool.isRequired,
  setExpandCard: PropTypes.func.isRequired,
  spsLoading: PropTypes.object,
  handleSpsLoading: PropTypes.func.isRequired,
  enforceType: PropTypes.text,
};

export { Header };
