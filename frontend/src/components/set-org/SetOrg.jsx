import Cookies from "js-cookie";
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
import { useExceptionHandler } from "../../hooks/useExceptionHandler";
import { useAlertStore } from "../../store/alert-store";
import { useUserSession } from "../../hooks/useUserSession.js";

function SetOrg() {
  const { state } = useLocation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [loadingOrgId, setLoadingOrgId] = useState(null);
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const userSession = useUserSession();
  useEffect(() => {
    const fetchData = async () => {
      try {
        const userSessionData = await userSession();
        const signedInOrgId = userSessionData?.organization_id;
        if (state === null || signedInOrgId) {
          navigate("/");
        }
      } catch (error) {
        navigate("/");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [state, navigate]);

  const handleContinue = (id) => {
    setLoading(true);
    setLoadingOrgId(id);
    const csrfToken = Cookies.get("csrftoken");
    const requestOptions = {
      method: "POST",
      url: `/api/v1/organization/${id}/set`,
      headers: {
        "X-CSRFToken": csrfToken,
      },
    };

    axios(requestOptions)
      .then(() => {
        window.location.reload();
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
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
