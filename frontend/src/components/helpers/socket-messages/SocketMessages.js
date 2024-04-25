import PropTypes from "prop-types";
import { useContext, useEffect } from "react";

import { SocketContext } from "../../../helpers/SocketContext";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useSocketLogsStore } from "../../../store/socket-logs-store";
import { useSocketMessagesStore } from "../../../store/socket-messages-store";
import { useSocketCustomToolStore } from "../../../store/socket-custom-tool";
import { useUsageStore } from "../../../store/usage-store";
function SocketMessages({ logId }) {
  const {
    pushStagedMessage,
    updateMessage,
    stagedMessages,
    pointer,
    setPointer,
  } = useSocketMessagesStore();
  const { pushLogMessages } = useSocketLogsStore();
  const { updateCusToolMessages } = useSocketCustomToolStore();
  const socket = useContext(SocketContext);
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const { setLLMTokenUsage } = useUsageStore();

  const onMessage = (data) => {
    try {
      const msg = JSON.parse(new TextDecoder().decode(data.data));
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
        updateCusToolMessages(msg);
      }
      if (msg?.type === "LOG" && msg?.service === "usage") {
        setLLMTokenUsage(msg?.added_token_count);
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

SocketMessages.propTypes = {
  logId: PropTypes.string,
};

export { SocketMessages };
