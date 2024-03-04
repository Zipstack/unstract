import PropTypes from "prop-types";

import { GridView } from "../../widgets/grid-view/GridView";
import { ListView } from "../../widgets/list-view/ListView";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import "./ViewTools.css";
import { EmptyState } from "../../widgets/empty-state/EmptyState.jsx";
import { Typography } from "antd";

function ViewTools({
  isLoading,
  viewType,
  isEmpty,
  listOfTools,
  setOpenAddTool,
  handleEdit,
  handleDelete,
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

  if (!listOfTools?.length || !viewType?.length) {
    return (
      <div className="center">
        <Typography.Title level={5}>
          No results found for this search
        </Typography.Title>
      </div>
    );
  }

  if (viewType === "grid") {
    return (
      <GridView
        listOfTools={listOfTools}
        handleEdit={handleEdit}
        handleDelete={handleDelete}
      />
    );
  }

  return (
    <ListView
      listOfTools={listOfTools}
      handleEdit={handleEdit}
      handleDelete={handleDelete}
    />
  );
}

ViewTools.propTypes = {
  isLoading: PropTypes.bool.isRequired,
  viewType: PropTypes.string.isRequired,
  isEmpty: PropTypes.bool.isRequired,
  listOfTools: PropTypes.array,
  setOpenAddTool: PropTypes.func,
  handleEdit: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
};

export { ViewTools };
