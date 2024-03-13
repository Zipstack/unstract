import { Card, Col, Row, Typography } from "antd";
import PropTypes from "prop-types";
import { useDrag } from "react-dnd";

import "./ToolInfoCard.css";
import { ToolIcon } from "../tool-icon/ToolIcon";

function ToolInfoCard({ toolInfo }) {
  const [, ref] = useDrag({
    type: "STEP",
    item: { function_name: toolInfo?.function_name },
  });

  return (
    <Card className="toolinfo-card" ref={ref}>
      <Row>
        <Col span={4}>
          <ToolIcon iconSrc={toolInfo?.icon} showBorder={true} />
        </Col>
        <Col span={20}>
          <div className="tool-info-header">
            <div className="tool-info-title">
              <Typography.Text strong>{toolInfo?.name}</Typography.Text>
            </div>
            <Typography
              type="secondary"
              className="tool-info-typo-sec"
              style={{ color: "#00A6ED", marginTop: "-2px" }}
            >
              by Zipstack Inc
            </Typography>
            <Typography.Paragraph
              type="secondary"
              className="tool-info-typo-sec"
              ellipsis={{ rows: 2, expandable: false }}
              style={{ marginTop: "2px" }}
            >
              {toolInfo?.description}
            </Typography.Paragraph>
          </div>
        </Col>
      </Row>
    </Card>
  );
}

ToolInfoCard.propTypes = {
  toolInfo: PropTypes.object.isRequired,
};

export { ToolInfoCard };
