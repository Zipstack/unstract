import { SendOutlined } from "@ant-design/icons";
import { Space } from "antd";
import { useEffect, useState } from "react";

import { useAxiosPrivate } from "../../hooks/useAxiosPrivate";
import { useChatStore } from "../../store/chat-store.js";
import { useSessionStore } from "../../store/session-store.js";
import { ChatCard } from "../chat-card/ChatCard.jsx";
import { GridLayout } from "../grid-layout/GridLayout.jsx";
import "./Chat.css";

function Chat() {
  const [message, setMessage] = useState("");
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const {
    setDefaultChatDetails,
    updateChatHistory,
    chatTranscript,
    currentContext,
    setCurrentContext,
    updateChatTranscript,
  } = useChatStore();

  useEffect(() => {
    return () => {
      setDefaultChatDetails();
    };
  }, []);

  const sendOrUpdateMessage = async (message, id) => {
    const messageBody = {
      message: message,
    };
    const header = {
      "X-CSRFToken": sessionDetails?.csrfToken,
      "Content-Type": "application/json",
    };
    const messageRequestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/chats/${id}/`,
      headers: header,
      data: messageBody,
    };
    const resTranscript = await axiosPrivate(messageRequestOptions);
    resTranscript.data.forEach((element) => {
      updateChatTranscript({
        id: element.id,
        role: element.role,
        message: element.message,
      });
    });
  };

  const sendMessage = async (e) => {
    e.preventDefault();
    const header = {
      "X-CSRFToken": sessionDetails?.csrfToken,
      "Content-Type": "application/json",
    };

    const body = {
      label: message.slice(0, 15),
      app_deployment: sessionDetails?.appId,
    };

    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/chats/`,
      headers: header,
      data: body,
    };
    if (!currentContext.id) {
      const res = await axiosPrivate(requestOptions);
      setCurrentContext(res.data);
      updateChatHistory({
        id: res.data.id,
        label: message.slice(0, 15),
      });
      sendOrUpdateMessage(message, res.data.id);
    } else {
      sendOrUpdateMessage(message, currentContext.id);
    }

    setMessage("");
  };

  return (
    <GridLayout>
      <div className="grid-main-layout">
        <div className="chat-messages">
          {chatTranscript.map((item, index) => (
            <ChatCard
              key={item.id}
              content={item.message}
              chatTitle={
                item.role === "USER" ? sessionDetails.name : "Assistant"
              }
            />
          ))}
        </div>
        <div className="chat-input-box">
          <form onSubmit={sendMessage}>
            <div className="flex items-center justify-between">
              <Space.Compact>
                <input
                  type="text"
                  placeholder="Write a message"
                  name="message"
                  required
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                />
                <button type="submit">
                  <SendOutlined />
                </button>
              </Space.Compact>
            </div>
          </form>
        </div>
      </div>
    </GridLayout>
  );
}

export { Chat };
