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
import { JsonView } from "./JsonView";

let TableView;
let promptOutputApiSps;
try {
  TableView =
    require("../../../plugins/simple-prompt-studio/TableView").TableView;
  promptOutputApiSps =
    require("../../../plugins/simple-prompt-studio/helper").promptOutputApiSps;
} catch {
  // The component will remain null of it is not available
}
function CombinedOutput({ docId, setFilledFields }) {
  const [combinedOutput, setCombinedOutput] = useState({});
  const [isOutputLoading, setIsOutputLoading] = useState(false);
  const {
    details,
    defaultLlmProfile,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    isSimplePromptStudio,
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
  }, [docId, singlePassExtractMode, isSinglePassExtractLoading]);

  const handleOutputApiRequest = async () => {
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/?tool_id=${details?.tool_id}&document_manager=${docId}&is_single_pass_extract=${singlePassExtractMode}`;
    if (isSimplePromptStudio) {
      url = promptOutputApiSps(details?.tool_id, null, docId);
    }
    const requestOptions = {
      method: "GET",
      url,
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

  if (isSimplePromptStudio && TableView) {
    return <TableView combinedOutput={combinedOutput} />;
  }

  return <JsonView combinedOutput={combinedOutput} />;
}

CombinedOutput.propTypes = {
  docId: PropTypes.string,
  setFilledFields: PropTypes.func,
};

export { CombinedOutput };
