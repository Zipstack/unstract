import { Input, Space, Typography } from "antd";

import "./EditToolInfo.css";

function EditToolInfo() {
  return (
    <div>
      <br />
      <div>
        <Space direction="vertical" className="custom-space">
          <Typography.Text>Tool Name</Typography.Text>
          <Input />
        </Space>
      </div>
      <br />
      <div>
        <Space direction="vertical" className="custom-space">
          <Typography.Text>Author/Org Name</Typography.Text>
          <Input />
        </Space>
      </div>
      <br />
      <div>
        <Space direction="vertical" className="custom-space">
          <Typography.Text>Description</Typography.Text>
          <Input.TextArea rows={3} />
        </Space>
      </div>
      <br />
      <div>
        <Space direction="vertical" className="custom-space">
          <Typography.Text>Search Icons</Typography.Text>
          <div>
            <Input />
            <Typography.Text
              type="secondary"
              className="edit-tool-info-helper-text"
            >
              Choose icons from here -{" "}
              <a
                href="https://fonts.google.com/icons"
                target="_blank"
                rel="noreferrer"
              >
                fonts.google.com/icons
              </a>
            </Typography.Text>
          </div>
        </Space>
      </div>
      <br />
    </div>
  );
}

export { EditToolInfo };
