import PropTypes from "prop-types";
import { SearchOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Collapse,
  Divider,
  Row,
  Select,
  Space,
  Typography,
} from "antd";
import { useEffect, useRef, useState } from "react";

import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import { EditableText } from "../editable-text/EditableText";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { Header } from "./Header";
import { OutputForIndex } from "./OutputForIndex";
import { PromptOutput } from "./PromptOutput";
import { TABLE_ENFORCE_TYPE } from "./constants";

let TableExtractionSettingsBtn;
try {
  TableExtractionSettingsBtn =
    require("../../../plugins/prompt-card/TableExtractionSettingsBtn").TableExtractionSettingsBtn;
} catch {
  // The component will remain null of it is not available
}

function PromptCardItems({
  promptDetails,
  enforceTypeList,
  isRunLoading,
  promptKey,
  setPromptKey,
  promptText,
  setPromptText,
  coverage,
  progressMsg,
  handleRun,
  handleChange,
  handleDelete,
  handleTypeChange,
  updateStatus,
  updatePlaceHolder,
  isCoverageLoading,
  setOpenOutputForDoc,
  selectedLlmProfileId,
  handleSelectDefaultLLM,
  timers,
  spsLoading,
  handleSpsLoading,
  promptOutputs,
}) {
  const {
    llmProfiles,
    selectedDoc,
    listOfDocs,
    disableLlmOrDocChange,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    indexDocs,
    isSimplePromptStudio,
    isPublicSource,
    adapters,
    defaultLlmProfile,
  } = useCustomToolStore();
  const [isEditingPrompt, setIsEditingPrompt] = useState(false);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [expandCard, setExpandCard] = useState(true);
  const [llmProfileDetails, setLlmProfileDetails] = useState([]);
  const [openIndexProfile, setOpenIndexProfile] = useState(null);
  const [coverageCount, setCoverageCount] = useState(0);
  const [enabledProfiles, setEnabledProfiles] = useState(
    llmProfiles.map((profile) => profile.profile_id)
  );
  const [isIndexOpen, setIsIndexOpen] = useState(false);
  const isNotSingleLlmProfile = llmProfiles.length > 1;
  const divRef = useRef(null);
  const [enforceType, setEnforceType] = useState("");

  useEffect(() => {
    if (enforceType !== promptDetails?.enforce_type) {
      setEnforceType(promptDetails?.enforce_type);
    }
  }, [promptDetails]);

  const getModelOrAdapterId = (profile, adapters) => {
    const result = { conf: {} };
    const keys = [
      { key: "llm", label: "LLM" },
      { key: "embedding_model", label: "Embedding Model" },
      { key: "vector_store", label: "Vector Store" },
      { key: "x2text", label: "Text Extractor" },
    ];

    keys.forEach((key) => {
      const adapterName = profile[key.key];
      const adapter = adapters?.find(
        (adapter) => adapter?.adapter_name === adapterName
      );
      if (adapter) {
        result.conf[key.label] =
          adapter?.model || adapter?.adapter_id?.split("|")[0];
        if (adapter?.adapter_type === "LLM") result.icon = adapter?.icon;
        result.conf["Profile Name"] = profile?.profile_name;
      }
    });
    return result;
  };

  const getAdapterInfo = async (adapterData) => {
    // If simple prompt studio, return early
    if (isSimplePromptStudio) {
      return;
    }

    // Update llmProfiles with additional fields
    const updatedProfiles = llmProfiles?.map((profile) => {
      return { ...getModelOrAdapterId(profile, adapterData), ...profile };
    });
    setLlmProfileDetails(
      updatedProfiles
        .map((profile) => ({
          ...profile,
          isDefault: profile?.profile_id === selectedLlmProfileId,
          isEnabled: enabledProfiles.includes(profile?.profile_id),
        }))
        .sort((a, b) => {
          if (a?.isDefault) return -1; // Default profile comes first
          if (b?.isDefault) return 1;
          if (a?.isEnabled && !b?.isEnabled) return -1; // Enabled profiles come before disabled
          if (!a?.isEnabled && b?.isEnabled) return 1;
          return 0;
        })
    );
  };

  const getCoverageData = () => {
    const profileId = singlePassExtractMode
      ? defaultLlmProfile
      : selectedLlmProfileId;
    const keySuffix = `${promptDetails?.prompt_id}_${profileId}`;
    const key = singlePassExtractMode ? `singlepass_${keySuffix}` : keySuffix;
    return coverage[key]?.docs_covered?.length || 0;
  };

  useEffect(() => {
    setExpandCard(true);
  }, [isSinglePassExtractLoading]);

  useEffect(() => {
    setCoverageCount(getCoverageData());
  }, [singlePassExtractMode, coverage]);

  useEffect(() => {
    getAdapterInfo(adapters);
  }, [llmProfiles, selectedLlmProfileId, enabledProfiles]);

  return (
    <Card className="prompt-card">
      <div className="prompt-card-div prompt-card-bg-col1 prompt-card-rad">
        <Space direction="vertical" className="width-100" ref={divRef}>
          <Header
            promptDetails={promptDetails}
            promptKey={promptKey}
            setPromptKey={setPromptKey}
            progressMsg={progressMsg}
            handleRun={handleRun}
            handleChange={handleChange}
            handleDelete={handleDelete}
            updateStatus={updateStatus}
            updatePlaceHolder={updatePlaceHolder}
            isCoverageLoading={isCoverageLoading}
            isEditingTitle={isEditingTitle}
            setIsEditingTitle={setIsEditingTitle}
            expandCard={expandCard}
            setExpandCard={setExpandCard}
            enabledProfiles={enabledProfiles}
            spsLoading={spsLoading}
            handleSpsLoading={handleSpsLoading}
          />
        </Space>
      </div>
      <Collapse
        className="prompt-card-collapse prompt-card-bg-col1"
        ghost
        activeKey={expandCard && "1"}
      >
        <Collapse.Panel key={"1"} showArrow={false}>
          <div className="prompt-card-div-body">
            <EditableText
              isEditing={isEditingPrompt}
              setIsEditing={setIsEditingPrompt}
              text={promptText}
              setText={setPromptText}
              promptId={promptDetails?.prompt_id}
              defaultText={promptDetails?.prompt}
              handleChange={handleChange}
              isTextarea={true}
              placeHolder={updatePlaceHolder}
            />
          </div>
          <>
            {!isSimplePromptStudio && (
              <>
                <Divider className="prompt-card-divider" />
                <Space
                  direction="vertical"
                  className={`prompt-card-comp-layout ${
                    !isRunLoading && "prompt-card-comp-layout-border"
                  }`}
                >
                  <div className="prompt-card-llm-profiles">
                    <Space direction="horizontal">
                      <Button
                        size="small"
                        type="link"
                        className="display-flex-align-center prompt-card-action-button"
                        onClick={() => setOpenOutputForDoc(true)}
                      >
                        <Space>
                          {isCoverageLoading ? (
                            <SpinnerLoader size="small" />
                          ) : (
                            <SearchOutlined className="font-size-12" />
                          )}
                          <Typography.Link className="font-size-12">
                            Coverage: {coverageCount} of{" "}
                            {listOfDocs?.length || 0} docs
                          </Typography.Link>
                        </Space>
                      </Button>
                    </Space>
                    <Space>
                      {enforceType === TABLE_ENFORCE_TYPE &&
                        TableExtractionSettingsBtn && (
                          <TableExtractionSettingsBtn
                            promptId={promptDetails?.prompt_id}
                          />
                        )}
                      <Select
                        className="prompt-card-select-type"
                        size="small"
                        placeholder="Enforce Type"
                        optionFilterProp="children"
                        options={enforceTypeList}
                        value={promptDetails?.enforce_type || null}
                        disabled={
                          disableLlmOrDocChange.includes(
                            promptDetails?.prompt_id
                          ) ||
                          isSinglePassExtractLoading ||
                          indexDocs.includes(selectedDoc?.document_id) ||
                          isPublicSource
                        }
                        onChange={(value) => handleTypeChange(value)}
                      />
                    </Space>
                  </div>
                </Space>
              </>
            )}
          </>
          <Row>
            <PromptOutput
              promptDetails={promptDetails}
              isRunLoading={isRunLoading}
              handleRun={handleRun}
              selectedLlmProfileId={selectedLlmProfileId}
              handleSelectDefaultLLM={handleSelectDefaultLLM}
              timers={timers}
              spsLoading={spsLoading}
              llmProfileDetails={llmProfileDetails}
              setOpenIndexProfile={setOpenIndexProfile}
              enabledProfiles={enabledProfiles}
              setEnabledProfiles={setEnabledProfiles}
              isNotSingleLlmProfile={isNotSingleLlmProfile}
              setIsIndexOpen={setIsIndexOpen}
              enforceType={enforceType}
              promptOutputs={promptOutputs}
            />
          </Row>
        </Collapse.Panel>
      </Collapse>
      <OutputForIndex
        chunkData={openIndexProfile}
        isIndexOpen={isIndexOpen}
        setIsIndexOpen={setIsIndexOpen}
      />
    </Card>
  );
}

PromptCardItems.propTypes = {
  promptDetails: PropTypes.object.isRequired,
  enforceTypeList: PropTypes.array,
  isRunLoading: PropTypes.object,
  promptKey: PropTypes.string,
  setPromptKey: PropTypes.func.isRequired,
  promptText: PropTypes.string,
  setPromptText: PropTypes.func.isRequired,
  coverage: PropTypes.object.isRequired,
  progressMsg: PropTypes.object.isRequired,
  handleRun: PropTypes.func.isRequired,
  handleChange: PropTypes.func.isRequired,
  handleSelectDefaultLLM: PropTypes.func.isRequired,
  handleTypeChange: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  updateStatus: PropTypes.object.isRequired,
  updatePlaceHolder: PropTypes.string,
  isCoverageLoading: PropTypes.bool.isRequired,
  setOpenOutputForDoc: PropTypes.func.isRequired,
  selectedLlmProfileId: PropTypes.string,
  timers: PropTypes.object.isRequired,
  spsLoading: PropTypes.object,
  handleSpsLoading: PropTypes.func.isRequired,
  promptOutputs: PropTypes.object.isRequired,
};

export { PromptCardItems };
