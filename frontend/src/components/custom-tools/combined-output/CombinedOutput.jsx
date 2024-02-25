import { Button, Segmented, Space } from "antd";
import jsYaml from "js-yaml";
import Prism from "prismjs";
import "prismjs/components/prism-json";
import "prismjs/plugins/line-numbers/prism-line-numbers.css";
import "prismjs/plugins/line-numbers/prism-line-numbers.js";
import "prismjs/themes/prism.css";
import { useEffect, useState } from "react";

import { handleException, promptType } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import "./CombinedOutput.css";

const outputTypes = {
  json: "JSON",
  yaml: "YAML",
};

function CombinedOutput() {
  const [combinedOutput, setCombinedOutput] = useState({});
  const [yamlData, setYamlData] = useState(null);
  const [selectedOutputType, setSelectedOutputType] = useState(
    outputTypes.json
  );
  const [isOutputLoading, setIsOutputLoading] = useState(false);
  const { details, selectedDoc } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();

  useEffect(() => {
    if (!selectedDoc) {
      return;
    }

    setIsOutputLoading(true);
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

          const outputDetails = data.find(
            (outputValue) =>
              outputValue?.prompt_id === item?.prompt_id &&
              outputValue?.profile_manager === item?.profile_manager
          );

          if (!outputDetails) {
            return;
          }

          output[item?.prompt_key] = outputDetails?.output || "";
        });
        setCombinedOutput(output);

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
  }, [selectedDoc]);

  useEffect(() => {
    Prism.highlightAll();
  }, [combinedOutput, selectedOutputType]);

  const handleOutputTypeChange = (value) => {
    setSelectedOutputType(value);
  };

  const handleOutputApiRequest = async () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/?tool_id=${details?.tool_id}&doc_name=${selectedDoc}`,
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
        <Space>
          <div>
            <Button disabled>Compare</Button>
          </div>
        </Space>
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

export { CombinedOutput };
