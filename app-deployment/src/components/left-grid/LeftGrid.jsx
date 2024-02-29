import { Tabs } from "antd";

import { CannedQuestions } from "../canned-questions/CannedQuestions.jsx";
import { ChatContext } from "../chat-context/ChatContext.jsx";
import { GridLayout } from "../grid-layout/GridLayout.jsx";
import "./LeftGrid.css";

function LeftGrid() {
  const items = [
    {
      key: "1",
      label: "Chats",
      children: <ChatContext />,
    },
    {
      key: "2",
      label: "Canned Questions",
      children: <CannedQuestions />,
    },
  ];

  return (
    <GridLayout>
      <div className="grid-main-layout">
        <Tabs defaultActiveKey="1" items={items} />
      </div>
    </GridLayout>
  );
}

LeftGrid.propTypes = {};

export { LeftGrid };
