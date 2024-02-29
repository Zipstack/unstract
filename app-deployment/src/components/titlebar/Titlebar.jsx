import { Col, Row, Typography } from "antd";
import "./Titlebar.css";

function Titlebar() {
  return (
    <Row align="middle" className="title-layout">
      <Col span={12}>
        <div className="title-text">
          <Typography.Text className="title-text-typo" strong>
            Simple Chat
          </Typography.Text>
        </div>
      </Col>
    </Row>
  );
}

export { Titlebar };
