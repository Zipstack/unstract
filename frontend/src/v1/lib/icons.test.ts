import { expect, it } from "vitest";
import {
  ACTION_ICONS,
  CATEGORY_ICONS,
  PLATFORM_MENU_ICONS,
  RAIL_ICONS,
  SHELL_ICONS,
  STATUS_ICONS,
} from "./icons";

const MAPS = {
  RAIL_ICONS,
  SHELL_ICONS,
  PLATFORM_MENU_ICONS,
  ACTION_ICONS,
  STATUS_ICONS,
  CATEGORY_ICONS,
};

it("gives each of the fifteen rail destinations its designed glyph", () => {
  const glyphs = Object.fromEntries(
    Object.entries(RAIL_ICONS).map(([destination, icon]) => [
      destination,
      icon.displayName,
    ]),
  );
  expect(glyphs).toEqual({
    "prompt-studio": "ScanText",
    "agentic-studio": "Bot",
    workflows: "Workflow",
    "api-deployments": "Braces",
    "etl-pipelines": "CalendarClock",
    "task-pipelines": "Zap",
    dashboard: "LayoutDashboard",
    logs: "ScrollText",
    "human-review": "FileCheckCorner",
    llms: "BrainCircuit",
    "vector-dbs": "Database",
    embedding: "Boxes",
    "text-extractor": "FileType",
    connectors: "Plug",
    platform: "SlidersHorizontal",
  });
});

it("maps every role to a Lucide icon component", () => {
  for (const [mapName, map] of Object.entries(MAPS)) {
    for (const [role, icon] of Object.entries(map)) {
      expect(
        typeof icon.displayName,
        `${mapName}.${role} has no displayName`,
      ).toBe("string");
      expect(icon.$$typeof, `${mapName}.${role} is not a component`).toBe(
        Symbol.for("react.forward_ref"),
      );
    }
  }
});

it("gives the status set distinct glyphs", () => {
  const names = Object.values(STATUS_ICONS).map((icon) => icon.displayName);
  expect(new Set(names).size).toBe(names.length);
});
