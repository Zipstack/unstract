import { memo, useRef } from "react";
import PropTypes from "prop-types";
import { useDrag, useDrop } from "react-dnd";
import "./PromptsReorder.css";
import { Card, Typography } from "antd";

const ItemTypes = {
  PROMPT: "prompt",
};

function DraggablePrompt({ prompt, index, movePrompt, onDrop, cancelDrag }) {
  const ref = useRef(null);

  const [{ handlerId }, drop] = useDrop({
    accept: ItemTypes.PROMPT,
    hover: (item, monitor) => {
      if (!ref.current) return;

      const dragIndex = item.index;
      const hoverIndex = index;

      if (dragIndex === hoverIndex) return;

      // Move the item visually during drag
      movePrompt(dragIndex, hoverIndex);

      // Update the index for dragged item
      item.index = hoverIndex;
    },
    drop: () => {
      // Return the drop result
      return { index };
    },
    collect: (monitor) => ({
      handlerId: monitor.getHandlerId(),
    }),
  });

  const [{ isDragging }, drag] = useDrag({
    type: ItemTypes.PROMPT,
    item: { id: prompt.prompt_key, index, originalIndex: index },
    end: (item, monitor) => {
      if (!monitor.didDrop()) {
        // Drag was canceled, revert back
        cancelDrag();
        return;
      }
      const dropResult = monitor.getDropResult();
      if (dropResult) {
        const { originalIndex } = item;
        const toIndex = dropResult.index;
        onDrop(originalIndex, toIndex);
      }
    },
    collect: (monitor) => ({
      isDragging: monitor.isDragging(),
    }),
  });

  // Connect drag and drop refs
  drag(drop(ref));

  return (
    <Card
      ref={ref}
      className={`draggable-prompt prompt-card-bg-col1 ${
        isDragging ? "dragging" : ""
      }`}
      data-handler-id={handlerId}
    >
      <Typography.Text strong>{prompt?.prompt_key}</Typography.Text>
    </Card>
  );
}

DraggablePrompt.propTypes = {
  prompt: PropTypes.shape({
    prompt_id: PropTypes.string.isRequired,
    prompt_key: PropTypes.string.isRequired,
    sequence_number: PropTypes.number.isRequired,
  }).isRequired,
  index: PropTypes.number.isRequired,
  movePrompt: PropTypes.func.isRequired,
  onDrop: PropTypes.func.isRequired,
  cancelDrag: PropTypes.func.isRequired,
};

export default memo(DraggablePrompt);
