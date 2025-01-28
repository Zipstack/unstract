import PropTypes from "prop-types";
import { Typography } from "antd";
import { useCallback } from "react";

import { ListView } from "../../widgets/list-view/ListView";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import "./ViewTools.css";
import { EmptyState } from "../../widgets/empty-state/EmptyState";

function ViewTools({
  isLoading,
  isEmpty,
  listOfTools = [],
  setOpenAddTool = () => {},
  handleEdit,
  handleDelete,
  titleProp,
  descriptionProp = "",
  iconProp = "",
  idProp,
  centered = false,
  isClickable = true,
  handleShare = null,
  showOwner = false,
  type = "",
}) {
  const handleEmptyStateClick = useCallback(() => {
    setOpenAddTool(true);
  }, [setOpenAddTool]);

  if (isLoading) {
    return <SpinnerLoader />;
  }

  if (isEmpty) {
    const text = type
      ? `No ${type.toLowerCase()} available`
      : "No tools available";
    const btnText = type || "New Tool";

    return (
      <EmptyState
        text={text}
        btnText={btnText}
        handleClick={handleEmptyStateClick}
      />
    );
  }

  if (!listOfTools?.length) {
    return (
      <div className="center">
        <Typography.Title level={5}>
          No results found for this search
        </Typography.Title>
      </div>
    );
  }

  return (
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
      showOwner={showOwner}
      type={type}
    />
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
  titleProp: PropTypes.string.isRequired,
  descriptionProp: PropTypes.string,
  iconProp: PropTypes.string,
  idProp: PropTypes.string.isRequired,
  centered: PropTypes.bool,
  isClickable: PropTypes.bool,
  showOwner: PropTypes.bool,
  type: PropTypes.string,
};

export { ViewTools };
