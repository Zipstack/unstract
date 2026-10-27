import axios from "axios";

// Raw axios on purpose: flags are listed during session bootstrap
// (useSessionValid), before useAxiosPrivate's logout handling applies. CSRF
// comes from the global interceptor in App.jsx.
async function makeApiCall(method, url, data) {
  try {
    const response = await axios({ method, url, data });
    return response?.data;
  } catch (error) {
    console.error(`Error making API call to ${url}: ${error}`);
    return null;
  }
}

export async function evaluateFeatureFlag(orgId, featureFlag) {
  const url = `/api/v1/unstract/${orgId}/evaluate/`;
  const data = {
    flag_key: featureFlag,
  };

  const response = await makeApiCall("POST", url, data);
  return response?.flag_status ?? false;
}

export async function listFlags(orgId) {
  const url = `/api/v1/unstract/${orgId}/flags/`;

  const response = await makeApiCall("GET", url, null);
  return response.feature_flags.flags ?? {};
}
