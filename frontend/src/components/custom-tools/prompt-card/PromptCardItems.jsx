import { Search } from "lucide-react";
import PropTypes from "prop-types";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/shims/antd-button";
import { Select } from "@/components/ui/shims/antd-inputs";
import { Row, Space } from "@/components/ui/shims/antd-layout";
import { Divider, Tag } from "@/components/ui/shims/antd-leaves";
import { Collapse } from "@/components/ui/shims/antd-overlays";
import { Card } from "@/components/ui/shims/antd-structure";
import { Typography } from "@/components/ui/shims/antd-typography";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import { EditableText } from "../editable-text/EditableText";
import { Header } from "./Header";
import { OutputForIndex } from "./OutputForIndex";
import { PromptOutput } from "./PromptOutput";

let TableExtractionSettingsBtn;
try {
  const mod = await import(
    "../../../plugins/prompt-card/TableExtractionSettingsBtn"
  );
  TableExtractionSettingsBtn = mod.TableExtractionSettingsBtn;
} catch {
  // The component will remain null of it is not available
}

let LookupIndicator;
try {
  const mod = await import(
    "../../../plugins/lookup-studio/prompt-card/LookupIndicator"
  );
  LookupIndicator = mod.LookupIndicator;
} catch {}

let AgenticTableChecklist;
try {
  const mod = await import(
    "../../../plugins/prompt-card/AgenticTableChecklist"
  );
  AgenticTableChecklist = mod.AgenticTableChecklist;
} catch {
  // The component will remain null of it is not available
}

