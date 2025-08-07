import { Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useMemo, useState } from "react";

import { sourceTypes } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { EmptyState } from "../../widgets/empty-state/EmptyState";
import { ConfigureDs } from "../configure-ds/ConfigureDs";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import useRequestUrl from "../../../hooks/useRequestUrl";

let transformLlmWhispererJsonSchema;
let LLMW_V2_ID;
let PLAN_TYPES;
let unstractSubscriptionPlanStore;
let llmWhipererAdapterSchema;
try {
  transformLlmWhispererJsonSchema =
    require("../../../plugins/unstract-subscription/helper/transformLlmWhispererJsonSchema").transformLlmWhispererJsonSchema;
  LLMW_V2_ID =
    require("../../../plugins/unstract-subscription/helper/transformLlmWhispererJsonSchema").LLMW_V2_ID;
  PLAN_TYPES =
    require("../../../plugins/unstract-subscription/helper/constants").PLAN_TYPES;
  unstractSubscriptionPlanStore = require("../../../plugins/store/unstract-subscription-plan-store");
  llmWhipererAdapterSchema = require("../../../plugins/unstract-subscription/hooks/useLlmWhispererAdapterSchema.js");
} catch (err) {
  // Ignore if not available
}

function AddSource({
  selectedSourceId,
  selectedSourceName,
  setOpen,
  type,
  sourceType,
  addNewItem,
  editItemId,
  metadata,
}) {
  const [spec, setSpec] = useState({});
  const [formData, setFormData] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [oAuthProvider, setOAuthProvider] = useState("");
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const { getUrl } = useRequestUrl();

  let transformLlmWhispererFormData;
  try {
    transformLlmWhispererFormData =
      llmWhipererAdapterSchema?.useLlmWhipererAdapterSchema()
        ?.transformLlmWhispererFormData;
  } catch {
    // Ignore if not available
  }

  let planType;
  if (unstractSubscriptionPlanStore?.useUnstractSubscriptionPlanStore) {
    planType = unstractSubscriptionPlanStore?.useUnstractSubscriptionPlanStore(
      (state) => state?.unstractSubscriptionPlan?.planType
    );
  }

  const isLLMWPaidSchema = useMemo(() => {
    return (
      LLMW_V2_ID &&
      transformLlmWhispererJsonSchema &&
      PLAN_TYPES &&
      selectedSourceId === LLMW_V2_ID &&
      planType === PLAN_TYPES?.PAID
    );
  }, [
    LLMW_V2_ID,
    transformLlmWhispererJsonSchema,
    PLAN_TYPES,
    selectedSourceId,
    planType,
  ]);

  useEffect(() => {
    if (!isLLMWPaidSchema || !transformLlmWhispererFormData) return;

    const modifiedFormData = transformLlmWhispererFormData(formData);

    if (JSON.stringify(modifiedFormData) !== JSON.stringify(formData)) {
      setFormData(modifiedFormData);
    }
  }, [isLLMWPaidSchema, formData]);

  useEffect(() => {
    if (!selectedSourceId) {
      setSpec({});
      setOAuthProvider("");
      return;
    }

    let url;
    if (sourceType === Object.keys(sourceTypes)[0]) {
      url = getUrl(`connector_schema/?id=${selectedSourceId}`);
    } else {
      url = getUrl(`adapter_schema/?id=${selectedSourceId}`);
    }

    const requestOptions = {
      method: "GET",
      url,
    };

    setIsLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        setFormData(metadata || {});

        if (isLLMWPaidSchema) {
          setSpec(transformLlmWhispererJsonSchema(data?.json_schema || {}));
        } else {
          setSpec(data?.json_schema || {});
        }

        if (data?.oauth) {
          setOAuthProvider(data?.python_social_auth_backend);
        } else {
          setOAuthProvider("");
        }
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
        setOpen(false);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [selectedSourceId]);

  useEffect(() => {
    if (editItemId?.length && metadata && Object.keys(metadata)?.length) {
      setFormData(metadata);
    }
  }, [metadata]);

  if (selectedSourceId.includes("pcs|")) {
    return (
      <Typography.Text>
        Edit is not supported for this connector
      </Typography.Text>
    );
  }

  if (!spec || !Object.keys(spec)?.length) {
    return <EmptyState text="Failed to load the settings form" />;
  }

  return (
    <ConfigureDs
      spec={spec}
      formData={formData}
      setFormData={setFormData}
      setOpen={setOpen}
      oAuthProvider={oAuthProvider}
      selectedSourceId={selectedSourceId}
      isLoading={isLoading}
      addNewItem={addNewItem}
      type={type}
      editItemId={editItemId}
      sourceType={sourceType}
      metadata={metadata}
      selectedSourceName={selectedSourceName}
    />
  );
}

AddSource.propTypes = {
  selectedSourceId: PropTypes.string.isRequired,
  selectedSourceName: PropTypes.string,
  setOpen: PropTypes.func,
  type: PropTypes.string,
  sourceType: PropTypes.oneOf([
    Object.keys(sourceTypes)[0],
    Object.keys(sourceTypes)[1],
  ]),
  addNewItem: PropTypes.func,
  editItemId: PropTypes.string,
  metadata: PropTypes.object,
};

export { AddSource };
