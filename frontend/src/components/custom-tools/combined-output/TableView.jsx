import { Table } from "antd";
import PropTypes from "prop-types";

function TableView({ combinedOutput }) {
  const dataSource = Object.keys(combinedOutput).map((key, index) => ({
    key: index + 1,
    field_name: key,
    ai_response: combinedOutput[key],
  }));

  const columns = [
    {
      title: "Field Name",
      dataIndex: "field_name",
      key: "field_name",
    },
    {
      title: "AI Response",
      dataIndex: "ai_response",
      key: "ai_response",
    },
  ];

  return <Table dataSource={dataSource} columns={columns} pagination={null} />;
}

TableView.propTypes = {
  combinedOutput: PropTypes.object.isRequired,
};

export { TableView };
