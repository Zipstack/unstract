import { describe, expect, it } from "vitest";
import {
  highlightsByPage,
  normaliseAgentic,
  normaliseLine,
  normaliseLines,
  normaliseWords,
} from "./highlights";

// US Letter. LLMWhisperer renders page images at 300 dpi: 2550 × 3300.
const LETTER = { width: 612, height: 792 };
const pageSizes = [LETTER, LETTER, { width: 792, height: 612 }];

describe("Prompt Studio: LLMWhisperer line_metadata", () => {
  // Shaped like a prompt's highlight_data: one entry per line it cites, with
  // line_confidence as the 5th element and [0, 0, 0, 0] padding.
  const payload = [
    [0, 412, 34, 3300, 0.98],
    [0, 0, 0, 0],
    [1, 980, 30, 3300, 0.71],
    [2, 120, 20, 2550],
  ];

  it("maps each line to a full-width band ending at its baseline", () => {
    const [first] = normaliseLines(payload);
    expect(first).toMatchObject({
      id: "line-0",
      page: 0,
      x: 0,
      w: 1,
      variant: "line",
      tone: "default",
      confidence: 0.98,
    });
    expect(first?.y).toBeCloseTo((412 - 34) / 3300);
    expect(first?.h).toBeCloseTo(34 / 3300);
  });

  it("drops padding, keeps ids tied to the entry's position", () => {
    expect(normaliseLines(payload).map((h) => h.id)).toEqual([
      "line-0",
      "line-2",
      "line-3",
    ]);
  });

  it("marks lines below 0.9 confidence as low, and a line without one as default", () => {
    const [, low, none] = normaliseLines(payload);
    expect(low?.tone).toBe("low-confidence");
    expect(none?.tone).toBe("default");
    expect(none?.confidence).toBeUndefined();
    expect(normaliseLines(payload, { lowConfidenceBelow: 0.5 })[1]?.tone).toBe(
      "default",
    );
  });
});

describe("HITL: word boxes from confidence_metadata", () => {
  const line = [0, 412, 34, 3300, 0.81];
  const words = [
    { text: "Invoice", confidence: 0.62, offset: 1275, width: 255 },
    { text: "No.", confidence: 0.88, offset: 1550, width: 90 },
  ];

  it("places words on their line, with x from the PDF page's aspect ratio", () => {
    const [invoice] = normaliseWords(line, words, { pageSizes });
    // 3300 × 612/792 = 2550 units across the page.
    expect(invoice?.x).toBeCloseTo(1275 / 2550);
    expect(invoice?.w).toBeCloseTo(255 / 2550);
    expect(invoice?.y).toBeCloseTo((412 - 34) / 3300);
    expect(invoice).toMatchObject({
      variant: "box",
      tone: "low-confidence",
      confidence: 0.62,
    });
  });

  it("does not divide x by the page height, as v0 did", () => {
    const [invoice] = normaliseWords(line, words, { pageSizes });
    expect(invoice?.x).not.toBeCloseTo(1275 / 3300);
  });

  it("reads the legacy shape with the word appended to the line", () => {
    const legacy = [0, 412, 34, 3300, words[0]];
    expect(normaliseLine(legacy, "hitl-0", { pageSizes })).toMatchObject({
      variant: "box",
      x: expect.closeTo(0.5),
    });
  });

  it("skips words when the page width cannot be known", () => {
    expect(normaliseWords(line, words)).toEqual([]);
  });
});

describe("Agentic table: [page, y, height, 792, {offset, width, page_width}]", () => {
  // EXPECTED_COORDS in workers/plugins/agentic_table/tests/test_highlight_data.py
  const meta = { offset: 0, width: 612, page_width: 612 };
  const payload = [
    [
      0,
      Math.trunc((100 / 3168) * 792),
      Math.trunc((20 / 3168) * 792),
      792,
      meta,
    ],
    [
      1,
      Math.trunc((200 / 3168) * 792),
      Math.trunc((20 / 3168) * 792),
      792,
      meta,
    ],
  ];

  it("uses the sent page width and reads a full-width word as a line", () => {
    const [first, second] = normaliseLines(payload);
    expect(first).toMatchObject({ page: 0, x: 0, w: 1, variant: "line" });
    expect(first?.y).toBeCloseTo((25 - 5) / 792);
    expect(second?.page).toBe(1);
  });

  it("uses page_width over the aspect ratio when both are known", () => {
    const narrow = [
      0,
      100,
      20,
      792,
      { offset: 306, width: 153, page_width: 612 },
    ];
    expect(
      normaliseLine(narrow, "t", { pageSizes: [{ width: 1000, height: 792 }] }),
    ).toMatchObject({ x: 0.5, w: 0.25 });
  });
});

describe("Agentic Prompt Studio: [page, left%, top%, width%, height%, hasMetadata]", () => {
  // transformHighlightData output in the cloud agentic-prompt-studio plugin.
  const payload = [
    [0, 0, 12.5, 100, 2.5, false],
    [1, 10, 20, 30, 4, true],
    [0, 0, 0, 0, 0, false],
  ];

  it("turns percentages into fractions", () => {
    const [line, word] = normaliseAgentic(payload);
    expect(line).toMatchObject({
      page: 0,
      x: 0,
      y: 0.125,
      w: 1,
      h: expect.closeTo(0.025),
    });
    expect(line?.variant).toBe("line");
    expect(word).toMatchObject({
      page: 1,
      x: 0.1,
      y: 0.2,
      w: expect.closeTo(0.3),
      h: expect.closeTo(0.04),
    });
    expect(word?.variant).toBe("box");
  });

  it("drops empty boxes", () => {
    expect(normaliseAgentic(payload)).toHaveLength(2);
  });
});

describe("robustness", () => {
  it("clamps boxes that run off the page", () => {
    const [box] = normaliseAgentic([[0, 90, -5, 20, 10]]);
    expect(box).toMatchObject({
      x: 0.9,
      y: 0,
      w: expect.closeTo(0.1),
      h: 0.05,
    });
  });

  it("ignores junk entries", () => {
    expect(
      normaliseLines([null, "x", [0, 1, 2], [-1, 10, 10, 100], [0, 10, 10, 0]]),
    ).toEqual([]);
  });
});

it("groups highlights by page in their original order", () => {
  const highlights = normaliseAgentic([
    [1, 0, 0, 10, 10],
    [0, 0, 0, 10, 10],
    [1, 0, 50, 10, 10],
  ]);
  const byPage = highlightsByPage(highlights);
  expect(byPage.get(1)?.map((h) => h.id)).toEqual(["agentic-0", "agentic-2"]);
  expect(byPage.get(0)?.map((h) => h.id)).toEqual(["agentic-1"]);
});
