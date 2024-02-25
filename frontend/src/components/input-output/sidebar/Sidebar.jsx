import { Button, Menu } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";

import "./Sidebar.css";

function Sidebar({
  selectedItem,
  setSelectedItem,
  listOfItems,
  handleOpenModal,
  btnText,
}) {
  const handleSelectItem = (e) => {
    const id = e.key;
    setSelectedItem(id?.toString());
  };

  return (
    <div className="sidebar-layout">
      <Button block icon={<PlusOutlined />} onClick={handleOpenModal}>
        {btnText}
      </Button>
      {selectedItem && (
        <Menu
          className="sidebar-menu"
          style={{ border: 0 }}
          selectedKeys={[selectedItem]}
          mode="inline"
          items={listOfItems}
          onClick={handleSelectItem}
        />
      )}
    </div>
  );
}

Sidebar.propTypes = {
  selectedItem: PropTypes.string,
  setSelectedItem: PropTypes.func,
  listOfItems: PropTypes.array,
  handleOpenModal: PropTypes.func.isRequired,
  btnText: PropTypes.string.isRequired,
};

export { Sidebar };
