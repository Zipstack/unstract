import PropTypes from "prop-types";

import { GridView } from "../../widgets/grid-view/GridView";
import { ListView } from "../../widgets/list-view/ListView";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import "./ViewTools.css";
import { EmptyState } from "../../widgets/empty-state/EmptyState.jsx";

function ViewTools({
  isLoading,
  viewType,
  listOfTools,
  setOpenAddTool,
  handleEdit,
  handleDelete,
}) {
  if (isLoading) {
    return <SpinnerLoader />;
  }

  if (!listOfTools?.length || !viewType?.length) {
    return (
      <EmptyState
        text="No tools available"
        btnText="New Tool"
        handleClick={() => setOpenAddTool(true)}
      />
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
  listOfTools: PropTypes.array,
  setOpenAddTool: PropTypes.func,
  handleEdit: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
};

export { ViewTools };
