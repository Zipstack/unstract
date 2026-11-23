import { act, waitFor } from "@testing-library/react";
import { setOrganizationId } from "@v1/services/context";
import {
  apiPath,
  DEFAULT_SESSION,
  HttpResponse,
  http,
  mockApi,
  renderHookV1,
} from "@v1/test";
import { TOOL_ID } from "@v1/test/fixtures/promptDocuments";
import { afterEach, beforeEach, expect, it } from "vitest";
import { useDocumentSelection } from "./useDocumentSelection";

const TOOL = apiPath(DEFAULT_SESSION, `/prompt-studio/${TOOL_ID}/`);

beforeEach(() => setOrganizationId(DEFAULT_SESSION.organization.id));
afterEach(() => setOrganizationId(null));

it("starts on the tool's saved document and saves a new choice", async () => {
  const saved: unknown[] = [];
  mockApi(
    http.patch(TOOL, async ({ request }) => {
      saved.push(await request.json());
      return HttpResponse.json({});
    }),
  );
  const { result } = renderHookV1(() => useDocumentSelection(TOOL_ID, "a"));
  expect(result.current.selectedId).toBe("a");
  act(() => result.current.select("b"));
  expect(result.current.selectedId).toBe("b");
  await waitFor(() => expect(saved).toEqual([{ output: "b" }]));
});

it("puts the previous document back when the save fails", async () => {
  mockApi(http.patch(TOOL, () => HttpResponse.json({}, { status: 500 })));
  const { result } = renderHookV1(() => useDocumentSelection(TOOL_ID, "a"));
  act(() => result.current.select("b"));
  await waitFor(() => expect(result.current.selectedId).toBe("a"));
});

it("moves to the first document left when the shown one is removed", () => {
  const { result } = renderHookV1(() => useDocumentSelection(TOOL_ID, "a"));
  act(() => result.current.removed("b", ["a", "c"]));
  expect(result.current.selectedId).toBe("a");
  act(() => result.current.removed("a", ["c"]));
  expect(result.current.selectedId).toBe("c");
  act(() => result.current.removed("c", []));
  expect(result.current.selectedId).toBeNull();
});
