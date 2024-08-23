import PropTypes from "prop-types";

import { ApiDeployment } from "../components/deployments/api-deployment/ApiDeployment";
import { Pipelines } from "../components/pipelines-or-deployments/pipelines/Pipelines";

function DeploymentsPage({ type }) {
  if (type === "api") {
    return <ApiDeployment type="api" />;
  } else {
    return <Pipelines type={type} />;
  }
}

DeploymentsPage.propTypes = {
  type: PropTypes.string.isRequired,
};

export { DeploymentsPage };
