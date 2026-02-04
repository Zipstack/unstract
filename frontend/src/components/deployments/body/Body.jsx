import PropTypes from "prop-types";

import { deploymentsStaticContent } from "../../../helpers/GetStaticData";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout";
import { EmptyState } from "../../widgets/empty-state/EmptyState";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import { CardGridView } from "../../widgets/card-grid-view";

function Body({
  type,
  tableData,
  isTableLoading,
  openAddModal,
  cardConfig,
  onCardClick,
  listMode = false,
  forceExpandedId = null,
  scrollToId = null,
  pagination = null,
}) {
  if (isTableLoading) {
    return <SpinnerLoader />;
  }
  if (!tableData?.length) {
    return (
      <IslandLayout>
        <EmptyState
          text={`Currently you have no ${deploymentsStaticContent[type].addBtn}`}
          btnText={deploymentsStaticContent[type].addBtn}
          handleClick={() => openAddModal(false)}
        />
      </IslandLayout>
    );
  }

  return (
    <IslandLayout>
      <div className="body-div pipeline-card-grid-container">
        <CardGridView
          data={tableData}
          cardConfig={cardConfig}
          loading={isTableLoading}
          onCardClick={onCardClick}
          rowKey="id"
          listMode={listMode}
          forceExpandedId={forceExpandedId}
          scrollToId={scrollToId}
          pagination={pagination}
        />
      </div>
    </IslandLayout>
  );
}

Body.propTypes = {
  type: PropTypes.string.isRequired,
  tableData: PropTypes.array.isRequired,
  isTableLoading: PropTypes.bool.isRequired,
  openAddModal: PropTypes.func.isRequired,
  cardConfig: PropTypes.object.isRequired,
  onCardClick: PropTypes.func,
  listMode: PropTypes.bool,
  forceExpandedId: PropTypes.string,
  scrollToId: PropTypes.string,
  pagination: PropTypes.shape({
    current: PropTypes.number,
    pageSize: PropTypes.number,
    total: PropTypes.number,
    onChange: PropTypes.func,
  }),
};

export { Body };
