import { Button, Col, Row } from "antd";

import { getBaseUrl } from "../../helpers/GetStaticData";
import "./Login.css";
import { UnstractBlackLogo } from "../../assets";
import { ProductContentLayout } from "./ProductContentLayout";

let LoginForm = null;
try {
  const mod = await import("../../plugins/login-form/LoginForm");
  LoginForm = mod.LoginForm;
} catch {
  // Plugin not available (OSS version)
}

function Login() {
  const baseUrl = getBaseUrl();
  const selectedProduct = localStorage.getItem("selectedProduct");
  const isValidProduct =
    selectedProduct && ["unstract", "llm-whisperer"].includes(selectedProduct);

  const handleLogin = () => {
    const loginUrl = isValidProduct
      ? `${baseUrl}/api/v1/login?selectedProduct=${selectedProduct}`
      : `${baseUrl}/api/v1/login`;
    window.location.href = loginUrl;
  };

  const handleSignup = () => {
    const signupUrl = isValidProduct
      ? `${baseUrl}/api/v1/signup?selectedProduct=${selectedProduct}`
      : `${baseUrl}/api/v1/signup`;
    window.location.href = signupUrl;
  };

  return (
    <div className="login-main">
      <Row>
        {LoginForm ? (
          <LoginForm handleLogin={handleLogin} handleSignup={handleSignup} />
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
