import { isCancelledError } from "@tanstack/react-query";
import { type AxiosError, AxiosHeaders, isAxiosError, isCancel } from "axios";

// The error contract: every failed request becomes one ApiError (see README.md).

export const REQUEST_ID_HEADER = "X-Request-ID";

export const API_ERROR_KINDS = [
  "validation",
  "subscription",
  "unauthenticated",
  "forbidden",
  "not_found",
  "client",
  "server",
  "network",
  "unknown",
] as const;
export type ApiErrorKind = (typeof API_ERROR_KINDS)[number];

const DEFAULT_MESSAGES: Readonly<Record<ApiErrorKind, string>> = {
  validation: "Some fields need attention.",
  subscription: "Your plan does not allow this. Contact your admin.",
  unauthenticated: "Your session has expired. Sign in again.",
  forbidden: "You don't have permission to do this.",
  not_found: "Not found.",
  client: "The request could not be completed.",
  server: "Something went wrong on our side. Try again.",
  network: "Can't reach the server. Check your connection and try again.",
  unknown: "Something went wrong.",
};
const CANCELLED_MESSAGE = "The request was cancelled.";

export type FieldErrors = Readonly<Record<string, readonly string[]>>;

export type ApiErrorInit = Readonly<{
  kind: ApiErrorKind;
  message: string;
  status?: number;
  fieldErrors?: FieldErrors;
  formErrors?: readonly string[];
  requestId?: string;
  cause?: unknown;
}>;

/** One failed request: what kind it is, a message for people, and its request id. */
export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | undefined;
  /** Validation errors by field (`attr`), as the backend names it. */
  readonly fieldErrors: FieldErrors;
  /** Validation errors not tied to a field. */
  readonly formErrors: readonly string[];
  readonly requestId: string | undefined;

  constructor(init: ApiErrorInit) {
    super(init.message, { cause: init.cause });
    this.name = "ApiError";
    this.kind = init.kind;
    this.status = init.status;
    this.fieldErrors = init.fieldErrors ?? {};
    this.formErrors = init.formErrors ?? [];
    this.requestId = init.requestId;
  }
}

type ErrorItem = Readonly<{ code?: string; detail: string; attr?: string }>;

// drf-standardized-errors, or a `{message}` / `{error}` / `{detail}` body.
type ErrorBody = Readonly<{
  type?: string;
  items: readonly ErrorItem[];
  text?: string;
}>;

const NON_FIELD = "non_field_errors";
const GATEWAY_STATUSES = new Set([502, 503, 504]);
const SUBSCRIPTION_TYPES = new Set([
  "subscription_error",
  "subscription_inactive",
]);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const text = (value: unknown): string | undefined =>
  typeof value === "string" && value !== "" ? value : undefined;

function toItems(value: unknown): ErrorItem[] {
  const detail = isRecord(value) ? text(value.detail) : undefined;
  if (!isRecord(value) || detail === undefined) {
    return [];
  }
  return [{ code: text(value.code), detail, attr: text(value.attr) }];
}

function parseBody(data: unknown): ErrorBody {
  if (!isRecord(data)) {
    return { items: [] };
  }
  const { errors } = data;
  return {
    type: text(data.type),
    items: Array.isArray(errors) ? errors.flatMap(toItems) : [],
    text:
      text(data.error) ??
      text(data.detail) ??
      text(data.message) ??
      text(errors),
  };
}

const isSubscription = (status: number, body: ErrorBody): boolean =>
  status === 402 ||
  SUBSCRIPTION_TYPES.has(body.type ?? "") ||
  body.items.some((item) => SUBSCRIPTION_TYPES.has(item.code ?? ""));

function kindOf(status: number, body: ErrorBody): ApiErrorKind {
  // Only the auth middleware's untyped 401 is session expiry; a typed one is a provider's or connector's.
  if (status === 401 && body.type === undefined) {
    return "unauthenticated";
  }
  if (isSubscription(status, body)) {
    return "subscription";
  }
  if (body.type === "validation_error") {
    return "validation";
  }
  if (status === 403) {
    return "forbidden";
  }
  if (status === 404) {
    return "not_found";
  }
  return status >= 500 ? "server" : "client";
}

