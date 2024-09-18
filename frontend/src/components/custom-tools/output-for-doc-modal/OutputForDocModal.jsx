import { Button, Modal, Table, Tabs, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import {
  CheckCircleFilled,
  CloseCircleFilled,
  InfoCircleFilled,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import TabPane from "antd/es/tabs/TabPane";

import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import "./OutputForDocModal.css";
import {
  displayPromptResult,
  getDocIdFromKey,
  getLLMModelNamesForProfiles,
} from "../../../helpers/GetStaticData";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { TokenUsage } from "../token-usage/TokenUsage";
import { useTokenUsageStore } from "../../../store/token-usage-store";
import { ProfileInfoBar } from "../profile-info-bar/ProfileInfoBar";

let publicOutputsApi;
let publicAdapterApi;
try {
  publicOutputsApi =
    require("../../../plugins/prompt-studio-public-share/helpers/PublicShareAPIs").publicOutputsApi;
  publicAdapterApi =
    require("../../../plugins/prompt-studio-public-share/helpers/PublicShareAPIs").publicAdapterApi;
} catch {
  // The component will remain null of it is not available
}

const outputStatus = {
  yet_to_process: "YET_TO_PROCESS",
  success: "SUCCESS",
  fail: "FAIL",
};

const errorTypes = ["null", "undefined", "false"];

function OutputForDocModal({
  open,
  setOpen,
  promptId,
  promptKey,
  profileManagerId,
  docOutputs,
}) {
  const [promptOutputs, setPromptOutputs] = useState([]);
  const [rows, setRows] = useState([]);
  const [adapterData, setAdapterData] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const {
    details,
    listOfDocs,
    selectedDoc,
    disableLlmOrDocChange,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    isPublicSource,
    llmProfiles,
    defaultLlmProfile,
  } = useCustomToolStore();
  const [selectedProfile, setSelectedProfile] = useState(defaultLlmProfile);
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const navigate = useNavigate();
  const { id } = useParams();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const { tokenUsage } = useTokenUsageStore();

  useEffect(() => {
    if (!open) {
      return;
    }
    handleGetOutputForDocs(selectedProfile || profileManagerId);
    getAdapterInfo();
  }, [
    open,
    selectedProfile,
    singlePassExtractMode,
    isSinglePassExtractLoading,
  ]);

  useEffect(() => {
    updatePromptOutput(docOutputs);
  }, [docOutputs]);

  useEffect(() => {
    handleRowsGeneration(promptOutputs);
  }, [promptOutputs, tokenUsage]);

  const moveSelectedDocToTop = () => {
    // Create a copy of the list of documents
    const docs = [...listOfDocs];

    // Find the index of the selected document within the list
    const index = docs.findIndex(
      (item) => item?.document_id === selectedDoc?.document_id
    );

    // If the selected document exists in the list and is not already at the top (index 0)
    if (index !== -1 && index !== 0) {
      // Remove the selected document from its current position
      const doc = docs.splice(index, 1)[0];
      // Insert the selected document at the beginning of the list
      docs.unshift(doc);
    }

    // Return the updated list of documents
    return docs;
  };

  const updatePromptOutput = (data) => {
    setPromptOutputs((prev) => {
      const updatedPromptOutput = data || [...prev];
      const keys = Object.keys(docOutputs);

      keys.forEach((key) => {
        const docId = getDocIdFromKey(key);
        updatePromptOutputInstance(updatedPromptOutput, docId, key);
      });

      return updatedPromptOutput;
    });
  };

  const updatePromptOutputInstance = (updatedPromptOutput, docId, key) => {
    const index = findPromptOutputIndex(updatedPromptOutput, docId);
    const promptOutputInstance = createOrUpdatePromptOutputInstance(
      updatedPromptOutput,
      docId,
      key,
      index
    );

    if (index > -1) {
      updatedPromptOutput[index] = promptOutputInstance;
    } else {
      updatedPromptOutput.push(promptOutputInstance);
    }
  };

  const findPromptOutputIndex = (updatedPromptOutput, docId) => {
    return updatedPromptOutput.findIndex(
      (promptOutput) => promptOutput?.document_manager === docId
    );
  };

  const createOrUpdatePromptOutputInstance = (
    updatedPromptOutput,
    docId,
    key,
    index
  ) => {
    let promptOutputInstance = {};

    if (index > -1) {
      promptOutputInstance = { ...updatedPromptOutput[index] };
    }

    promptOutputInstance["document_manager"] = docId;
    promptOutputInstance["output"] = docOutputs[key]?.output;
    promptOutputInstance["isLoading"] = docOutputs[key]?.isLoading || false;

    return promptOutputInstance;
  };

  const getAdapterInfo = () => {
    let url = `/api/v1/unstract/${sessionDetails.orgId}/adapter/?adapter_type=LLM`;
    if (isPublicSource) {
      url = publicAdapterApi(id, "LLM");
    }
    axiosPrivate.get(url).then((res) => {
      const adapterList = res.data;
      setAdapterData(getLLMModelNamesForProfiles(llmProfiles, adapterList));
    });
  };

  const handleGetOutputForDocs = (profile = profileManagerId) => {
    if (!profile) {
      setRows([]);
      return;
    }
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/?tool_id=${details?.tool_id}&prompt_id=${promptId}&profile_manager=${profile}&is_single_pass_extract=${singlePassExtractMode}`;
    if (isPublicSource) {
      url = publicOutputsApi(id, promptId, singlePassExtractMode);
      url += `&profile_manager=${profile}`;
    }
    const requestOptions = {
      method: "GET",
      url,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    setIsLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data || [];
        updatePromptOutput(data);
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to loaded the prompt results")
        );
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  const handleRowsGeneration = (data) => {
    const rowsData = [];
    const docs = moveSelectedDocToTop();
    docs.forEach((item) => {
      const output = data.find((outputValue) => {
        const docId =
          outputValue?.document_manager ||
          (outputValue?.key && getDocIdFromKey(outputValue?.key)) ||
          null;
        return docId === item?.document_id;
      });
      const key = `${promptId}__${item?.document_id}__${
        selectedProfile || profileManagerId
      }`;

      let status = outputStatus.fail;
      let message = displayPromptResult(output?.output, true);

      if (
        (output?.output || output?.output === 0) &&
        !errorTypes.includes(output?.output)
      ) {
        status = outputStatus.success;
        message = displayPromptResult(output?.output, true);
      }

      if (output?.output === undefined) {
        status = outputStatus.yet_to_process;
        message = "Yet to process";
      }
      const isLoading = docOutputs.find((obj) => obj?.key === key)?.isLoading;

      const result = {
        key: item?.document_id,
        document: item?.document_name,
        token_count: !singlePassExtractMode && (
          <TokenUsage
            tokenUsageId={
              promptId +
              "__" +
              item?.document_id +
              "__" +
              (selectedProfile || profileManagerId)
            }
          />
        ),
        value: (
          <>
            {isLoading ? (
              <SpinnerLoader align="default" />
            ) : (
              <Typography.Text>
                <span style={{ marginRight: "8px" }}>
                  {status === outputStatus.yet_to_process && (
                    <InfoCircleFilled style={{ color: "#F0AD4E" }} />
                  )}
                  {status === outputStatus.fail && (
                    <CloseCircleFilled style={{ color: "#FF4D4F" }} />
                  )}
                  {status === outputStatus.success && (
                    <CheckCircleFilled style={{ color: "#52C41A" }} />
                  )}
                </span>{" "}
                {message}
              </Typography.Text>
            )}
          </>
        ),
      };
      rowsData.push(result);
    });
    setRows(rowsData);
  };

  const handleTabChange = (key) => {
    if (key === "0") {
      setSelectedProfile(defaultLlmProfile);
    } else {
      setSelectedProfile(adapterData[key - 1]?.profile_id);
    }
  };

  const columns = [
    {
      title: "Document",
      dataIndex: "document",
      key: "document",
    },
    !singlePassExtractMode && {
      title: "Token Count",
      dataIndex: "token_count",
      key: "token_count",
      width: 200,
    },
    {
      title: "Value",
      dataIndex: "value",
      key: "value",
      width: 600,
    },
  ].filter(Boolean);

  return (
    <Modal
      className="pre-post-amble-modal"
      open={open}
      width={1000}
      onCancel={() => setOpen(false)}
      footer={null}
      centered
      maskClosable={false}
    >
      <div className="pre-post-amble-body output-doc-layout">
        <div>
          <Typography.Text className="add-cus-tool-header">
            {promptKey}
          </Typography.Text>
        </div>
        <div className="output-doc-gap" />
        <div className="lmm-profile-outputs">
          <Tabs defaultActiveKey="0" onChange={handleTabChange}>
            <TabPane tab={<span>Default</span>} key={"0"}></TabPane>
            {adapterData?.map((adapter, index) => (
              <TabPane
                tab={<span>{adapter?.llm_model || adapter?.profile_name}</span>}
                key={(index + 1)?.toString()}
              ></TabPane>
            ))}
          </Tabs>{" "}
          <ProfileInfoBar
            profileId={selectedProfile || profileManagerId}
            profiles={llmProfiles}
          />
        </div>
        <div className="display-flex-right">
          <Button
            size="small"
            onClick={() => navigate("outputAnalyzer")}
            disabled={
              disableLlmOrDocChange?.length > 0 || isSinglePassExtractLoading
            }
          >
            View in Output Analyzer
          </Button>
        </div>
        <div className="output-doc-gap" />
        <div className="output-doc-table">
          <Table
            columns={columns}
            dataSource={rows}
            pagination={{ pageSize: 5 }}
            loading={{
              indicator: (
                <div>
                  <SpinnerLoader />
                </div>
              ),
              spinning: isLoading,
            }}
          />
        </div>
      </div>
    </Modal>
  );
}

OutputForDocModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  promptId: PropTypes.string.isRequired,
  promptKey: PropTypes.string.isRequired,
  profileManagerId: PropTypes.string,
  docOutputs: PropTypes.object,
};

export { OutputForDocModal };
