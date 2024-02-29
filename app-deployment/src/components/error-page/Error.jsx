import { Result } from "antd";
import { useLocation } from "react-router-dom";

const ErrorPage = () => {
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  return (
    <Result
      status={queryParams.get("status")}
      title={queryParams.get("title")}
      subTitle={queryParams.get("subTitle")}
    />
  );
};

export { ErrorPage };
