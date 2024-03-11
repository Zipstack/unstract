import PropTypes from "prop-types";

import { ListView } from "../../widgets/list-view/ListView";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import "./ViewTools.css";
import { EmptyState } from "../../widgets/empty-state/EmptyState.jsx";

import { Typography } from "antd";

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
}) {
  if (isLoading) {
    return <SpinnerLoader />;
  }

  if (isEmpty) {
    return (
      <EmptyState
        text="No tools available"
        btnText="New Tool"
        handleClick={() => setOpenAddTool(true)}
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
  titleProp: PropTypes.string.isRequired,
  descriptionProp: PropTypes.string,
  iconProp: PropTypes.string,
  idProp: PropTypes.string.isRequired,
  centered: PropTypes.bool,
};

export { ViewTools };
