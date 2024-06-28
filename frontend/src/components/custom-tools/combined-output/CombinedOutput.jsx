import Prism from "prismjs";
import "prismjs/components/prism-json";
import "prismjs/plugins/line-numbers/prism-line-numbers.css";
import "prismjs/plugins/line-numbers/prism-line-numbers.js";
import "prismjs/themes/prism.css";
import { useEffect, useState } from "react";
import PropTypes from "prop-types";

import {
  displayPromptResult,
  promptType,
} from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import "./CombinedOutput.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useParams } from "react-router-dom";

function CombinedOutput({ docId, setFilledFields }) {
  const [combinedOutput, setCombinedOutput] = useState({});
  const [isOutputLoading, setIsOutputLoading] = useState(false);
  const {
    details,
    defaultLlmProfile,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    isPublicSource,
  } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const { id } = useParams();
  const handleException = useExceptionHandler();

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

          let profileManager = item?.profile_manager;
          if (singlePassExtractMode) {
            profileManager = defaultLlmProfile;
          }
          const outputDetails = data.find(
            (outputValue) =>
              outputValue?.prompt_id === item?.prompt_id &&
              outputValue?.profile_manager === profileManager,
          );

          if (!outputDetails) {
            return;
          }

          output[item?.prompt_key] = displayPromptResult(
            outputDetails?.output,
            false,
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
          handleException(err, "Failed to generate combined output"),
        );
      })
      .finally(() => {
        setIsOutputLoading(false);
      });
  }, [docId, singlePassExtractMode, isSinglePassExtractLoading]);

  useEffect(() => {
    Prism.highlightAll();
  }, [combinedOutput]);

  const handleOutputApiRequest = async () => {
    const requestPrivateOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/?tool_id=${details?.tool_id}&document_manager=${docId}&is_single_pass_extract=${singlePassExtractMode}`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    const requestPublicOptions = {
      method: "GET",
      url: `/public/share/outputs-metadata/?id=${id}&document_manager=${docId}&is_single_pass_extract=${singlePassExtractMode}`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    const requestOptions = isPublicSource
      ? requestPublicOptions
      : requestPrivateOptions;
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
        <div className="combined-op-segment"></div>
      </div>
      <div className="combined-op-divider" />
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
