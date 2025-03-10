import { useState, useRef, useCallback, useEffect } from "react";

import { LogsHeader } from "./LogsHeader";
import "./DisplayLogsAndNotifications.css";
import { LogsAndNotificationsTable } from "./LogsAndNotificationsTable";
import { useAxiosPrivate } from "../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../store/session-store";
import { useSocketLogsStore } from "../../store/socket-logs-store";
import { useAlertStore } from "../../store/alert-store";
import { useExceptionHandler } from "../../hooks/useExceptionHandler";

export function DisplayLogsAndNotifications() {
  const [contentHeight, setContentHeight] = useState(0);
  const [errorCount, setErrorCount] = useState(0);
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { pushLogMessages } = useSocketLogsStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const draggingRef = useRef(false);
  const startYRef = useRef(0);
  const startHeightRef = useRef(0);
  const containerRef = useRef(null);

  useEffect(() => {
    getLogs();
    const parent = containerRef.current?.parentElement;
    if (parent) {
      if (window.getComputedStyle(parent).position === "static") {
        parent.style.position = "relative";
      }
    }
  }, []);

  const getLogs = async () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/logs/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data?.data || [];
        pushLogMessages(data, false);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  const getParentHeight = useCallback(() => {
    const parent = containerRef.current?.parentElement;
    return parent ? parent.getBoundingClientRect().height : 0;
  }, []);

  // Minimizes the logs (height = 0).
  const minimize = useCallback(() => {
    setContentHeight(0);
  }, []);

  // Sets the logs height to "semi" (30% of parent minus 40).
  const semiExpand = useCallback(() => {
    const parentHeight = getParentHeight();
    const height = 0.3 * parentHeight;
    const semiHeight = height - 40;
    const newHeight = Math.max(0, semiHeight);
    setContentHeight(newHeight);
  }, [getParentHeight]);

  // Sets the logs height to "full" (parent minus 40).
  const fullExpand = useCallback(() => {
    const parentHeight = getParentHeight();
    const newHeight = Math.max(0, parentHeight - 40);
    setContentHeight(newHeight);
  }, [getParentHeight]);

  const handleToggleExpand = useCallback(() => {
    const parentHeight = getParentHeight();
    const height = 0.3 * parentHeight;
    const semiHeight = height - 40;
    const fullHeight = parentHeight - 40;

    const isCurrentlyFull = contentHeight >= fullHeight - 1;

    if (isCurrentlyFull) {
      semiExpand();
    } else if (contentHeight < semiHeight) {
      semiExpand();
    } else {
      fullExpand();
    }
  }, [contentHeight, getParentHeight, semiExpand, fullExpand]);

  const onMouseDown = useCallback(
    (e) => {
      draggingRef.current = true;
      startYRef.current = e.clientY;
      startHeightRef.current = contentHeight;
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    },
    [contentHeight]
  );

  const onMouseMove = useCallback(
    (e) => {
      if (!draggingRef.current) return;
      const diff = startYRef.current - e.clientY;
      const newHeight = startHeightRef.current + diff;
      const parentHeight = getParentHeight();
      const maxHeight = parentHeight - 40;
      setContentHeight(Math.max(0, Math.min(maxHeight, newHeight)));
    },
    [getParentHeight]
  );

  const onMouseUp = useCallback(() => {
    draggingRef.current = false;
    document.removeEventListener("mousemove", onMouseMove);
    document.removeEventListener("mouseup", onMouseUp);
  }, [onMouseMove]);

  const parentHeight = getParentHeight();
  const fullHeight = parentHeight - 40;
  const isFull = contentHeight >= fullHeight - 1; // a small tolerance

  return (
    <div
      ref={containerRef}
      className="logs-container"
      style={{ height: contentHeight + 40 }}
    >
      <div className="logs-handle" onMouseDown={onMouseDown}>
        <LogsHeader
          isMinimized={contentHeight === 0}
          isFull={isFull}
          errorCount={errorCount}
          onToggleExpand={handleToggleExpand}
          onMinimize={minimize}
        />
      </div>
      <div className="logs-content">
        <LogsAndNotificationsTable
          errorCount={errorCount}
          setErrorCount={setErrorCount}
          isMinimized={contentHeight === 0}
        />
      </div>
    </div>
  );
}
