import PropTypes from "prop-types";
import { useDrag, useDrop } from "react-dnd";
import { useRef } from "react";

import { NotesCard } from "../notes-card/NotesCard";
import { PromptCard } from "./PromptCard";
import { promptType } from "../../../helpers/GetStaticData";
import { useCustomToolStore } from "../../../store/custom-tool-store";

function PromptDnd({
  item,
  index,
  handleChangePromptCard,
  handleDelete,
  moveItem,
  outputs,
  enforceTypeList,
  setUpdatedPromptsCopy,
  promptRunStatus,
}) {
  const ref = useRef(null);
  const { isSimplePromptStudio } = useCustomToolStore();

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
}

PromptDnd.propTypes = {
  item: PropTypes.object.isRequired,
  index: PropTypes.number.isRequired,
  handleChangePromptCard: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  moveItem: PropTypes.func.isRequired,
  outputs: PropTypes.object.isRequired,
  enforceTypeList: PropTypes.array.isRequired,
  setUpdatedPromptsCopy: PropTypes.func.isRequired,
  promptRunStatus: PropTypes.object.isRequired,
};

export { PromptDnd };
