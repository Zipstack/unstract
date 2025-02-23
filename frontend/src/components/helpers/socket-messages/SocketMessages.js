import {
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
  useMemo,
} from "react";
import throttle from "lodash/throttle";

import { SocketContext } from "../../../helpers/SocketContext";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useSocketLogsStore } from "../../../store/socket-logs-store";
import { useSocketMessagesStore } from "../../../store/socket-messages-store";
import { useSessionStore } from "../../../store/session-store";
import { useUsageStore } from "../../../store/usage-store";

const THROTTLE_DELAY = 2000;

function SocketMessages() {
  const [logId, setLogId] = useState("");
  const {
    pushStagedMessage,
    updateMessage,
    stagedMessages,
    pointer,
    setPointer,
  } = useSocketMessagesStore();
  const { pushLogMessages } = useSocketLogsStore();
  const { sessionDetails } = useSessionStore();
  const socket = useContext(SocketContext);
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const { setLLMTokenUsage } = useUsageStore();

  // Buffer to hold logs between throttle intervals
  const logBufferRef = useRef([]);

  useEffect(() => {
    setLogId(sessionDetails?.logEventsId || "");
  }, [sessionDetails]);

  // Throttled function that batches log messages
  const logMessagesThrottledUpdate = useMemo(
    () =>
      throttle((logsBatch) => {
        if (!logsBatch.length) return;
        pushLogMessages(logsBatch);
        logBufferRef.current = [];
      }, THROTTLE_DELAY),
    [pushLogMessages]
  );

  // Clean up throttling on unmount
  useEffect(() => {
    return () => logMessagesThrottledUpdate.cancel();
  }, [logMessagesThrottledUpdate]);

  // Batches log messages, then invokes the throttled function
  const handleLogMessages = useCallback(
    (msg) => {
      logBufferRef.current = [...logBufferRef.current, msg];
      logMessagesThrottledUpdate(logBufferRef.current);
    },
    [logMessagesThrottledUpdate]
  );

  // Socket message handler
  const onMessage = useCallback(
    (data) => {
      try {
        let msg = data.data;

        if (typeof msg === "string" || msg instanceof Uint8Array) {
          msg =
            typeof msg === "string"
              ? JSON.parse(msg)
              : JSON.parse(new TextDecoder().decode(msg));
        }

        if (
          (msg?.type === "LOG" || msg?.type === "COST") &&
          msg?.service !== "prompt"
        ) {
          msg.message = msg?.log;
          handleLogMessages(msg);
        } else if (msg?.type === "UPDATE") {
          pushStagedMessage(msg);
        } else if (msg?.type === "LOG" && msg?.service === "prompt") {
          handleLogMessages(msg);
        }

        if (msg?.type === "LOG" && msg?.service === "usage") {
          const remainingTokens =
            msg?.max_token_count_set - msg?.added_token_count;
          setLLMTokenUsage(Math.max(remainingTokens, 0));
        }
      } catch (err) {
        setAlertDetails(
          handleException(err, "Failed to process socket message")
        );
      }
    },
    [handleLogMessages, pushStagedMessage]
  );

  // Subscribe/unsubscribe to the socket channel
  useEffect(() => {
    if (!logId) return;

    const channel = `logs:${logId}`;
    socket.on(channel, onMessage);
    return () => {
      socket.off(channel, onMessage);
    };
  }, [socket, logId, onMessage]);

  // Process staged messages sequentially
  useEffect(() => {
    if (pointer > stagedMessages?.length - 1) return;

    const stagedMsg = stagedMessages[pointer];
    const timer = setTimeout(() => {
      updateMessage(stagedMsg);
      setPointer(pointer + 1);
    }, 0);

    return () => clearTimeout(timer);
  }, [stagedMessages, pointer, setPointer, updateMessage]);

  return null;
}

export { SocketMessages };
