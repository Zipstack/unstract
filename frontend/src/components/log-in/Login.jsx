import { Button } from "@/components/ui/shims/antd-button";
import { Col, Row } from "@/components/ui/shims/antd-layout";

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

/*
 * The products a `selectedProduct` may name, from whoever defines them.
 *
 * This used to be a literal pair here, which made this file the place a
 * deployment's product set was decided — and it is not: the plugin owns
 * that set, and already does for the product chooser and the session
 * check. A product the plugin knows but this literal did not was silently
 * dropped from the login URL, so the backend never learned which product
 * the visitor came for and the identity provider showed them the wrong
 * branding.
 *
 * Falls back to the pair this file always had, which is what an OSS-only
 * build (no plugins) gets and is exactly its previous behaviour.
 */
const FALLBACK_PRODUCTS = ["unstract", "llm-whisperer"];
let knownProducts = FALLBACK_PRODUCTS;
try {
  const helpers = await import("../../plugins/helpers/common");
  const names = Object.values(helpers.PRODUCT_NAMES ?? {});
  if (names.length) {
    knownProducts = names;
  }
} catch {
  // Plugin not available (OSS version): keep the fallback.
}

function Login() {
  const baseUrl = getBaseUrl();
  const selectedProduct = localStorage.getItem("selectedProduct");
  const isValidProduct =
    selectedProduct && knownProducts.includes(selectedProduct);

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
