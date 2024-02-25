import { ExperimentOutlined } from "@ant-design/icons";
import { Tag, Tooltip } from "antd";
import PropTypes from "prop-types";

import "./EvalMetricTag.css";

/*
  e.g.
    {
        "release": "stable",
        "id": "correctness",
        "type": "quality",
        "name": "Correctness",
        "value": "4.72 / 5",
        "status": "pass|failed|disabled"
    }
 */
function EvalMetricTag({ metric }) {
  if (!metric?.name) {
    return <></>;
  }

  return (
    // overlayStyle is required for adding line breaks in tooltip text
    <Tooltip overlayStyle={{ whiteSpace: "pre-line" }} title={metric?.feedback}>
      <Tag className="eval-metric-tag">
        <Tag
          className={
            "eval-metric-tag-part eval-metric-tag-name eval-metric-tag-begin eval-metric-tag-type-" +
            metric?.type
          }
        >
          {metric?.release === "stable" ? (
            ""
          ) : (
            <>
              <Tooltip
                title={
                  metric?.release[0].toUpperCase() +
                  metric?.release.slice(1) +
                  " release"
                }
              >
                <ExperimentOutlined />
              </Tooltip>
              &nbsp;
            </>
          )}
          {metric?.name}
        </Tag>
        <Tag
          className={
            "eval-metric-tag-part eval-metric-tag-end eval-metric-tag-value eval-metric-tag-value-" +
            (metric.status ? metric.status : "disabled")
          }
        >
          {metric?.status !== "disabled" ? metric?.value : "--"}
        </Tag>
      </Tag>
    </Tooltip>
  );
}

EvalMetricTag.propTypes = {
  metric: PropTypes.object.isRequired,
};

export { EvalMetricTag };
