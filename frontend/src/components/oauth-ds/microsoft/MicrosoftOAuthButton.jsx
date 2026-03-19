import { Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { MicrosoftLoginButton } from "react-social-login-buttons";

import "./MicrosoftOAuthButton.css";

const MicrosoftOAuthButton = ({
  handleOAuth,
  status,
  buttonText = "Authenticate with Microsoft",
  disabled = false,
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
    <div className="microsoft-oauth-layout">
      <MicrosoftLoginButton onClick={handleOAuth} disabled={disabled}>
        <Typography.Text>{text}</Typography.Text>
      </MicrosoftLoginButton>
    </div>
  );
};

MicrosoftOAuthButton.propTypes = {
  handleOAuth: PropTypes.func.isRequired,
  status: PropTypes.string,
  buttonText: PropTypes.string,
  disabled: PropTypes.bool,
};

export default MicrosoftOAuthButton;
