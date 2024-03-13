import { Segmented } from "antd";
import jsYaml from "js-yaml";
import Prism from "prismjs";
import "prismjs/components/prism-json";
import "prismjs/plugins/line-numbers/prism-line-numbers.css";
import "prismjs/plugins/line-numbers/prism-line-numbers.js";
import "prismjs/themes/prism.css";
import { useEffect, useState } from "react";
import PropTypes from "prop-types";

import { promptType } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import "./CombinedOutput.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

const outputTypes = {
  json: "JSON",
  yaml: "YAML",
};

function CombinedOutput({ docId, setFilledFields }) {
  const [combinedOutput, setCombinedOutput] = useState({});
  const [yamlData, setYamlData] = useState(null);
  const [selectedOutputType, setSelectedOutputType] = useState(
    outputTypes.json
  );
  const [isOutputLoading, setIsOutputLoading] = useState(false);
  const { details } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  useEffect(() => {
    if (!docId) {
      return;
    }

    let filledFields = 0;
    setIsOutputLoading(true);
    handleOutputApiRequest()
      .then((res) => {
        const data = res?.data || [];
        data.sort((a, b) => {
          return new Date(b.modified_at) - new Date(a.modified_at);
        });
        const prompts = details?.prompts;
        const output = {};
        prompts.forEach((item) => {
          if (item?.prompt_type === promptType.notes) {
            return;
          }
          output[item?.prompt_key] = "";

          const outputDetails = data.find(
            (outputValue) =>
              outputValue?.prompt_id === item?.prompt_id &&
              outputValue?.profile_manager === item?.profile_manager
          );

          if (!outputDetails) {
            return;
          }

          try {
            output[item?.prompt_key] = JSON.parse(outputDetails?.output);
          } catch (err) {
            output[item?.prompt_key] = outputDetails?.output || "";
          }

          if (outputDetails?.output?.length > 0) {
            filledFields++;
          }
        });
        setCombinedOutput(output);

        if (setFilledFields) {
          setFilledFields(filledFields);
        }

        const yamlDump = jsYaml.dump(output);
        setYamlData(yamlDump);
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to generate combined output")
        );
      })
      .finally(() => {
        setIsOutputLoading(false);
      });
  }, [docId]);

  useEffect(() => {
    Prism.highlightAll();
  }, [combinedOutput, selectedOutputType]);

  const handleOutputTypeChange = (value) => {
    setSelectedOutputType(value);
  };

  const handleOutputApiRequest = async () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/?tool_id=${details?.tool_id}&document_manager=${docId}`,
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

  if (isOutputLoading) {
    return <SpinnerLoader />;
  }

  return (
    <div className="combined-op-layout">
      <div className="combined-op-header">
        <div className="combined-op-segment">
          <Segmented
            size="small"
            defaultValue={selectedOutputType}
            options={["JSON", "YAML"]}
            onChange={handleOutputTypeChange}
          />
        </div>
      </div>
      <div className="combined-op-divider" />
      <div className="combined-op-body code-snippet">
        {combinedOutput && (
          <pre className="line-numbers width-100">
            <code className="language-javascript width-100">
              {selectedOutputType === outputTypes.json
                ? JSON.stringify(combinedOutput, null, 2)
                : yamlData}
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
