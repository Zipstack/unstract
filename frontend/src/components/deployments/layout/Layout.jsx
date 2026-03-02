import PropTypes from "prop-types";

import { Body } from "../body/Body";
import { Header } from "../header/Header";
import "./Layout.css";

function Layout({
  type,
  tableData,
  isTableLoading,
  openAddModal,
  cardConfig,
  onCardClick,
  listMode = false,
  forceExpandedId = null,
  scrollToId = null,
  enableSearch = false,
  onSearch,
  setSearchList,
  pagination = null,
}) {
  return (
    <div className="deploy-layout">
      <div>
        <Header
          type={type}
          openAddModal={openAddModal}
          enableSearch={enableSearch}
          onSearch={onSearch}
          setSearchList={setSearchList}
        />
      </div>
      <div className="layout-body">
        <Body
          type={type}
          tableData={tableData}
          isTableLoading={isTableLoading}
          openAddModal={openAddModal}
          cardConfig={cardConfig}
          onCardClick={onCardClick}
          listMode={listMode}
          forceExpandedId={forceExpandedId}
          scrollToId={scrollToId}
          pagination={pagination}
        />
      </div>
    </div>
  );
}

Layout.propTypes = {
  type: PropTypes.string.isRequired,
  tableData: PropTypes.array.isRequired,
  isTableLoading: PropTypes.bool.isRequired,
  openAddModal: PropTypes.func.isRequired,
  cardConfig: PropTypes.object.isRequired,
  onCardClick: PropTypes.func,
  listMode: PropTypes.bool,
  forceExpandedId: PropTypes.string,
  scrollToId: PropTypes.string,
  enableSearch: PropTypes.bool,
  onSearch: PropTypes.func,
  setSearchList: PropTypes.func,
  pagination: PropTypes.shape({
    current: PropTypes.number,
    pageSize: PropTypes.number,
    total: PropTypes.number,
    onChange: PropTypes.func,
  }),
};

export { Layout };
