import { Typography, Button } from "antd";
import { Row, Col } from "antd";

import logo from "../../assets/UnstractLogoBlack.svg";
import loginRightBanner from "../../assets/login-right-panel.svg";
import { getBaseUrl } from "../../helpers/GetStaticData";
import "./Login.css";
import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useSelectedProductStore } from "../../plugins/llm-whisperer/store/select-product-store";

let LoginForm = null;
let PRODUCT_NAMES = {};
try {
  LoginForm = require("../../plugins/login-form/LoginForm").LoginForm;
  PRODUCT_NAMES = require("../../plugins/llm-whisperer/helper").PRODUCT_NAMES;
} catch {
  // The components will remain null of it is not available
}

function Login() {
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const selectedProduct = queryParams.get("selectedProduct");
  const baseUrl = getBaseUrl();
  const newURL = baseUrl + "/api/v1/login";
  const handleLogin = () => {
    window.location.href = newURL;
  };
  const { setSelectedProduct } = useSelectedProductStore();

  useEffect(() => {
    if (
      selectedProduct &&
      Object.values(PRODUCT_NAMES).includes(selectedProduct)
    ) {
      setSelectedProduct(selectedProduct);
    }
  }, [selectedProduct]);

  return (
    <div className="login-main">
      <Row>
        <Col xs={24} md={12} className="login-left-section">
          <div className="button-wraper">
            <img src={logo} alt="Logo" className="logo" />
            {LoginForm && <LoginForm handleLogin={handleLogin} />}
            {!LoginForm && (
              <div>
                <Button
                  className="login-button button-margin"
                  onClick={handleLogin}
                >
                  Login
                </Button>
              </div>
            )}
          </div>
        </Col>
        <Col xs={24} md={12} className="login-right-section">
          <div className="right-section-text-wrapper">
            <div className="right-title-cover">
              <Typography.Title className="right-section-title">
                UNLOCK VALUE FROM UNSTRUCTURED DATA.
              </Typography.Title>
            </div>
            <div className="right-subtitle-cover">
              <Typography align="center" className="right-subtitle">
                Unstract is a no-code LLM platform that lets you automate even
                the most complex workflows involving unstructured data, saving
                you time, money, and automation headaches.
              </Typography>
            </div>
            <div>
              <img
                src={loginRightBanner}
                alt="login background"
                className="login-background"
              />
            </div>
          </div>
        </Col>
      </Row>
    </div>
  );
}

export { Login };
