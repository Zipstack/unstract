import { Button, Typography } from "antd";

import logo from "../../assets/UnstractLogoBlack.svg";
import loginBG from "../../assets/login-page-bg.svg";
import { getBaseUrl } from "../../helpers/GetStaticData";
import "./Login.css";

function Login() {
  const baseUrl = getBaseUrl();
  const newURL = baseUrl + "/api/v1/login";
  const handleLogin = () => {
    window.location.href = newURL;
  };

  return (
    <div className="login-main">
      <div className="login-left-section">
        <div className="button-wraper">
          <img src={logo} alt="Logo" className="logo" />
          <div className="text-wrapper">
            <Typography.Title level={3}>Sign Up</Typography.Title>
            <Typography>
              Try Unstract free for 14 days. No credit card required.
            </Typography>
          </div>
          <Button className="login-button" onClick={handleLogin}>
            Create Your free account
          </Button>
          <div className="signin-text-wrapper">
            <Typography>
              Already have an account? <a href={newURL}>Sign in</a>
            </Typography>
          </div>
        </div>
      </div>
      <div className="login-right-section">
        <div className="right-section-text-wrapper">
          <div className="right-title-cover">
            <Typography.Title align="center">
              UNLOCK VALUE FROM UNSTRUCTURED DATA.
            </Typography.Title>
          </div>
          <div className="right-subtitle-cover">
            <Typography align="center" className="right-subtitle">
              Unstract is a no-code LLM platform that lets you automate even the
              most complex workflows involving unstructured data, saving you
              time, money, and automation headaches.
            </Typography>
          </div>
        </div>
        <img
          src={loginBG}
          alt="login background"
          className="login-background"
        />
      </div>
    </div>
  );
}

export { Login };
