import { Dropdown, List, Typography } from "antd";
import PropTypes from "prop-types";

import "./ListView.css";
import { DeleteOutlined, EditOutlined, MoreOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";

function ListView({ listOfTools, handleEdit, handleDelete }) {
  const navigate = useNavigate();
  return (
    <List
      size="large"
      dataSource={listOfTools}
      style={{ marginInline: "4px" }}
      className="list-view-wrapper"
      renderItem={(item) => {
        return (
          <List.Item
            key={item?.id}
            onClick={() => navigate(`${item?.tool_id}`)}
            className="cur-pointer"
            extra={
              <Dropdown
                menu={{
                  items: [
                    {
                      label: "Edit",
                      key: "edit",
                      icon: <EditOutlined />,
                      onClick: (event) => handleEdit(event, item?.id),
                    },
                    {
                      label: "Delete",
                      key: "delete",
                      icon: <DeleteOutlined />,
                      onClick: (event) => handleDelete(event, item?.id),
                    },
                  ],
                }}
                trigger={["click"]}
                placement="bottomRight"
                onClick={(evt) => evt.stopPropagation()}
              >
                <MoreOutlined />
              </Dropdown>
            }
          >
            <div className="list-view-item">
              <Typography.Text strong ellipsis>
                {item?.tool_name}
              </Typography.Text>
              <Typography.Text type="secondary" ellipsis>
                {item?.description || "No description provided"}
              </Typography.Text>
            </div>
          </List.Item>
        );
      }}
    />
  );
}

ListView.propTypes = {
  listOfTools: PropTypes.array.isRequired,
  handleEdit: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
};

export { ListView };
