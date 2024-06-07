import PropTypes from "prop-types";
import { LeftOutlined, RightOutlined, SearchOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Collapse,
  Divider,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import { useEffect, useRef, useState } from "react";

import { displayPromptResult } from "../../../helpers/GetStaticData";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import { EditableText } from "../editable-text/EditableText";
import { TokenUsage } from "../token-usage/TokenUsage";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { Header } from "./Header";

const EvalBtn = null;
const EvalMetrics = null;

function PromptCardItems({
  promptDetails,
  enforceTypeList,
  isRunLoading,
  promptKey,
  setPromptKey,
  promptText,
  setPromptText,
  result,
  coverage,
  progressMsg,
  handleRun,
  handleChange,
  handleDelete,
  handlePageLeft,
  handlePageRight,
  handleTypeChange,
  updateStatus,
  updatePlaceHolder,
  isCoverageLoading,
  setOpenEval,
  setOpenOutputForDoc,
  selectedLlmProfileId,
  page,
}) {
  const [isEditingPrompt, setIsEditingPrompt] = useState(false);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [expandCard, setExpandCard] = useState(true);
  const divRef = useRef(null);
  const {
    llmProfiles,
    selectedDoc,
    listOfDocs,
    disableLlmOrDocChange,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    indexDocs,
  } = useCustomToolStore();

  useEffect(() => {
    setExpandCard(true);
  }, [isSinglePassExtractLoading]);

  const enableEdit = (event) => {
    event.stopPropagation();
    setExpandCard(true);
    setIsEditingTitle(true);
    setIsEditingPrompt(true);
  };

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
            enableEdit={enableEdit}
            expandCard={expandCard}
            setExpandCard={setExpandCard}
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
              defaultText={promptDetails.prompt}
              handleChange={handleChange}
              isTextarea={true}
              placeHolder={updatePlaceHolder}
            />
          </div>
          <>
            <Divider className="prompt-card-divider" />
            <Space
              direction="vertical"
              className={`prompt-card-comp-layout ${
                !(isRunLoading || result?.output || result?.output === 0) &&
                "prompt-card-comp-layout-border"
              }`}
            >
              <div className="prompt-card-llm-profiles">
                <Space direction="horizontal">
                  {EvalBtn && !singlePassExtractMode && (
                    <EvalBtn
                      btnText={promptDetails?.evaluate ? "On" : "Off"}
                      promptId={promptDetails.prompt_id}
                      setOpenEval={setOpenEval}
                    />
                  )}
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
                        Coverage: {coverage} of {listOfDocs?.length || 0} docs
                      </Typography.Link>
                    </Space>
                  </Button>
                </Space>
                <Space>
                  {!singlePassExtractMode && (
                    <TokenUsage
                      tokenUsageId={
                        promptDetails?.prompt_id +
                        "__" +
                        selectedDoc?.document_id
                      }
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
                      indexDocs.includes(selectedDoc?.document_id)
                    }
                    onChange={(value) => handleTypeChange(value)}
                  />
                </Space>
              </div>
              <div className="prompt-card-llm-profiles">
                {!singlePassExtractMode && (
                  <>
                    {llmProfiles?.length > 0 &&
                    promptDetails?.profile_manager?.length > 0 &&
                    selectedLlmProfileId ? (
                      <div>
                        {llmProfiles
                          .filter(
                            (profile) =>
                              profile.profile_id === selectedLlmProfileId
                          )
                          .map((profile, index) => (
                            <div key={profile?.profile_id}>
                              <Tag>{profile.llm}</Tag>
                              <Tag>{profile.vector_store}</Tag>
                              <Tag>{profile.embedding_model}</Tag>
                              <Tag>{profile.x2text}</Tag>
                              <Tag>{`${profile.chunk_size}/${profile.chunk_overlap}/${profile.retrieval_strategy}/${profile.similarity_top_k}/${profile.section}`}</Tag>
                            </div>
                          ))}
                      </div>
                    ) : (
                      <div>
                        <Typography.Text className="font-size-12">
                          No LLM Profile Selected
                        </Typography.Text>
                      </div>
                    )}
                  </>
                )}
                {!singlePassExtractMode && (
                  <div className="display-flex-right prompt-card-paginate-div">
                    <Button
                      type="text"
                      size="small"
                      className="prompt-card-action-button"
                      disabled={
                        page <= 1 ||
                        disableLlmOrDocChange.includes(
                          promptDetails?.prompt_id
                        ) ||
                        isSinglePassExtractLoading ||
                        indexDocs.includes(selectedDoc?.document_id)
                      }
                      onClick={handlePageLeft}
                    >
                      <LeftOutlined className="prompt-card-paginate" />
                    </Button>
                    <Button
                      type="text"
                      size="small"
                      className="prompt-card-action-button"
                      disabled={
                        page >= llmProfiles?.length ||
                        disableLlmOrDocChange.includes(
                          promptDetails?.prompt_id
                        ) ||
                        isSinglePassExtractLoading ||
                        indexDocs.includes(selectedDoc?.document_id)
                      }
                      onClick={handlePageRight}
                    >
                      <RightOutlined className="prompt-card-paginate" />
                    </Button>
                  </div>
                )}
              </div>
              {EvalMetrics && <EvalMetrics result={result} />}
            </Space>
          </>
          {(isRunLoading || result?.output || result?.output === 0) && (
            <>
              <Divider className="prompt-card-divider" />
              <div className="prompt-card-result prompt-card-div">
                {isRunLoading ? (
                  <Spin indicator={<SpinnerLoader size="small" />} />
                ) : (
                  <Typography.Paragraph className="prompt-card-res font-size-12">
                    <div>{displayPromptResult(result?.output, true)}</div>
                  </Typography.Paragraph>
                )}
              </div>
            </>
          )}
        </Collapse.Panel>
      </Collapse>
    </Card>
  );
}

PromptCardItems.propTypes = {
  promptDetails: PropTypes.object.isRequired,
  enforceTypeList: PropTypes.array,
  isRunLoading: PropTypes.bool,
  promptKey: PropTypes.text,
  setPromptKey: PropTypes.func.isRequired,
  promptText: PropTypes.text,
  setPromptText: PropTypes.func.isRequired,
  result: PropTypes.object.isRequired,
  coverage: PropTypes.number.isRequired,
  progressMsg: PropTypes.object.isRequired,
  handleRun: PropTypes.func.isRequired,
  handleChange: PropTypes.func.isRequired,
  handlePageLeft: PropTypes.func.isRequired,
  handlePageRight: PropTypes.func.isRequired,
  handleTypeChange: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  updateStatus: PropTypes.object.isRequired,
  updatePlaceHolder: PropTypes.string,
  isCoverageLoading: PropTypes.bool.isRequired,
  setOpenEval: PropTypes.func.isRequired,
  setOpenOutputForDoc: PropTypes.func.isRequired,
  selectedLlmProfileId: PropTypes.string,
  page: PropTypes.number.isRequired,
};

export { PromptCardItems };
