import PropTypes from "prop-types";

import { Body } from "../body/Body";
import { Header } from "../header/Header";
import "./Layout.css";

function Layout({ type, columns, tableData, isTableLoading, openAddModal }) {
  return (
    <div className="deploy-layout">
      <div>
        <Header type={type} openAddModal={openAddModal} />
      </div>
      <div className="layout-body">
        <Body
          type={type}
          columns={columns}
          tableData={tableData}
          isTableLoading={isTableLoading}
          openAddModal={openAddModal}
        />
      </div>
    </div>
  );
}

Layout.propTypes = {
  type: PropTypes.string.isRequired,
  columns: PropTypes.array.isRequired,
  tableData: PropTypes.array.isRequired,
  isTableLoading: PropTypes.bool.isRequired,
  openAddModal: PropTypes.func.isRequired,
};

export { Layout };
