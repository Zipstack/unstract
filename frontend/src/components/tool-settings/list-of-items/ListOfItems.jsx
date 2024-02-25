import { DeleteOutlined, EditOutlined, MoreOutlined } from "@ant-design/icons";
import { Card, Dropdown, Image } from "antd";
import PropTypes from "prop-types";

import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";
import { EmptyState } from "../../widgets/empty-state/EmptyState";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import "./ListOfItems.css";

function ListOfItems({
  isLoading,
  tableRows,
  setEditItemId,
  handleDelete,
  handleClick,
}) {
  if (isLoading) {
    return <SpinnerLoader />;
  }

  if (!tableRows?.length) {
    return (
      <EmptyState
        text="No adapters available"
        btnText="Adapter Profile"
        handleClick={handleClick}
      />
    );
  }

  return (
    <div className="grid-view-wrapper">
      <div className="grid-view-list">
        {tableRows.map((item) => {
          return (
            <Card
              key={item?.id}
              size="small"
              type="inner"
              bordered={true}
              className="ds-card"
              title={item?.adapter_name}
              extra={
                <Dropdown
                  menu={{
                    items: [
                      {
                        label: "Edit",
                        key: "edit",
                        icon: <EditOutlined />,
                        onClick: () => setEditItemId(item?.id),
                      },
                      {
                        label: (
                          <ConfirmModal
                            handleConfirm={() => handleDelete(item?.id)}
                            content="Want to delete this profile"
                          >
                            Delete
                          </ConfirmModal>
                        ),
                        key: "delete",
                        icon: <DeleteOutlined />,
                      },
                    ],
                  }}
                  trigger={["click"]}
                  placement="bottomRight"
                >
                  <MoreOutlined />
                </Dropdown>
              }
            >
              <div className="cover-img">
                <Image src={item?.icon} preview={false} className="fit-cover" />
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

ListOfItems.propTypes = {
  isLoading: PropTypes.bool.isRequired,
  tableRows: PropTypes.array.isRequired,
  setEditItemId: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  handleClick: PropTypes.func.isRequired,
};

export { ListOfItems };
