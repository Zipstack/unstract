import { useContext, useEffect, useState } from "react";

import { SocketContext } from "../../../helpers/SocketContext";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useSocketLogsStore } from "../../../store/socket-logs-store";
import { useSocketMessagesStore } from "../../../store/socket-messages-store";
import { useSessionStore } from "../../../store/session-store";
import { useUsageStore } from "../../../store/usage-store";

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

  useEffect(() => {
    setLogId(sessionDetails?.logEventsId || "");
  }, [sessionDetails]);

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
        pushLogMessages(msg);
      }
      if (msg?.type === "UPDATE") {
        pushStagedMessage(msg);
      }
      if (msg?.type === "LOG" && msg?.service === "prompt") {
        pushLogMessages(msg);
      }
      if (msg?.type === "LOG" && msg?.service === "usage") {
        const remainingTokens =
          msg?.max_token_count_set - msg?.added_token_count;
        setLLMTokenUsage(Math.max(remainingTokens, 0));
      }
    } catch (err) {
      setAlertDetails(handleException(err, "Failed to process socket message"));
    }
  };

  useEffect(() => {
    if (!logId) {
      return;
    }
    const logMessageChannel = `logs:${logId}`;
    socket.on(logMessageChannel, onMessage);

    return () => {
      // unsubscribe to the channel to stop listening the socket messages for the logId
      socket.off(logMessageChannel);
    };
  }, [logId]);

  useEffect(() => {
    if (pointer > stagedMessages?.length - 1) {
      return;
    }

    const stagedMsg = stagedMessages[pointer];
    setTimeout(() => {
      updateMessage(stagedMsg);
      setPointer(pointer + 1);
    }, 0);
  }, [stagedMessages, pointer]);
}

export { SocketMessages };
