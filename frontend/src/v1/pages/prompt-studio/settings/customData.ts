import type { JsonValue, ToolPrompt } from "@v1/services/promptStudioTool";
import { z } from "zod";

/*
 * Custom Data as key-value rows over the project's `custom_data` object.
 * Values may nest (prompts read `{{custom_data.user.name}}`): a typed value
 * that starts with `{` or `[` is JSON, anything else is text. A loaded string
 * stays text until it is edited; a value loaded as a number, boolean or null
 * shows as JSON and keeps its type while it parses.
 */

/** `loaded` is a loaded string's text, kept so an unchanged value saves as it came. */
export type CustomDataRow = {
  key: string;
  value: string;
  json: boolean;
  loaded?: string;
};

type JsonObject = { readonly [key: string]: JsonValue };

const isObject = (v: JsonValue | null | undefined): v is JsonObject =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/** The saved object as rows; null, or a value that is not an object, has none. */
export function customDataRows(data: JsonValue | null): CustomDataRow[] {
  if (!isObject(data)) {
    return [];
  }
  return Object.entries(data).map(([key, value]) =>
    typeof value === "string"
      ? { key, value, json: false, loaded: value }
      : { key, value: JSON.stringify(value), json: true },
  );
}

const STRUCTURED = /^\s*[[{]/;

type Parsed = { ok: true; value: JsonValue } | { ok: false };

function parseJson(text: string): Parsed {
  try {
    return { ok: true, value: JSON.parse(text) as JsonValue };
  } catch {
    return { ok: false };
  }
}

/**
 * A row's value: an unchanged loaded string is text; otherwise JSON when it
 * starts an object or array (or was loaded as JSON and still parses), else text.
 */
function rowValue(row: CustomDataRow): Parsed {
  if (row.loaded !== undefined && row.value === row.loaded) {
    return { ok: true, value: row.value };
  }
  if (STRUCTURED.test(row.value)) {
    return parseJson(row.value);
  }
  if (row.json) {
    const parsed = parseJson(row.value);
    return parsed.ok ? parsed : { ok: true, value: row.value };
  }
  return { ok: true, value: row.value };
}

const isBlank = (row: CustomDataRow) =>
  row.key.trim() === "" && row.value.trim() === "";

const rowSchema = z.object({
  key: z.string(),
  value: z.string(),
  json: z.boolean(),
  loaded: z.string().optional(),
});

/** The section's form: rows in, `custom_data` to save (null for none) out. */
export const customDataFormSchema = z
  .object({ rows: z.array(rowSchema) })
  .superRefine(({ rows }, ctx) => {
    const seen = new Set<string>();
    rows.forEach((row, index) => {
      if (isBlank(row)) {
        return;
      }
      const key = row.key.trim();
      if (key === "") {
        ctx.addIssue({
          code: "custom",
          path: ["rows", index, "key"],
          message: "Enter a key",
        });
      } else if (seen.has(key)) {
        ctx.addIssue({
          code: "custom",
          path: ["rows", index, "key"],
          message: "This key is already used",
        });
      }
      seen.add(key);
      if (!rowValue(row).ok) {
        ctx.addIssue({
          code: "custom",
          path: ["rows", index, "value"],
          message: "Enter valid JSON, or text that does not start with { or [",
        });
      }
    });
  })
  .transform(({ rows }) => {
    const data = previewData(rows);
    return { custom_data: Object.keys(data).length === 0 ? null : data };
  });

export type CustomDataValues = z.input<typeof customDataFormSchema>;
export type CustomDataOutput = z.output<typeof customDataFormSchema>;

/** The rows as data, skipping blank keys and values that do not parse (for the live variable check). */
export function previewData(rows: readonly CustomDataRow[]): JsonObject {
  const entries = rows.flatMap((row) => {
    const parsed = rowValue(row);
    const key = row.key.trim();
    return key && parsed.ok ? [[key, parsed.value] as const] : [];
  });
  return Object.fromEntries(entries);
}

const VARIABLE = /\{\{custom_data\.([a-zA-Z0-9_.]+)\}\}/g;
const NOTES = "NOTES";

/** Every `{{custom_data.path}}` in active prompts (notes and inactive prompts skipped), each once. */
export function referencedVariables(
  prompts: readonly Pick<ToolPrompt, "prompt" | "active" | "prompt_type">[],
): string[] {
  const paths = prompts
    .filter((p) => p.active !== false && p.prompt_type !== NOTES)
    .flatMap((p) => [...(p.prompt ?? "").matchAll(VARIABLE)].map((m) => m[1]))
    .filter((path): path is string => path !== undefined);
  return [...new Set(paths)];
}

/** True when the dotted path resolves to a value in `data`. */
export function isDefined(data: JsonValue | null, path: string): boolean {
  let current: JsonValue | undefined = data;
  for (const part of path.split(".")) {
    if (!isObject(current) || !Object.hasOwn(current, part)) {
      return false;
    }
    current = current[part];
  }
  return current !== undefined;
}