function PromptCardItems({
  promptDetails,
  enforceTypeList,
  allTableSettings,
  setAllTableSettings,
  promptKey,
  setPromptKey,
  promptText,
  setPromptText,
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
  spsLoading,
  handleSpsLoading,
  promptOutputs,
  promptRunStatus,
  coverageCountData,
  isChallenge,
  handleSelectHighlight,
  fieldErrors,
}) {
  const {
    llmProfiles,
    selectedDoc,
    listOfDocs,
    isSinglePassExtractLoading,
    indexDocs,
    isSimplePromptStudio,
    isPublicSource,
    selectedHighlight,
    details,
    singlePassExtractMode,
  } = useCustomToolStore();

  const [isEditingPrompt, setIsEditingPrompt] = useState(false);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [expandCard, setExpandCard] = useState(true);
  const [llmProfileDetails, setLlmProfileDetails] = useState([]);
  const [openIndexProfile, setOpenIndexProfile] = useState(null);
  const [isIndexOpen, setIsIndexOpen] = useState(false);
  const isNotSingleLlmProfile = llmProfiles.length > 1;
  const divRef = useRef(null);
  const [enforceType, setEnforceType] = useState("");
  const [tableSettings, setTableSettings] = useState({});
  const [isAgenticTableReady, setIsAgenticTableReady] = useState(true);
  const promptId = promptDetails?.prompt_id;

  useEffect(() => {
    if (enforceType !== promptDetails?.enforce_type) {
      setEnforceType(promptDetails?.enforce_type);
    }
  }, [promptDetails]);

  useEffect(() => {
    setTableSettings(
      allTableSettings.find((item) => item.prompt_id === promptId) || {},
    );
  }, [allTableSettings]);

  const getUpdatedCoverage = (promptId, singlePass, promptOutputs) => {
    let updatedCoverage = null;
    Object.keys(promptOutputs).forEach((key) => {
      const [keyPromptId, , , keyIsSinglePass] = key.split("__"); // Destructure the key parts

      // Check if the key matches the criteria
      if (keyPromptId === promptId && keyIsSinglePass === String(singlePass)) {
        const currentCoverage = promptOutputs[key]?.coverage || [];

        // Update the highestCoverage if the current one is longer
        if (
          !updatedCoverage ||
          currentCoverage.length > updatedCoverage.length
        ) {
          updatedCoverage = currentCoverage;
        }
      }
    });

    return updatedCoverage;
  };

  const promptCoverage =
    getUpdatedCoverage(promptId, singlePassExtractMode, promptOutputs) ||
    coverageCountData;

  useEffect(() => {
    setExpandCard(true);
  }, [isSinglePassExtractLoading]);

  useEffect(() => {
    if (isSimplePromptStudio) {
      return;
    }
    // conf and icon come from the profile payload, not the viewer's adapters.
    setLlmProfileDetails(
      (llmProfiles || [])
        .map((profile) => ({
          ...profile,
          isDefault: profile?.profile_id === selectedLlmProfileId,
        }))
        .sort((a, b) => {
          if (a?.isDefault) {
            return -1; // Default profile comes first
          }
          if (b?.isDefault) {
            return 1;
          }
          return 0;
        }),
    );
  }, [llmProfiles, selectedLlmProfileId, isSimplePromptStudio]);

  return (
    <Card
      className={`prompt-card ${
        details?.enable_highlight &&
        selectedHighlight?.highlightedPrompt === promptDetails?.prompt_id &&
        "highlighted-prompt"
      }`}
    >
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
            spsLoading={spsLoading}
            handleSpsLoading={handleSpsLoading}
            enforceType={enforceType}
            isAgenticTableReady={isAgenticTableReady}
            promptKeyError={fieldErrors?.prompt_key}
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
            {AgenticTableChecklist && (
              <AgenticTableChecklist
                promptId={promptDetails?.prompt_id}
                promptText={promptText}
                enforceType={enforceType}
                onReadinessChange={setIsAgenticTableReady}
              />
            )}
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
              isCoverageLoading={isCoverageLoading}
            />
          </div>
          <>
            {!isSimplePromptStudio && (
              <>
                <Divider className="prompt-card-divider" />
                <Space direction="vertical" className="prompt-card-comp-layout">
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
                            // size-3 (12px), not `font-size-12`: that class is
                            // a TEXT utility shared with the Typography.Link
                            // below, and font-size does nothing to an SVG — the
                            // icon fell back to lucide's 24px default.
                            <Search className="size-3" />
                          )}
                          <Typography.Link className="font-size-12">
                            Coverage: {promptCoverage?.length || 0} of{" "}
                            {listOfDocs?.length || 0} docs
                          </Typography.Link>
                        </Space>
                      </Button>
                      {LookupIndicator && (
                        <LookupIndicator promptDetails={promptDetails} />
                      )}
                    </Space>
                    <Space>
                      {details?.enable_highlight &&
                        ["table", "record"].includes(enforceType) && (
                          <Tag
                            color="red"
                            style={{
                              whiteSpace: "normal",
                              wordWrap: "break-word",
                              minWidth: "200px",
                            }}
                          >
                            Highlighting is not supported when enforce type is{" "}
                            {enforceType}
                          </Tag>
                        )}
                    </Space>
                    <Space>
                      {TableExtractionSettingsBtn && (
                        <TableExtractionSettingsBtn
                          promptId={promptDetails?.prompt_id}
                          enforceType={enforceType}
                          setAllTableSettings={setAllTableSettings}
                        />
                      )}
                      <Select
                        className="prompt-card-select-type"
                        size="small"
                        placeholder="Enforce Type"
                        showSearch
                        options={enforceTypeList}
                        value={promptDetails?.enforce_type || null}
                        disabled={
                          isCoverageLoading ||
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
              handleRun={handleRun}
              selectedLlmProfileId={selectedLlmProfileId}
              handleSelectDefaultLLM={handleSelectDefaultLLM}
              spsLoading={spsLoading}
              llmProfileDetails={llmProfileDetails}
              setOpenIndexProfile={setOpenIndexProfile}
              isNotSingleLlmProfile={isNotSingleLlmProfile}
              setIsIndexOpen={setIsIndexOpen}
              enforceType={enforceType}
              tableSettings={tableSettings}
              promptOutputs={promptOutputs}
              promptRunStatus={promptRunStatus}
              isChallenge={isChallenge}
              handleSelectHighlight={handleSelectHighlight}
              progressMsg={progressMsg}
              isAgenticTableReady={isAgenticTableReady}
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
  fieldErrors: PropTypes.object,
  promptDetails: PropTypes.object.isRequired,
  enforceTypeList: PropTypes.array,
  allTableSettings: PropTypes.array,
  setAllTableSettings: PropTypes.func,
  promptKey: PropTypes.string,
  setPromptKey: PropTypes.func.isRequired,
  promptText: PropTypes.string,
  setPromptText: PropTypes.func.isRequired,
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
  spsLoading: PropTypes.object,
  handleSpsLoading: PropTypes.func.isRequired,
  promptOutputs: PropTypes.object.isRequired,
  promptRunStatus: PropTypes.object.isRequired,
  coverageCountData: PropTypes.array,
  isChallenge: PropTypes.bool.isRequired,
  handleSelectHighlight: PropTypes.func.isRequired,
};

export { PromptCardItems };
