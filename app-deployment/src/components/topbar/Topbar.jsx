import { LogoutOutlined } from "@ant-design/icons";
import { Col, Row, Typography } from "antd";
import { Logo } from "../../assets";
import useLogout from "../../hooks/useLogout.js";
import "./Topbar.css";

function Topbar() {
  const logout = useLogout();
  return (
    <Row align="middle" className="topbar-layout">
      <Col span={8}>
        <Logo className="topbar-logo" />
      </Col>
      <Col span={8}>
        <div className="topbar-text">
          <Typography.Text className="topbar-text-typo" strong>
            Simple Chat
          </Typography.Text>
        </div>
      </Col>
      <Col span={8}>
        <div className="topbar-logout">
          <LogoutOutlined onClick={logout} />
        </div>
      </Col>
    </Row>
  );
}

export { Topbar };
