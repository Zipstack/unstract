import PropTypes from "prop-types";
import { useEffect, useRef, useState } from "react";
import { DndProvider } from "react-dnd";
import { HTML5Backend } from "react-dnd-html5-backend";

import "./DocumentParser.css";
import {
  promptStudioUpdateStatus,
  promptType,
} from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { EmptyState } from "../../widgets/empty-state/EmptyState";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { PromptDnd } from "../prompt-card/PrompDnd";
import { usePromptOutputStore } from "../../../store/prompt-output-store";

let promptPatchApiSps;
let promptReorderApiSps;
let SpsPromptsEmptyState;
try {
  promptPatchApiSps =
    require("../../../plugins/simple-prompt-studio/helper").promptPatchApiSps;
  promptReorderApiSps =
    require("../../../plugins/simple-prompt-studio/helper").promptReorderApiSps;
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
  const [updateStatus, setUpdateStatus] = useState({
    promptId: null,
    status: null,
  });
  const bottomRef = useRef(null);
  const { details, isSimplePromptStudio, updateCustomTool } =
    useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const { promptOutputs } = usePromptOutputStore();

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

  const handleChange = async (
    event,
    promptId,
    dropdownItem,
    isUpdateStatus = false,
    isPromptUpdate = false
  ) => {
    const promptsAndNotes = details?.prompts || [];
    let name = "";
    let value = "";
    if (dropdownItem?.length) {
      name = dropdownItem;
      value = event;
    } else {
      name = event.target.name;
      value = event.target.value;
    }

    if (name === "prompt_key") {
      // Return if the prompt or the prompt key is empty
      if (!value) {
        return;
      }
      if (!isValidJsonKey(value)) {
        handleUpdateStatus(
          isUpdateStatus,
          promptId,
          promptStudioUpdateStatus.validationError
        );
        return;
      }
    }

    function isValidJsonKey(key) {
      // Check for Prompt-Key
      // Allowed case, contains alphanumeric characters and underscores,
      // and doesn't start with a number.
      const regex = /^[a-zA-Z_][a-zA-Z0-9_]*$/;
      return regex.test(key);
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

    const modifiedDetails = { ...details };
    const modifiedPrompts = [...(modifiedDetails?.prompts || [])].map(
      (item) => {
        if (item?.prompt_id === promptId) {
          return {
            ...item,
            [name]: value, // Update the specific field instantly
          };
        }
        return item;
      }
    );
    modifiedDetails["prompts"] = modifiedPrompts;
    updateCustomTool({ details: modifiedDetails });

    handleUpdateStatus(
      isUpdateStatus,
      promptId,
      promptStudioUpdateStatus.isUpdating
    );

    return axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        const modifiedPrompts = [...(modifiedDetails?.prompts || [])].map(
          (item) => {
            if (item?.prompt_id === data?.prompt_id) {
              return data;
            }
            return item;
          }
        );
        modifiedDetails["prompts"] = modifiedPrompts;
        if (!isPromptUpdate) {
          updateCustomTool({ details: modifiedDetails });
        }
        handleUpdateStatus(
          isUpdateStatus,
          promptId,
          promptStudioUpdateStatus.done
        );
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to update"));
        updateCustomTool({ details });
        handleUpdateStatus(isUpdateStatus, promptId, null);
      })
      .finally(() => {
        if (isUpdateStatus) {
          setTimeout(() => {
            handleUpdateStatus(true, promptId, null);
          }, 3000);
        }
      });
  };

  const handleUpdateStatus = (isUpdate, promptId, value) => {
    if (!isUpdate) {
      return;
    }
    setUpdateStatus({
      promptId: promptId,
      status: value,
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

  const moveItem = (startIndex, endIndex) => {
    if (startIndex === endIndex) {
      return;
    }

    // Clone details and prompts
    const updatedPrompts = [...(details?.prompts || [])];

    // Move the item within the updated prompts array
    const [movedStep] = updatedPrompts.splice(startIndex, 1);
    updatedPrompts.splice(endIndex, 0, movedStep);

    // Modify the prompts order and update
    const modifiedDetails = { ...details, prompts: updatedPrompts };
    updateCustomTool({ details: modifiedDetails });

    // Prepare the body for the POST request
    const body = {
      start_sequence_number: details.prompts[startIndex]?.sequence_number,
      end_sequence_number: details.prompts[endIndex]?.sequence_number,
      prompt_id: details.prompts[startIndex]?.prompt_id,
    };

    let url = promptUrl("reorder/");
    if (isSimplePromptStudio) {
      url = promptReorderApiSps;
    }

    const requestOptions = {
      method: "POST",
      url,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data || [];

        // Update sequence numbers based on the response
        handleMoveItemSuccess(updatedPrompts, data);
      })
      .catch((err) => {
        // Revert to the original prompts on error
        updateCustomTool({
          details: { ...details, prompts: details?.prompts },
        });
        setAlertDetails(handleException(err, "Failed to re-order the prompts"));
      });
  };

  const handleMoveItemSuccess = (updatedPrompts, updatedSequenceNums) => {
    const updatedPromptSequenceNum = updatedPrompts.map((promptItem) => {
      const newPromptSeqNum = updatedSequenceNums.find(
        (item) => item?.id === promptItem?.prompt_id
      );
      if (newPromptSeqNum) {
        return {
          ...promptItem,
          sequence_number: newPromptSeqNum.sequence_number,
        };
      }
      return promptItem;
    });

    updateCustomTool({
      details: { ...details, prompts: updatedPromptSequenceNum },
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
      <DndProvider backend={HTML5Backend}>
        {details?.prompts.map((item, index) => {
          return (
            <div key={item.prompt_id}>
              <div className="doc-parser-pad-top" />
              <PromptDnd
                item={item}
                index={index}
                handleChange={handleChange}
                handleDelete={handleDelete}
                updateStatus={updateStatus}
                moveItem={moveItem}
                outputs={getPromptOutputs(item?.prompt_id)}
              />
              <div ref={bottomRef} className="doc-parser-pad-bottom" />
            </div>
          );
        })}
      </DndProvider>
    </div>
  );
}

DocumentParser.propTypes = {
  addPromptInstance: PropTypes.func.isRequired,
  scrollToBottom: PropTypes.bool.isRequired,
  setScrollToBottom: PropTypes.func.isRequired,
};

export { DocumentParser };
