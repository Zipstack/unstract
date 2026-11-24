import { formatBytes } from "./documentFacts";

/*
 * What the drop zone takes before anything is sent. The backend validates
 * again (extension, sniffed MIME type, size), so this only saves a round trip
 * and says why in the user's terms.
 */

export type UploadType = Readonly<{
  /** How the caption names it: "PDF". */
  label: string;
  /** Lower-case extensions without the dot. */
  extensions: readonly string[];
}>;

export type UploadPolicy = Readonly<{
  types: readonly UploadType[];
  maxBytes: number;
}>;

/**
 * The OSS backend's limits (`file_management/constants.py`): PDF only, up
 * to 200 MB. A distribution that accepts more types passes its own policy.
 */
export const OSS_UPLOAD_POLICY: UploadPolicy = {
  types: [{ label: "PDF", extensions: ["pdf"] }],
  maxBytes: 200 * 1024 * 1024,
};

export type RefusedUpload = Readonly<{ name: string; reason: string }>;
export type UploadPlan = Readonly<{
  accepted: readonly File[];
  refused: readonly RefusedUpload[];
}>;

const typeList = (policy: UploadPolicy) =>
  policy.types.map((type) => type.label).join(", ");

/** "Supports PDF · up to 200 MB". */
export function policyCaption(policy: UploadPolicy): string {
  return `Supports ${typeList(policy)} · up to ${formatBytes(policy.maxBytes)}`;
}

/** The file picker's `accept`: ".pdf,.docx". */
export function acceptAttribute(policy: UploadPolicy): string {
  return policy.types
    .flatMap((type) => type.extensions)
    .map((extension) => `.${extension}`)
    .join(",");
}

function extensionOf(name: string): string | null {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : null;
}

/**
 * The name without its extension: the backend stores extracts by it. Lower-cased
 * here, so names that differ only in case also count as one (stricter than the
 * backend).
 */
function stemOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return (dot > 0 ? name.slice(0, dot) : name).toLowerCase();
}

function refusal(
  file: File,
  policy: UploadPolicy,
  taken: ReadonlySet<string>,
): string | null {
  const extension = extensionOf(file.name);
  const allowed = policy.types.some(
    (type) => extension !== null && type.extensions.includes(extension),
  );
  if (!allowed) {
    return `${file.name} is not a supported type. Upload ${typeList(policy)}.`;
  }
  if (file.size > policy.maxBytes) {
    return `${file.name} is larger than ${formatBytes(policy.maxBytes)}.`;
  }
  if (taken.has(stemOf(file.name))) {
    return `A document named ${file.name.slice(0, file.name.lastIndexOf("."))} already exists.`;
  }
  return null;
}

/**
 * Splits dropped files into those to upload and those refused, with why.
 * Two names that differ only in extension are one name: their extracted
 * text would share a file on the server.
 */
export function planUploads(
  files: readonly File[],
  policy: UploadPolicy,
  existingNames: readonly string[],
): UploadPlan {
  const taken = new Set(existingNames.map(stemOf));
  const accepted: File[] = [];
  const refused: RefusedUpload[] = [];
  for (const file of files) {
    const reason = refusal(file, policy, taken);
    if (reason === null) {
      accepted.push(file);
      taken.add(stemOf(file.name));
    } else {
      refused.push({ name: file.name, reason });
    }
  }
  return { accepted, refused };
}

/**
 * Why uploads are refused for a tool's LLM profiles, as v0 words it: the
 * backend reads the default profile when a file arrives. Null when allowed.
 */
export function profileGate(
  profiles: readonly Readonly<{ is_default: boolean }>[],
): string | null {
  if (profiles.length === 0) {
    return "Add an LLM profile before uploading a document";
  }
  return profiles.some((profile) => profile.is_default)
    ? null
    : "Set the default LLM profile before uploading a document";
}
