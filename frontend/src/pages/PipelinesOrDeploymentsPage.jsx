import PropTypes from "prop-types";

import { PipelinesOrDeployments } from "../components/pipelines-or-deployments/pipelines-or-deployments/PipelinesOrDeployments";

function PipelinesOrDeploymentsPage({ type }) {
  return <PipelinesOrDeployments type={type} />;
}

PipelinesOrDeploymentsPage.propTypes = {
  type: PropTypes.string.isRequired,
};
export { PipelinesOrDeploymentsPage };
