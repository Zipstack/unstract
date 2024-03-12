import moment from "moment";
import momentTz from "moment-timezone";

const THEME = {
  DARK: "dark",
  LIGHT: "light",
};

const calculateDivHeight = (offset) => {
  const windowHeight = window.innerHeight;
  const calculatedHeight = windowHeight - offset;
  return calculatedHeight;
};

const publicRoutes = ["/landing"];

/*
  This function will return the url without the path/routes
  For ex,
  If the url is http://localhost:3000/home,
  then it will return http://localhost:3000/
*/
const getBaseUrl = () => {
  const location = window.location.href;
  const url = new URL(location).origin;
  return url;
};

const getOrgNameFromPathname = (pathname) => {
  if (!pathname) {
    return null;
  }

  if (publicRoutes.includes(pathname)) {
    return null;
  }
  return pathname?.split("/")[1];
};

const replaceFirstRoute = (url, newRoute) => {
  // Regular expression to match the first route segment
  const regex = /^(\/?[^/]+)/;
  const match = url.match(regex);

  // If there is a match, replace the first route with the new route
  if (match) {
    const oldRoute = match[1];
    const replacedUrl = url.replace(oldRoute, newRoute);
    return "/" + replacedUrl;
  }

  // Return the home page with the new route
  return "/" + newRoute;
};

const formatBytes = (bytes, decimals = 1) => {
  if (!+bytes) return "0 B";

  const k = 1000;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"];

  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return sizes[i]
    ? `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`
    : `${bytes / Math.pow(k, i - 1)} ${sizes.at(-1)}`;
};

const O_AUTH_PROVIDERS = {
  GOOGLE: "google-oauth2",
};

const CONNECTOR_TYPE_MAP = {
  input: "Source",
  output: "Destination",
};

const workflowStatus = {
  yet_to_start: "YET TO START",
  in_progress: "IN PROGRESS",
  generated: "GENERATED",
};

const setInitialWorkflowInstance = (promptName, prompt) => {
  return {
    promptName,
    prompt,
    status: workflowStatus.yet_to_start,
    details: {},
  };
};

const wfExecutionTypes = ["START", "NEXT", "STOP", "CONTINUE", "RUN_WORKFLOW"];

const toolIdeOutput = [
  {
    company: "Apple Inc.",
    stockholders_equity: "USD 33,400",
  },
  {
    company: "Apple Inc.",
    stockholders_equity: "USD 33,400",
  },
  {
    company: "Apple Inc.",
    stockholders_equity: "USD 33,400",
  },
  {
    company: "Apple Inc.",
    stockholders_equity: "USD 33,400",
  },
  {
    company: "Apple Inc.",
    stockholders_equity: "USD",
  },
];

// TODO: Remove this once the BE API for it is ready.
const listOfAppDeployments = [
  {
    id: "08a47c30-e2ec-48b3-be45-5b1f06639031",
    pipeline_name: "Financial document Q&A",
    app_id: null,
    active: true,
    scheduled: false,
    pipeline_type: "ETL",
    run_count: 6,
    last_run_time: "2023-07-28T08:09:31.045244Z",
    last_run_status: "SUCCESS",
    workflow: "73b57446-fafc-445e-96fe-f5d072044dcd",
    cron: null,
    workflow_name: "demo",
    source_name: "MinioFS/S3",
    source_icon:
      "https://storage.googleapis.com/pandora-static/connector-icons/S3.png",
    destination_name: "Unstract Cloud Storage",
    destination_icon:
      "https://storage.googleapis.com/pandora-static/connector-icons/Pandora%20Storage.png",
    goto: "https://finance-qa.pandora-demo.zipstack.io/",
  },
  {
    id: "08a47c30-e2ec-48b3-be45-5b1f06639032",
    pipeline_name: "Legal document Q&A",
    app_id: null,
    active: true,
    scheduled: false,
    pipeline_type: "ETL",
    run_count: 6,
    last_run_time: "2023-07-28T08:09:31.045244Z",
    last_run_status: "SUCCESS",
    workflow: "73b57446-fafc-445e-96fe-f5d072044dcd",
    cron: null,
    workflow_name: "demo",
    source_name: "MinioFS/S3",
    source_icon:
      "https://storage.googleapis.com/pandora-static/connector-icons/S3.png",
    destination_name: "Unstract Cloud Storage",
    destination_icon:
      "https://storage.googleapis.com/pandora-static/connector-icons/Pandora%20Storage.png",
    goto: "https://legal-qa.pandora-demo.zipstack.io/",
  },
];

const getReadableDateAndTime = (timestamp) => {
  const currentDate = new Date(timestamp);

  // Options for formatting the date and time
  const options = {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  };
  const formattedDate = currentDate.toLocaleDateString("en-US", options);
  const formattedTime = currentDate.toLocaleTimeString("en-US", options);
  return formattedDate + ", " + formattedTime;
};

const promptType = {
  prompt: "PROMPT",
  notes: "NOTES",
};

const sourceTypes = {
  connectors: ["input", "output"],
  adapters: ["llm", "vector_db", "embedding"],
};

const deploymentTypes = {
  etl: "etl",
  task: "task",
  api: "api",
  app: "app",
};

