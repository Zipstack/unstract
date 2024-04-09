import { ArrowLeftOutlined } from "@ant-design/icons";
import { Button, Form, Input, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout.jsx";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";

const defaultFromDetails = {
  org_name: "",
  invitee_email: "",
};

function Admin() {
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const [isLoading, setIsLoading] = useState(true);
  const handleException = useExceptionHandler();
  const [formDetails, setFormDetails] = useState({ ...defaultFromDetails });
  useEffect(() => {
    setIsLoading(false);
  });

  const handleSubmit = async () => {
    const body = formDetails;

    const header = {
      "X-CSRFToken": sessionDetails?.csrfToken,
      "Content-Type": "application/json",
    };
    const requestOptions = {
      method: "POST",
      // url: `/api/v1/unstract/${sessionDetails?.orgId}/get_role/`,
      // url: `/api/v1/get_role`,
      url: `/api/v1/create_organization`,
      headers: header,
      data: body,
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        setAlertDetails({
          type: "success",
          content: "Default triad setting saved successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to update Default Triads")
        );
      });
  };

  const handleInputChange = (changedValues, allValues) => {
    setFormDetails({ ...formDetails, ...allValues });
  };

  return (
    <>
      <div className="plt-set-head">
        <Button size="small" type="text" onClick={() => navigate(-1)}>
          <ArrowLeftOutlined />
        </Button>
        <Typography.Text className="plt-set-head-typo">Admin</Typography.Text>
      </div>
      <div className="plt-set-layout">
        <IslandLayout>
          {isLoading ? (
            <SpinnerLoader />
          ) : (
            <div className="plt-set-layout-2 form-width">
              <Form
                form={form}
                name="myForm"
                layout="vertical"
                initialValues={formDetails}
                onValuesChange={handleInputChange}
              >
                <Form.Item
                  label="Organization name"
                  name="org_name"
                  rules={[
                    { required: true, message: "Please organization name" },
                  ]}
                >
                  <Input />
                </Form.Item>

                <Form.Item
                  label="Invitee"
                  name="invitee_email"
                  rules={[
                    {
                      required: true,
                      message: "Please enter the invtees's email",
                    },
                  ]}
                >
                  <Input />
                </Form.Item>
              </Form>

              <CustomButton
                type="primary"
                className="friction-less"
                onClick={handleSubmit}
              >
                Onboard
              </CustomButton>
            </div>
          )}
        </IslandLayout>
      </div>
    </>
  );
}

export { Admin };
