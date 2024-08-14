import { Form, Input, Select } from "antd";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout.jsx";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import { TopBar } from "../../widgets/top-bar/TopBar.jsx";
import "./InviteEditUser.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import usePostHogEvents from "../../../hooks/usePostHogEvents.js";

function InviteEditUser() {
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const location = useLocation();
  const navigate = useNavigate();
  const handleException = useExceptionHandler();
  const [userRoles, setUserRoles] = useState();
  const [loading, setLoading] = useState(true);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [initialRole, setInitialRole] = useState();
  const { setPostHogCustomEvent } = usePostHogEvents();

  const isInvite = location.pathname.split("/").slice(-1)[0] === "invite";
  const validateMessages = {
    required: "required!",
    types: {
      email: "Enter a valid email!",
      number: "Enter a valid number!",
    },
  };
  const USER_ROLE = "unstract_user";

  const getUserRoles = async () => {
    setLoading(true);
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/roles`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        const members = res?.data?.members || [];
        setUserRoles(members);
        setInitialRole(
          isInvite
            ? members.find((role) => role.name === USER_ROLE)
            : members.find((role) => role.name === location.state.role)
        );
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to load user roles"));
      })
      .finally(() => {
        setLoading(false);
      });
  };
  const inviteUserToOrg = async (value) => {
    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/users/invite/`,
      data: { users: [value] },
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        const message = res?.data?.message[0] || {};
        setAlertDetails({
          type: message.status === "success" ? "success" : "error",
          content:
            message.status === "success"
              ? "Invited user successfully"
              : `Failed to invite user, ${message?.message}`,
        });
        navigate(`/${sessionDetails?.orgName}/users/`);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to invite user"));
      })
      .finally(() => setSubmitLoading(false));
  };

  const updateUserRole = (user) => {
    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/users/role/`,
      data: { ...user },
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        const response = res?.data || {};
        setAlertDetails({
          type: response.status === "success" ? "success" : "error",
          content:
            response.status === "success"
              ? "User updated successfully"
              : "Failed to update user",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to update user"));
      })
      .finally(() => setSubmitLoading(false));
  };

  const onSubmit = (values) => {
    setSubmitLoading(true);
    if (isInvite) {
      const roleName = userRoles?.filter((val) => val.id === values.role)[0]
        ?.name;
      values.role = roleName;
      inviteUserToOrg(values);
    } else {
      updateUserRole(values);
    }

    try {
      const info = isInvite
        ? "Clicked on 'Invite' button"
        : "Clicked on 'Update' button";
      setPostHogCustomEvent("intent_success_add_user", { info });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
  };

  const formatOptionLabel = (value) => {
    return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  };

  useEffect(() => {
    if (!isInvite && !location.state) {
      navigate(`/${sessionDetails?.orgName}/tools`);
    }
    getUserRoles();
  }, []);
  return (
    <>
      <TopBar
        enableSearch={false}
        title={isInvite ? "Invite User" : "Edit User"}
      />
      <IslandLayout>
        <div className="invite-user-container">
          {loading ? (
            <div className="loader-container">
              <SpinnerLoader />
            </div>
          ) : (
            <Form
              name="invite-edit-form"
              onFinish={onSubmit}
              validateMessages={validateMessages}
            >
              <Form.Item
                name={["email"]}
                rules={[{ type: "email", required: true }]}
                initialValue={isInvite ? null : location.state.email}
              >
                <Input placeholder="Email" disabled={!isInvite} />
              </Form.Item>
              <div className="invite-button-container">
                <div className="admin-toggle-container">
                  <Form.Item
                    name="role"
                    initialValue={initialRole.id}
                    className="form-select"
                  >
                    <Select
                      className="role-select"
                      options={userRoles.map((role) => {
                        return {
                          value: role.id,
                          label: formatOptionLabel(role.name),
                        };
                      })}
                    />
                  </Form.Item>
                </div>
                <CustomButton
                  type="primary"
                  htmlType="submit"
                  loading={submitLoading}
                >
                  {isInvite ? "Invite" : "Update"}
                </CustomButton>
              </div>
            </Form>
          )}
        </div>
      </IslandLayout>
    </>
  );
}

export { InviteEditUser };
