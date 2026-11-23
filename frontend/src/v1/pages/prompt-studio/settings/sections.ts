import type { SlotId } from "@v1/lib/plugins";
import {
  Braces,
  Database,
  FileText,
  Highlighter,
  type LucideIcon,
  ScrollText,
  Sparkles,
  Type,
} from "lucide-react";

/*
 * The Settings tab's sections in design order (frame D09). Three are cloud
 * extensions: a plugin fills their slot, and in OSS they are absent, from
 * the page and from the section list.
 */

export type SettingsSlotId = Extract<
  SlotId,
  `prompt-studio.settings.${string}`
>;

export type SettingsSection = Readonly<{
  /** Anchor of the section (or, for Postamble, of its field). */
  id: string;
  label: string;
  /** The list's glyph (frame D09). */
  icon: LucideIcon;
  slot?: SettingsSlotId;
}>;

export const SETTINGS_SECTIONS: readonly SettingsSection[] = [
  { id: "llm-profiles", label: "LLM Profiles", icon: Braces },
  {
    id: "summarized-extraction",
    label: "Summarized Extraction",
    icon: Sparkles,
    slot: "prompt-studio.settings.summarized-extraction",
  },
  {
    id: "llm-challenge",
    label: "LLM Challenge",
    icon: ScrollText,
    slot: "prompt-studio.settings.llm-challenge",
  },
  { id: "custom-data", label: "Custom Data", icon: Database },
  { id: "grammar", label: "Grammar", icon: Type },
  // One section with two fields (D15); the list keeps both labels (D09).
  { id: "preamble", label: "Preamble", icon: FileText },
  { id: "postamble", label: "Postamble", icon: FileText },
  {
    id: "highlighting",
    label: "Highlighting",
    icon: Highlighter,
    slot: "prompt-studio.settings.highlighting",
  },
];

/** The sections this build shows: OSS ones always, cloud ones when a plugin fills their slot. */
export function visibleSections(
  isFilled: (slot: SettingsSlotId) => boolean,
): readonly SettingsSection[] {
  return SETTINGS_SECTIONS.filter((s) => !s.slot || isFilled(s.slot));
}

/** The DOM id for a section anchor, namespaced so two tabs never clash. */
export const anchorId = (id: string): string => `ps-settings-${id}`;
