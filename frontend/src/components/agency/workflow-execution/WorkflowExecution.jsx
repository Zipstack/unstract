import { Typography } from "antd";
import PropTypes from "prop-types";

import "./WorkflowExecution.css";
import { WorkflowExecutionMain } from "../workflow-execution-layout/WorkflowExecutionMain";

function WorkflowExecution({
  setSteps,
  activeToolId,
  inputMd,
  outputMd,
  sourceMsg,
  destinationMsg,
}) {
  return (
    <div className="wf-exec-layout">
      <div className="wf-exec-heading">
        <Typography.Text className="wf-exec-heading-typo" strong>
          Workflow
        </Typography.Text>
      </div>
      <div className="wf-exec-main">
        <WorkflowExecutionMain
          setSteps={setSteps}
          activeToolId={activeToolId}
          inputMd={inputMd}
          outputMd={outputMd}
          sourceMsg={sourceMsg}
          destinationMsg={destinationMsg}
        />
      </div>
    </div>
  );
}

WorkflowExecution.propTypes = {
  setSteps: PropTypes.func,
  activeToolId: PropTypes.string,
  inputMd: PropTypes.string,
  outputMd: PropTypes.string,
  sourceMsg: PropTypes.string,
  destinationMsg: PropTypes.string,
};

export { WorkflowExecution };
