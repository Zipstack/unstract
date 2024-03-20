import { useEffect, useState } from "react";
import { Select, Button } from "antd";
import { useLocation, useNavigate } from "react-router-dom";
import "./SetOrg.css"; // Import your CSS file for styling
import axios from "axios";

function SetOrg() {
  const { state } = useLocation();
  const navigate = useNavigate();
  const [selectedOrg, setSelectedOrg] = useState(null);
  const signedInOrgId =
    document?.cookie
      ?.split("; ")
      ?.find((row) => row.startsWith("org_id="))
      ?.split("=")[1] || null;
  useEffect(() => {
    if (!state || signedInOrgId) {
      navigate("/");
    }
  }, []);

  const handleChange = (value) => {
    setSelectedOrg(value);
  };

  const handleContinue = async () => {
    const requestOptions = {
      method: "GET",
      url: "/api/v1/organization",
    };
    const csrfToken = ("; " + document.cookie)
      .split(`; csrftoken=`)
      .pop()
      .split(";")[0];

    requestOptions.url = `/api/v1/organization/${selectedOrg}/set`;
    requestOptions.headers = {
      "X-CSRFToken": csrfToken,
    };
    requestOptions.method = "POST";

    await axios(requestOptions);
    window.location.reload();
  };

  const options = state?.map((org) => {
    return {
      value: org.id,
      label: org.display_name,
    };
  });

  return (
    <div className="org-container">
      <Select
        className="select-org"
        placeholder="Please select an Organization"
        options={options}
        onChange={handleChange}
        value={selectedOrg}
      />
      <Button
        type="primary"
        className="continue-button"
        onClick={handleContinue}
        disabled={!selectedOrg}
      >
        Continue as {options?.find((org) => org.value === selectedOrg)?.label}
      </Button>
    </div>
  );
}

export { SetOrg };
