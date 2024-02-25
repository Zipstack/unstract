import { ScheduleOutlined } from "@ant-design/icons";
import { Button, Input, Modal, Select, Space } from "antd";
import Typography from "antd/es/typography/Typography";
import PropTypes from "prop-types";

import { ToolInfoCard } from "../../agency/tool-info-card/ToolInfoCard";
import "../etl-task-deploy/EtlTaskDeploy.css";

const AppDeploy = ({ open, setOpen }) => {
  const { Option } = Select;
  const { TextArea } = Input;

  return (
    <Modal
      title="Deploy App Development"
      centered
      open={open}
      onOk={() => setOpen(false)}
      onCancel={() => setOpen(false)}
      okText="Save and Deploy"
      okButtonProps={{ style: { background: "#092C4C" } }}
      width={800}
      closable={true}
      maskClosable={false}
    >
      <div
        style={{
          display: "flex",
          width: "100%",
          justifyContent: "space-between",
        }}
      >
        <div style={{ width: "46%" }}>
          <Typography className="formLabel">Project Name</Typography>
          <Input placeholder="Name"></Input>
          <br />
          <Typography className="formLabel">Workflow</Typography>
          <Select
            defaultValue="lucy"
            style={{
              width: "100%",
            }}
          >
            <Option value="jack">Jack</Option>

            <Option value="lucy">Lucy</Option>

            <Option value="Yiminghe">yiminghe</Option>
          </Select>
          <br />
          <Typography className="formLabel">Frequency of runs</Typography>
          <TextArea rows={2} />
        </div>
        <div style={{ width: "46%" }}>
          <Typography style={{ padding: "4px" }}>App Template</Typography>
          <div>
            <ToolInfoCard
              toolInfo={{
                name: "Document Q&A",
                description:
                  "Two liner explanatory text can go here. In case if there is any.",
                icon: "https://storage.googleapis.com/pandora-static/tool-icons/ZSDBWriter.svg",
              }}
            />

            <ToolInfoCard
              toolInfo={{
                name: "Semantic Search",
                description:
                  "Two liner explanatory text can go here. In case if there is any.",
                icon: "https://storage.googleapis.com/pandora-static/tool-icons/ZSFileOps.svg",
              }}
            />
          </div>
        </div>
      </div>
      <Space style={{ margin: "20px 0px" }}>
        <Button icon={<ScheduleOutlined />}></Button>
        <Typography.Text style={{ fontSize: "10px", opacity: 0.6 }}>
          The task will run at the start of every third hour, every day, every
          month, regardless of the day of the week
        </Typography.Text>
      </Space>
    </Modal>
  );
};
AppDeploy.propTypes = {
  setOpen: PropTypes.func.isRequired,
  onOk: PropTypes.func.isRequired,
  open: PropTypes.bool.isRequired,
};
export default AppDeploy;
