import PropTypes from "prop-types";
import { useDrag, useDrop } from "react-dnd";
import { memo, useRef } from "react";

import { NotesCard } from "../notes-card/NotesCard";
import { PromptCard } from "./PromptCard";
import { promptType } from "../../../helpers/GetStaticData";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import usePromptRun from "../../../hooks/usePromptRun";
import { usePromptRunStatusStore } from "../../../store/prompt-run-status-store";

const PromptDnd = memo(function PromptDnd({
  item,
  index,
  handleChangePromptCard,
  handleDelete,
  moveItem,
  outputs,
  enforceTypeList,
  setUpdatedPromptsCopy,
}) {
  const ref = useRef(null);
  const { isSimplePromptStudio } = useCustomToolStore();
  const { handlePromptRunRequest } = usePromptRun();
  const promptRunStatus = usePromptRunStatusStore(
    (state) => state?.promptRunStatus?.[item?.prompt_id] || {}
  );

  const [, drop] = useDrop({
    accept: "PROMPT_CARD",
    drop: (draggedItem) => {
      moveItem(/* Start Index*/ draggedItem?.index, /* Drop Index*/ index);
    },
  });

  const [, drag] = useDrag({
    type: "PROMPT_CARD",
    item: { index },
    collect: (monitor) => ({
      isDragging: monitor.isDragging(),
    }),
  });

  drag(drop(ref));

  return (
    <div ref={ref}>
      {(item.prompt_type === promptType.prompt || isSimplePromptStudio) && (
        <PromptCard
          promptDetails={item}
          handleChangePromptCard={handleChangePromptCard}
          handleDelete={handleDelete}
          updatePlaceHolder="Enter Prompt"
          promptOutputs={outputs}
          enforceTypeList={enforceTypeList}
          setUpdatedPromptsCopy={setUpdatedPromptsCopy}
          handlePromptRunRequest={handlePromptRunRequest}
          promptRunStatus={promptRunStatus}
        />
      )}
      {item.prompt_type === promptType.notes && (
        <NotesCard
          promptDetails={item}
          handleChangePromptCard={handleChangePromptCard}
          handleDelete={handleDelete}
          updatePlaceHolder="Enter Notes"
          setUpdatedPromptsCopy={setUpdatedPromptsCopy}
        />
      )}
    </div>
  );
});

PromptDnd.displayName = "PromptDnd";

PromptDnd.propTypes = {
  item: PropTypes.object.isRequired,
  index: PropTypes.number.isRequired,
  handleChangePromptCard: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  moveItem: PropTypes.func.isRequired,
  outputs: PropTypes.object.isRequired,
  enforceTypeList: PropTypes.array.isRequired,
  setUpdatedPromptsCopy: PropTypes.func.isRequired,
};

export { PromptDnd };
