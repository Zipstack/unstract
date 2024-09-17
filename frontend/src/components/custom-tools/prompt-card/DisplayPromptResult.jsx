import { Typography } from "antd";
import PropTypes from "prop-types";
import { displayPromptResult } from "../../../helpers/GetStaticData";

function DisplayPromptResult({ output }) {
  return (
    <Typography.Paragraph className="prompt-card-display-output font-size-12">
      <div>{displayPromptResult(output, true)}</div>
    </Typography.Paragraph>
  );
}

DisplayPromptResult.propTypes = {
  output: PropTypes.any.isRequired,
};

export { DisplayPromptResult };
