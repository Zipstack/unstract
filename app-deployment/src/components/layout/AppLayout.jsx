import { Col, Row, Spin } from "antd";
import { useEffect, useState } from "react";

import useSessionValid from "../../hooks/useSessionValid.js";
import { useSessionStore } from "../../store/session-store.js";
import { Chat } from "../chat-layout/Chat.jsx";
import { LeftGrid } from "../left-grid/LeftGrid.jsx";
import { PdfViewer } from "../pdf-viewer/PdfViewer.jsx";
import { Topbar } from "../topbar/Topbar.jsx";
import "./AppLayout.css";

function AppLayout() {
  const { sessionDetails } = useSessionStore();
  const checkSessionValidity = useSessionValid();
  const [isMounted, setIsMounted] = useState(false);
  useEffect(() => {
    const verifySession = async () => {
      try {
        await checkSessionValidity();
      } finally {
        setIsMounted(true);
      }
    };

    if (!sessionDetails?.isLoggedIn) {
      verifySession();
    } else {
      setIsMounted(true);
    }

    return () => setIsMounted(true);
  }, [checkSessionValidity, sessionDetails]);
  if (isMounted) {
    return (
      <div className="base-layout">
        <Topbar />
        {/* <Titlebar /> */}
        <Row className="layout-row" gutter={14}>
          <Col span={4}>
            <LeftGrid />
          </Col>
          <Col span={10}>
            <Chat />
          </Col>
          <Col span={10}>
            <PdfViewer />
          </Col>
        </Row>
      </div>
    );
  }
  return (
    <div className="app-loading">
      <Spin size="large" />
    </div>
  );
}

export { AppLayout };
