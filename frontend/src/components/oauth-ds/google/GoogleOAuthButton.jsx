import { Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { GoogleLoginButton } from "react-social-login-buttons";

import "./GoogleOAuthButton.css";

const GoogleOAuthButton = ({
  handleOAuth,
  status,
  buttonText = "Authenticate with Google",
}) => {
  const [text, setText] = useState("");
  useEffect(() => {
    if (status === "success") {
      setText("Authenticated");
      return;
    }
    setText(buttonText);
  }, [status, buttonText]);

  return (
    <div className="google-oauth-layout">
      <GoogleLoginButton onClick={handleOAuth}>
        <Typography.Text>{text}</Typography.Text>
      </GoogleLoginButton>
    </div>
  );
};

GoogleOAuthButton.propTypes = {
  handleOAuth: PropTypes.func.isRequired,
  status: PropTypes.string,
  buttonText: PropTypes.string,
};

export default GoogleOAuthButton;
