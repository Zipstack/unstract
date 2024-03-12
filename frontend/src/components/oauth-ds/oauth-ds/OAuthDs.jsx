import { Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { O_AUTH_PROVIDERS, getBaseUrl } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useAlertStore } from "../../../store/alert-store";
import GoogleOAuthButton from "../google/GoogleOAuthButton.jsx";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
function OAuthDs({ oAuthProvider, setCacheKey, setStatus }) {
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const [oauthStatus, setOAuthStatus] = useState(
    localStorage.getItem("oauth-status")
  );

  useEffect(() => {
    const handleStorageChange = () => {
      const updatedOAuthStatus = localStorage.getItem("oauth-status");
      setOAuthStatus(updatedOAuthStatus);
      setStatus(updatedOAuthStatus);
    };

    window.addEventListener("storage", handleStorageChange);

    return () => {
      window.removeEventListener("storage", handleStorageChange);
      localStorage.removeItem("oauth-status");
      setOAuthStatus("");
    };
  }, []);

  const handleOAuth = async () => {
    try {
      const requestOptions = {
        method: "GET",
        url: `/api/v1/oauth/cache-key/${oAuthProvider}`,
      };

      const response = await axiosPrivate(requestOptions);
      const cacheKey = response?.data?.cache_key;
      const encodedCacheKey = encodeURIComponent(cacheKey);
      setCacheKey(cacheKey);

      const baseUrl = getBaseUrl();

      const url = `${baseUrl}/api/v1/oauth/login/${oAuthProvider}?oauth-key=${encodedCacheKey}`;

      // Open in a new window
      window.open(
        url,
        "_blank",
        "toolbar=yes,scrollbars=yes,resizable=yes,top=200,left=500,width=500,height=600"
      );
    } catch (err) {
      setAlertDetails(handleException(err));
    }
  };

  if (O_AUTH_PROVIDERS["GOOGLE"] === oAuthProvider) {
    return (
      <>
        <GoogleOAuthButton handleOAuth={handleOAuth} status={oauthStatus} />
      </>
    );
  }

  return <Typography>Provider not available.</Typography>;
}

OAuthDs.propTypes = {
  oAuthProvider: PropTypes.string,
  setCacheKey: PropTypes.func,
  setStatus: PropTypes.func,
};

export { OAuthDs };
