import { CloseOutlined } from "@ant-design/icons";
import { Card, Col, Progress, Row, Typography } from "antd";
import PropTypes from "prop-types";
import { useRef } from "react";
import { useDrag, useDrop } from "react-dnd";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useToolSettingsStore } from "../../../store/tool-settings";
import { useWorkflowStore } from "../../../store/workflow-store";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";
import "../step-card/StepCard.css";
import "./CardList.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { ToolIcon } from "../tool-icon/ToolIcon";

const CardsList = ({ step, index, activeTool, moveItem }) => {
  const ref = useRef(null);
  const { sessionDetails } = useSessionStore();
  const { toolSettings, setToolSettings, cleanUpToolSettings } =
    useToolSettingsStore();
  const { deleteToolInstance } = useWorkflowStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const handleClick = (id, toolId, index) => {
    const toolSettings = { id, tool_id: toolId };
    setToolSettings(toolSettings);
  };
  const deleteStep = () => {
    const requestOptions = {
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/tool_instance/${toolSettings?.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    axiosPrivate(requestOptions)
      .then(() => {
        deleteToolInstance(toolSettings?.id);
        cleanUpToolSettings();
        setAlertDetails({
          type: "success",
          content: "Successfully deleted the tool instance",
        });
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to delete the tool instance"),
        );
      });
  };
  const [, drop] = useDrop({
    accept: "STEP",
    drop: (draggedItem) => {
      if (!index && !draggedItem?.function_name) {
        moveItem(draggedItem.index, index, draggedItem?.function_name);
      } else if (draggedItem.index !== index && !draggedItem?.function_name) {
        moveItem(draggedItem.index, index, draggedItem?.function_name);
      }
    },
    hover(item, monitor) {
      if (!ref.current) {
        return;
      }
      const dragIndex = item.index;
      const hoverIndex = index;
      // Don't replace items with themselves
      if (dragIndex === hoverIndex) {
        return;
      }
      // Determine rectangle on screen
      const hoverBoundingRect = ref.current?.getBoundingClientRect();
      // Get vertical middle
      const hoverMiddleY =
        (hoverBoundingRect.bottom - hoverBoundingRect.top) / 2;
      // Determine mouse position
      const clientOffset = monitor.getClientOffset();
      // Get pixels to the top
      const hoverClientY = clientOffset.y - hoverBoundingRect.top;
      // Only perform the move when the mouse has crossed half of the items height
      // When dragging downwards, only move when the cursor is below 50%
      // When dragging upwards, only move when the cursor is above 50%
      // Dragging downwards
      if (dragIndex < hoverIndex && hoverClientY < hoverMiddleY) {
        return;
      }
      // Dragging upwards
      if (dragIndex > hoverIndex && hoverClientY > hoverMiddleY) {
        return;
      }
      // Time to actually perform the action
      moveItem(dragIndex, hoverIndex, item?.function_name, true);
      // Note: we're mutating the monitor item here!
      // Generally it's better to avoid mutations,
      // but it's good here for the sake of performance
      // to avoid expensive index searches.
      item.index = hoverIndex;
    },
  });
  const [{ isDragging }, drag] = useDrag({
    type: "STEP",
    item: { index },
    collect: (monitor) => ({
      isDragging: monitor.isDragging(),
    }),
  });
  drag(drop(ref));
  return (
    <div ref={ref}>
      <Card
        className={
          "wf-step-card-layout card-body " +
          (toolSettings?.id === step?.id ? "tool-active" : "") +
          (isDragging ? "tool-dragging" : "")
        }
        onClick={() => handleClick(step?.id, step?.tool_id, index)}
      >
        <Row className="card-row">
          <Col span={5} className="card-col">
            <div className="card-col-div">
              <div className="display-flex-center">
                <Typography.Text className="card-typography">
                  STEP
                </Typography.Text>
              </div>
              <div className="wf-step-card-progress display-flex-center">
                <Progress type="circle" size="small" format={() => index + 1} />
              </div>
            </div>
          </Col>
          <Col
            span={19}
            className={`card-col-details ${
              activeTool === step?.id ? "active" : ""
            }`}
          >
            <div className="card-col-div">
              <Row align="middle">
                <Col span={2}>
                  <ToolIcon iconSrc={step?.icon} showBorder={false} />
                </Col>
                <Col span={21}>
                  <div className="step-name">
                    <Typography.Text
                      strong
                      ellipsis={{
                        tooltip: step?.name,
                      }}
                    >
                      {step?.name}
                    </Typography.Text>
                  </div>
                </Col>
                <Col span={1}>
                  {toolSettings?.id === step?.id && (
                    <div>
                      <ConfirmModal
                        handleConfirm={() => deleteStep()}
                        content="Want to delete this step"
                      >
                        <CloseOutlined />
                      </ConfirmModal>
                    </div>
                  )}
                </Col>
              </Row>
              <Typography.Text type="secondary" className="wf-step-card-status">
                Status: {step?.status}
              </Typography.Text>
            </div>
          </Col>
        </Row>
      </Card>
    </div>
  );
};

CardsList.propTypes = {
  step: PropTypes.object,
  index: PropTypes.number.isRequired,
  activeTool: PropTypes.string.isRequired,
  moveItem: PropTypes.func.isRequired,
};
export { CardsList };
