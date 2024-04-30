import { Col, Row } from "antd";
import PropTypes from "prop-types";

import { Prompt } from "../prompt/Prompt";
import { Steps } from "../steps/Steps";
import "./WorkflowExecutionMain.css";
import { InputOutput } from "../input-output/InputOutput";

function WorkflowExecutionMain({
  setSteps,
  activeToolId,
  inputMd,
  outputMd,
  sourceMsg,
  destinationMsg,
}) {
  return (
    <div className="wf-exec-main-layout">
      <Row className="wf-exec-main-layout">
        <Col span={8} className="wf-exec-main-layout">
          <div className="wf-exec-main-col-1">
            <div className="wf-exec-main-prompt">
              <Prompt />
            </div>
            <div className="wf-exec-main-steps">
              <Steps
                setSteps={setSteps}
                activeToolId={activeToolId}
                sourceMsg={sourceMsg}
                destinationMsg={destinationMsg}
              />
            </div>
          </div>
        </Col>
        <Col span={16} className="wf-exec-main-layout">
          <div className="wf-exec-main-col-2">
            <InputOutput input={inputMd} output={outputMd} />
          </div>
        </Col>
      </Row>
    </div>
  );
}

WorkflowExecutionMain.propTypes = {
  setSteps: PropTypes.func,
  activeToolId: PropTypes.string,
  inputMd: PropTypes.string,
  outputMd: PropTypes.string,
  sourceMsg: PropTypes.string,
  destinationMsg: PropTypes.string,
};

export { WorkflowExecutionMain };
