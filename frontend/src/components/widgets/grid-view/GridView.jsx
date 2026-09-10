import { CircleHelp, EllipsisVertical, Pencil, Trash2 } from "lucide-react";
import PropTypes from "prop-types";
import { useNavigate } from "react-router-dom";
import { Dropdown, Popconfirm } from "@/components/ui/shims/antd-overlays";
import { Card } from "@/components/ui/shims/antd-structure";
import { Typography } from "@/components/ui/shims/antd-typography";
import "./GridView.css";

function GridView({ listOfTools, handleEdit, handleDelete }) {
  const navigate = useNavigate();

  return (
    <div className="grid-view-wrapper">
      <div className="grid-view-list">
        {listOfTools.map((item) => {
          return (
            <Card
              key={item?.tool_id}
              title={item?.tool_name}
              style={{ width: "100%" }}
              size="small"
              type="inner"
              hoverable
              onClick={() => navigate(`${item?.tool_id}`)}
              extra={
                <Dropdown
                  menu={{
                    items: [
                      {
                        label: "Edit",
                        key: "edit",
                        icon: <Pencil />,
                        onClick: (event) => handleEdit(event, item?.tool_id),
                      },
                      {
                        label: (
                          <Popconfirm
                            title="Delete the tool"
                            description="Are you sure to delete this tool?"
                            okText="Yes"
                            cancelText="No"
                            icon={
                              <CircleHelp
                                style={{
                                  color: "#dc4446",
                                }}
                              />
                            }
                            onConfirm={(event) => {
                              handleDelete(event, item?.tool_id);
                            }}
                          >
                            <Typography.Text type="danger">
                              <Trash2
                                style={{
                                  color: "#dc4446",
                                  marginInlineEnd: "8px",
                                }}
                              />
                              Delete
                            </Typography.Text>
                          </Popconfirm>
                        ),
                        key: "delete",
                        onClick: (event) => event.domEvent.stopPropagation(),
                      },
                    ],
                  }}
                  trigger={["click"]}
                  placement="bottomRight"
                  onClick={(evt) => evt.stopPropagation()}
                >
                  <EllipsisVertical />
                </Dropdown>
              }
            >
              <div className="grid-view-card-content">
                <Typography.Paragraph type="secondary">
                  {item?.description || "No description"}
                </Typography.Paragraph>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

GridView.propTypes = {
  listOfTools: PropTypes.array.isRequired,
  handleEdit: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
};

export { GridView };
