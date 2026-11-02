import { useLocation } from "react-router-dom";
import { Button } from "@/components/ui/shims/antd-button";
import { Col, Row } from "@/components/ui/shims/antd-layout";

import { getBaseUrl } from "../../helpers/GetStaticData";
import {
  getPostLoginPath,
  LOGIN_FROM_STATE_KEY,
  REDIRECT_URL_PARAM,
} from "../../helpers/loginRedirect";
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
  const location = useLocation();
  const baseUrl = getBaseUrl();
  const selectedProduct = localStorage.getItem("selectedProduct");
  const isValidProduct =
    selectedProduct && ["unstract", "llm-whisperer"].includes(selectedProduct);

  const handleLogin = () => {
    const query = new URLSearchParams();
    if (isValidProduct) {
      query.set("selectedProduct", selectedProduct);
    }
    const postLoginPath = getPostLoginPath(
      location.state?.[LOGIN_FROM_STATE_KEY],
    );
    if (postLoginPath) {
      query.set(REDIRECT_URL_PARAM, postLoginPath);
    }
    const queryString = query.toString();
    window.location.href = queryString
      ? `${baseUrl}/api/v1/login?${queryString}`
      : `${baseUrl}/api/v1/login`;
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
