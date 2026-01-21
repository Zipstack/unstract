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
import {
  Button,
  Checkbox,
  Col,
  Dropdown,
  Input,
  Row,
  Select,
  Tag,
  Tooltip,
} from "antd";
import debounce from "lodash/debounce";
import PropTypes from "prop-types";
import { useEffect, useState, useRef, useCallback } from "react";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../../store/session-store";
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
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const [items, setItems] = useState([]);

  const [isDisablePrompt, setIsDisablePrompt] = useState(null);
  const [required, setRequired] = useState(false);
  const [webhookEnabled, setWebhookEnabled] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState("");

  // Lookup state
  const [lookupEnabled, setLookupEnabled] = useState(false);
  const [selectedLookup, setSelectedLookup] = useState(null);
  const [availableLookups, setAvailableLookups] = useState([]);
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupsFetched, setLookupsFetched] = useState(false);

  // Stable debounced functions using useRef
  const debouncedWebhookEnabledChangeRef = useRef(
    debounce((value, promptId, handleChangeFn, setStateFn) => {
      handleChangeFn(
        value,
        promptId,
        "enable_postprocessing_webhook",
        true,
        true
      ).catch(() => {
        setStateFn(!value);
      });
    }, 300)
  );

  const debouncedWebhookUrlChangeRef = useRef(
    debounce((value, promptId, handleChangeFn, setStateFn) => {
      handleChangeFn(
        value,
        promptId,
        "postprocessing_webhook_url",
        true,
        true
      ).catch(() => {
        setStateFn(promptDetails?.postprocessing_webhook_url || "");
      });
    }, 500)
  );

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

  const handleWebhookEnabledChange = (e) => {
    const newValue = e.target.checked;
    setWebhookEnabled(newValue);
    debouncedWebhookEnabledChangeRef.current(
      newValue,
      promptDetails?.prompt_id,
      handleChange,
      setWebhookEnabled
    );
  };

  const handleWebhookUrlChange = (value) => {
    setWebhookUrl(value);
    debouncedWebhookUrlChangeRef.current(
      value,
      promptDetails?.prompt_id,
      handleChange,
      setWebhookUrl
    );
  };

  // Fetch available lookup projects for this PS project (lazy load on dropdown open)
  const fetchAvailableLookups = useCallback(async () => {
    if (!details?.tool_id || !sessionDetails?.orgId) return;
    if (lookupsFetched) return; // Already fetched, skip

    setLookupLoading(true);
    try {
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails.orgId}/prompt-studio/prompt/available_lookups/`,
        { params: { tool_id: details.tool_id } }
      );
      setAvailableLookups(response?.data || []);
      setLookupsFetched(true);
    } catch (error) {
      console.error("Failed to fetch available lookups:", error);
      setAvailableLookups([]);
    } finally {
      setLookupLoading(false);
    }
  }, [details?.tool_id, sessionDetails?.orgId, axiosPrivate, lookupsFetched]);

  // Handle lookup enabled checkbox change
  const handleLookupEnabledChange = (e) => {
    const newValue = e.target.checked;
    setLookupEnabled(newValue);
    if (!newValue) {
      // When disabling, clear the selected lookup
      setSelectedLookup(null);
      handleChange(
        null,
        promptDetails?.prompt_id,
        "lookup_project",
        true,
        true
      ).catch(() => {
        // Rollback on error
        setLookupEnabled(true);
        setSelectedLookup(promptDetails?.lookup_project || null);
      });
    }
  };

  // Handle lookup project selection change
  const handleLookupChange = (value) => {
    const newValue = value || null;
    setSelectedLookup(newValue);
    if (!newValue) {
      // If clearing the selection, also disable lookup
      setLookupEnabled(false);
    }
    handleChange(
      newValue,
      promptDetails?.prompt_id,
      "lookup_project",
      true,
      true
    ).catch(() => {
      // Rollback on error
      setLookupEnabled(!!promptDetails?.lookup_project);
      setSelectedLookup(promptDetails?.lookup_project || null);
    });
  };

  useEffect(() => {
    setIsDisablePrompt(promptDetails?.active);
    setRequired(promptDetails?.required);
    setWebhookEnabled(promptDetails?.enable_postprocessing_webhook || false);
    setWebhookUrl(promptDetails?.postprocessing_webhook_url || "");
    setLookupEnabled(!!promptDetails?.lookup_project);
    setSelectedLookup(promptDetails?.lookup_project || null);
  }, [promptDetails, details]);

  // Reset lookupsFetched when tool changes so we refetch on next dropdown open
  useEffect(() => {
    setLookupsFetched(false);
  }, [details?.tool_id]);

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
                  At least 1 JSON Value Required
                </Checkbox>
                <Tooltip title="When set, saving this record won't be allowed in Human Quality Review without at least one value filled in this JSON structure.">
                  <InfoCircleOutlined />
                </Tooltip>
                <div
                  style={{
                    marginTop: "8px",
                    borderTop: "1px solid #f0f0f0",
                    paddingTop: "8px",
                  }}
                >
                  <Checkbox
                    checked={webhookEnabled}
                    onChange={handleWebhookEnabledChange}
                    onClick={(e) => e.stopPropagation()}
                  >
                    Enable Postprocessing Webhook{" "}
                    <Tooltip title="Enable external webhook call to postprocess JSON responses before returning to user.">
                      <InfoCircleOutlined />
                    </Tooltip>
                  </Checkbox>
                  {webhookEnabled && (
                    <div style={{ marginTop: "8px", marginLeft: "24px" }}>
                      <Input
                        placeholder="https://example.com/webhook"
                        value={webhookUrl}
                        onChange={(e) => handleWebhookUrlChange(e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        size="small"
                        style={{ width: "280px" }}
                      />
                      <div
                        style={{
                          fontSize: "11px",
                          color: "#999",
                          marginTop: "4px",
                        }}
                      >
                        External service URL for JSON postprocessing
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        ),
        key: "required",
      },
      {
        label: (
          <div>
            <Checkbox
              checked={lookupEnabled}
              onChange={handleLookupEnabledChange}
              onClick={(e) => e.stopPropagation()}
              disabled={availableLookups.length === 0 && !lookupEnabled}
            >
              Enable Look-up{" "}
              <Tooltip title="Enable lookup enrichment for this prompt. Only lookup projects linked at the project level can be selected.">
                <InfoCircleOutlined />
              </Tooltip>
            </Checkbox>
            {lookupEnabled && availableLookups.length > 0 && (
              <div style={{ marginTop: "8px", marginLeft: "24px" }}>
                <Select
                  placeholder="Select Lookup Project"
                  value={selectedLookup}
                  onChange={handleLookupChange}
                  onClick={(e) => e.stopPropagation()}
                  onMouseDown={(e) => e.stopPropagation()}
                  size="small"
                  style={{ width: "100%" }}
                  allowClear
                  loading={lookupLoading}
                >
                  {availableLookups.map((lookup) => (
                    <Select.Option
                      key={lookup.id}
                      value={lookup.id}
                      disabled={!lookup.is_ready}
                    >
                      {lookup.name} {!lookup.is_ready && "(Not Ready)"}
                    </Select.Option>
                  ))}
                </Select>
              </div>
            )}
            {availableLookups.length === 0 && !lookupLoading && (
              <div
                style={{
                  fontSize: "11px",
                  color: "#999",
                  marginTop: "4px",
                }}
              >
                No lookup projects linked at project level.
                <br />
                Link lookups in Settings → Lookups first.
              </div>
            )}
          </div>
        ),
        key: "lookup",
      },
      {
        type: "divider",
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
  }, [
    isDisablePrompt,
    required,
    enforceType,
    webhookEnabled,
    webhookUrl,
    lookupEnabled,
    selectedLookup,
    availableLookups,
    lookupLoading,
  ]);

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
                  spsLoading?.[selectedDoc?.document_id]
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
        <Dropdown
          menu={{ items }}
          trigger={["click"]}
          placement="bottomLeft"
          onOpenChange={(open) => {
            if (open) {
              fetchAvailableLookups();
            }
          }}
        >
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
  promptKey: PropTypes.string,
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
  enforceType: PropTypes.string,
};

export { Header };
