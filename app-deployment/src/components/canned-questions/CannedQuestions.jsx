import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Card, Input, Modal, Typography } from "antd";
import { useEffect, useState } from "react";

import { useAxiosPrivate } from "../../hooks/useAxiosPrivate";
import { useChatStore } from "../../store/chat-store.js";
import { useSessionStore } from "../../store/session-store.js";
import { Placeholder } from "../placeholder/Placeholder.jsx";
import "./CannedQuestions.css";

const CannedQuestions = () => {
  const [addQuestionsModal, setAddQuestionsModal] = useState(false);
  const [deleteQuestionsModal, setDeleteQuestionsModal] = useState(false);
  const [question, setQuestion] = useState("");
  const [currentQuestion, setCurrentQuestion] = useState({});
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const [questions, setQuestions] = useState([]);
  const [message, setMessage] = useState("");
  const {
    updateChatHistory,
    currentContext,
    setCurrentContext,
    updateChatTranscript,
  } = useChatStore();
  useEffect(() => {
    const fetchData = async () => {
      try {
        const requestOptions = {
          method: "GET",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/canned_question/`,
        };
        const res = await axiosPrivate(requestOptions);
        setQuestions(res?.data);
      } catch (err) {
        console.error("Error fetching data:", err);
      }
    };

    fetchData();
  }, [sessionDetails]);

  const header = {
    "X-CSRFToken": sessionDetails?.csrfToken,
    "Content-Type": "multipart/form-data",
  };

  const handleQuestionSaveOrUpdate = async () => {
    try {
      if (!question.trim()) return;

      const body = {
        question: question,
        app_deployment: sessionDetails.appId,
      };

      let requestOptions = {
        method: "POST",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/canned_question/`,
        headers: header,
        data: body,
      };

      if (currentQuestion?.id) {
        body.is_active = true;

        requestOptions = {
          method: "PUT",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/canned_question/${currentQuestion.id}/`,
          headers: header,
          data: body,
        };
      }

      const res = await axiosPrivate(requestOptions);
      setQuestions((prevQuestions) => [
        ...prevQuestions,
        { id: res.id, question: question },
      ]);
      // Show success alert
      message.success("Question saved successfully!");
    } catch (err) {
      console.error("Error saving question:", err);
      // Show error alert
      message.error("Failed to save question. Please try again.");
    } finally {
      setQuestion("");
      setAddQuestionsModal(false);
    }
  };

  const deleteQuestionById = (idToDelete) => {
    setQuestions((prevQuestions) =>
      prevQuestions.filter((question) => question.id !== idToDelete)
    );
  };

  const deleteQuestion = async () => {
    try {
      const requestOptions = {
        method: "DELETE",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/canned_question/${currentQuestion.id}/`,
        headers: header,
      };
      await axiosPrivate(requestOptions);
      deleteQuestionById(currentQuestion.id);
      setDeleteQuestionsModal(false);
      // Show success alert
      message.success("Question deleted successfully!");
    } catch (err) {
      console.error("Error deleting question:", err);
      // Show error alert
      message.error("Failed to delete question. Please try again.");
    }
  };

  const cancelAddQuestion = () => {
    setCurrentQuestion({});
    setQuestion("");
    setAddQuestionsModal(false);
  };

  const cancelDeleteQuestion = () => {
    setDeleteQuestionsModal(false);
  };

  const editQuestion = (item) => {
    setQuestion(item.question);
    setAddQuestionsModal(true);
    setCurrentQuestion(item);
  };

  const deleteQuestionModal = (item) => {
    setQuestion(item.question);
    setCurrentQuestion(item);
    setDeleteQuestionsModal(true);
  };
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
    updateChatTranscript({
      id: resTranscript.data.id,
      message: message,
      created_by: sessionDetails.name,
    });
  };

  const sendMessage = async (item) => {
    const header = {
      "X-CSRFToken": sessionDetails?.csrfToken,
      "Content-Type": "application/json",
    };

    const body = {
      label: item.question.slice(0, 15),
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
        label: item.question.slice(0, 15),
      });
      sendOrUpdateMessage(item.question, res.data.id);
    } else {
      sendOrUpdateMessage(item.question, currentContext.id);
    }

    setMessage("");
  };
  return (
    <div>
      <Button
        onClick={() => setAddQuestionsModal(true)}
        className="add-question-button"
      >
        <PlusOutlined />
      </Button>
      {questions.length === 0 && (
        <Placeholder
          text="Create canned questions"
          subText="Please click on the add button and create."
        />
      )}
      {questions.map((item, index) => (
        <div key={item?.id}>
          <Card
            className="curated-qa-card"
            hoverable
            onClick={() => sendMessage(item)}
          >
            <Typography.Text strong>
              {`${index + 1}. ${item?.question}`}
            </Typography.Text>
            <DeleteOutlined
              className="context-edit-icon"
              onClick={() => deleteQuestionModal(item)}
            />
            <EditOutlined
              className="context-edit-icon"
              onClick={() => editQuestion(item)}
            />
          </Card>
        </div>
      ))}
      <Modal
        title={currentQuestion?.id ? "Update Question" : "Add Question"}
        open={addQuestionsModal}
        onOk={handleQuestionSaveOrUpdate}
        okText={currentQuestion?.id ? "Update" : "Save"}
        onCancel={cancelAddQuestion}
      >
        <Input.TextArea
          rows={4}
          placeholder="Enter the question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
      </Modal>
      <Modal
        title="Are you sure want to delete?"
        open={deleteQuestionsModal}
        onOk={deleteQuestion}
        okText="Delete"
        onCancel={cancelDeleteQuestion}
      >
        <Typography.Text strong>{question}</Typography.Text>
      </Modal>
    </div>
  );
};

export { CannedQuestions };
