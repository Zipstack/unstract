import { useContext, useEffect, useRef, useState, useCallback } from "react";
import throttle from "lodash/throttle";
import { SocketContext } from "../../../helpers/SocketContext";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useSocketLogsStore } from "../../../store/socket-logs-store";
import { useSocketMessagesStore } from "../../../store/socket-messages-store";
import { useSocketCustomToolStore } from "../../../store/socket-custom-tool";
import { useSessionStore } from "../../../store/session-store";
import { useUsageStore } from "../../../store/usage-store";

const THROTTLE_DELAY = 2000; // 2 seconds

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
  const { updateCusToolMessages } = useSocketCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const socket = useContext(SocketContext);
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const { setLLMTokenUsage } = useUsageStore();

  // Buffer to hold the logs between throttle intervals
  const psLogs = useRef([]);
  const wfLogs = useRef([]);

  useEffect(() => {
    setLogId(sessionDetails?.logEventsId || "");
  }, [sessionDetails]);

  // Throttled function for PS logs
  const psLogsThrottledUpdate = useRef(
    throttle((psLogMessages) => {
      updateCusToolMessages(psLogMessages);
      psLogs.current = [];
    }, THROTTLE_DELAY)
  ).current;

  // Throttled function for WF logs
  const wfLogsThrottledUpdate = useRef(
    throttle((wfLogMessages) => {
      pushLogMessages(wfLogMessages);
      wfLogs.current = [];
    }, THROTTLE_DELAY)
  ).current;

  // Clean up throttling functions on unmount
  useEffect(() => {
    return () => {
      psLogsThrottledUpdate.cancel();
      wfLogsThrottledUpdate.cancel();
    };
  }, [psLogsThrottledUpdate, wfLogsThrottledUpdate]);

  const handlePsLogs = useCallback(
    (msg) => {
      psLogs.current = [...psLogs.current, msg];
      psLogsThrottledUpdate(psLogs.current);
    },
    [psLogsThrottledUpdate]
  );

  const handleWfLogs = useCallback(
    (msg) => {
      wfLogs.current = [...wfLogs.current, msg];
      wfLogsThrottledUpdate(wfLogs.current);
    },
    [wfLogsThrottledUpdate]
  );

  // Handle incoming socket messages
  const onMessage = (data) => {
    try {
      let msg = data.data;
      // Attempt to decode data as JSON if it's in encoded state
      if (typeof msg === "string" || msg instanceof Uint8Array) {
        if (typeof msg === "string") {
          msg = JSON.parse(msg);
        } else {
          msg = JSON.parse(new TextDecoder().decode(msg));
        }
      }

      if (
        (msg?.type === "LOG" || msg?.type === "COST") &&
        msg?.service !== "prompt"
      ) {
        msg.message = msg?.log;
        handleWfLogs(msg);
      } else if (msg?.type === "UPDATE") {
        pushStagedMessage(msg);
      } else if (msg?.type === "LOG" && msg?.service === "prompt") {
        handlePsLogs(msg);
      } else if (msg?.type === "LOG" && msg?.service === "usage") {
        const remainingTokens =
          msg?.max_token_count_set - msg?.added_token_count;
        setLLMTokenUsage(Math.max(remainingTokens, 0));
      }
    } catch (err) {
      setAlertDetails(handleException(err, "Failed to process socket message"));
    }
  };

  useEffect(() => {
    if (!logId) return;

    const logMessageChannel = `logs:${logId}`;
    socket.on(logMessageChannel, onMessage);

    return () => {
      // unsubscribe to the channel to stop listening the socket messages for the logId
      socket.off(logMessageChannel);
    };
  }, [logId]);

  useEffect(() => {
    if (pointer > stagedMessages?.length - 1) return;

    const stagedMsg = stagedMessages[pointer];
    const timer = setTimeout(() => {
      updateMessage(stagedMsg);
      setPointer(pointer + 1);
    }, 0);

    return () => clearTimeout(timer); // Cleanup timer on unmount
  }, [stagedMessages, pointer]);
}

export { SocketMessages };
