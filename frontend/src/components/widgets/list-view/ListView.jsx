import { Flex, Image, List, Popconfirm, Typography } from "antd";
import PropTypes from "prop-types";
import "./ListView.css";
import {
  DeleteOutlined,
  EditOutlined,
  QuestionCircleOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";

function ListView({
  listOfTools,
  handleEdit,
  handleDelete,
  titleProp,
  descriptionProp,
  iconProp,
  idProp,
  centered,
  isClickable = true,
}) {
  const navigate = useNavigate();
  const handleDeleteClick = (event, tool) => {
    event.stopPropagation(); // Stop propagation to prevent list item click
    handleDelete(event, tool);
  };

  const renderTitle = (record) => {
    if (iconProp && record[iconProp].length > 4) {
      return (
        <Flex gap={20} align="center">
          <div className="cover-img">
            <Image
              src={record[iconProp]}
              preview={false}
              className="fit-cover"
            />
          </div>
          <Typography.Text>{record[titleProp]}</Typography.Text>
        </Flex>
      );
    } else if (iconProp) {
      return `${record[iconProp]} ${record[titleProp]}`;
    } else {
      return record[titleProp];
    }
  };

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
            onClick={() => {
              isClickable && navigate(`${item[idProp]}`);
            }}
            className={`cur-pointer ${centered ? "centered" : ""}`}
            extra={
              <div onClick={(event) => event.stopPropagation()} role="none">
                <EditOutlined
                  key={`${item.id}-edit`}
                  onClick={(event) => handleEdit(event, item)}
                  className="action-icon-buttons"
                />
                <Popconfirm
                  key={`${item.id}-delete`}
                  title="Delete the tool"
                  description="Are you sure to delete this tool?"
                  okText="Yes"
                  cancelText="No"
                  icon={<QuestionCircleOutlined />}
                  onConfirm={(event) => {
                    handleDeleteClick(event, item);
                  }}
                >
                  <Typography.Text>
                    <DeleteOutlined className="action-icon-buttons" />
                  </Typography.Text>
                </Popconfirm>
              </div>
            }
          >
            <List.Item.Meta
              title={renderTitle(item)}
              description={item[descriptionProp]}
            />
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
  titleProp: PropTypes.string.isRequired,
  descriptionProp: PropTypes.string,
  iconProp: PropTypes.string,
  idProp: PropTypes.string.isRequired,
  centered: PropTypes.bool,
  isClickable: PropTypes.bool,
};

export { ListView };
