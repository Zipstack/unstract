import { act, waitFor } from "@testing-library/react";
import { setOrganizationId } from "@v1/services/context";
import {
  apiPath,
  DEFAULT_SESSION,
  delay,
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

it("moves to the first document left, and saves it, when the shown one is removed", async () => {
  const saved: unknown[] = [];
  mockApi(
    http.patch(TOOL, async ({ request }) => {
      saved.push(await request.json());
      return HttpResponse.json({});
    }),
  );
  const { result } = renderHookV1(() => useDocumentSelection(TOOL_ID, "a"));
  act(() => result.current.removed("b", ["a", "c"]));
  expect(result.current.selectedId).toBe("a");
  act(() => result.current.removed("a", ["c"]));
  expect(result.current.selectedId).toBe("c");
  await waitFor(() => expect(saved).toEqual([{ output: "c" }]));
  act(() => result.current.removed("c", []));
  expect(result.current.selectedId).toBeNull();
});

it("keeps a newer choice when an earlier save fails", async () => {
  mockApi(
    http.patch(TOOL, async ({ request }) => {
      const { output } = (await request.json()) as { output: string };
      await delay(output === "b" ? 20 : 0);
      return HttpResponse.json({}, { status: output === "b" ? 500 : 200 });
    }),
  );
  const { result } = renderHookV1(() => useDocumentSelection(TOOL_ID, "a"));
  act(() => result.current.select("b"));
  act(() => result.current.select("c"));
  await delay(40);
  expect(result.current.selectedId).toBe("c");
});
