import axios from "axios";

async function makeApiCall(method, url, data, csrfToken) {
  const headers = {
    "X-CSRFToken": csrfToken,
  };

  try {
    const response = await axios({ method, url, data, headers });
    return response?.data;
  } catch (error) {
    console.error(`Error making API call to ${url}: ${error}`);
    return null;
  }
}

export async function evaluateFeatureFlag(orgId, csrfToken, featureFlag) {
  const url = `/api/v1/unstract/${orgId}/evaluate/`;
  const data = {
    flag_key: featureFlag,
  };

  const response = await makeApiCall("POST", url, data, csrfToken);
  return response?.flag_status ?? false;
}

export async function listFlags(orgId, csrfToken, namespace = "default") {
  const url = `/api/v1/unstract/${orgId}/flags/?namespace=${namespace}`;

  const response = await makeApiCall("GET", url, null, csrfToken);
  return response.feature_flags.flags ?? {};
}
