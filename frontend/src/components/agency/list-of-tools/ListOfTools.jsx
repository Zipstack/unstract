import { Empty } from "antd";
import PropTypes from "prop-types";
import { DndProvider } from "react-dnd";
import { HTML5Backend } from "react-dnd-html5-backend";

import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import { ToolInfoCard } from "../tool-info-card/ToolInfoCard.jsx";
import "./ListOfTools.css";

function ListOfTools({ listOfTools, isLoading }) {
  if (isLoading) {
    return <SpinnerLoader />;
  }

  if (listOfTools?.length === 0) {
    return <Empty description="No tools to display" />;
  }

  return (
    <div className="wf-list-of-tools-layout">
      <DndProvider backend={HTML5Backend}>
        {listOfTools.map((toolInfo) => {
          return <ToolInfoCard key={toolInfo?.name} toolInfo={toolInfo} />;
        })}
      </DndProvider>
    </div>
  );
}

ListOfTools.propTypes = {
  listOfTools: PropTypes.array,
  isLoading: PropTypes.bool.isRequired,
};

export { ListOfTools };
