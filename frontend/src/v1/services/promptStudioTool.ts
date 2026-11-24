import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";
import { currentOrganizationId } from "./context";
import { http, orgPath, type RequestOptions } from "./http";

/*
 * A Prompt Studio project (the backend calls it a custom tool): the settings
 * fields the Settings tab reads and writes. `PATCH prompt-studio/{id}/` takes
 * a partial body, so saving one section never sends another's fields.
 * Responses are parsed here, so a contract change fails at this boundary.
 */

/** Any JSON value; custom data may nest objects and arrays. */
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | readonly JsonValue[]
  | { readonly [key: string]: JsonValue };

const jsonValueSchema: z.ZodType<JsonValue> = z.lazy(() =>
  z.union([
    z.string(),
    z.number(),
    z.boolean(),
    z.null(),
    z.array(jsonValueSchema),
    z.record(z.string(), jsonValueSchema),
  ]),
);

/** A prompt or note of the project; the Settings tab reads only its text. */
export const toolPromptSchema = z.looseObject({
  prompt: z.string().nullable().optional(),
  /** Absent on older rows; only `false` means inactive. */
  active: z.boolean().optional(),
  prompt_type: z.string().nullable().optional(),
});
export type ToolPrompt = z.infer<typeof toolPromptSchema>;

/**
 * The fields of `GET prompt-studio/{id}/` the Settings tab uses. Other
 * fields pass through untouched, so a cached project stays whole for other
 * readers of the same key.
 */
export const toolSettingsSchema = z.looseObject({
  tool_id: z.string(),
  tool_name: z.string(),
  preamble: z.string().nullable(),
  postamble: z.string().nullable(),
  /** Grammar: word -> equivalent words and phrases. The backend spells it so. */
  prompt_grammer: z.record(z.string(), z.array(z.string())).nullable(),
  custom_data: jsonValueSchema.nullable(),
  /** Absent for older projects that have no default profile yet. */
  default_profile: z.string().nullable().optional(),
  prompts: z.array(toolPromptSchema),
});
export type ToolSettings = z.infer<typeof toolSettingsSchema>;

/** What one section saves; every key is optional. The backend refuses a null preamble or postamble. */
export type ToolSettingsPatch = Partial<
  Pick<ToolSettings, "prompt_grammer" | "custom_data"> & {
    preamble: string;
    postamble: string;
  }
>;

const toolPath = (toolId: string) =>
  `/prompt-studio/${encodeURIComponent(toolId)}/` as const;

/** `GET /api/v1/unstract/<org>/prompt-studio/<id>/`. */
export async function getToolSettings(
  toolId: string,
  { signal, org }: RequestOptions = {},
): Promise<ToolSettings> {
  const { data } = await http.get<unknown>(orgPath(toolPath(toolId), org), {
    signal,
  });
  return toolSettingsSchema.parse(data);
}

/** `PATCH /api/v1/unstract/<org>/prompt-studio/<id>/` with only the given fields. */
export async function updateToolSettings(
  toolId: string,
  patch: ToolSettingsPatch,
  { signal, org }: RequestOptions = {},
): Promise<ToolSettings> {
  const { data } = await http.patch<unknown>(
    orgPath(toolPath(toolId), org),
    patch,
    { signal },
  );
  return toolSettingsSchema.parse(data);
}

/** Query keys: `[org, "prompt-studio-tools", "detail", toolId]`. */
export const promptStudioToolKeys = {
  all: () => [currentOrganizationId(), "prompt-studio-tools"] as const,
  detail: (toolId: string) =>
    [...promptStudioToolKeys.all(), "detail", toolId] as const,
};

export const promptStudioToolQueries = {
  detail: (toolId: string) =>
    queryOptions({
      queryKey: promptStudioToolKeys.detail(toolId),
      queryFn: ({ queryKey: [org], signal }) =>
        getToolSettings(toolId, { signal, org }),
    }),
};
