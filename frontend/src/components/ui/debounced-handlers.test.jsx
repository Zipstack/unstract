import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Search handlers built on `lodash/debounce` must survive a re-render.
 *
 * Each of these components declared its handler inline in the component body —
 * `const onSearchDebounce = debounce(fn, 600)`. That is a NEW debounced
 * instance every render, so a render between two keystrokes orphans the armed
 * timer instead of resetting it: both eventually fire and the "debounce"
 * degrades to one call per keystroke. SonarCloud flags it as javascript:S9114.
 *
 * THE RE-RENDER IS THE WHOLE TEST. These inputs are uncontrolled, so typing on
 * its own does not re-render the component and even the inline version looks
 * correctly debounced — which is why a naive test passes against the bug. In
 * the app the re-render arrives from somewhere else (the parent committing the
 * previous result, a context update, a sibling's state), so these tests supply
 * it explicitly with `rerender`. Drop that and they stop discriminating.
 *
 * Guard the other half of the fix too: memoising with the wrong deps silences
 * Sonar while pinning the closure to its mount-time props, so one case checks
 * the handler still sees the CURRENT data.
 */

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

// Imported after the mock is registered.
const { TopBar } = await import("@/components/widgets/top-bar/TopBar");
const { ListOfSources } = await import(
  "@/components/input-output/list-of-sources/ListOfSources"
);

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

/**
 * Type `text` one character at a time, re-rendering between keystrokes and
 * never pausing long enough to close the debounce window.
 */
function typeThrough(input, text, rerender, makeTree) {
  let sofar = "";
  for (const ch of text) {
    sofar += ch;
    act(() => {
      fireEvent.change(input, { target: { value: sofar } });
    });
    // A FRESH element every time: re-rendering the same element object is a
    // referential no-op that React skips, which silently defeats this test.
    rerender(makeTree());
  }
}

describe("debounced search handlers survive a re-render", () => {
  it("TopBar filters once for a burst of keystrokes, not once per key", () => {
    const setFilteredUserList = vi.fn();
    const searchData = [
      { email: "ada@example.com" },
      { email: "grace@example.com" },
    ];
    const makeTree = () => (
      <MemoryRouter>
        <TopBar
          title="Users"
          enableSearch
          searchData={searchData}
          setFilteredUserList={setFilteredUserList}
        />
      </MemoryRouter>
    );

    const { rerender } = render(makeTree());
    typeThrough(
      screen.getByTestId("top-bar-search"),
      "ada",
      rerender,
      makeTree,
    );

    // Still inside the 600ms window.
    expect(setFilteredUserList).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(600);
    });

    // ONE call for three keystrokes. With the handler rebuilt each render this
    // was three, each firing with its own orphaned timer.
    expect(setFilteredUserList).toHaveBeenCalledTimes(1);
    expect(setFilteredUserList).toHaveBeenCalledWith([
      { email: "ada@example.com" },
    ]);
  });

  it("TopBar filters against the CURRENT searchData, not the mount-time list", () => {
    const setFilteredUserList = vi.fn();
    const treeWith = (searchData) => (
      <MemoryRouter>
        <TopBar
          title="Users"
          enableSearch
          searchData={searchData}
          setFilteredUserList={setFilteredUserList}
        />
      </MemoryRouter>
    );

    const { rerender } = render(treeWith([{ email: "ada@example.com" }]));

    // The users load after mount — the case a `useMemo(..., [])` would break.
    const loaded = [
      { email: "ada@example.com" },
      { email: "adam@example.com" },
    ];
    rerender(treeWith(loaded));

    typeThrough(screen.getByTestId("top-bar-search"), "ada", rerender, () =>
      treeWith(loaded),
    );
    act(() => {
      vi.advanceTimersByTime(600);
    });

    expect(setFilteredUserList).toHaveBeenCalledTimes(1);
    expect(setFilteredUserList).toHaveBeenCalledWith(loaded);
  });

  it("ListOfSources holds one 300ms window open across a burst of keystrokes", () => {
    const sourcesList = [{ id: "1", name: "Google Drive" }];
    const makeTree = () => (
      <ListOfSources
        setSelectedSourceId={vi.fn()}
        sourcesList={sourcesList}
        type="input"
        isConnector={false}
        connectorMode={null}
      />
    );
    const { rerender } = render(makeTree());
    const input = screen.getByPlaceholderText(/search/i);

    // Four keystrokes 100ms apart: 400ms of wall clock but no 300ms GAP, so a
    // correctly debounced handler has not fired and the row is still listed.
    // Rebuilt per render, the first keystroke's orphaned timer has already
    // elapsed and filtered "Google Drive" away.
    let sofar = "";
    for (const ch of "zzzz") {
      sofar += ch;
      act(() => {
        fireEvent.change(input, { target: { value: sofar } });
        vi.advanceTimersByTime(100);
      });
      rerender(makeTree());
    }
    expect(screen.getByText("Google Drive")).toBeInTheDocument();

    // Let the window actually elapse: "zzzz" matches nothing, so the row goes.
    // This is what proves the handler ran at all rather than never firing.
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(screen.queryByText("Google Drive")).not.toBeInTheDocument();
  });
});
