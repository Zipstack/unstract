import { Button } from "antd";
import { Row, Col } from "antd";

import { getBaseUrl } from "../../helpers/GetStaticData";
import "./Login.css";
import { UnstractBlackLogo } from "../../assets";
import { ProductContentLayout } from "./ProductContentLayout";

let LoginForm = null;
try {
  LoginForm = require("../../plugins/login-form/LoginForm").LoginForm;
} catch {
  // The components will remain null of it is not available
}

function Login() {
  const baseUrl = getBaseUrl();
  const newURL = baseUrl + "/api/v1/login";
  const handleLogin = () => {
    window.location.href = newURL;
  };

  return (
    <div className="login-main">
      <Row>
        {LoginForm ? (
          <LoginForm handleLogin={handleLogin} />
        ) : (
          <>
            <Col xs={24} md={12} className="login-left-section">
              <div className="button-wraper">
                <UnstractBlackLogo className="logo" />
                <div>
                  <Button
                    className="login-button button-margin"
                    onClick={handleLogin}
                  >
                    Login
                  </Button>
                </div>
              </div>
            </Col>
            <Col xs={24} md={12} className="login-right-section">
              <ProductContentLayout />
            </Col>
          </>
        )}
      </Row>
    </div>
  );
}

export { Login };
