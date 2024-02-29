import { MessageOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Card, Typography } from "antd";
import { useEffect } from "react";

import { useAxiosPrivate } from "../../hooks/useAxiosPrivate";
import { useChatStore } from "../../store/chat-store.js";
import { useSessionStore } from "../../store/session-store.js";

import "./ChatContext.css";

function ChatContext() {
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { chatHistory, setChatHistory, setChatTranscript, setCurrentContext } =
    useChatStore();
  useEffect(() => {
    const fetchData = async () => {
      try {
        // TODO: app_deployment should be removed from query param and
        // use the session in the backend as discussed.
        const requestOptions = {
          method: "GET",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/chats/?app_deployment=${sessionDetails.appId}`,
        };
        const res = await axiosPrivate(requestOptions);
        setChatHistory(res.data);
      } catch (err) {
        console.error("Error fetching data:", err);
      }
    };
    fetchData();
  }, [sessionDetails]);
  const fetchTranscriptData = async (context) => {
    try {
      const requestOptions = {
        method: "GET",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/chats/${context.id}/`,
      };
      const res = await axiosPrivate(requestOptions);
      setChatTranscript(res.data);
    } catch (err) {
      console.error("Error fetching data:", err);
    }
  };
  const createNewChat = () => {
    setChatTranscript([]);
    setCurrentContext({});
  };
  const changeContext = (context) => {
    setCurrentContext(context);
    fetchTranscriptData(context);
  };
  // const editChatContext = async (context) => {
  //   const body = {
  //     label: "string",
  //     app_deployment: "3e0b2d4a-b029-4713-9303-176a2bfec217",
  //   };
  //   requestOptions = {
  //     method: "PUT",
  //     url: `/api/v1/unstract/${sessionDetails?.orgId}/canned_question/${currentQuestion.id}/`,
  //     data: body,
  //   };
  //   const res = await axiosPrivate(requestOptions);
  //   setCurrentContext(context);
  //   fetchTranscriptData(context);
  // };
  return (
    <div>
      <Button onClick={() => createNewChat()} className="add-question-button">
        <PlusOutlined />
      </Button>
      <div className="chat-history-box">
        {chatHistory.map((item, index) => (
          <Card
            key={item.id}
            className="chat-context"
            hoverable
            onClick={() => changeContext(item)}
          >
            <MessageOutlined />
            <Typography.Text className="context-text">
              {item.label}
            </Typography.Text>
            {/* <DeleteOutlined
              className="context-edit-icon"
              onClick={() => deleteChatHistory(item)}
            /> */}
            {/* <EditOutlined
            className="context-edit-icon"
            onClick={() => editChatContext(item)}
          /> */}
          </Card>
        ))}
      </div>
    </div>
  );
}

ChatContext.propTypes = {};

export { ChatContext };
