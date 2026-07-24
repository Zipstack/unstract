import { Flex, Pagination } from "antd";
import PropTypes from "prop-types";

import { ListView } from "../../widgets/list-view/ListView";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import "./ViewTools.css";
import { EmptyState } from "../../widgets/empty-state/EmptyState.jsx";

function ViewTools({
  isLoading,
  isEmpty,
  listOfTools,
  setOpenAddTool,
  handleEdit,
  handleDelete,
  titleProp,
  descriptionProp,
  iconProp,
  idProp,
  centered,
  isClickable = true,
  handleShare,
  handleCoOwner,
  showOwner,
  showModified,
  type,
  pagination,
}) {
  if (isLoading) {
    return <SpinnerLoader />;
  }

  if (isEmpty) {
    let text = "No tools available";
    let btnText = "New Tool";
    if (type) {
      text = `No ${type.toLowerCase()} available`;
      btnText = type;
    }
    return (
      <EmptyState
        text={text}
        btnText={btnText}
        handleClick={() => setOpenAddTool(true)}
      />
    );
  }

  if (!listOfTools?.length) {
    return <EmptyState text="No results found for this search" />;
  }

  const showPagination = pagination && pagination.total > pagination.pageSize;

  return (
    <>
      <ListView
        listOfTools={listOfTools}
        handleEdit={handleEdit}
        handleDelete={handleDelete}
        descriptionProp={descriptionProp}
        iconProp={iconProp}
        titleProp={titleProp}
        idProp={idProp}
        centered={centered}
        isClickable={isClickable}
        handleShare={handleShare}
        handleCoOwner={handleCoOwner}
        showOwner={showOwner}
        showModified={showModified}
        type={type}
      />
      {showPagination && (
        <Flex justify="flex-end" className="view-tools-pagination">
          <Pagination
            current={pagination.current}
            pageSize={pagination.pageSize}
            total={pagination.total}
            onChange={pagination.onChange}
            showSizeChanger
            pageSizeOptions={["10", "20", "50"]}
            showTotal={(total, range) =>
              `${range[0]}-${range[1]} of ${total} ${
                pagination.itemLabel || "items"
              }`
            }
          />
        </Flex>
      )}
    </>
  );
}

ViewTools.propTypes = {
  isLoading: PropTypes.bool.isRequired,
  isEmpty: PropTypes.bool.isRequired,
  listOfTools: PropTypes.array,
  setOpenAddTool: PropTypes.func,
  handleEdit: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  handleShare: PropTypes.func,
  handleCoOwner: PropTypes.func,
  titleProp: PropTypes.string.isRequired,
  descriptionProp: PropTypes.string,
  iconProp: PropTypes.string,
  idProp: PropTypes.string.isRequired,
  centered: PropTypes.bool,
  isClickable: PropTypes.bool,
  showOwner: PropTypes.bool,
  showModified: PropTypes.bool,
  type: PropTypes.string,
  pagination: PropTypes.shape({
    current: PropTypes.number,
    pageSize: PropTypes.number,
    total: PropTypes.number,
    onChange: PropTypes.func,
    itemLabel: PropTypes.string,
  }),
};

export { ViewTools };
