import { Copy, EllipsisVertical, Pencil, Trash2 } from "lucide-react";
import PropTypes from "prop-types";
import { Image } from "@/components/ui/shims/antd-leaves";
import { Dropdown } from "@/components/ui/shims/antd-overlays";
import { Card } from "@/components/ui/shims/antd-structure";

import { useCopyToClipboard } from "../../../hooks/useCopyToClipboard";
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
  const copyToClipboard = useCopyToClipboard();

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
                        // The adapter's instance UUID. It was reachable only
                        // through the network tab: the card renders the NAME,
                        // and `id` was used as a React key and for
                        // edit/delete but never shown. Callers of the
                        // Agent-KV API have to name their own `llm` /
                        // `lite_llm` / `x2text` adapters by this id, so
                        // "which UUID is 'sonnet 4.6'?" had no answer in the
                        // product.
                        //
                        // `item.id`, NOT `item.adapter_id` -- the latter is
                        // the provider descriptor (`anthropic|90ebd4cd-...`),
                        // shared by every instance of that provider, and
                        // passing it where an instance id belongs fails with
                        // "no such adapter in this organization".
                        //
                        // On the menu ENTRY rather than the kebab trigger:
                        // the dropdown opens on pointerdown and pins
                        // `pointer-events: none` on <body> while open, so a
                        // handler on the trigger itself never fires (the same
                        // trap Manage Users hit).
                        label: "Copy ID",
                        key: "copy-id",
                        icon: <Copy />,
                        onClick: () => copyToClipboard(item?.id, "Adapter ID"),
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
