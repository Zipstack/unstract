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
    logEventsId: sessionData?.logEventsId,
    allOrganization: sessionData?.allOrganization,
    isPlatformAdmin: sessionData?.isPlatformAdmin,
    loginOnboardingMessage: sessionData?.loginOnboardingMessage,
    promptOnboardingMessage: sessionData?.promptOnboardingMessage,
    flags: sessionData?.flags,
    role: sessionData?.role,
    provider: sessionData?.provider,
  };
}

export { getSessionData };
