import { Spin } from "antd";
import "./Loader.css";
import { LoadingOutlined } from "@ant-design/icons";

function Loader() {
  return (
    <div className="center-position">
      <Spin indicator={<LoadingOutlined className="loader-icon" spin />} />
    </div>
  );
}

export { Loader };
