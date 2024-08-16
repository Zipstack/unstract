import moment from "moment";
import momentTz from "moment-timezone";
import { v4 as uuidv4 } from "uuid";

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
    source_icon: "/icons/connector-icons/S3.png",
    destination_name: "Unstract Cloud Storage",
    destination_icon: "/icons/connector-icons/Pandora%20Storage.png",
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
    source_icon: "/icons/connector-icons/S3.png",
    destination_name: "Unstract Cloud Storage",
    destination_icon: "/icons/connector-icons/Pandora%20Storage.png",
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

const getSequenceNumber = (listOfPrompts) => {
  let maxSequenceNumber = 0;
  listOfPrompts.forEach((item) => {
    if (item?.sequence_number > maxSequenceNumber) {
      maxSequenceNumber = item?.sequence_number;
    }
  });

  return maxSequenceNumber + 1;
};

const deploymentTypes = {
  etl: "etl",
  task: "task",
  api: "api",
  app: "app",
};

const deploymentApiTypes = {
  api: "api",
  pipeline: "pipeline",
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

const getDateTimeString = (timestamp) => {
  // Convert to milliseconds
  const timestampInMilliseconds = timestamp * 1000;

  // Create a new Date object
  const date = new Date(timestampInMilliseconds);

  // Extract date components
  const year = date.getFullYear();
  const month = (date.getMonth() + 1).toString().padStart(2, "0"); // Months are zero-indexed
  const day = date.getDate().toString().padStart(2, "0");
  const hours = date.getHours().toString().padStart(2, "0");
  const minutes = date.getMinutes().toString().padStart(2, "0");
  const seconds = date.getSeconds().toString().padStart(2, "0");
  const milliseconds = date.getMilliseconds().toString().padStart(3, "0");

  // Formatted date-time string
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}.${milliseconds}`;
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

const displayPromptResult = (output, isFormat = false) => {
  /*
    output: The data to be displayed or parsed
    isFormat: A flag indicating whether the output should be formatted
  */

  let i = 0;
  let parsedData = output;

  while (i < 3) {
    i++;
    try {
      parsedData = JSON.parse(parsedData);
    } catch {
      // Break the loop if parsing fails
      break;
    }
  }

  if (!isFormat) {
    // If formatting is not requested, return the parsed data directly
    return parsedData;
  }

  // Check if the parsed data is an array or object and formatting is requested
  if (Array.isArray(parsedData) || typeof parsedData === "object") {
    // If formatting is requested, return the JSON string with indentation
    return JSON.stringify(parsedData, null, 4);
  }

  return String(parsedData);
};

const onboardCompleted = (adaptersList) => {
  if (!Array.isArray(adaptersList)) {
    return false;
  }
  const MANDATORY_ADAPTERS = ["llm", "vector_db", "embedding", "x2text"];
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

const getMenuItem = (label, key, icon, children, type, isDisabled) => {
  return {
    key,
    icon,
    children,
    label,
    type,
    isDisabled,
  };
};

const docIndexStatus = {
  yet_to_start: "YET_TO_START",
  indexing: "INDEXING",
  done: "DONE",
};

const isNonNegativeNumber = (value) => {
  return typeof value === "number" && !isNaN(value) && value >= 0;
};

// Default token usage object with all counts initialized to 0
const defaultTokenUsage = {
  embedding_tokens: 0,
  prompt_tokens: 0,
  completion_tokens: 0,
  total_tokens: 0,
};

// Generate a UUID
const generateUUID = () => {
  const uuid = uuidv4();
  return uuid;
};
const convertTimestampToHHMMSS = (timestamp) => {
  // Convert the timestamp to milliseconds
  const date = new Date(timestamp * 1000);

  // Extract hours, minutes, and seconds
  const [hours, minutes, seconds] = [
    date.getUTCHours(),
    date.getUTCMinutes(),
    date.getUTCSeconds(),
  ].map((unit) => unit.toString().padStart(2, "0"));
  // Return the formatted time string
  return `${hours}:${minutes}:${seconds}`;
};

const isSubPage = (type, path) => {
  const regex = new RegExp(`^/[^/]+/${type}/.+`);
  return regex.test(path);
};

function getLLMModelNamesForProfiles(profiles, adapters) {
  // Create a mapping of adapter_ids to model names
  const adapterMap = adapters.reduce((map, adapter) => {
    map[adapter?.adapter_name] = adapter?.model;
    return map;
  }, {});

  // Map through profiles and find corresponding model names using the adapterMap
  return profiles.map((profile) => {
    return {
      profile_name: profile?.profile_name,
      llm_model: adapterMap[profile?.llm],
      profile_id: profile?.profile_id,
    };
  });
}

function getFormattedTotalCost(result, profile) {
  // Find the relevant object in the result array
  const value =
    result.find((r) => r?.profileManager === profile?.profile_id)?.totalCost ??
    0;

  // Format the value to 5 decimal places or return "0" if the value is zero
  return value === 0 ? 0 : value.toFixed(5);
}

const pollForCompletion = (
  startTime,
  requestOptions,
  maxWaitTime,
  pollingInterval,
  makeApiRequest
) => {
  const elapsedTime = Date.now() - startTime;
  if (elapsedTime >= maxWaitTime) {
    return Promise.reject(
      new Error(
        "Unable to fetch results since there's an ongoing extraction, please try again later"
      )
    );
  }

  const recursivePoll = () => {
    return makeApiRequest(requestOptions)
      .then((response) => {
        if (response?.data?.status === "pending") {
          return new Promise((resolve) =>
            setTimeout(resolve, pollingInterval)
          ).then(recursivePoll);
        } else {
          return response;
        }
      })
      .catch((err) => {
        throw err;
      });
  };

  return recursivePoll();
};

function getDocIdFromKey(key) {
  // Split the key by '__'
  const parts = key.split("__");

  // Return the docId part, which is the second element in the array
  if (parts.length === 3) {
    return parts[1];
  } else {
    return null;
  }
}

const displayURL = (text) => {
  return getBaseUrl() + "/" + text;
};

export {
  CONNECTOR_TYPE_MAP,
  O_AUTH_PROVIDERS,
  THEME,
  calculateDivHeight,
  deploymentTypes,
  deploymentApiTypes,
  deploymentsStaticContent,
  endpointType,
  formatBytes,
  formattedDateTime,
  getBaseUrl,
  getOrgNameFromPathname,
  getReadableDateAndTime,
  getTimeForLogs,
  getDateTimeString,
  listOfAppDeployments,
  onboardCompleted,
  promptStudioUpdateStatus,
  promptType,
  publicRoutes,
  replaceFirstRoute,
  setInitialWorkflowInstance,
  sourceTypes,
  getSequenceNumber,
  toolIdeOutput,
  wfExecutionTypes,
  workflowStatus,
  base64toBlob,
  removeFileExtension,
  isJson,
  displayPromptResult,
  getBackendErrorDetail,
  titleCase,
  getMenuItem,
  docIndexStatus,
  isNonNegativeNumber,
  defaultTokenUsage,
  generateUUID,
  convertTimestampToHHMMSS,
  isSubPage,
  getLLMModelNamesForProfiles,
  getFormattedTotalCost,
  pollForCompletion,
  getDocIdFromKey,
  displayURL,
};
