import { Radio } from "antd";
import { Filter } from "lucide-react";
import PropTypes from "prop-types";
import { Button } from "@/components/ui/antd-button";
import { Space } from "@/components/ui/antd-layout";

const FilterIcon = ({ filtered }) => (
  <Filter style={{ color: filtered ? "#1677ff" : undefined }} />
);

const FilterDropdown = ({
  setSelectedKeys,
  selectedKeys,
  confirm,
  handleClearFilter,
  filterOptions,
}) => (
  <div style={{ padding: 8 }}>
    <Radio.Group
      onChange={(e) => {
        setSelectedKeys(e.target.value ? [e.target.value] : []);
        confirm();
      }}
      value={selectedKeys[0] || null}
    >
      <Space direction="vertical">
        {filterOptions.map((filter) => (
          <Radio key={filter} value={filter}>
            {filter}
          </Radio>
        ))}
      </Space>
    </Radio.Group>
    <br />
    <Button
      className="clear-button"
      type="primary"
      size="small"
      onClick={() => handleClearFilter(confirm)}
    >
      Clear
    </Button>
  </div>
);

FilterIcon.propTypes = {
  filtered: PropTypes.bool,
};

FilterDropdown.propTypes = {
  setSelectedKeys: PropTypes.func,
  selectedKeys: PropTypes.any,
  confirm: PropTypes.func,
  handleClearFilter: PropTypes.func,
  filterOptions: PropTypes.array,
};

export { FilterDropdown, FilterIcon };
