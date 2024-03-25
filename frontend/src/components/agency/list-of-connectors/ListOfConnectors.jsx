import { Menu, Tooltip } from "antd";
import PropTypes from "prop-types";
import comingSoon from "../../../assets/coming-soon.png";

function ListOfConnectors({ listOfConnectors, selectedId, handleSelectItem }) {
  return (
    <div className="conn-modal-menu">
      <Menu
        className="sidebar-menu"
        style={{ border: 0 }}
        selectedKeys={[selectedId]}
        mode="inline"
        items={listOfConnectors.map((item) => ({
          label: (
            <>
              {item?.isDisabled ? (
                <Tooltip title="Coming Soon">
                  <div
                    style={{
                      position: "relative",
                      display: "inline-block",
                      width: "100%",
                    }}
                  >
                    <img
                      src={comingSoon}
                      alt="Coming Soon"
                      style={{
                        position: "absolute",
                        top: 0,
                        right: 0,
                        width: "40px", // Adjust width and height according to your image size
                        height: "40px",
                      }}
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
