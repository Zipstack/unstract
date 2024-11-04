import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import PropTypes from "prop-types";
import { DndProvider } from "react-dnd";
import { HTML5Backend } from "react-dnd-html5-backend";
import { Space } from "antd";

import { useCustomToolStore } from "../../../store/custom-tool-store";
import DraggablePrompt from "./DraggablePrompt";
import "./PromptsReorder.css";
import { useSessionStore } from "../../../store/session-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

function PromptsReorder({ isOpen, updateReorderedStatus }) {
  const [listOfPrompts, setListOfPrompts] = useState([]);
  const previousListOfPrompts = useRef([]);
  const { details } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  useEffect(() => {
    if (!isOpen) {
      setListOfPrompts([]);
      return;
    }

    const prompts = details?.prompts || [];
    setListOfPrompts(
      prompts.map((prompt) => ({
        prompt_key: prompt.prompt_key,
        prompt_id: prompt.prompt_id,
        sequence_number: prompt.sequence_number,
      }))
    );
  }, [isOpen, details]);

  const movePrompt = useCallback(
    (fromIndex, toIndex) => {
      if (fromIndex === toIndex) return;

      // Store the previous state if not already stored
      if (!previousListOfPrompts.current?.length) {
        previousListOfPrompts.current = listOfPrompts;
      }

      setListOfPrompts((prevPrompts) => {
        const updatedPrompts = [...prevPrompts];
        const [movedItem] = updatedPrompts.splice(fromIndex, 1);
        updatedPrompts.splice(toIndex, 0, movedItem);
        return updatedPrompts;
      });
    },
    [listOfPrompts]
  );

  const handleDropSuccess = useCallback((data) => {
    const responseData = data || [];
    const sequenceMap = responseData.reduce((acc, item) => {
      acc[item.id] = item.sequence_number;
      return acc;
    }, {});

    setListOfPrompts((prevPrompts) => {
      const updatedPrompts = prevPrompts.map((prompt) => {
        const newSequenceNumber = sequenceMap[prompt.prompt_id];
        if (newSequenceNumber !== undefined) {
          return { ...prompt, sequence_number: newSequenceNumber };
        }
        return prompt;
      });

      // Sort the prompts based on new sequence numbers
      updatedPrompts.sort((a, b) => a.sequence_number - b.sequence_number);
      return updatedPrompts;
    });

    previousListOfPrompts.current = [];
  }, []);

  const handleDropError = useCallback(
    (err) => {
      // Revert back the listOfPrompts state
      setListOfPrompts(previousListOfPrompts.current);
      previousListOfPrompts.current = [];
      setAlertDetails(handleException(err, "Failed to reorder the prompts"));
    },
    [handleException, setAlertDetails]
  );

  const onDrop = useCallback(
    async (fromIndex, toIndex) => {
      if (fromIndex === toIndex) return;

      updateReorderedStatus(true);

      const body = {
        start_sequence_number:
          previousListOfPrompts.current[fromIndex]?.sequence_number,
        end_sequence_number:
          previousListOfPrompts.current[toIndex]?.sequence_number,
        prompt_id: previousListOfPrompts.current[fromIndex]?.prompt_id,
      };

      const requestOptions = {
        method: "POST",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt/reorder/`,
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
          "Content-Type": "application/json",
        },
        data: body,
      };

      try {
        const res = await axiosPrivate(requestOptions);
        handleDropSuccess(res?.data);
      } catch (err) {
        handleDropError(err);
      }
    },
    [
      axiosPrivate,
      handleDropError,
      handleDropSuccess,
      previousListOfPrompts,
      sessionDetails?.csrfToken,
      sessionDetails?.orgId,
      updateReorderedStatus,
    ]
  );

  const cancelDrag = useCallback(() => {
    if (previousListOfPrompts.current?.length) {
      setListOfPrompts(previousListOfPrompts.current);
      previousListOfPrompts.current = [];
    }
  }, []);

  const renderedPrompts = useMemo(
    () =>
      listOfPrompts.map((prompt, index) => (
        <DraggablePrompt
          key={prompt.prompt_key}
          index={index}
          prompt={prompt}
          movePrompt={movePrompt}
          onDrop={onDrop}
          cancelDrag={cancelDrag}
        />
      )),
    [listOfPrompts, movePrompt, onDrop, cancelDrag]
  );

  return (
    <DndProvider backend={HTML5Backend}>
      <Space direction="vertical" className="prompts-container">
        {renderedPrompts}
      </Space>
    </DndProvider>
  );
}

PromptsReorder.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  updateReorderedStatus: PropTypes.func.isRequired,
};

export { PromptsReorder };