const isFieldItem = (item: ErrorItem): item is ErrorItem & { attr: string } =>
  item.attr !== undefined && item.attr !== NON_FIELD;

const describe = (item: ErrorItem): string =>
  isFieldItem(item) ? `${item.attr}: ${item.detail}` : item.detail;

function splitItems(items: readonly ErrorItem[]) {
  const fieldErrors: Record<string, string[]> = {};
  const formErrors: string[] = [];
  for (const item of items) {
    if (isFieldItem(item)) {
      fieldErrors[item.attr] = [...(fieldErrors[item.attr] ?? []), item.detail];
    } else {
      formErrors.push(item.detail);
    }
  }
  return { fieldErrors, formErrors };
}

function messageOf(kind: ApiErrorKind, body: ErrorBody): string {
  if (kind === "validation") {
    // Every error, so a toast drops none of them.
    const all = body.items.map(describe).join(" ");
    return all || body.text || DEFAULT_MESSAGES.validation;
  }
  return body.text ?? body.items[0]?.detail ?? DEFAULT_MESSAGES[kind];
}

// axios hands both request and response headers over as AxiosHeaders.
const requestIdIn = (headers: unknown): string | undefined =>
  headers instanceof AxiosHeaders
    ? text(headers.get(REQUEST_ID_HEADER))
    : undefined;

/* The id the backend echoed, else the one the client sent. */
const requestIdOf = (error: AxiosError): string | undefined =>
  requestIdIn(error.response?.headers) ?? requestIdIn(error.config?.headers);

function fromAxios(error: AxiosError): ApiError {
  const requestId = requestIdOf(error);
  if (!error.response) {
    const message = DEFAULT_MESSAGES.network;
    return new ApiError({ kind: "network", message, requestId, cause: error });
  }
  const { status, data } = error.response;
  const body = parseBody(data);
  const kind = kindOf(status, body);
  return new ApiError({
    kind,
    status,
    message: messageOf(kind, body),
    ...(kind === "validation" ? splitItems(body.items) : {}),
    requestId,
    cause: error,
  });
}

/** True for a request the caller cancelled; it is not a failure. */
export function isCancelled(error: unknown): boolean {
  return isCancel(error) || isCancelledError(error);
}

/** Maps any failure to an ApiError; a cancel is `unknown`. Check isCancelled() first. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  // Before axios: its cancel has no response, so it would read as `network`.
  if (isCancelled(error)) {
    const message = CANCELLED_MESSAGE;
    return new ApiError({ kind: "unknown", message, cause: error });
  }
  if (isAxiosError(error)) {
    return fromAxios(error);
  }
  const message = DEFAULT_MESSAGES.unknown;
  return new ApiError({ kind: "unknown", message, cause: error });
}

/** Failures worth retrying for a read: no response, or a gateway error. */
export function isTransient(error: unknown): boolean {
  if (isCancelled(error)) {
    return false;
  }
  const { kind, status } = toApiError(error);
  return kind === "network" || GATEWAY_STATUSES.has(status ?? 0);
}

export type FormErrors<F extends string> = Readonly<{
  /** One message per field the form shows. */
  fields: Partial<Record<F, string>>;
  /** Everything else, for one message above the form; never dropped. */
  form: string | undefined;
}>;

/** Splits a failure into the form's field errors and one form-level message for the rest. */
export function mapFieldErrors<F extends string>(
  error: unknown,
  fields: readonly F[],
): FormErrors<F> {
  // No error yet (an idle mutation), or a cancel: nothing to show.
  if (error == null || isCancelled(error)) {
    return { fields: {}, form: undefined };
  }
  const apiError = toApiError(error);
  const shown = new Set<string>(fields);
  const isShown = (attr: string): attr is F => shown.has(attr);
  const mapped: Partial<Record<F, string>> = {};
  const rest = [...apiError.formErrors];
  for (const [attr, details] of Object.entries(apiError.fieldErrors)) {
    if (isShown(attr)) {
      mapped[attr] = details.join(" ");
    } else {
      rest.push(`${attr}: ${details.join(" ")}`);
    }
  }
  if (rest.length > 0) {
    return { fields: mapped, form: rest.join(" ") };
  }
  const anyField = Object.keys(mapped).length > 0;
  return { fields: mapped, form: anyField ? undefined : apiError.message };
}
