import { Collapse, Table } from "antd";
import PropTypes from "prop-types";
import { useState } from "react";

import { deploymentsStaticContent } from "../../../helpers/GetStaticData";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout";
import { LogsLabel } from "../../agency/logs-label/LogsLabel";
import { EmptyState } from "../../widgets/empty-state/EmptyState";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import { DisplayLogs } from "../../agency/display-logs/DisplayLogs";

function Body({ type, columns, tableData, isTableLoading, openAddModal }) {
  const [activeKey, setActiveKey] = useState([]);
  const getItems = () => [
    {
      key: "1",
      label: activeKey?.length > 0 ? <LogsLabel /> : "Logs",
      children: (
        <div className="tool-ide-logs">
          <IslandLayout>
            <DisplayLogs />
          </IslandLayout>
        </div>
      ),
    },
  ];

  const handleCollapse = (keys) => {
    setActiveKey(keys);
  };
  if (isTableLoading) {
    return <SpinnerLoader />;
  }
  if (!tableData?.length) {
    return (
      <EmptyState
        text={`Currently you have no ${deploymentsStaticContent[type].addBtn}`}
        btnText={deploymentsStaticContent[type].addBtn}
        handleClick={() => openAddModal(false)}
      />
    );
  }
  return (
    <IslandLayout>
      <div className="body-div">
        <div className="table-div">
          <Table
            className="table"
            size="middle"
            columns={columns}
            dataSource={tableData}
            rowKey="id"
            loading={{
              indicator: <SpinnerLoader />,
              spinning: isTableLoading,
            }}
          />
        </div>
        {deploymentsStaticContent[type].isLogsRequired && (
          <>
            <div className="gap" />
            <Collapse
              className="tool-ide-collapse-panel"
              size="small"
              activeKey={activeKey}
              items={getItems()}
              expandIconPosition="end"
              onChange={handleCollapse}
            />
          </>
        )}
      </div>
    </IslandLayout>
  );
}

Body.propTypes = {
  type: PropTypes.string.isRequired,
  columns: PropTypes.array.isRequired,
  tableData: PropTypes.array.isRequired,
  isTableLoading: PropTypes.bool.isRequired,
  openAddModal: PropTypes.func.isRequired,
};

export { Body };
