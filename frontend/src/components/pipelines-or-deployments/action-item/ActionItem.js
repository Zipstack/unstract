import { Space, Typography } from "antd";
const actionItem = ({ text, icon, action }) => {
  return (
    <Space direction="horizontal" className="action-items" onClick={action}>
      <div>{icon}</div>
      <div>
        <Typography.Text>{text}</Typography.Text>
      </div>
    </Space>
  );
};

export default actionItem;
