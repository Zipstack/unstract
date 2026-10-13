import { EllipsisVertical, Pencil, Trash2 } from "lucide-react";
import PropTypes from "prop-types";
import { Image } from "@/components/ui/shims/antd-leaves";
import { Dropdown } from "@/components/ui/shims/antd-overlays";
import { Card } from "@/components/ui/shims/antd-structure";

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
                        icon: <Pencil />,
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
                        icon: <Trash2 />,
                      },
                    ],
                  }}
                  trigger={["click"]}
                  placement="bottomRight"
                >
                  <EllipsisVertical />
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
