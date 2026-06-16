// All deployments report to a single PostHog project; tag events with
// their origin so they can be segmented. Non-prod envs are expected to
// disable PostHog via VITE_ENABLE_POSTHOG instead of being mapped here.
const DEPLOYMENT_BY_HOST = {
  "us-central.unstract.com": "us-prod",
  "eu-west.unstract.com": "eu-prod",
};

const getDeployment = () =>
  DEPLOYMENT_BY_HOST[window?.location?.hostname] || "self-hosted";

// PII (email, name) may only leave Unstract-managed SaaS deployments
const isSaasProdDeployment = () => getDeployment() !== "self-hosted";

export { getDeployment, isSaasProdDeployment };
