import { Avatar, Card, Typography } from "antd";
import PropTypes from "prop-types";
import "./ChatCard.css";

const { Text, Paragraph } = Typography;

const CardTitle = ({ chatTitle }) => (
  <div>
    <Avatar
      style={{ backgroundColor: "#f56a00", verticalAlign: "middle" }}
      size="small"
      gap={5}
    >
      {chatTitle[0]}
    </Avatar>
    <Text className="chat-user-name">{chatTitle}</Text>
  </div>
);

const ChatCard = ({ chatTitle, content }) => (
  <Card
    title={<CardTitle chatTitle={chatTitle} />}
    headStyle={{ backgroundColor: "#EBEFF3" }}
    className="chat-card"
  >
    <div className="chat-response-content">
      <Paragraph>{content}</Paragraph>
    </div>
  </Card>
);

CardTitle.propTypes = {
  chatTitle: PropTypes.string.isRequired,
};

ChatCard.propTypes = {
  content: PropTypes.string.isRequired,
  chatTitle: PropTypes.string.isRequired,
};

export { ChatCard };
