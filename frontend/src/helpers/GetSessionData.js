function getSessionData(sessionData) {
  if (!sessionData || sessionData?.isLoggedIn === false) {
    return {
      isLoggedIn: false,
    };
  }

  return {
    id: sessionData?.id,
    email: sessionData?.email,
    name: sessionData?.name,
    display_name: sessionData?.display_name,
    family_name: sessionData?.family_name,
    picture: sessionData?.picture,
    orgId: sessionData?.orgId,
    orgName: sessionData?.orgName,
    csrfToken: sessionData?.csrfToken,
    zCode: sessionData?.zCode,
    isLoggedIn: true,
    isAdmin: sessionData.isAdmin,
    adapters: sessionData?.adapters,
    remainingTrialDays: sessionData?.remainingTrialDays,
  };
}

export { getSessionData };
