import { Menu } from "antd";
import PropTypes from "prop-types";

function ListOfConnectors({ listOfConnectors, selectedId, handleSelectItem }) {
  return (
    <div className="conn-modal-menu">
      <Menu
        className="sidebar-menu"
        style={{ border: 0 }}
        selectedKeys={[selectedId]}
        mode="inline"
        items={listOfConnectors}
        onClick={handleSelectItem}
      />
    </div>
  );
}

ListOfConnectors.propTypes = {
  listOfConnectors: PropTypes.array.isRequired,
  selectedId: PropTypes.string,
  handleSelectItem: PropTypes.func.isRequired,
};

export { ListOfConnectors };
