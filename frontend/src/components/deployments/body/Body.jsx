import { Table } from "antd";
import PropTypes from "prop-types";

import { deploymentsStaticContent } from "../../../helpers/GetStaticData";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout";
import { EmptyState } from "../../widgets/empty-state/EmptyState";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";

function Body({ type, columns, tableData, isTableLoading, openAddModal }) {
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
