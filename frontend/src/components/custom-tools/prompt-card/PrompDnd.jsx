import PropTypes from "prop-types";
import { useDrag, useDrop } from "react-dnd";
import { useRef } from "react";

import { NotesCard } from "../notes-card/NotesCard";
import { PromptCard } from "./PromptCard";
import { promptType } from "../../../helpers/GetStaticData";

function PromptDnd({
  item,
  index,
  handleChange,
  handleDelete,
  updateStatus,
  moveItem,
}) {
  const ref = useRef(null);

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
      {item.prompt_type === promptType.prompt && (
        <PromptCard
          promptDetails={item}
          handleChange={handleChange}
          handleDelete={handleDelete}
          updateStatus={updateStatus}
          updatePlaceHolder="Enter Prompt"
        />
      )}
      {item.prompt_type === promptType.notes && (
        <NotesCard
          details={item}
          handleChange={handleChange}
          handleDelete={handleDelete}
          updateStatus={updateStatus}
          updatePlaceHolder="Enter Notes"
        />
      )}
    </div>
  );
}

PromptDnd.propTypes = {
  item: PropTypes.object.isRequired,
  index: PropTypes.number.isRequired,
  handleChange: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  updateStatus: PropTypes.object.isRequired,
  moveItem: PropTypes.func.isRequired,
};

export { PromptDnd };
