import { Button, Modal, Table, Tabs, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import {
  CheckCircleFilled,
  CloseCircleFilled,
  InfoCircleFilled,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";

import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import "./OutputForDocModal.css";
import {
  displayPromptResult,
  getLLMModelNamesForProfiles,
} from "../../../helpers/GetStaticData";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { TokenUsage } from "../token-usage/TokenUsage";
import { useTokenUsageStore } from "../../../store/token-usage-store";
import TabPane from "antd/es/tabs/TabPane";
import { ProfileInfoBar } from "../profile-info-bar/ProfileInfoBar";


let publicOutputsApi;
try {
  publicOutputsApi =
    require("../../../plugins/prompt-studio-public-share/helpers/PublicShareAPIs").publicOutputsApi;
} catch {
  // The component will remain null of it is not available
}
const columns = [
  {
    title: "Document",
    dataIndex: "document",
    key: "document",
  },
  {
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
];

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
    defaultLlmProfile,
    disableLlmOrDocChange,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    isPublicSource,
    llmProfiles,
  } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const navigate = useNavigate();
  const { id } = useParams();
  const { setAlertDetails } = useAlertStore();
  const { handleException } = useExceptionHandler();
  const { tokenUsage } = useTokenUsageStore();
  const [selectedProfile, setSelectedProfile] = useState(defaultLlmProfile);

  useEffect(() => {
    if (!open) {
      return;
    }
    handleGetOutputForDocs();
    getAdapterInfo();
  }, [open, singlePassExtractMode, isSinglePassExtractLoading]);

  useEffect(() => {
    updatePromptOutput();
  }, [docOutputs]);

  useEffect(() => {
    handleRowsGeneration(promptOutputs);
  }, [promptOutputs, tokenUsage]);

  useEffect(() => {
    if (selectedProfile) {
      handleGetOutputForDocs(selectedProfile);
    }
  }, [selectedProfile]);

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
      // If data is provided, use it; otherwise, create a copy of the previous state
      const updatedPromptOutput = data || [...prev];

      // Get the keys of docOutputs
      const keys = Object.keys(docOutputs);

      keys.forEach((key) => {
        // Find the index of the prompt output corresponding to the document manager key
        const index = updatedPromptOutput.findIndex(
          (promptOutput) => promptOutput?.document_manager === key
        );

        let promptOutputInstance = {};
        // If the prompt output for the current key doesn't exist, skip it
        if (index > -1) {
          promptOutputInstance = updatedPromptOutput[index];
          promptOutputInstance["output"] = docOutputs[key]?.output;
        }

        // Update output and isLoading properties based on docOutputs
        promptOutputInstance["document_manager"] = key;
        promptOutputInstance["isLoading"] = docOutputs[key]?.isLoading || false;

        // Update the prompt output instance in the array
        if (index > -1) {
          updatedPromptOutput[index] = promptOutputInstance;
        } else {
          updatedPromptOutput.push(promptOutputInstance);
        }
      });

      return updatedPromptOutput;
    });
  };

  const getAdapterInfo = () => {
    axiosPrivate
      .get(`/api/v1/unstract/${sessionDetails.orgId}/adapter/?adapter_type=LLM`)
      .then((res) => {
        const adapterList = res.data;
        setAdapterData(getLLMModelNamesForProfiles(llmProfiles, adapterList));
      });
  };

  const handleGetOutputForDocs = (profile = profileManagerId) => {
    if (singlePassExtractMode) {
      profile = defaultLlmProfile;
    }

    if (!profile) {
      setRows([]);
      return;
    }
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/?tool_id=${details?.tool_id}&prompt_id=${promptId}&profile_manager=${profile}&is_single_pass_extract=${singlePassExtractMode}`;
    if (isPublicSource) {
      url = publicOutputsApi(id, promptId, profile, singlePassExtractMode);
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
      const output = data.find(
        (outputValue) => outputValue?.document_manager === item?.document_id
      );

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

      const result = {
        key: item?.document_id,
        document: item?.document_name,
        token_count: (
          <TokenUsage
            tokenUsageId={
              promptId + "__" + item?.document_id + "__" + profileManagerId
            }
          />
        ),
        value: (
          <>
            {output?.isLoading ? (
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
      setSelectedProfile(profileManagerId);
    } else {
      setSelectedProfile(adapterData[key - 1]?.profile_id);
    }
  };

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
                tab={<span>{adapter?.llm_model}</span>}
                key={(index + 1)?.toString()}
              ></TabPane>
            ))}
          </Tabs>{" "}
          <ProfileInfoBar profileId={selectedProfile} profiles={llmProfiles} />
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