const deploymentsStaticContent = {
  etl: {
    title: "Unstructured to Structured ETL Pipelines",
    modalTitle: "Deploy ETL Pipeline",
    addBtn: "ETL Pipeline",
    isLogsRequired: true,
  },
  task: {
    title: "Unstructured to Structured Task Pipelines",
    modalTitle: "Deploy Task Pipeline",
    addBtn: "Task Pipeline",
    isLogsRequired: true,
  },
  api: {
    title: "API Deployments",
    addBtn: "API Deployment",
    isLogsRequired: false,
  },
  app: {
    title: "App Deployments",
    addBtn: "App Deployment",
    isLogsRequired: false,
  },
};

const endpointType = {
  input: "SOURCE",
  output: "DESTINATION",
};

const promptStudioUpdateStatus = {
  isUpdating: "IS_UPDATING",
  done: "DONE",
  validationError: "VALIDATION_ERROR",
};

const getTimeForLogs = () => {
  const timestamp = Date.now();
  const date = new Date(timestamp);

  const hours = ("0" + date.getHours()).slice(-2);
  const minutes = ("0" + date.getMinutes()).slice(-2);
  const seconds = ("0" + date.getSeconds()).slice(-2);

  const formattedDate = `${hours}:${minutes}:${seconds}`;
  return formattedDate;
};

const handleException = (err, errMessage, setBackendErrors = undefined) => {
  if (err?.response?.data?.type === "validation_error") {
    // Handle validation errors
    if (setBackendErrors) {
      setBackendErrors(err?.response?.data);
    } else {
      return {
        type: "error",
        content: errMessage || "Something went wrong",
      };
    }
  }

  if (["client_error", "server_error"].includes(err?.response?.data?.type)) {
    // Handle client_error, server_error
    return {
      type: "error",
      content:
        err?.response?.data?.errors[0].detail ||
        errMessage ||
        "Something went wrong",
    };
  }

  return {
    type: "error",
    content: errMessage || err?.message,
  };
};

const base64toBlob = (data) => {
  const bytes = atob(data);
  let length = bytes.length;
  const out = new Uint8Array(length);

  while (length--) {
    out[length] = bytes.charCodeAt(length);
  }

  return new Blob([out], { type: "application/pdf" });
};

const removeFileExtension = (fileName) => {
  if (!fileName) {
    return "";
  }
  const fileNameSplit = fileName.split(".");
  const fileNameSplitLength = fileNameSplit.length;
  const modFileName = fileNameSplit.slice(0, fileNameSplitLength - 1);
  return modFileName.join(".");
};

const isJson = (text) => {
  try {
    if (typeof text === "object") {
      return true;
    }

    if (typeof text === "string") {
      const json = JSON.parse(text);
      return typeof json === "object";
    }
    return false;
  } catch (err) {
    return false;
  }
};

const displayPromptResult = (output) => {
  try {
    if (isJson(output)) {
      return JSON.stringify(JSON.parse(output), null, 4);
    }

    const outputParsed = JSON.parse(output);
    return outputParsed;
  } catch (err) {
    return output;
  }
};

const onboardCompleted = (adaptersList) => {
  if (!Array.isArray(adaptersList)) {
    return false;
  }
  const MANDATORY_ADAPTERS = ["llm", "vector_db", "embedding"];
  adaptersList = adaptersList.map((element) => element.toLowerCase());
  return MANDATORY_ADAPTERS.every((value) => adaptersList.includes(value));
};

// Input: ISOdateTime format
// Output: Mar 10, 2023 7:33 PM IST
const formattedDateTime = (ISOdateTime) => {
  if (ISOdateTime) {
    const validIsoDate = moment.utc(ISOdateTime).toISOString();
    // eslint-disable-next-line new-cap
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return momentTz.tz(validIsoDate, zone).format("lll z");
  } else {
    return "";
  }
};

const getBackendErrorDetail = (attr, backendErrors) => {
  if (backendErrors) {
    const error = backendErrors?.errors.find((error) => error?.attr === attr);
    return error ? error?.detail : null;
  }
  return null;
};

const titleCase = (str) => {
  if (str === null || str.length === 0) {
    return "";
  }
  const words = str.toLowerCase().split(" ");
  for (let i = 0; i < words.length; i++) {
    words[i] = words[i][0].toUpperCase() + words[i].slice(1);
  }
  return words.join(" ");
};

export {
  CONNECTOR_TYPE_MAP,
  O_AUTH_PROVIDERS,
  THEME,
  calculateDivHeight,
  deploymentTypes,
  deploymentsStaticContent,
  endpointType,
  formatBytes,
  formattedDateTime,
  getBaseUrl,
  getOrgNameFromPathname,
  getReadableDateAndTime,
  getTimeForLogs,
  handleException,
  listOfAppDeployments,
  onboardCompleted,
  promptStudioUpdateStatus,
  promptType,
  publicRoutes,
  replaceFirstRoute,
  setInitialWorkflowInstance,
  sourceTypes,
  toolIdeOutput,
  wfExecutionTypes,
  workflowStatus,
  base64toBlob,
  removeFileExtension,
  isJson,
  displayPromptResult,
  getBackendErrorDetail,
  titleCase,
};
