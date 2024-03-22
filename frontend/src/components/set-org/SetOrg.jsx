import { useEffect, useState } from "react";
import { Button, Card } from "antd";
import { useLocation, useNavigate } from "react-router-dom";
import "./SetOrg.css"; // Import your CSS file for styling
import axios from "axios";
import Proptypes from "prop-types";
import {
  OrgAvatar,
  OrgSelection,
  RedGradCircle,
  YellowGradCircle,
  UnstractBlackLogo,
} from "../../assets/index";

function SetOrg() {
  const { state } = useLocation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [loadingOrgId, setLoadingOrgId] = useState(null);
  useEffect(() => {
    if (state === null || signedInOrgId) {
      navigate("/");
    }
  }, []);

  const signedInOrgId =
    document?.cookie
      ?.split("; ")
      ?.find((row) => row.startsWith("org_id="))
      ?.split("=")[1] || null;
  const handleContinue = async (id) => {
    setLoading(true);
    setLoadingOrgId(id);
    const csrfToken = ("; " + document.cookie)
      ?.split(`; csrftoken=`)
      ?.pop()
      ?.split(";")[0];
    console.log(csrfToken);

    const requestOptions = {
      method: "POST",
      url: `/api/v1/organization/${id}/set`,
      headers: {
        "X-CSRFToken": csrfToken,
      },
    };

    await axios(requestOptions)
      .then(() => {
        window.location.reload();
      })
      .catch(() => {})
      .finally(() => {
        setLoading(false);
        setLoadingOrgId(null);
      });
  };

  return (
    state && (
      <div className="org-container">
        <div className="org-list">
          <UnstractBlackLogo className="select-org-unstract-logo" />
          <div className="card-list-container">
            {state.map((org) => (
              <OrganizationCard
                key={org?.id}
                organization={org}
                onConnect={(id) => handleContinue(id)}
                loading={loading && loadingOrgId === org?.id}
                disabled={loadingOrgId !== null && loadingOrgId !== org?.id}
              />
            ))}
          </div>
          <YellowGradCircle className="yellow-grad-circle" />
        </div>
        <div className="org-svg">
          <OrgSelection className="org-selection-svg" />
          <RedGradCircle className="red-grad-circle" />
        </div>
      </div>
    )
  );
}

function OrganizationCard({ organization, onConnect, loading, disabled }) {
  return (
    <Card className="org-card-container">
      <Card.Meta
        avatar={<OrgAvatar className="org-avatar" />}
        title={organization.display_name}
      />
      <Button
        className="select-org-button"
        onClick={() => onConnect(organization.id)}
        loading={loading}
        disabled={disabled}
      >
        Connect
      </Button>
    </Card>
  );
}

OrganizationCard.propTypes = {
  organization: Proptypes.object.isRequired,
  onConnect: Proptypes.func.isRequired,
  loading: Proptypes.bool.isRequired,
  disabled: Proptypes.bool.isRequired,
};

export { SetOrg };
