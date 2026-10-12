import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCallback, useMemo, useState } from "react";
import { describe, expect, it } from "vitest";

import { Input } from "@/components/ui/shims/antd-inputs";

/**
 * CustomSynonyms stores LIVE <Input> elements as its table cells. The original
 * code built them inside a `useEffect` keyed on [synonyms] and parked the
 * result in state, so each keystroke rendered once with the STALE element —
 * still carrying the previous value — before the effect swapped it in. Against
 * a strictly controlled input that resets the field mid-typing and drops the
 * leading characters: typing "bill" into the Word column produced "il" on dev.
 *
 * The component itself pulls in axios and three zustand stores, so this
 * exercises the row-building PATTERN in isolation: rows derived during render,
 * exactly as the fixed component does it.
 */
function Harness() {
  const [items, setItems] = useState([{ word: "" }]);

  const handleChange = useCallback((index, value) => {
    setItems((prev) =>
      prev.map((it, i) => (i === index ? { ...it, word: value } : it)),
    );
  }, []);

  const rows = useMemo(
    () =>
      items.map((item, index) => (
        <Input
          key={index}
          value={item.word}
          onChange={(e) => handleChange(index, e.target.value)}
        />
      )),
    [items, handleChange],
  );

  return <div>{rows}</div>;
}

describe("CustomSynonyms row building", () => {
  it("keeps every typed character when rows are derived during render", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(screen.getByRole("textbox"), "bill");
    expect(screen.getByRole("textbox")).toHaveValue("bill");
  });

  it("keeps characters typed into the middle of an existing value", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const box = screen.getByRole("textbox");
    await user.type(box, "bll");
    await user.type(box, "i", { initialSelectionStart: 1 });
    expect(box).toHaveValue("bill");
  });
});
