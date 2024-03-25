import { Menu, Tooltip } from "antd";
import PropTypes from "prop-types";
import comingSoon from "../../../assets/coming-soon.png";
import "./ListOfConnectors.css";

function ListOfConnectors({ listOfConnectors, selectedId, handleSelectItem }) {
  return (
    <div className="conn-modal-menu">
      <Menu
        className="sidebar-menu"
        style={{ border: 0 }}
        selectedKeys={[selectedId]}
        mode="inline"
        items={listOfConnectors.map((item) => ({
          key: item?.key,
          label: (
            <>
              {item?.isDisabled ? (
                <Tooltip title="Coming Soon">
                  <div className="coming-soon-container">
                    <img
                      src={comingSoon}
                      alt="Coming Soon"
                      className="coming-soon-img"
                    />
                    {item?.label}
                  </div>
                </Tooltip>
              ) : (
                item?.label
              )}
            </>
          ),
          disabled: item?.isDisabled,
          icon: item?.icon,
        }))}
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
