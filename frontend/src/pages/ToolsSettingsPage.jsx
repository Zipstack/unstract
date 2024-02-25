import PropTypes from "prop-types";

import { ToolSettings } from "../components/tool-settings/tool-settings/ToolSettings";

function ToolsSettingsPage({ type }) {
  return <ToolSettings type={type} />;
}

ToolsSettingsPage.propTypes = {
  type: PropTypes.string.isRequired,
};

export { ToolsSettingsPage };
