import { Col, Row, Typography } from "antd";

import "./LogsLabel.css";

function LogsLabel() {
  return (
    <div className="logs-label-layout">
      <Row style={{ padding: "0px 0px", flex: "none" }}>
        <Col style={{ borderRight: "1px solid #C9C9C9" }} span={2}>
          <Typography>Time</Typography>
        </Col>
        <Col style={{ borderRight: "1px solid #C9C9C9" }} span={2}>
          <Typography style={{ paddingLeft: "5px" }}>Stage</Typography>
        </Col>
        <Col style={{ borderRight: "1px solid #C9C9C9" }} span={2}>
          <Typography style={{ paddingLeft: "5px" }}>Step</Typography>
        </Col>
        <Col style={{ borderRight: "1px solid #C9C9C9" }} span={8}>
          <Typography style={{ paddingLeft: "5px" }}>Message</Typography>
        </Col>
        <Col style={{ borderRight: "1px solid #C9C9C9" }} span={2}>
          <Typography style={{ paddingLeft: "5px" }}>Cost Type</Typography>
        </Col>
        <Col style={{ borderRight: "1px solid #C9C9C9" }} span={2}>
          <Typography style={{ paddingLeft: "5px" }}>Cost Units</Typography>
        </Col>
        <Col style={{ borderRight: "1px solid #C9C9C9" }} span={2}>
          <Typography style={{ paddingLeft: "5px" }}>Cost Value</Typography>
        </Col>
        <Col style={{ borderRight: "1px solid #C9C9C9" }} span={2}>
          <Typography style={{ paddingLeft: "5px" }}>Iteration</Typography>
        </Col>
        <Col style={{}} span={2}>
          <Typography style={{ paddingLeft: "5px" }}>
            Iteration Total
          </Typography>
        </Col>
      </Row>
    </div>
  );
}

export { LogsLabel };
