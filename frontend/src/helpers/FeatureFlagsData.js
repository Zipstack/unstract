import axios from "axios";

async function makeApiCall(url, data, csrfToken) {
  const headers = {
    "X-CSRFToken": csrfToken,
  };

  try {
    const response = await axios.post(url, data, { headers });
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

  const response = await makeApiCall(url, data, csrfToken);
  return response?.flag_status ?? false;
}

export async function listFlags(orgId, csrfToken, namespace = "default") {
  const url = `/api/v1/unstract/${orgId}/flags/`;
  const data = {
    namespace: namespace ?? null,
  };

  const response = await makeApiCall(url, data, csrfToken);
  return response.feature_flags.flags ?? {};
}
