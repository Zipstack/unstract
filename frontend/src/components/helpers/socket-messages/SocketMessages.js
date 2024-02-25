import PropTypes from "prop-types";
import { useContext, useEffect } from "react";

import { handleException } from "../../../helpers/GetStaticData";
import { SocketContext } from "../../../helpers/SocketContext";
import { useAlertStore } from "../../../store/alert-store";
import { useSocketLogsStore } from "../../../store/socket-logs-store";
import { useSocketMessagesStore } from "../../../store/socket-messages-store";
function SocketMessages({ logId }) {
  const {
    pushStagedMessage,
    updateMessage,
    stagedMessages,
    pointer,
    setPointer,
  } = useSocketMessagesStore();
  const { pushLogMessages } = useSocketLogsStore();
  const socket = useContext(SocketContext);
  const { setAlertDetails } = useAlertStore();

  const onMessage = (data) => {
    try {
      const msg = JSON.parse(new TextDecoder().decode(data.data));
      if (msg?.type === "LOG" || msg?.type === "COST") {
        msg.message = msg?.log;
        pushLogMessages(msg);
      }
      if (msg?.type === "UPDATE") {
        pushStagedMessage(msg);
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
