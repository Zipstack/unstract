import { Col, Row, Typography } from "antd";
import PropTypes from "prop-types";

import { InputPlaceholder, OutputPlaceholder } from "../../../assets";
import "./InputOutput.css";
import { MarkdownRenderer } from "../markdown-renderer/MarkdownRenderer";

function InputOutput({ input, output }) {
  if (!input && !output) {
    return (
      <div className="wf-input-output-layout wf-input-output-placeholder wf-input-output-box">
        <Row className="display-flex-center">
          <Col>
            <div style={{ padding: "5px" }}>
              <InputPlaceholder />
            </div>
          </Col>
          <Col>
            <div style={{ padding: "5px" }}>
              <OutputPlaceholder />
            </div>
          </Col>
        </Row>
        <Typography.Text className="wf-steps-empty-state">
          Select a workflow stage to see input and output data here.
        </Typography.Text>
      </div>
    );
  }

  return (
    <div className="wf-input-output-layout">
      <Row className="wf-input-output-layout">
        <Col span={12} className="wf-input-output-layout">
          <div className="wf-input-output-md wf-input-output-md-right wf-input-output-box">
            <MarkdownRenderer markdownText={input} />
          </div>
        </Col>
        <Col span={12} className="wf-input-output-layout">
          <div className="wf-input-output-md wf-input-output-md-left wf-input-output-box">
            <MarkdownRenderer markdownText={output} />
          </div>
        </Col>
      </Row>
    </div>
  );
}

InputOutput.propTypes = {
  input: PropTypes.string,
  output: PropTypes.string,
};

export { InputOutput };
