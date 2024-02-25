import { Typography } from "antd";
import PropTypes from "prop-types";
import { useDrop } from "react-dnd";

import { ListOfWfStepsPlaceholder } from "../../../assets";
import { CardsList } from "../cards-list/CardsList.jsx";

import "./StepCard.css";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper.jsx";

const StepCard = ({ steps, activeTool, moveItem }) => {
  const [, drop] = useDrop({
    accept: "STEP",
    drop: (draggedItem, indexNew) => {
      if (
        (steps.length === 0 || draggedItem?.function_name) &&
        !draggedItem?.index
      ) {
        const index = steps.length;
        moveItem(draggedItem.index, index, draggedItem?.function_name);
      }
    },
  });

  return (
    <div ref={drop} className="wf-steps-container">
      {steps.length === 0 && (
        <div className="content-center-body-3 display-flex-center-h-and-v">
          <SpaceWrapper>
            <div>
              <ListOfWfStepsPlaceholder />
            </div>
            <div>
              <Typography.Text className="wf-steps-empty-state">
                Enter the prompt to generate the workflow <br />
                OR <br /> Drag tool and drop.
              </Typography.Text>
            </div>
          </SpaceWrapper>
        </div>
      )}
      <SpaceWrapper>
        {steps.map((step, index) => {
          return (
            <CardsList
              key={step.id}
              step={step}
              activeTool={activeTool}
              moveItem={moveItem}
              index={index}
            />
          );
        })}
      </SpaceWrapper>
    </div>
  );
};

StepCard.propTypes = {
  steps: PropTypes.array,
  activeTool: PropTypes.string.isRequired,
  moveItem: PropTypes.func.isRequired,
};

export { StepCard };
