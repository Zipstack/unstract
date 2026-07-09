import { Checkbox, Form, Select, Tag, Tooltip } from "antd";
import PropTypes from "prop-types";
import { useCallback, useEffect, useState } from "react";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { ApiKeyManager } from "../api-key-manager/ApiKeyManager.jsx";

function DeploymentScopeFields({ form, deployments }) {
  const allowAll = Form.useWatch("allow_all_deployments", form);
  return (
    <>
      <Form.Item
        name="allow_all_deployments"
        valuePropName="checked"
        initialValue={false}
      >
        <Checkbox>Allow all API deployments</Checkbox>
      </Form.Item>
      <Form.Item
        name="api_deployments"
        label="Select API Deployments"
        rules={
          allowAll === false
            ? [{ required: true, message: "Select at least one deployment" }]
            : []
        }
      >
        <Select
          mode="multiple"
          placeholder="Search and select deployments"
          optionFilterProp="children"
          className="api-key-manager__deployment-select"
          showSearch
          disabled={allowAll !== false}
        >
          {deployments?.map((d) => (
            <Select.Option key={d?.id} value={d?.id}>
              {d?.display_name || d?.api_name}
              {!d?.is_active && " (inactive)"}
            </Select.Option>
          ))}
        </Select>
      </Form.Item>
    </>
  );
}

DeploymentScopeFields.propTypes = {
  form: PropTypes.object.isRequired,
  deployments: PropTypes.array,
};

const scopeColumn = {
  title: "Scope",
  key: "scope",
  width: "14%",
  render: (_, record) =>
    record?.allow_all_deployments ? (
      <Tag color="blue">All Deployments</Tag>
    ) : (
      <Tooltip
        title={record?.api_deployments
          ?.map((d) => d?.display_name || d?.api_name)
          ?.join(", ")}
      >
        <Tag>{record?.api_deployments?.length || 0} deployment(s)</Tag>
      </Tooltip>
    ),
};

// Scoped keys carry an explicit deployment list; org-wide keys must not (the
// backend rejects an incoherent pair). Mirror that shaping on the client.
const shapeApiDeployments = (values) =>
  values?.allow_all_deployments === false ? values?.api_deployments || [] : [];

function GlobalApiDeploymentKeys() {
  const [deployments, setDeployments] = useState([]);
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  const basePath = `/api/v1/unstract/${sessionDetails?.orgId}/global-api-deployment`;

  const fetchDeployments = useCallback(() => {
    if (!sessionDetails?.orgId) {
      return;
    }
    axiosPrivate({ method: "GET", url: `${basePath}/deployments/` })
      .then((res) => setDeployments(res?.data || []))
      .catch((err) =>
        // Surface it: a scoped key requires picking from this list, so a silent
        // empty picker would leave the admin unable to create one with no clue why.
        setAlertDetails(handleException(err, "Failed to load API deployments")),
      );
  }, [basePath, sessionDetails?.orgId]);

  useEffect(() => {
    fetchDeployments();
  }, [fetchDeployments]);

  const renderScopeFields = (form) => (
    <DeploymentScopeFields form={form} deployments={deployments} />
  );

  return (
    <ApiKeyManager
      title="Global API Deployment Keys"
      entityLabel="Global API Deployment Key"
      resourcePath="global-api-deployment"
      extraColumns={[scopeColumn]}
      renderCreateFields={renderScopeFields}
      renderEditFields={renderScopeFields}
      getEditInitialValues={(record) => ({
        allow_all_deployments: record?.allow_all_deployments,
        api_deployments: record?.api_deployments?.map((d) => d?.id) || [],
      })}
      transformCreatePayload={(values) => ({
        ...values,
        allow_all_deployments: values?.allow_all_deployments ?? false,
        api_deployments: shapeApiDeployments(values),
      })}
      transformEditPayload={(values) => ({
        ...values,
        api_deployments: shapeApiDeployments(values),
      })}
    />
  );
}

export { GlobalApiDeploymentKeys };
