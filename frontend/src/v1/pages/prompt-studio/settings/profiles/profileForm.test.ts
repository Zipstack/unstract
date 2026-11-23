import {
  makeProfile,
  SETTINGS_TOOL_ID,
} from "@v1/test/fixtures/promptStudioSettings";
import { describe, expect, it } from "vitest";
import {
  approxTokens,
  NEW_PROFILE,
  profileFormSchema,
  profileValues,
  toProfileBody,
} from "./profileForm";

const valid = {
  ...NEW_PROFILE,
  profile_name: "prod",
  llm: "a",
  embedding_model: "b",
  vector_store: "c",
  x2text: "d",
};

const errorsOf = (input: unknown, taken: string[] = []) => {
  const result = profileFormSchema(taken).safeParse(input);
  return result.success
    ? {}
    : Object.fromEntries(
        result.error.issues.map((i) => [i.path.join("."), i.message]),
      );
};

describe("profileFormSchema", () => {
  it("accepts a complete profile and outputs numbers", () => {
    const out = profileFormSchema([]).parse({
      ...valid,
      chunk_size: "1024",
      chunk_overlap: "128",
      similarity_top_k: "5",
    });
    expect(out).toMatchObject({
      chunk_size: 1024,
      chunk_overlap: 128,
      similarity_top_k: 5,
    });
  });

  it("requires a name and every adapter", () => {
    expect(errorsOf({ ...NEW_PROFILE, profile_name: "   " })).toMatchObject({
      profile_name: "Enter a name",
      llm: "Select an LLM",
      embedding_model: "Select an embedding model",
      vector_store: "Select a vector database",
      x2text: "Select a text extractor",
    });
  });

  it("rejects a name another profile of the project uses", () => {
    expect(errorsOf({ ...valid, profile_name: " prod " }, ["prod"])).toEqual({
      profile_name: "A profile with this name already exists",
    });
    // The backend's unique constraint is case-sensitive, so this one is too.
    expect(errorsOf({ ...valid, profile_name: "Prod" }, ["prod"])).toEqual({});
  });

  it("takes whole numbers of 0 or more for the chunk fields", () => {
    expect(
      errorsOf({ ...valid, chunk_size: "-1", chunk_overlap: "1.5" }),
    ).toEqual({
      chunk_size: "Enter a whole number, 0 or more",
      chunk_overlap: "Enter a whole number, 0 or more",
    });
  });

  it("keeps the chunk overlap below the chunk size", () => {
    expect(
      errorsOf({ ...valid, chunk_size: "512", chunk_overlap: "512" }),
    ).toEqual({
      chunk_overlap: "Chunk overlap must be smaller than the chunk size",
    });
    expect(
      errorsOf({ ...valid, chunk_size: "512", chunk_overlap: "511" }),
    ).toEqual({});
  });

  it("ignores the overlap when chunk size is 0 (no chunking)", () => {
    expect(
      errorsOf({ ...valid, chunk_size: "0", chunk_overlap: "200" }),
    ).toEqual({});
  });

  it("turns a blank matching count and section into null", () => {
    const out = profileFormSchema([]).parse({
      ...valid,
      similarity_top_k: "",
      section: "",
    });
    expect(out.similarity_top_k).toBeNull();
    expect(out.section).toBeNull();
    expect(errorsOf({ ...valid, similarity_top_k: "0" })).toEqual({
      similarity_top_k: "Enter a whole number, 1 or more",
    });
  });
});

describe("profileValues and toProfileBody", () => {
  it("edits a profile by its adapter ids, not names", () => {
    const values = profileValues(makeProfile({ chunk_size: null }));
    expect(values).toMatchObject({
      llm: makeProfile().llm_id,
      x2text: makeProfile().x2text_id,
      chunk_size: "0",
      similarity_top_k: "3",
    });
  });

  it("reads a blank strategy as simple and a null section as blank", () => {
    const values = profileValues(
      makeProfile({ retrieval_strategy: "", section: null }),
    );
    expect(values.retrieval_strategy).toBe("simple");
    expect(values.section).toBe("");
  });

  it("builds the request body with the project id", () => {
    const out = profileFormSchema([]).parse(valid);
    expect(toProfileBody(out, SETTINGS_TOOL_ID)).toEqual({
      ...out,
      prompt_studio_tool: SETTINGS_TOOL_ID,
    });
  });
});

it("estimates tokens as v0 does: four characters a token, in thousands", () => {
  expect(approxTokens(8192)).toBe("2.0k");
  expect(approxTokens(0)).toBe("0.0k");
});
