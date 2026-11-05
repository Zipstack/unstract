import { getBaseUrl } from "./GetStaticData";

/*
 * The session response carries `org_switch_via_login: true` only when the
 * identity provider picked the organization at login (Unstract ID with its
 * organization claims on). An organization pick or switch then logs in again
 * naming the organization, so the provider records the choice for every
 * product. Any other session leaves the key out and keeps the local
 * `/organization/<id>/set`.
 */
const ORG_SWITCH_VIA_LOGIN = "org_switch_via_login";

function isOrgSwitchViaLogin(sessionData) {
  return sessionData?.[ORG_SWITCH_VIA_LOGIN] === true;
}

// `prompt=none`: the provider already has a session, so no screen is shown.
function getOrgSwitchLoginUrl(orgId) {
  const query = new URLSearchParams({ organization: orgId, prompt: "none" });
  return `${getBaseUrl()}/api/v1/login?${query.toString()}`;
}

function switchOrgViaLogin(orgId) {
  window.location.assign(getOrgSwitchLoginUrl(orgId));
}

export { getOrgSwitchLoginUrl, isOrgSwitchViaLogin, switchOrgViaLogin };
