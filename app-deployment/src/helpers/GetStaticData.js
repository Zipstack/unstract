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

const listOfCusTools = [
  {
    id: 1,
    project_name: "Software Invoice Structured Info Tool",
    description: "",
  },
];

const promptType = {
  prompt: "PROMPT",
  note: "NOTE",
};

const billedLineItems = [
  {
    product_service_name: "Jira Software Monthly Standard",
    billing_period: {
      period_start: 11 - 18 - 2023,
      period_end: 12 - 18 - 2023,
    },
    list_price: 293.4,
    discount: 0,
    item_cost: 293.4,
    tax: 0,
    amount: 293.4,
  },
  {
    product_service_name: "Confluence Monthly Standard",
    billing_period: {
      period_start: 11 - 18 - 2023,
      period_end: 12 - 18 - 2023,
    },
    list_price: 223.85,
    discount: 0,
    item_cost: 223.85,
    tax: 0,
    amount: 223.85,
  },
  {
    product_service_name: "draw.io Diagrams & Whiteboards Cloud Standard",
    billing_period: {
      period_start: 11 - 18 - 2023,
      period_end: 12 - 18 - 2023,
    },
    list_price: 37.0,
    discount: 0,
    item_cost: 37.0,
    tax: 0,
    amount: 37.0,
  },
];

const listOfPromptsAndNotes = [
  {
    id: 1,
    type: promptType.prompt,
    output_type: "string",
    title: "Issuer name",
    prompt: "What is the name of the company which has issued this invoice?",
    response: "Atlassian Pty Ltd",
  },
  {
    id: 2,
    type: promptType.prompt,
    output_type: "string",
    title: "Billed to name",
    prompt:
      "Who is the primary contact to whom this invoice has been issued to or addresses to?",
    response: "Naren",
  },
  {
    id: 3,
    type: promptType.prompt,
    output_type: "string",
    title: "Billed to email",
    prompt:
      "What is the email address of the person to whom this invoice has been issued?",
    response: "naren@zipstack.com",
  },
  {
    id: 4,
    type: promptType.prompt,
    output_type: "string",
    title: "Currency",
    prompt:
      "What is the billing currency in internaional 3-letter code for this invoice?",
    response: "USD",
  },
  {
    id: 5,
    type: promptType.note,
    output_type: "string",
    title: "A note on extracting line items",
    note: "We need a single JSON object with multiple items in there. You can see that the prompt is a little more involved as a result. We have to let the LLM know what kind of a structure we actually need in detail, else this won't work.",
  },
  {
    id: 6,
    type: promptType.prompt,
    output_type: "string",
    title: "Billed line items",
    prompt:
      "In a single JSON list, create one object for each line item in this invoice with the keys given in the following description:\n'product_service_name': this is the name of the product or service mentioned in the line item.\n'billing_period': this has two keys 'period_start' and 'period_end', which denote the two dates for the start and the end of the billing period.\n'list_price': the list price of the line item\n'discount': the discount for the line item\n'item_cost': cost of the line item\n'tax': tax for this line item\n'amount': final cost of the line item",
    response: billedLineItems,
  },
  {
    id: 7,
    type: promptType.prompt,
    output_type: "float",
    title: "Total Amount",
    prompt: "What is the total amount mentioned in this invoice?",
    response: 554.25,
  },
  {
    id: 8,
    type: promptType.prompt,
    output_type: "float",
    title: "Total Tax",
    prompt: "What is the total tax amount mentioned in this invoice?",
    response: 0.0,
  },
  {
    id: 9,
    type: promptType.prompt,
    output_type: "float",
    title: "Amount Due",
    prompt: "What is the amount mentioned as due in this invoice?",
    response: 0.0,
  },
];

const combinedOutput = {
  issuer_name: "Atlassian Pty Ltd",
  billed_to_name: "Naren",
  billed_to_email: "naren@zipstack.com",
  currency: "USD",
  billed_line_items: billedLineItems,
  total_amount: 554.25,
  total_tax: 0.0,
  amount_due: 0.0,
};

const sourceTypes = {
  connectors: ["input", "output"],
  adapters: ["llm", "vector_db", "embedding"],
};

export {
  THEME,
  calculateDivHeight,
  publicRoutes,
  getBaseUrl,
  getOrgNameFromPathname,
  replaceFirstRoute,
  formatBytes,
  O_AUTH_PROVIDERS,
  CONNECTOR_TYPE_MAP,
  workflowStatus,
  setInitialWorkflowInstance,
  wfExecutionTypes,
  toolIdeOutput,
  listOfAppDeployments,
  getReadableDateAndTime,
  listOfCusTools,
  promptType,
  listOfPromptsAndNotes,
  combinedOutput,
  sourceTypes,
};
