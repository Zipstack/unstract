import { Filter } from "lucide-react";
import PropTypes from "prop-types";
import { Button } from "@/components/ui/shims/antd-button";
import { Radio } from "@/components/ui/shims/antd-inputs";
import { Space } from "@/components/ui/shims/antd-layout";

const FilterIcon = ({ filtered }) => (
  <Filter style={{ color: filtered ? "var(--primary)" : undefined }} />
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
      // "" rather than null: Radix reads a nullish value as "uncontrolled", so
      // picking the first level flipped the group from uncontrolled to
      // controlled and React warned about it. An empty string is the
      // controlled spelling of "nothing selected".
      value={selectedKeys[0] ?? ""}
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
      /*
       * Empty the draft BEFORE confirming. `confirm()` publishes whatever
       * `setSelectedKeys` last set — it cannot see the parent state
       * `handleClearFilter` is about to clear, because that re-render has not
       * happened yet. Without this, Clear republished the level it was meant
       * to remove and the log list stayed filtered.
       */
      onClick={() => {
        setSelectedKeys([]);
        handleClearFilter(confirm);
      }}
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
