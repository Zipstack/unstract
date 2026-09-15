import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/shims/antd-button";
import { Result } from "@/components/ui/shims/antd-structure";

function NotFound() {
  const navigate = useNavigate();
  return (
    <Result
      status="404"
      title="Page Not Found"
      subTitle="Sorry, the page you visited does not exist."
      extra={
        <Button type="primary" onClick={() => navigate(-1)}>
          Go Back
        </Button>
      }
    />
  );
}

export { NotFound };
