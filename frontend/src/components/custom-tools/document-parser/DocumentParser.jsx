import PropTypes from "prop-types";
import { useEffect, useRef, useState } from "react";

import "./DocumentParser.css";
import { promptType } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { EmptyState } from "../../widgets/empty-state/EmptyState";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { PromptCardWrapper } from "../prompt-card/PromptCardWrapper";
import { usePromptOutputStore } from "../../../store/prompt-output-store";

let promptPatchApiSps;
let SpsPromptsEmptyState;
try {
  promptPatchApiSps =
    require("../../../plugins/simple-prompt-studio/helper").promptPatchApiSps;
  SpsPromptsEmptyState =
    require("../../../plugins/simple-prompt-studio/SpsPromptsEmptyState").SpsPromptsEmptyState;
} catch {
  // The component will remain null of it is not available
}

function DocumentParser({
  addPromptInstance,
  scrollToBottom,
  setScrollToBottom,
}) {
  const [enforceTypeList, setEnforceTypeList] = useState([]);
  const [updatedPromptsCopy, setUpdatedPromptsCopy] = useState({});
  const [isChallenge, setIsChallenge] = useState(false);
  const bottomRef = useRef(null);
  const {
    details,
    isSimplePromptStudio,
    updateCustomTool,
    getDropdownItems,
    isChallengeEnabled,
  } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const { promptOutputs } = usePromptOutputStore();

  useEffect(() => {
    const outputTypeData = getDropdownItems("output_type") || {};
    const dropdownList1 = Object.keys(outputTypeData)?.map((item) => {
      return { value: outputTypeData[item] };
    });
    setEnforceTypeList(dropdownList1);
    setIsChallenge(isChallengeEnabled);

    return () => {
      // Set the prompts with updated changes when the component is unmounted
      const modifiedDetails = { ...details };
      const modifiedPrompts = [...(modifiedDetails?.prompts || [])]?.map(
        (item) => {
          const itemPromptId = item?.prompt_id;
          if (itemPromptId && updatedPromptsCopy[itemPromptId]) {
            return updatedPromptsCopy[itemPromptId];
          }
          return item;
        }
      );
      modifiedDetails["prompts"] = modifiedPrompts;
      updateCustomTool({ details: modifiedDetails });
    };
  }, []);

  useEffect(() => {
    setIsChallenge(details.enable_challenge);
  }, [details.enable_challenge]);

  useEffect(() => {
    if (scrollToBottom) {
      // Scroll down to the lastest chat.
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      setScrollToBottom(false);
    }
  }, [scrollToBottom]);

  const promptUrl = (urlPath) => {
    return `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt/${urlPath}`;
  };

  const handleChangePromptCard = async (name, value, promptId) => {
    const promptsAndNotes = details?.prompts || [];

    if (name === "prompt_key") {
      // Return if the prompt or the prompt key is empty
      if (!value) {
        return;
      }
    }

    const index = promptsAndNotes.findIndex(
      (item) => item?.prompt_id === promptId
    );

    if (index === -1) {
      setAlertDetails({
        type: "error",
        content: "Prompt not found",
      });
      return;
    }

    const promptDetails = promptsAndNotes[index];

    const body = {
      [`${name}`]: value,
    };

    let url = promptUrl(promptDetails?.prompt_id + "/");
    if (isSimplePromptStudio) {
      url = promptPatchApiSps(promptDetails?.prompt_id);
    }
    const requestOptions = {
      method: "PATCH",
      url,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    return axiosPrivate(requestOptions)
      .then((res) => res)
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to update"));
      });
  };

  const handleDelete = (promptId) => {
    let url = promptUrl(promptId + "/");
    if (isSimplePromptStudio) {
      url = promptPatchApiSps(promptId);
    }
    const requestOptions = {
      method: "DELETE",
      url,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    axiosPrivate(requestOptions)
      .then(() => {
        const modifiedDetails = { ...details };
        const modifiedPrompts = [...(modifiedDetails?.prompts || [])].filter(
          (item) => item?.prompt_id !== promptId
        );
        modifiedDetails["prompts"] = modifiedPrompts;
        updateCustomTool({ details: modifiedDetails });
        setAlertDetails({
          type: "success",
          content: "Deleted successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to delete"));
      });
  };

  const getPromptOutputs = (promptId) => {
    const keys = Object.keys(promptOutputs || {});

    if (!keys?.length) return {};

    const outputs = {};
    keys.forEach((key) => {
      if (key.startsWith(promptId)) {
        outputs[key] = promptOutputs[key];
      }
    });
    return outputs;
  };

  if (!details?.prompts?.length) {
    if (isSimplePromptStudio && SpsPromptsEmptyState) {
      return <SpsPromptsEmptyState />;
    }

    return (
      <EmptyState
        text="Add prompt or a note and choose the LLM profile"
        btnText="Add Prompt"
        handleClick={() => addPromptInstance(promptType.prompt)}
      />
    );
  }

  return (
    <div className="doc-parser-layout">
      {details?.prompts?.map((item) => {
        return (
          <div key={item.prompt_id}>
            <div className="doc-parser-pad-top" />
            <PromptCardWrapper
              item={item}
              handleChangePromptCard={handleChangePromptCard}
              handleDelete={handleDelete}
              outputs={getPromptOutputs(item?.prompt_id)}
              enforceTypeList={enforceTypeList}
              setUpdatedPromptsCopy={setUpdatedPromptsCopy}
              coverageCountData={item?.coverage}
              isChallenge={isChallenge}
            />
            <div ref={bottomRef} className="doc-parser-pad-bottom" />
          </div>
        );
      })}
    </div>
  );
}

DocumentParser.propTypes = {
  addPromptInstance: PropTypes.func.isRequired,
  scrollToBottom: PropTypes.bool.isRequired,
  setScrollToBottom: PropTypes.func.isRequired,
};

export { DocumentParser };
