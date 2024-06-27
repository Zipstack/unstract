import Prism from "prismjs";
import "prismjs/components/prism-json";
import "prismjs/plugins/line-numbers/prism-line-numbers.css";
import "prismjs/plugins/line-numbers/prism-line-numbers.js";
import "prismjs/themes/prism.css";
import { useEffect, useState } from "react";
import PropTypes from "prop-types";

import {
  displayPromptResult,
  getLLMModelNamesForProfiles,
  promptType,
} from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import "./CombinedOutput.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import TabPane from "antd/es/tabs/TabPane";
import { Tabs } from "antd";
import { ProfileInfoBar } from "../profile-info-bar/ProfileInfoBar";

function CombinedOutput({ docId, setFilledFields }) {
  const [combinedOutput, setCombinedOutput] = useState({});
  const [isOutputLoading, setIsOutputLoading] = useState(false);
  const [adapterData, setAdapterData] = useState([]);
  const [activeKey, setActiveKey] = useState("0");
  const {
    details,
    defaultLlmProfile,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    llmProfiles,
  } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const [selectedProfile, setSelectedProfile] = useState(defaultLlmProfile);

  useEffect(() => {
    getAdapterInfo();
  }, []);
  useEffect(() => {
    if (!docId || isSinglePassExtractLoading) {
      return;
    }

    let filledFields = 0;
    setIsOutputLoading(true);
    setCombinedOutput({});
    handleOutputApiRequest()
      .then((res) => {
        const data = res?.data || [];
        const prompts = details?.prompts;
        const output = {};
        prompts.forEach((item) => {
          if (item?.prompt_type === promptType.notes) {
            return;
          }
          output[item?.prompt_key] = "";

          let profileManager = selectedProfile || item?.profile_manager;
          if (singlePassExtractMode) {
            profileManager = defaultLlmProfile;
          }
          const outputDetails = data.find(
            (outputValue) =>
              outputValue?.prompt_id === item?.prompt_id &&
              outputValue?.profile_manager === profileManager
          );

          if (!outputDetails) {
            return;
          }

          output[item?.prompt_key] = displayPromptResult(
            outputDetails?.output,
            false
          );

          if (outputDetails?.output?.length > 0) {
            filledFields++;
          }
        });

        setCombinedOutput(output);

        if (setFilledFields) {
          setFilledFields(filledFields);
        }
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to generate combined output")
        );
      })
      .finally(() => {
        setIsOutputLoading(false);
      });
  }, [
    docId,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    selectedProfile,
  ]);

  useEffect(() => {
    Prism.highlightAll();
  }, [combinedOutput]);

  const handleOutputApiRequest = async () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${
        sessionDetails?.orgId
      }/prompt-studio/prompt-output/?tool_id=${
        details?.tool_id
      }&document_manager=${docId}&is_single_pass_extract=${singlePassExtractMode}&profile_manager=${
        selectedProfile || defaultLlmProfile
      }`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    return axiosPrivate(requestOptions)
      .then((res) => res)
      .catch((err) => {
        throw err;
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

  if (isOutputLoading) {
    return <SpinnerLoader />;
  }

  const handleTabChange = (key) => {
    if (key === "0") {
      setSelectedProfile(defaultLlmProfile);
    } else {
      setSelectedProfile(adapterData[key - 1]?.profile_id);
    }
    setActiveKey(key);
  };

  return (
    <div className="combined-op-layout">
      <div className="combined-op-header">
        <Tabs activeKey={activeKey} onChange={handleTabChange} moreIcon={<></>}>
          <TabPane tab={<span>{"Default"}</span>} key={"0"}></TabPane>
          {adapterData.map((adapter, index) => (
            <TabPane
              tab={<span>{adapter.llm_model}</span>}
              key={(index + 1)?.toString()}
            ></TabPane>
          ))}
        </Tabs>
        <div className="combined-op-segment"></div>
      </div>
      <div className="combined-op-divider" />
      <ProfileInfoBar profileId={selectedProfile} profiles={llmProfiles} />
      <div className="combined-op-body code-snippet">
        {combinedOutput && (
          <pre className="line-numbers width-100">
            <code className="language-javascript width-100">
              {JSON.stringify(combinedOutput, null, 2)}
            </code>
          </pre>
        )}
      </div>
      <div className="gap" />
    </div>
  );
}

CombinedOutput.propTypes = {
  docId: PropTypes.string,
  setFilledFields: PropTypes.func,
};

export { CombinedOutput };
