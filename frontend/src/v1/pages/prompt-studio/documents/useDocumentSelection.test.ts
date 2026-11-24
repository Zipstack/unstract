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

/** A PATCH endpoint the test answers by hand, one save at a time. */
function serveSaves() {
  const saves: { output: string; answer: (status: number) => void }[] = [];
  mockApi(
    http.patch(TOOL, async ({ request }) => {
      const { output } = (await request.json()) as { output: string };
      const status = await new Promise<number>((resolve) =>
        saves.push({ output, answer: resolve }),
      );
      return HttpResponse.json({}, { status });
    }),
  );
  return saves;
}

it("keeps a newer choice when an earlier save fails", async () => {
  const saves = serveSaves();
  const { result } = renderHookV1(() => useDocumentSelection(TOOL_ID, "a"));
  act(() => result.current.select("b"));
  await waitFor(() => expect(saves).toHaveLength(1));
  act(() => result.current.select("c"));
  await act(async () => saves[0]?.answer(500));
  expect(result.current.selectedId).toBe("c");
  await waitFor(() => expect(saves).toHaveLength(2));
  await act(async () => saves[1]?.answer(200));
  expect(result.current.selectedId).toBe("c");
});

it("goes back to the saved document, not an unsaved choice, when saves fail", async () => {
  const saves = serveSaves();
  const { result } = renderHookV1(() => useDocumentSelection(TOOL_ID, "a"));
  act(() => result.current.select("b"));
  await waitFor(() => expect(saves).toHaveLength(1));
  act(() => result.current.select("c"));
  await act(async () => saves[0]?.answer(500));
  await waitFor(() => expect(saves).toHaveLength(2));
  await act(async () => saves[1]?.answer(500));
  await waitFor(() => expect(result.current.selectedId).toBe("a"));
});

it("saves one choice at a time, so the server ends on the last one", async () => {
  const saves = serveSaves();
  const { result } = renderHookV1(() => useDocumentSelection(TOOL_ID, "a"));
  act(() => result.current.select("b"));
  await waitFor(() => expect(saves).toHaveLength(1));
  act(() => result.current.select("c"));
  act(() => result.current.select("d"));
  await delay(10);
  // Nothing else is sent while the first save is open.
  expect(saves).toHaveLength(1);
  await act(async () => saves[0]?.answer(200));
  await waitFor(() => expect(saves).toHaveLength(2));
  await act(async () => saves[1]?.answer(200));
  // The superseded "c" is never sent.
  expect(saves.map((save) => save.output)).toEqual(["b", "d"]);
  expect(result.current.selectedId).toBe("d");
});

it("never goes back to a removed document when saving the next one fails", async () => {
  const saves = serveSaves();
  const { result } = renderHookV1(() => useDocumentSelection(TOOL_ID, "a"));
  act(() => result.current.removed("a", ["c"]));
  await waitFor(() => expect(saves).toHaveLength(1));
  await act(async () => saves[0]?.answer(500));
  await delay(10);
  expect(result.current.selectedId).toBe("c");
});

it("clears the saved document when the last one is removed", async () => {
  const saves = serveSaves();
  const { result } = renderHookV1(() => useDocumentSelection(TOOL_ID, "a"));
  act(() => result.current.removed("a", []));
  expect(result.current.selectedId).toBeNull();
  await waitFor(() => expect(saves.map((save) => save.output)).toEqual([""]));
});

it("judges a removal against the current choice, not an earlier render's", async () => {
  serveSaves();
  const { result } = renderHookV1(() => useDocumentSelection(TOOL_ID, "a"));
  const early = result.current.removed;
  act(() => result.current.select("b"));
  act(() => early("a", ["c"]));
  expect(result.current.selectedId).toBe("b");
});

it("treats an unset saved document as none, and takes one that arrives later", () => {
  const { result, rerender } = renderHookV1(
    ({ saved }: { saved: string | null }) =>
      useDocumentSelection(TOOL_ID, saved),
    { initialProps: { saved: "" } },
  );
  expect(result.current.selectedId).toBeNull();
  rerender({ saved: "a" });
  expect(result.current.selectedId).toBe("a");
});

it("keeps the user's choice when the saved document changes afterwards", async () => {
  serveSaves();
  const { result, rerender } = renderHookV1(
    ({ saved }: { saved: string | null }) =>
      useDocumentSelection(TOOL_ID, saved),
    { initialProps: { saved: "a" as string | null } },
  );
  act(() => result.current.select("b"));
  rerender({ saved: "c" });
  expect(result.current.selectedId).toBe("b");
});

it("starts again from the new tool's saved document", async () => {
  serveSaves();
  const { result, rerender } = renderHookV1(
    ({ tool, saved }: { tool: string; saved: string }) =>
      useDocumentSelection(tool, saved),
    { initialProps: { tool: TOOL_ID, saved: "a" } },
  );
  act(() => result.current.select("b"));
  rerender({ tool: "other-tool", saved: "x" });
  expect(result.current.selectedId).toBe("x");
});
